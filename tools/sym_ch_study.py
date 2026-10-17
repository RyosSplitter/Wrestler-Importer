"""Reproduce the read-only SYM CH.PAC study; never invokes the converter.

python -m tools.sym_ch_study path/to/ch.pac --out local/sym-study --previews
Optional --extract preserves exact directory slices plus their allocation gaps.
All outputs go to a NEW folder; source PACs are never modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import struct

from tools.hctp_weights import read_hctp_with_weights
from tools.pac_inspect import FormatError, inspect_pac
from tools.sym_research import Limits, geometry_preflight
from tools.sym_source import read_atlas, read_ch_directory, sha
from tools.yobj_read import compare_skeletons, read_yobj
from tools.yukes_bpe import decompress


def export_obj(model, directory, indices, palette):
    """Source axes, UVs and corner splits unchanged. OBJ cannot carry rigging."""
    from PIL import Image
    Image.fromarray(palette[indices]).save(directory/'atlas.png')
    (directory/'source.mtl').write_text('newmtl atlas\nKd 1 1 1\nmap_Kd atlas.png\n', encoding='utf-8')
    with (directory/'source.obj').open('x', encoding='utf-8') as f:
        f.write('# SYM source bind geometry, NOT a PSP conversion; rigging in model.json\nmtllib source.mtl\n')
        base = 1
        for mesh in model['meshes']:
            f.write(f"o mesh_{mesh['index']:02d}\n")
            for key, tag in (('position', 'v'), ('uv', 'vt'), ('normal', 'vn')):
                for vertex in mesh['vertices']:
                    f.write(tag+' '+' '.join(str(x) for x in vertex[key])+'\n')
            f.write('usemtl atlas\n')
            for j, material in enumerate(mesh['materials']):
                f.write(f"g mesh_{mesh['index']:02d}_material_{j:02d}\n")
                for tri in material['triangles']:
                    f.write('f '+' '.join(f'{base+i}/{base+i}/{base+i}' for i in tri)+'\n')
            base += len(mesh['vertices'])
    (directory/'model.json').write_text(json.dumps(model, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def source_render(model, indices, palette, ident, view='front-left', resolution=256):
    from PIL import ImageDraw
    from desktop.preview import render
    # Single-atlas candidate mapping, checked by caller. Do not use texture names
    # as body-region classifications: "rmomo" can name the entire Rock atlas.
    result = render(dict(model, texture_names=model['textures']),
        {model['textures'][0]: None}, view, resolution,
        gim_reader=lambda _: (indices, palette))
    draw = ImageDraw.Draw(result)
    draw.rectangle((0, 0, resolution, 30), fill=(72, 72, 72))
    draw.text((8, 8), f'SYM SOURCE {ident} | {view}', fill='white')
    return result


def compare_reference(model, reference):
    """Names/hierarchy only: deliberately does not infer an animation bone map."""
    active = {b for m in model['meshes'] for v in m['vertices']
              for b, w in v['original_source_influences'] if w > 1e-7}
    names = {b['name'] for b in reference['bones']}
    return dict(compare_skeletons(model, reference), source_bones=model['bone_count'],
        target_bones=reference['bone_count'], source_active_bones=len(active),
        source_active_unmatched_names=[model['bones'][b]['name'] for b in sorted(active)
                                       if model['bones'][b]['name'] not in names])


def inventory(report):
    """Small evidence index; full raw field/bone evidence remains in report.json."""
    result = {k: v for k, v in report.items() if k != 'entries'}
    result['entries'] = []
    for row in report['entries']:
        models = []
        for model in row['models']:
            item = {k: v for k, v in model.items()
                    if k not in ('bones', 'mesh_fields', 'weight_report')}
            if model.get('passed_existing_reader'):
                item['meshes'] = [dict(index=m['mesh'], source_vertices=m['source_vertex_count'],
                    groups=m['group_count'], materials=m['material_count'],
                    position_normal_packet_count=m['position_normal_packet_count'],
                    texture_slots=[x['texture_slot_candidate'] for x in m['materials']],
                    render_words=[x['shader_word_candidate'] for x in m['materials']])
                    for m in model['mesh_fields']]
            models.append(item)
        result['entries'].append(dict(id_hex=row['id_hex'], sections=row['sections'],
                                      atlases=row['atlases'], models=models))
    return result


def study(source, output, *, previews=False, extract=False, selected=('0000', '0001', '0118'), reference_psp=None):
    data = source.read_bytes()
    directory = read_ch_directory(data)
    # Fail before creating anything if archive directory is invalid or output exists.
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='ps2psp.sym-ch-study/1', source_name=source.name,
        directory=directory, source_modified=False, conversion_supported=False,
        contracts='Existing HCTP decoder probes; not independent animation validation',
        entries=[], errors=[], summary={})
    atlas_hist, sections_hist, bone_hist = Counter(), Counter(), Counter()
    reference = None
    if reference_psp is not None:
        from tools.psp_mesh_merge_trial import sections
        reference_data = reference_psp.read_bytes()
        candidates = [raw for sec, raw in sections(reference_data) if sec['id'] == 2 and raw.startswith(b'YOBJ')]
        if len(candidates) != 1:
            raise FormatError('Expected one main YOBJ in reference PSP PAC')
        reference = read_yobj(candidates[0], psp_geometry=True)
        report['reference_psp'] = dict(name=reference_psp.name, sha256=sha(reference_data),
            scope='Bone names/indices/parents only; no transform/animation equivalence asserted')
    expanded = 0
    tiles = []
    counts = Counter()
    for entry in directory['entries']:
        ident = entry['id_hex']
        raw = data[entry['offset']:entry['offset']+entry['stored_bytes']]
        if extract:
            destination = output/'extracted'
            destination.mkdir(exist_ok=True)
            (destination/(ident+'.pac')).write_bytes(raw)
            (destination/(ident+'.allocation-gap.bin')).write_bytes(
                data[entry['offset']+entry['stored_bytes']:entry['allocation_end']])
        pac = inspect_pac(raw)
        if len({s['id'] for s in pac['sections']}) != len(pac['sections']):
            raise FormatError('Duplicate inner PAC section IDs require investigation')
        row = dict(id_hex=ident, sections=[], models=[], atlases=[])
        decoded = {}
        sections_hist[tuple(s['id'] for s in pac['sections'])] += 1
        for section in pac['sections']:
            stored = raw[section['offset']:section['offset']+section['size']]
            blob = decompress(stored, max_output=16*1024*1024) if stored.startswith(b'BPE ') else stored
            expanded += len(blob)
            if expanded > 256*1024*1024:
                raise FormatError('Cumulative research expansion limit exceeded')
            decoded[section['id']] = blob
            row['sections'].append(dict(id=section['id'], offset=section['offset'],
                stored_bytes=len(stored), decoded_bytes=len(blob), stored_sha256=sha(stored),
                decoded_sha256=sha(blob), decoded_head_hex=blob[:16].hex()))
        atlas = None
        for sid, blob in decoded.items():
            if blob.startswith(b'TIM2'):
                try:
                    indices, palette, meta = read_atlas(blob)
                    meta['section_id'] = sid
                    row['atlases'].append(meta)
                    atlas_hist[(meta['width'], meta['height'], meta['bits_per_index'])] += 1
                    counts['atlases_decoded'] += 1
                    if sid == 1:
                        atlas = indices, palette
                except (ValueError, struct.error) as exc:
                    report['errors'].append(dict(id_hex=ident, section_id=sid, error=str(exc)))
        for sid, blob in decoded.items():
            if not blob.startswith(b'YOBJ'):
                continue
            counts['yobj_objects'] += 1
            record = dict(section_id=sid, sha256=sha(blob), bytes=len(blob))
            try:
                common = read_yobj(blob)
                fields = geometry_preflight(blob, common, Limits())
                record['common_header'] = {k: common[k] for k in
                    ('mesh_count', 'bone_count', 'texture_count', 'textures')}
                record['packet_count_probe'] = [dict(mesh=f['mesh'],
                    source_vertices=f['source_vertex_count'],
                    position_normal_packet_count=f['position_normal_packet_count']) for f in fields]
                model = read_hctp_with_weights(blob)
                active = Counter()
                for mesh in model['meshes']:
                    # Count source records once, not the UV/corner duplicates.
                    seen = set()
                    for vertex in mesh['vertices']:
                        index = vertex['source_vertex_index']
                        if index in seen:
                            continue
                        seen.add(index)
                        for bone, weight in vertex['original_source_influences']:
                            if weight > 1e-7:
                                active[model['bones'][bone]['name']] += 1
                record.update(passed_existing_reader=True,
                    **{k: model[k] for k in ('mesh_count', 'bone_count', 'texture_count',
                        'textures', 'source_vertex_count', 'vertex_count', 'triangle_count', 'bounds')},
                    bones=model['bones'], active_bone_source_records=dict(sorted(active.items())),
                    mesh_fields=fields, weight_report=model['source_weight_report'])
                if reference is not None:
                    record['psp_name_comparison'] = compare_reference(model, reference)
                counts['models_decoded'] += 1
                bone_hist[model['bone_count']] += 1
                if sid == 2:
                    counts['main_models_decoded'] += 1
                    counts['main_source_vertices'] += model['source_vertex_count']
                    counts['main_triangles'] += model['triangle_count']
                    if previews and atlas is not None and model['texture_count'] == 1:
                        indices, palette = atlas
                        tiles.append(source_render(model, indices, palette, ident))
                        if ident in selected:
                            folder = output/('source-'+ident)
                            folder.mkdir()
                            export_obj(model, folder, indices, palette)
                            for view in ('front-left', 'front', 'back', 'left', 'right'):
                                source_render(model, indices, palette, ident, view, 640).save(folder/(view+'.png'))
            except (ValueError, struct.error) as exc:
                record.update(passed_existing_reader=False, error=str(exc))
                report['errors'].append(dict(id_hex=ident, section_id=sid, error=str(exc)))
            row['models'].append(record)
        report['entries'].append(row)
    counts['expanded_section_bytes'] = expanded
    report['summary'] = dict(counts, atlas_configurations=[dict(width=w, height=h,
        bits_per_index=b, count=n) for (w, h, b), n in sorted(atlas_hist.items())],
        section_id_combinations=[dict(ids=list(ids), count=n) for ids, n in sorted(sections_hist.items())],
        decoded_bone_counts=[dict(bones=b, count=n) for b, n in sorted(bone_hist.items())])
    if tiles:
        from PIL import Image
        # Split into readable pages. Unsupported objects deliberately get no fake render.
        for page in range((len(tiles)+19)//20):
            sheet = Image.new('RGB', (5*256, 4*256), (48, 48, 48))
            for i, tile in enumerate(tiles[page*20:(page+1)*20]):
                sheet.paste(tile, ((i%5)*256, (i//5)*256))
            sheet.save(output/f'source-contact-{page+1:02d}.jpg', quality=90)
    if source.read_bytes() != data:
        raise RuntimeError('Source changed during read-only study')
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    (output/'inventory.json').write_text(json.dumps(inventory(report), indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--previews', action='store_true')
    parser.add_argument('--extract', action='store_true')
    parser.add_argument('--reference-psp', type=Path)
    args = parser.parse_args()
    result = study(args.source, args.out, previews=args.previews, extract=args.extract, reference_psp=args.reference_psp)
    print(json.dumps(dict(summary=result['summary'], errors=result['errors']), indent=2))


if __name__ == '__main__':
    main()

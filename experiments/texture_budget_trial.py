"""Isolated source-texture upgrades over a frozen PSP PAC, never an app default.

python -m experiments.texture_budget_trial SOURCE.pac BASELINE.pac NEW_FOLDER
    --texture NAME=128x64 --texture OTHER=128x32
    --experimental-pixel-limit 34176

The explicit allocation limit is an experiment parameter, not a certified game
heap limit. Oversize/invalid candidates are reported but never exported.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image, ImageDraw

from desktop.adapters import adapter
from desktop.accessories import decode_dependencies, source_models
from desktop.core import validate_pac
from desktop.preview import save_views
from desktop.skinning import exact_pose_checks
from desktop.texture_optimizer.analysis import measure, model_usage, occupied
from desktop.texture_optimizer.candidates import encode, read_gim
from tools.pac_inspect import inspect_pac, parse_textures
from tools.pac_repack import replace_sections, texture_table
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections, write_preview
from tools.yukes_bpe import compress, decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def allocation(data):
    """Sum actual padded pixel planes and fixed CLUTs across every GIM table."""
    tables = []
    for s, raw in sections(data):
        if len(raw) < 16 or raw[4:16] != bytes.fromhex('000100000000000010000000'):
            continue
        for t in parse_textures(raw):
            if t['extension'] != 'gim':
                raise ValueError('Unsupported texture allocation table')
            gim = raw[t['offset']:t['offset'] + t['size']]
            read_gim(gim)
            tables.append(dict(section=s['id'], name=t['name'], bytes=len(gim)-208))
    return dict(pixel_palette_bytes=sum(t['bytes'] for t in tables), textures=tables)


def run(source, baseline, output, selections, *, pixel_limit, target=148000, renders=True):
    source, baseline, output = map(Path, (source, baseline, output))
    if output.exists():
        raise FileExistsError(output)
    if not selections or pixel_limit <= 0 or target <= 0:
        raise ValueError('Explicit texture selections and positive budgets required')
    output.mkdir(parents=True)
    source_bytes, original = source.read_bytes(), baseline.read_bytes()
    native, old_images = validate_pac(original, gim_reader=read_gim)
    model, decoded = adapter('hctp').read(source)
    _, dependencies = source_models(source, model)
    decoded = decode_dependencies(source, decoded, dependencies)
    sources = {n: rgba for i, n, raw, rgba, details in decoded}
    before = {s['id']: (s, raw) for s, raw in sections(original)}
    table = before[9][1]
    names = [t['name'] for t in parse_textures(table)]
    if set(selections) - set(names) or any(n not in sources for n in selections):
        raise ValueError('Unknown selected texture')
    models = {i: audit_yobj(raw) for i, (s, raw) in before.items() if raw.startswith(b'YOBJ')}
    usage = model_usage(models, sources)
    images = dict(old_images)
    report = dict(experimental=True, inputs={str(source): sha(source_bytes), str(baseline): sha(original)},
                  target_pac_bytes=target, experimental_pixel_palette_limit=pixel_limit,
                  before_bytes=len(original), before_allocation=allocation(original), textures=[],
                  limitation='Explicit experimental allocation, not a validated SVR heap limit; PPSSPP testing required')
    (output/'textures').mkdir()
    for name, size in selections.items():
        p, c = read_gim(old_images[name])
        bits = 4 if len(c) == 16 else 8
        rgba = sources[name]
        mask = occupied(rgba, usage[name]['uv_mask'])
        candidate = encode(rgba, tuple(size), bits, len(c), mask)
        images[name] = candidate['raw']
        final_p, final_c = read_gim(images[name])
        report['textures'].append(dict(name=name,
            source_dimensions=list(rgba.shape[1::-1]),
            before=dict(width=p.shape[1], height=p.shape[0], bits=bits,
                        palette_entries=len(c), pixel_palette_bytes=len(old_images[name])-208,
                        metrics=measure(rgba, c[p], mask)), after=candidate['entry']))
        for label, image in (('source', rgba), ('before', c[p]), ('after', final_c[final_p])):
            Image.fromarray(image).save(output/'textures'/(name+'-'+label+'.png'))
    new_table = texture_table(names, [images[n] for n in names], gim_reader=read_gim)
    attempts = []
    for symbols in (200, 220):
        encoded = compress(new_table, max_distinct=symbols)
        if decompress(encoded) != new_table:
            raise ValueError('Texture compression changed decoded data')
        data = replace_sections(original, {9: encoded})
        attempts.append((data, dict(max_distinct=symbols, pac_bytes=len(data),
                                   stored_texture_table_bytes=len(encoded))))
    data, selected = min(attempts, key=lambda t: (len(t[0]), t[1]['stored_texture_table_bytes']))
    report.update(after_bytes=len(data), compression_attempts=[t[1] for t in attempts],
                  selected_compression=selected, after_allocation=allocation(data), sha256=sha(data))
    report['pac_budget_pass'] = len(data) <= target
    report['pixel_budget_pass'] = report['after_allocation']['pixel_palette_bytes'] <= pixel_limit
    if not report['pac_budget_pass'] or not report['pixel_budget_pass']:
        report['status'] = 'export-withheld'
        (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        raise ValueError('Experimental texture candidate exceeds a configured budget; no PAC exported')
    final_native, final_images = validate_pac(data, gim_reader=read_gim)
    final = {s['id']: (s, raw) for s, raw in sections(data)}
    if before.keys() != final.keys():
        raise ValueError('PAC section set changed')
    for i, (s, raw) in before.items():
        if i != 9 and (raw != final[i][1] or s['sha256'] != final[i][0]['sha256']):
            raise ValueError('Non-texture stored/decoded payload changed')
    untouched = sorted(set(names)-set(selections))
    if any(old_images[n] != final_images[n] for n in untouched):
        raise ValueError('Unselected GIM changed')
    report.update(status='native-and-analytical-checks-pass-gameplay-pending',
                  non_texture_stored_and_decoded_payloads_exact=True,
                  unselected_gims_byte_identical=untouched,
                  model_sha256=sha(before[2][1]), native_validation=final_native['report'],
                  poses=exact_pose_checks(native, final_native),
                  unused_pac_bytes=target-len(data))
    if source.read_bytes() != source_bytes or baseline.read_bytes() != original:
        raise ValueError('Input changed')
    (output/'candidate.pac').write_bytes(data)
    preview = output/'preview'
    preview.mkdir()
    (preview/'output.yobj').write_bytes(final[2][1])
    write_preview(final_native, preview/'output.obj')
    # The native OBJ writer uses texture_<index>; direct YOBJ uses source names.
    material = []
    for index, name in enumerate(native['texture_names']):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError('Unsafe preview name')
        p, c = read_gim(final_images[name])
        Image.fromarray(c[p]).save(preview/(name+'.png'))
        (preview/(name+'.gim')).write_bytes(final_images[name])
        material += ['newmtl texture_'+str(index), 'Kd 1 1 1', 'map_Kd '+name+'.png']
    (preview/'preview.mtl').write_text('\n'.join(material)+'\n')
    if renders:
        save_views(native, old_images, output/'before-renders', resolution=512, gim_reader=read_gim)
        save_views(final_native, final_images, output/'after-renders', resolution=512, gim_reader=read_gim)
    sheet = Image.new('RGB', (900, 210*len(selections)), (28,28,28))
    draw = ImageDraw.Draw(sheet)
    for row, name in enumerate(selections):
        for column, label in enumerate(('source', 'before', 'after')):
            im = Image.open(output/'textures'/(name+'-'+label+'.png'))
            w, h = im.size
            scale = min(285/w, 155/h)
            im = im.resize((int(w*scale), int(h*scale)), Image.Resampling.NEAREST)
            sheet.paste(im, (column*300+5, row*210+45))
            draw.text((column*300+5, row*210+6), name+' | '+label, fill='white')
            draw.text((column*300+5, row*210+24), '%dx%d'%(w,h), fill='white')
    sheet.save(output/'texture-comparison.png')
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    figures = ''.join('<h2>'+html.escape(n)+'</h2>'+''.join(
        '<figure style="display:inline-block"><figcaption>'+label+'</figcaption><img width="256" src="textures/'+n+'-'+label+'.png"></figure>'
        for label in ('source','before','after')) for n in selections)
    (output/'report.html').write_text('<!doctype html><meta charset="utf-8"><h1>Experimental texture allocation</h1><p>'+report['limitation']+
        '</p><p>PAC '+str(len(data))+' / '+str(target)+' bytes; pixels/CLUT '+str(report['after_allocation']['pixel_palette_bytes'])+
        ' / '+str(pixel_limit)+' experimental bytes. Only selected GIMs changed.</p><a href="report.json">Full metrics, hashes, structure and pose proof</a>'+figures)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source','baseline','output'):
        p.add_argument(name, type=Path)
    p.add_argument('--texture', action='append', required=True)
    p.add_argument('--experimental-pixel-limit', type=int, required=True)
    p.add_argument('--target', type=int, default=148000)
    p.add_argument('--no-renders', action='store_true')
    args = p.parse_args()
    selections = {}
    for value in args.texture:
        m = re.fullmatch(r'([A-Za-z0-9_-]+)=(\d+)x(\d+)', value)
        if not m or m[1] in selections:
            p.error('Use unique NAME=WIDTHxHEIGHT texture selections')
        selections[m[1]] = (int(m[2]), int(m[3]))
    r = run(args.source, args.baseline, args.output, selections,
            pixel_limit=args.experimental_pixel_limit, target=args.target, renders=not args.no_renders)
    print(json.dumps({k:r[k] for k in ('status','after_bytes','after_allocation','sha256')}, indent=2))

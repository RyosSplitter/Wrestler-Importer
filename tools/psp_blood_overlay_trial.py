"""Isolated native blood-layer experiment over an immutable converted PSP body.

python -m tools.psp_blood_overlay_trial --input converted.pac --donor base.pac
    --output new-directory [--coincident]
No production converter changes, body edits, texture reductions or rig transfer.
"""
from desktop.limits import IN_RING_MAX_PAC_BYTES
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageDraw

from desktop.core import validate_pac
from desktop.preview import render
from desktop.skinning import exact_pose_checks
from desktop.texture_optimizer.candidates import read_gim
from model_qa.geometry import geometry, posed
from model_qa.head import controller_probes
from model_qa.ocular import skin
from model_qa.pipeline import POSES
from tools.pac_inspect import inspect_pac, parse_textures
from tools.pac_repack import replace_sections, texture_table
from tools.prepare_model import Surface
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge import write_model
from tools.psp_mesh_merge_trial import sections, write_preview
from tools.stripify import stripify
from tools.yukes_bpe import compress, decompress


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unpack(data):
    return {s['id']: (s, raw) for s, raw in sections(data)}


def images(unpacked):
    out = {}
    for s, raw in unpacked.values():
        if len(raw) < 16 or raw[4:16] != bytes.fromhex('000100000000000010000000'):
            continue
        for t in parse_textures(raw):
            payload = raw[t['offset']:t['offset'] + t['size']]
            if t['name'] in out and out[t['name']] != payload:
                raise ValueError('Ambiguous donor image: ' + t['name'])
            out[t['name']] = payload
    return out


def ordinary(model):
    result = copy.deepcopy(model)
    for m in result['meshes']:
        m['materials'] = [a for a in m['materials'] if a['control'] in (5, 7)
                          and not model['texture_names'][a['texture_id']].lower().startswith('blood')]
    return result


def sample(surface, point):
    i, bary, distance = surface.nearest(point)
    mesh, tri = surface.corners[i]
    return mesh, tri, bary, bary @ surface.triangles[i], distance


def fit_layers(target, donor, *, coincident=False):
    # Controller semantics are not inferred from bone names. This first trial
    # requires the exact base rig the accepted conversion already uses.
    if target['bone_raw'] != donor['bone_raw']:
        raise ValueError('Experiment requires byte-identical donor/converted bind rigs')
    if any(n.lower().startswith('blood') for n in target['texture_names']):
        raise ValueError('Input already contains blood references; do not duplicate effects')
    if any(m['rigid'] or m['base_flag'] != 0x17ff for m in target['meshes']):
        raise ValueError('Only audited float32 weighted body buffers are supported')
    body = Surface(ordinary(donor))
    patches = {}
    for m in donor['meshes']:
        for a in m['materials']:
            name = donor['texture_names'][a['texture_id']]
            if name not in ('blood', 'blood_b'):
                continue
            if a['control'] != 0x115:
                raise ValueError('Unobserved blood material contract')
            patches.setdefault(name, []).append((m, a))
    if set(patches) != {'blood', 'blood_b'}:
        raise ValueError('Donor must contain the observed face and torso blood layers')
    result = copy.deepcopy(target)
    names = list(target['texture_names']) + list(patches)
    result['texture_names'] = names
    result['texture_raw'] = b''.join(n.encode('ascii').ljust(16, b'\0') for n in names)
    header = bytearray(result['header'])
    struct.pack_into('<I', header, 32, len(names))
    result['header'] = bytes(header)
    height = np.ptp(np.array([v['position'] for m in target['meshes'] for v in m['vertices']])[:, 1])
    records, patch_reports = [], {}
    for name, draws in patches.items():
        patch_model = copy.deepcopy(donor)
        patch_model['meshes'] = []
        distances, signed = [], []
        for mesh, mat in draws:
            row = copy.deepcopy(mesh)
            row['materials'] = [copy.deepcopy(mat)]
            patch_model['meshes'].append(row)
            for vi in sorted({i for t in mat['triangles'] for i in t}):
                v = mesh['vertices'][vi]
                dm, dt, bary, point, distance = sample(body, v['position'])
                normal = bary @ np.array([dm['vertices'][i]['normal'] for i in dt])
                normal /= np.linalg.norm(normal)
                distances.append(distance)
                signed.append(float(np.dot(np.array(v['position']) - point, normal)))
        patch = Surface(patch_model)
        # Coverage is inferred through the donor's ordinary surface, not by
        # stretching the new model to Kurt. Tolerance comes from measured native
        # patch/body separation. It is a provisional fitting rule, not a loader limit.
        tolerance = max(distances) + 1e-5
        offset = 0. if coincident else float(np.median(signed))
        if abs(offset) > tolerance:
            raise ValueError('Native normal separation exceeds measured surface gap')
        added_faces = 0
        for mesh in target['meshes']:
            selected = []
            for mat in mesh['materials']:
                if mat['control'] not in (5, 7):
                    continue  # Eyes, hair/cutout attachments remain untouched.
                for tri in mat['triangles']:
                    points = np.array([mesh['vertices'][i]['position'] for i in tri])
                    if np.linalg.norm(np.cross(points[1]-points[0], points[2]-points[0])) < 1e-10:
                        continue
                    center = points.mean(0)
                    _, _, _, basepoint, body_distance = sample(body, center)
                    pm, pt, bary, _, patch_distance = sample(patch, basepoint)
                    n = np.mean([mesh['vertices'][i]['normal'] for i in tri], axis=0)
                    pn = bary @ np.array([pm['vertices'][i]['normal'] for i in pt])
                    if (body_distance > height*.04 or patch_distance > tolerance
                            or np.dot(n, pn) / (np.linalg.norm(n)*np.linalg.norm(pn)) < .5):
                        continue
                    selected.append(tri)
            if not selected:
                continue
            if (mesh['opaque'] != draws[0][0]['opaque'] or
                    mesh['raw_palette_header'][12:16] != draws[0][0]['raw_palette_header'][12:16]):
                raise ValueError('Body metadata does not match the observed native overlay profile')
            row = copy.deepcopy(mesh)
            row['index'] = len(result['meshes'])
            row['vertices'] = []
            mapped, triangles = {}, []
            for tri in selected:
                face = []
                for vi in tri:
                    if vi not in mapped:
                        v = copy.deepcopy(mesh['vertices'][vi])
                        _, _, _, bp, gap = sample(body, v['position'])
                        pm, pt, bary, _, distance = sample(patch, bp)
                        uv = bary @ np.array([pm['vertices'][i]['uv'] for i in pt])
                        normal = np.array(v['normal'])
                        position = np.array(v['position']) + offset*normal/np.linalg.norm(normal)
                        v['uv'] = np.asarray(uv, dtype=np.float32).tolist()
                        v['position'] = np.asarray(position, dtype=np.float32).tolist()
                        v['color'] = [255, 255, 255, 255]
                        mapped[vi] = len(row['vertices'])
                        records.append(dict(mesh=row['index'], vertex=mapped[vi], body_mesh=mesh['index'],
                            body_vertex=vi, texture=name, native_offset=offset,
                            donor_body_distance=gap, donor_patch_distance=distance))
                        row['vertices'].append(v)
                    face.append(mapped[vi])
                triangles.append(face)
            row['raw_vertices'] = b''.join(struct.pack('<'+'f'*row['weight_slots']+'2f4B6f',
                *v['weights'], *v['uv'], *v['color'], *v['normal'], *v['position']) for v in row['vertices'])
            record = bytearray(draws[0][1]['raw'])
            struct.pack_into('<H', record, 22, names.index(name))
            strips = stripify(triangles)
            strip_header = draws[0][1]['strip_headers'][0]
            row['materials'] = [dict(raw=bytes(record), texture_id=names.index(name), control=0x115,
                strips=strips, triangles=triangles, strip_headers=[strip_header]*len(strips))]
            ps = np.array([v['position'] for v in row['vertices']])
            center = (ps.min(0)+ps.max(0))*.5
            bounds = bytearray(row['raw_header'])
            struct.pack_into('<4f', bounds, 48, *center, max(math.dist(p, center) for p in ps)+.001)
            row['raw_header'] = bytes(bounds)
            result['meshes'].append(row)
            added_faces += len(triangles)
        if not added_faces:
            raise ValueError('No supported coverage for ' + name)
        patch_reports[name] = dict(native_meshes=[m['index'] for m, a in draws],
            native_triangles=sum(len(a['triangles']) for m, a in draws),
            native_gap_range=[min(distances), max(distances)], signed_normal_gap_median=float(np.median(signed)),
            applied_normal_offset=offset, coverage_tolerance=tolerance, added_triangles=added_faces)
    return result, records, patch_reports


def validate_layers(before, after, records):
    body = copy.deepcopy(after)
    body['meshes'] = body['meshes'][:len(before['meshes'])]
    for old, new in zip(before['meshes'], body['meshes']):
        for key in ('raw_vertices', 'bone_palette', 'stride', 'flag', 'opaque'):
            if old[key] != new[key]:
                raise ValueError('Existing body changed: ' + key)
        if len(old['materials']) != len(new['materials']):
            raise ValueError('Existing body material count changed')
        for a, b in zip(old['materials'], new['materials']):
            if a['raw'][:132] != b['raw'][:132] or a['strips'] != b['strips']:
                raise ValueError('Existing draw state/topology changed')
    unchanged = exact_pose_checks(before, body)
    # Reference for overlay motion uses the exact corresponding body record,
    # not a nearest posed surface that might conceal attachment failures.
    reference = copy.deepcopy(after)
    for r in records:
        v = after['meshes'][r['mesh']]['vertices'][r['vertex']]
        m = before['meshes'][r['body_mesh']]
        bv = m['vertices'][r['body_vertex']]
        if after['meshes'][r['mesh']]['bone_palette'] != m['bone_palette'] or v['weights'] != bv['weights']:
            raise ValueError('Overlay uses different facial/body skinning inputs')
        reference['meshes'][r['mesh']]['vertices'][r['vertex']]['position'] = bv['position']
    a, b = geometry(after), geometry(reference)
    ids = np.array([sum(len(m['vertices']) for m in after['meshes'][:r['mesh']])+r['vertex'] for r in records])
    limit = max(abs(r['native_offset']) for r in records) + 2e-6
    values = {}
    for name, controls in POSES.items():
        x, y = posed(a, controls), posed(b, controls)
        gap = np.linalg.norm(x.vertices[ids]-y.vertices[ids], axis=1)
        if gap.max() > limit:
            raise ValueError('Blood layer separates during ' + name)
        values[name] = float(gap.max())
    head = {}
    for name, probe in controller_probes(before).items():
        x, _ = skin(a, probe); y, _ = skin(b, probe)
        gap = np.linalg.norm(x.vertices[ids]-y.vertices[ids], axis=1)
        if gap.max() > limit:
            raise ValueError('Blood layer separates during cranial probe ' + name)
        head[name] = float(gap.max())
    if before['bone_raw'] != after['bone_raw']:
        raise ValueError('Bind rig changed')
    return dict(body=unchanged, overlay_pose_gaps=values, overlay_cranial_gaps=head,
                maximum_allowed_gap=limit, bind_rig_exact=before['bone_raw']==after['bone_raw'],
                limitation='Synthetic analytical LBS; game activation, depth testing and runtime memory remain untested')


def run(input_path, donor_path, output, *, coincident=False, max_bytes=IN_RING_MAX_PAC_BYTES):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    baseline = Path(input_path).read_bytes(); donor_pac = Path(donor_path).read_bytes()
    old, native = unpack(baseline), unpack(donor_pac)
    if any(i != 2 and raw.startswith(b'YOBJ') for i, (s, raw) in old.items()):
        raise ValueError('First trial supports a main model only; accessories need separate dependency tests')
    target, donor = audit_yobj(old[2][1]), audit_yobj(native[2][1])
    fitted, records, patches = fit_layers(target, donor, coincident=coincident)
    yobj = write_model(fitted, [[i] for i in range(len(fitted['meshes']))])
    final = audit_yobj(yobj)
    validation = validate_layers(target, final, records)
    old_images, donor_images = images(old), images(native)
    all_images = dict(old_images)
    for name in ('blood', 'blood_b'):
        payload = donor_images[name]
        p, palette = read_gim(payload)
        if len(palette) != 16 or not np.any(palette[p][:, :, 3] < 255):
            raise ValueError('Blood image must retain native T4 alpha')
        all_images[name] = payload
    def texture_allocation(payloads):
        total = 0
        for payload in payloads.values():
            px, clut = read_gim(payload)
            bits = 4 if len(clut) == 16 else 8
            total += ((px.shape[1]*bits+127)//128*16)*px.shape[0] + clut.size
        return total
    table = texture_table(final['texture_names'], [all_images[n] for n in final['texture_names']], gim_reader=read_gim)
    attempts = []; candidates = []
    # Existing tested compression settings; no PAC writer or storage code edit.
    for symbols in (200, 220):
        changes = {2: compress(yobj, max_distinct=symbols), 9: compress(table, max_distinct=symbols)}
        for section, raw in ((2, yobj), (9, table)):
            if decompress(changes[section]) != raw:
                raise ValueError('BPE round trip changed')
        candidate = replace_sections(baseline, changes)
        attempts.append(dict(max_distinct=symbols, bytes=len(candidate), model_stored_bytes=len(changes[2]),
            textures_stored_bytes=len(changes[9])))
        candidates.append(candidate)
    candidate = min(candidates, key=len)
    unpacked = unpack(candidate)
    if unpacked[2][1] != yobj:
        raise ValueError('Preview and final model mismatch')
    for section in old:
        if section not in (2, 9):
            a, ar = old[section]; b, br = unpacked[section]
            if ar != br or baseline[a['offset']:a['offset']+a['size']] != candidate[b['offset']:b['offset']+b['size']]:
                raise ValueError('Unrelated section changed')
    for name in target['texture_names']:
        if images(unpacked)[name] != old_images[name]:
            raise ValueError('Existing body texture changed')
    fits = len(candidate) <= max_bytes
    if fits:
        validate_pac(candidate, baseline, max_bytes=max_bytes, gim_reader=read_gim)
    elif any(s['offset'] % 16 for s in inspect_pac(candidate)['sections']) or len(candidate) % 2048:
        raise ValueError('Oversize analytical candidate also violates alignment')
    output.mkdir(parents=True)
    report = dict(status='experimental PAC ready for gameplay test' if fits else 'export withheld: exceeds configured cap',
        input_sha256=sha(baseline), donor_sha256=sha(donor_pac), sha256=sha(candidate) if fits else None,
        before_bytes=len(baseline), candidate_bytes=len(candidate), max_pac_bytes=max_bytes,
        before_modeled_texture_bytes=texture_allocation(old_images),
        modeled_texture_bytes=texture_allocation(all_images),
        oversize_bytes=max(0, len(candidate)-max_bytes), compression_attempts=attempts,
        before={k:target['report'][k] for k in ('meshes','vertices','triangles','textures','expanded_bytes')},
        after={k:final['report'][k] for k in ('meshes','vertices','triangles','textures','expanded_bytes')},
        patches=patches, vertex_provenance=records, validation=validation,
        native_checks=dict(offsets_ranges_indices_palettes_weights_valid=final['report']['offsets_ranges_indices_palettes_weights_valid'],
            relocation_count=final['report']['relocation_count'],
            pac_section_alignment=16, pac_padded_alignment=2048,
            final_size_within_configured_cap=fits, model_bpe_roundtrip_exact=True),
        existing_body_textures_exact=True, unrelated_sections_exact=True,
        blood_images_exact_to_donor=True, production_converter_changed=False,
        confirmed=['Copied native blood image bytes and complete material non-pointer state',
            'Existing body attributes, topology, materials, weights and rig are exact',
            'New blood layers inherit corresponding target body weights with no pruning or transfer'],
        inferred=['Donor-surface coverage and native measured normal gap provide suitable converted blood layers'],
        unknown=['SVR blood-stage activation and name lookup', 'Coincident depth testing and offset behavior',
            'Extra mesh/allocation runtime heap tolerance', 'Appearance under actual gameplay animations'])
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    (output/'native-audit.json').write_text(json.dumps(final['report'], indent=2)+'\n')
    preview = output/'preview'; preview.mkdir()
    (preview/'blood-overlay.yobj').write_bytes(yobj)
    write_preview(final, preview/'blood-overlay.obj')
    write_preview(target, preview/'before.obj')
    lines = []
    for i, name in enumerate(final['texture_names']):
        p, palette = read_gim(all_images[name])
        (preview/(name+'.gim')).write_bytes(all_images[name])
        Image.fromarray(palette[p]).save(preview/(name+'.png'))
        lines += ['newmtl texture_'+str(i), 'Kd 1 1 1', 'map_Kd '+name+'.png']
        if name in ('blood','blood_b'):
            lines += ['map_d '+name+'.png']
    (preview/'preview.mtl').write_text('\n'.join(lines)+'\n')
    visible = copy.deepcopy(final)
    for mesh in visible['meshes'][len(target['meshes']):]:
        mesh['materials'] = []  # Same vertex bounds give an identical camera.
    for view in ('front','front-left','back'):
        a = render(visible, all_images, view, 640, gim_reader=read_gim)
        b = render(final, all_images, view, 640, gim_reader=read_gim)
        sheet = Image.new('RGB',(1280,675),(40,40,40)); d = ImageDraw.Draw(sheet)
        sheet.paste(a,(0,35)); sheet.paste(b,(640,35))
        d.text((10,10),'Unchanged body / effects hidden',fill='white')
        d.text((650,10),'Added blood layer forced visible / CPU diagnostic',fill='white')
        sheet.save(output/(view+'-comparison.png'))
    if fits:
        (output/'PSP-Blood-Overlay-EXPERIMENTAL.pac').write_bytes(candidate)
    assert Path(input_path).read_bytes()==baseline and Path(donor_path).read_bytes()==donor_pac
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--donor', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--coincident', action='store_true')
    args = parser.parse_args()
    report = run(args.input, args.donor, args.output, coincident=args.coincident)
    print(json.dumps({k:report[k] for k in ('status','before_bytes','candidate_bytes','sha256')}))

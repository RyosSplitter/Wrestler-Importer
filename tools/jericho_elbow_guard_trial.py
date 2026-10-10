"""Replay an opt-in decimation-protected pad onto the accepted PSP model.

This isolated experiment restores source-supported material geometry and its
shared skin boundary. It does not write a PAC or change converter defaults.
Unknown rendering metadata and unrelated native records remain unchanged.
"""
import argparse
import copy
from collections import Counter
import json
from pathlib import Path
import struct

import numpy as np

from tools.lance_anatomy_restore import boundary
from tools.psp_mesh_audit import audit_yobj, digest
from tools.psp_mesh_merge import write_model
from tools.psp_mesh_merge_trial import sections, write_json
from tools.stripify import stripify

TEXTURE = 'y2j_hiji'
BASE_SHA = 'da7a9fa75b0941e58aba86881472f40129448b22880b5cc4fba478b265961bd9'


def position(v):
    return struct.pack('<3f', *v['position'])


def selected(model, texture):
    names = model.get('texture_names', model.get('textures'))
    return [(m, a) for m in model['meshes'] for a in m['materials']
            if names[a['texture_id']] == texture]


def signature(model, texture):
    """Oriented position/UV/weight signatures, independent of vertex indices."""
    result = Counter()
    for m, a in selected(model, texture):
        for t in a['triangles']:
            corners = []
            for i in t:
                v = m['vertices'][i]
                w = np.zeros(len(model['bones']), dtype='<f4')
                w[m['bone_palette']] = v['weights']
                corners.append(position(v) + struct.pack('<2f', *v['uv']) + w.tobytes())
            result[min(tuple(corners[k:] + corners[:k]) for k in range(3))] += 1
    return result


def pack(v, mesh):
    dense = np.asarray(v['weights'])
    if np.any(dense[[i for i in range(len(dense)) if i not in mesh['bone_palette']]] > 1e-7):
        raise ValueError('Source weights exceed existing palette')
    local = dense[mesh['bone_palette']]
    if abs(local.sum() - 1) > 1e-6:
        raise ValueError('Source weights are not normalized')
    return struct.pack('<' + 'f' * len(local), *local) + struct.pack(
        '<2f4B3f3f', *v['uv'], *v['color'], *v['normal'], *v['position'])


def repair(raw, source, guarded):
    before = audit_yobj(raw)
    names = [b['name'] for b in before['bones']]
    if any([b['name'] for b in model['bones']] != names for model in (source, guarded)):
        raise ValueError('Source stage must already use the verified PSP bone mapping')
    if signature(source, TEXTURE) != signature(guarded, TEXTURE):
        raise ValueError('Guarded decimation changed source pad geometry, UVs or weights')
    old_parts, source_parts = selected(before, TEXTURE), selected(source, TEXTURE)
    if len(old_parts) != 1 or len(source_parts) != 1:
        raise ValueError('Experiment requires one verified source/native pad material')
    old_mesh, old_mat = old_parts[0]
    source_mesh, source_mat = source_parts[0]
    pad_ids = sorted({i for t in old_mat['triangles'] for i in t})
    other_ids = {i for a in old_mesh['materials'] if a is not old_mat for t in a['triangles'] for i in t}
    prefix = len(other_ids)
    if other_ids != set(range(prefix)) or pad_ids != list(range(prefix, len(old_mesh['vertices']))):
        raise ValueError('Pad records are not a disjoint trailing block')
    source_tid = source_mat['texture_id']
    native_tid = old_mat['texture_id']
    source_boundary = {p for e in boundary(source, source_tid) for p in e}
    old_boundary = {p for e in boundary(before, native_tid) for p in e}
    missing, extra = source_boundary - old_boundary, old_boundary - source_boundary
    if len(missing) != 3 or len(extra) != 3:
        raise ValueError('Unexpected pad-boundary discrepancy; requires new evidence')
    output = copy.deepcopy(before)
    buffers = {m['index']: bytearray(m['raw_vertices']) for m in output['meshes']}
    seam_changes = []
    # Match missing source corners using each skin alias's material-specific UV
    # or the pad UV, restricted to verified missing boundary positions. This
    # excludes ambiguous mirrored arm UVs and never assumes source indices.
    for bad in sorted(extra):
        aliases = [(m, i, v) for m in before['meshes'] for i, v in enumerate(m['vertices'])
                   if position(v) == bad]
        matches = set()
        for m, i, v in aliases:
            uses = {before['texture_names'][a['texture_id']] for a in m['materials']
                    if any(i in t for t in a['triangles'])}
            for texture in uses:
                for sm, a in selected(source, texture):
                    for j in {j for t in a['triangles'] for j in t}:
                        sv = sm['vertices'][j]
                        if position(sv) in missing and np.linalg.norm(np.asarray(sv['uv']) - v['uv']) < 1e-6:
                            matches.add(position(sv))
        if len(matches) != 1:
            raise ValueError('Shared pad anchor has no unique source UV evidence')
        good = matches.pop()
        for m, i, v in aliases:
            if m['index'] == old_mesh['index'] and i in pad_ids:
                continue  # Replaced by the complete preserved source pad below.
            uses = {before['texture_names'][a['texture_id']] for a in m['materials']
                    if any(i in t for t in a['triangles'])}
            candidates = [sm['vertices'][j] for texture in uses for sm, a in selected(source, texture)
                          for j in {j for t in a['triangles'] for j in t}
                          if position(sm['vertices'][j]) == good]
            if not candidates or any(pack(sv, m) != pack(candidates[0], m) for sv in candidates):
                raise ValueError('Conflicting source skin seam records')
            sv = candidates[0]
            record = pack(sv, m)
            buffers[m['index']][i*m['stride']:(i+1)*m['stride']] = record
            seam_changes.append(dict(mesh=m['index'], vertex=i, before_position=list(v['position']),
                after_position=list(sv['position']), displacement=float(np.linalg.norm(np.asarray(v['position'])-sv['position'])),
                before_uv=list(v['uv']), after_uv=sv['uv'], fields=['position', 'weights', 'uv', 'normal'],
                before_weights={names[b]:float(w) for b,w in zip(m['bone_palette'],v['weights']) if w},
                after_weights={names[b]:float(w) for b,w in enumerate(sv['weights']) if w},
                evidence='Unique material-specific UV at an original pad boundary; source skin alias at the same position'))
    for m in output['meshes']:
        m['raw_vertices'] = bytes(buffers[m['index']])
    mesh = output['meshes'][old_mesh['index']]
    mat = mesh['materials'][old_mesh['materials'].index(old_mat)]
    src_ids = sorted({i for t in source_mat['triangles'] for i in t})
    mapping = {i: prefix+k for k, i in enumerate(src_ids)}
    mesh['vertices'] = mesh['vertices'][:prefix] + [copy.deepcopy(source_mesh['vertices'][i]) for i in src_ids]
    mesh['raw_vertices'] = mesh['raw_vertices'][:prefix*mesh['stride']] + b''.join(pack(source_mesh['vertices'][i], mesh) for i in src_ids)
    mat['triangles'] = [[mapping[i] for i in t] for t in source_mat['triangles']]
    template = mat['strip_headers'][0][:8]
    if template != bytes.fromhex('0300000000000000') or any(h[:8] != template for h in mat['strip_headers']):
        raise ValueError('Unrecognized primitive rendering metadata')
    mat['strips'] = stripify(mat['triangles'])
    mat['strip_headers'] = [template + struct.pack('<2I', len(s), 0) for s in mat['strips']]
    result = write_model(output, [[i] for i in range(len(output['meshes']))])
    fixed = audit_yobj(result)
    if signature(source, TEXTURE) != signature(fixed, TEXTURE):
        raise ValueError('Serialized pad differs from the protected source surface')
    if boundary(source, source_tid) != boundary(fixed, native_tid):
        raise ValueError('Source pad boundary was not restored exactly')
    for field in ('bone_raw', 'texture_raw', 'model_descriptor_raw'):
        if before[field] != fixed[field]:
            raise ValueError('Unrelated model metadata changed')
    changed = {(r['mesh'], r['vertex']) for r in seam_changes}
    for a, b in zip(before['meshes'], fixed['meshes']):
        if a['bone_palette'] != b['bone_palette'] or a['opaque'] != b['opaque']:
            raise ValueError('Native palette/opaque state changed')
        for i in range(len(a['vertices'])):
            if a['index'] == old_mesh['index'] and i in pad_ids:
                continue
            if (a['index'], i) not in changed and a['raw_vertices'][i*a['stride']:(i+1)*a['stride']] != b['raw_vertices'][i*b['stride']:(i+1)*b['stride']]:
                raise ValueError('Unrelated vertex record changed')
        for aa, bb in zip(a['materials'], b['materials']):
            if aa['raw'][:132] != bb['raw'][:132]:
                raise ValueError('Material/rendering metadata changed')
            if aa['texture_id'] != native_tid and aa['strips'] != bb['strips']:
                raise ValueError('Unrelated triangle indices changed')
    return result, dict(policy='Opt-in material protection during decimation; replay original pad and verified shared skin anchors only',
        texture=TEXTURE, pad_mesh=old_mesh['index'], source_pad_vertices=len(src_ids), source_pad_triangles=len(source_mat['triangles']),
        before_pad_vertices=len(pad_ids), before_pad_triangles=len(old_mat['triangles']), shared_skin_records=seam_changes,
        before_yobj_sha256=digest(raw), candidate_yobj_sha256=digest(result),
        unrelated_vertices_weights_uvs_normals_indices_unchanged=True, facial_records_bit_identical=True,
        palettes_skeleton_textures_material_state_unchanged=True, source_pad_signature_exact=True, pac_written=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'source-stage', 'guarded-stage', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    pac = args.baseline.read_bytes()
    if digest(pac) != BASE_SHA:
        raise ValueError('Accepted baseline identity mismatch')
    raw = next(r for s, r in sections(pac) if s['id'] == 2)
    candidate, report = repair(raw, json.loads(args.source_stage.read_text()), json.loads(args.guarded_stage.read_text()))
    report.update(source_stage_sha256=digest(args.source_stage.read_bytes()), guarded_stage_sha256=digest(args.guarded_stage.read_bytes()))
    args.output.mkdir(parents=True)
    (args.output/'candidate.yobj').write_bytes(candidate)
    write_json(args.output/'experiment.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

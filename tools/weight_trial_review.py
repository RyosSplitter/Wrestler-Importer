"""Controlled, geometry-preserving weight studies and analytical LBS previews.

Inputs are decoded source-weighted.json and target.json in the study directory.
Outputs are diagnostic JSON, weights and posed OBJ/MTL files for real Noesis
captures. They are not native PSP exports or game-compatible PACs.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil

import numpy as np

from .prepare_model import LANDMARKS, Surface, bone_matrices, similarity_fit


METHODS = {1: 'direct', 2: 'redistribution', 3: 'hybrid', 4: 'base-transfer', 5: 'automatic-binding'}
POSES = {
    'elbow-flex': {'l_ninoude': ('z', -15), 'r_ninoude': ('z', 15),
                   'l_kote': ('z', -65), 'r_kote': ('z', 65),
                   'kubi': ('y', 20), 'd_kuchi': ('x', 18)},
    'arms-up': {'l_ninoude': ('z', -65), 'r_ninoude': ('z', 65),
                'l_kote': ('z', -20), 'r_kote': ('z', 20),
                'kubi': ('y', -20), 'd_kuchi': ('x', 18)},
    'knees-bent': {'l_sune': ('x', 35), 'r_sune': ('x', 35),
                   'l_kote': ('z', -30), 'r_kote': ('z', 30)},
    'rest': {},
}


def load_study(root):
    source = json.loads((root / 'source-weighted.json').read_text())
    target = json.loads((root / 'target.json').read_text())
    sb = {b['name']: b['index'] for b in source['bones']}
    tb = {b['name']: b['index'] for b in target['bones']}
    sm, tm = bone_matrices(source), bone_matrices(target)
    names = [n for n in LANDMARKS if n in sb and n in tb]
    scale, rotation, translation = similarity_fit([sm[sb[n]][:3, 3] for n in names],
                                                [tm[tb[n]][:3, 3] for n in names])
    aligned = copy.deepcopy(source)
    for mesh in aligned['meshes']:
        for v in mesh['vertices']:
            v['position'] = (scale * rotation @ v['position'] + translation).tolist()
            v['normal'] = (rotation @ v['normal']).tolist()
    positions = np.array([v['position'] for mesh in aligned['meshes'] for v in mesh['vertices']])
    originals = np.array([v['position'] for mesh in source['meshes'] for v in mesh['vertices']])
    sw = np.zeros((len(positions), source['bone_count']))
    for row, (mesh, v) in enumerate((m, v) for m in source['meshes'] for v in m['vertices']):
        for bone, weight in zip(mesh['bone_palette'], v['weights']):
            sw[row, bone] = weight
    # A common, recorded normalization corrects at most source float roundoff.
    original_sums = sw.sum(axis=1)
    sw /= original_sums[:, None]
    report = {'scale': scale, 'rotation': rotation.tolist(), 'translation': translation.tolist(),
              'landmarks': names, 'source_weight_sum_max_error': float(np.max(np.abs(original_sums-1))),
              'geometry_digest': hashlib.sha256(positions.tobytes()).hexdigest(),
              'alignment_shared_by_all_trials': True, 'triangles': aligned['triangle_count'],
              'vertices': aligned['vertex_count'], 'decimation_applied': False}
    return source, target, aligned, positions, originals, sw, report


def descendant_names(model, root_name):
    names = {b['name']: b['index'] for b in model['bones']}
    if root_name not in names:
        return set()
    root = names[root_name]
    result = set()
    for bone in model['bones']:
        index = bone['index']
        while index != -1:
            if index == root:
                result.add(bone['name'])
                break
            index = model['bones'][index]['parent']
    return result


def map_source(source, target, source_weights, redistribute):
    tb = {b['name']: b['index'] for b in target['bones']}
    mapped = np.zeros((len(source_weights), target['bone_count']))
    missing = np.zeros(len(source_weights))
    redirects = {}
    for bone in source['bones']:
        name = bone['name']
        # Unweighted dummy roots/endpoints have nothing to map. Some HCTP
        # models retain a separate object root with no PSP counterpart.
        if name not in tb and not np.any(source_weights[:, bone['index']] != 0):
            continue
        if name not in tb and redistribute:
            index = bone['parent']
            while index != -1 and source['bones'][index]['name'] not in tb:
                index = source['bones'][index]['parent']
            if index == -1:
                raise ValueError('No matching ancestor for ' + name)
            replacement = source['bones'][index]['name']
            redirects[name] = replacement
            name = replacement
        if name in tb:
            mapped[:, tb[name]] += source_weights[:, bone['index']]
        else:
            missing += source_weights[:, bone['index']]
    return mapped, missing, redirects


def transfer(target, positions, max_influences=4):
    # Ordinary body is the donor, excluding blood/effect overlay geometry.
    donor = copy.deepcopy(target)
    for mesh in donor['meshes']:
        mesh['materials'] = [m for m in mesh['materials'] if m.get('control') not in (0x117, 0x115)]
    surface = Surface(donor)
    output = np.zeros((len(positions), target['bone_count']))
    cache, distances = {}, []
    for i, position in enumerate(positions):
        key = tuple(position)
        if key not in cache:
            index, bary, distance = surface.nearest(position)
            mesh, triangle = surface.corners[index]
            dense = np.zeros(target['bone_count'])
            for coefficient, vi in zip(bary, triangle):
                for bone, weight in zip(mesh['bone_palette'], mesh['vertices'][vi]['weights']):
                    if weight > 0:
                        assert 0 <= bone < len(dense)
                        dense[bone] += coefficient * weight
            dense[np.argsort(dense)[:-max_influences]] = 0
            assert dense.sum() > 0
            dense /= dense.sum()
            cache[key] = dense
            distances.append(distance)
        output[i] = cache[key]
    return output, {'method': 'Nearest ordinary PSP body triangle, barycentric weight interpolation',
                    'max_influences': max_influences,
                    'distance_p95': float(np.percentile(distances, 95)), 'distance_max': max(distances)}


def rotation(axis, degrees):
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    if axis == 'x': return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == 'y': return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    if axis == 'z': return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    raise ValueError(axis)


def skin_matrices(model, pose):
    rest = bone_matrices(model)
    cache = {}
    def world(index):
        if index not in cache:
            bone = model['bones'][index]
            parent = bone['parent']
            local = rest[index] if parent == -1 else np.linalg.inv(rest[parent]) @ rest[index]
            motion = np.eye(4)
            if bone['name'] in pose:
                axis, degrees = pose[bone['name']]
                # Identical model-axis rotations, expressed in each bone's
                # rest local frame. Descendants inherit the parent motion.
                basis = rest[index][:3, :3]
                motion[:3, :3] = basis.T @ rotation(axis, degrees) @ basis
            cache[index] = local @ motion if parent == -1 else world(parent) @ local @ motion
        return cache[index]
    posed = np.array([world(i) for i in range(len(rest))])
    matrices = posed @ np.linalg.inv(rest)
    if not pose:
        assert np.max(np.abs(matrices-np.eye(4))) < 1e-10
    return matrices


def deform(model, positions, weights, pose, held_at_rest=None):
    matrices = skin_matrices(model, pose)
    homogeneous = np.column_stack((positions, np.ones(len(positions))))
    result = np.zeros_like(positions)
    for bone in range(model['bone_count']):
        result += weights[:, bone, None] * (homogeneous @ matrices[bone].T)[:, :3]
    if held_at_rest is not None:
        result += held_at_rest[:, None] * positions
    return result


def write_obj(aligned, positions, folder, name):
    obj = ['# Diagnostic analytical skinning; no native PSP serialization', 'mtllib preview.mtl']
    offset = 0
    for mesh in aligned['meshes']:
        obj.append('g source_mesh_' + str(mesh['index']))
        for p in positions[offset:offset+len(mesh['vertices'])]:
            x, y, z = p
            obj.append('v %.9f %.9f %.9f' % (x, z, -y))
        for v in mesh['vertices']:
            obj.append('vt %.9f %.9f' % tuple(v['uv']))
        for material in mesh['materials']:
            obj.append('usemtl texture_' + str(material['texture_id']))
            for triangle in material['triangles']:
                obj.append('f ' + ' '.join('%d/%d' % (offset+i+1, offset+i+1) for i in triangle))
        offset += len(mesh['vertices'])
    (folder / (name + '.obj')).write_text('\n'.join(obj) + '\n')
    mtl = []
    for i, texture in enumerate(aligned['textures']):
        mtl.extend(['newmtl texture_' + str(i), 'Kd 0.984 0.984 1.000',
                    'Ks 0.502 0.502 0.502', 'map_Kd ' + texture + '.png'])
    (folder / 'preview.mtl').write_text('\n'.join(mtl) + '\n')


def pose_metrics(aligned, positions, rest, reference):
    edges = set()
    index = 0
    for mesh in aligned['meshes']:
        for material in mesh['materials']:
            for a, b, c in material['triangles']:
                for x, y in ((a,b),(b,c),(c,a)):
                    edges.add(tuple(sorted((index+x, index+y))))
        index += len(mesh['vertices'])
    edge = np.array(sorted(edges))
    baseline = np.linalg.norm(rest[edge[:,0]]-rest[edge[:,1]], axis=1)
    current = np.linalg.norm(positions[edge[:,0]]-positions[edge[:,1]], axis=1)
    ratios = current[baseline>1e-7]/baseline[baseline>1e-7]
    seams = collections.defaultdict(list)
    for p, q in zip(rest, positions): seams[tuple(p)].append(q)
    seam_max = max((float(np.max(np.linalg.norm(np.array(q)-q[0],axis=1))) for q in seams.values()), default=0)
    distances = np.linalg.norm(positions-reference, axis=1)
    return {'edge_length_ratio_p95': float(np.percentile(ratios,95)),
            'edge_length_ratio_max': float(ratios.max()), 'duplicate_position_separation_max': seam_max,
            'distance_to_analytical_original_rig_rms': float(np.sqrt(np.mean(distances**2))),
            'distance_to_analytical_original_rig_p95': float(np.percentile(distances,95)),
            'note': 'LBS diagnostic metrics; original-game animation and PSP engine behavior are not established'}


def run(root, method):
    source, target, aligned, positions, originals, sw, alignment = load_study(root)
    folder = root / ('method-%d-' % method + METHODS[method])
    folder.mkdir(exist_ok=True)
    for p in (root/'textures').glob('*.png'): shutil.copyfile(p, folder/p.name)
    base, missing, redirects = map_source(source, target, sw, method != 1)
    detail = {'mapping': redirects}
    held = missing if method == 1 else np.zeros(len(positions))
    if method in (1,2): weights = base
    elif method in (3,4):
        transferred, detail_transfer = transfer(target, positions)
        if method == 4:
            weights = transferred
            detail = {'source_bone_mapping_used_for_weights': False,
                      'original_source_weight_values_used_for_assignment': False}
        else:
            head_names = descendant_names(source, 'atama')
            head_indices = [b['index'] for b in source['bones'] if b['name'] in head_names]
            head_fraction = sw[:, head_indices].sum(axis=1)
            weights = base*(1-head_fraction[:,None]) + transferred*head_fraction[:,None]
            detail['head_blend_vertices'] = int(np.count_nonzero(head_fraction > 1e-7))
            detail['head_mask'] = 'Original source weight mass in atama subtree; continuous blend'
            # One common four-influence ceiling for transferred/rebuilt values.
            order = np.argsort(weights,axis=1)
            np.put_along_axis(weights, order[:,:-4], 0, axis=1)
            weights /= weights.sum(axis=1)[:,None]
        detail['transfer'] = detail_transfer
    elif method == 5:
        automatic = np.load(root/'automatic-weights.npz')
        weights = automatic['weights']
        assert weights.shape == base.shape
        detail = json.loads((root/'automatic-binding-report.json').read_text())
    else: raise ValueError(method)
    assert np.isfinite(weights).all() and np.min(weights) >= 0
    assert np.max(np.abs(weights.sum(axis=1)+held-1)) < 1e-6
    np.savez_compressed(folder/'weights.npz', weights=weights, unmapped_held_at_rest=held,
                        aligned_positions=positions)
    report = {'method': method, 'name': METHODS[method], 'alignment': alignment,
              'details': detail, 'status': 'Incomplete direct mapping: diagnostic only' if held.max()>1e-7 else 'Weight-study candidate; native export and playability untested',
              'unmapped_vertices': int(np.count_nonzero(held>1e-7)), 'unmapped_mass_max': float(held.max()),
              'active_influence_histogram': dict(collections.Counter(np.count_nonzero(weights>1e-7,axis=1).tolist())),
              'pose_controls': POSES, 'poses': {},
              'source_only_bones': sorted(set(b['name'] for b in source['bones'])-set(b['name'] for b in target['bones'])),
              'native_psp_pac_written': False, 'source_triangles_preserved': True,
              'texture_and_uv_changes': False}
    for name, pose in POSES.items():
        actual = deform(target, positions, weights, pose, held)
        original = deform(source, originals, sw, pose)
        a = alignment
        reference = a['scale']*original@np.array(a['rotation']).T+np.array(a['translation'])
        assert np.isfinite(actual).all()
        if not pose: assert np.max(np.abs(actual-positions)) < 1e-8
        write_obj(aligned, actual, folder, name)
        report['poses'][name] = pose_metrics(aligned, actual, positions, reference)
        np.save(folder/(name+'-positions.npy'),actual)
    (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (root/'common-alignment.json').write_text(json.dumps(alignment,indent=2)+'\n')
    print(json.dumps(report,indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study',type=Path)
    parser.add_argument('method',type=int,choices=METHODS)
    args = parser.parse_args()
    run(args.study,args.method)


if __name__ == '__main__': main()

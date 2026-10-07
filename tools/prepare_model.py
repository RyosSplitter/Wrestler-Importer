"""Experimental HCTP -> PSP mesh preparation; does not write a playable PAC."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import sys

import numpy as np

try:
    from .hctp_read import load_hctp
    from .pac_inspect import FormatError
    from .yobj_read import load_model, write_obj
    from .stripify import stripify
except ImportError:
    from hctp_read import load_hctp
    from pac_inspect import FormatError
    from yobj_read import load_model, write_obj
    from stripify import stripify


LANDMARKS = ('koshi', 'atama', 'l_te', 'r_te', 'l_ashi', 'r_ashi',
             'l_kote', 'r_kote', 'l_sune', 'r_sune', 'l_sakotsu', 'r_sakotsu')


def local_matrix(bone):
    x, y, z = bone['rotation']
    cx, cy, cz, sx, sy, sz = math.cos(x), math.cos(y), math.cos(z), math.sin(x), math.sin(y), math.sin(z)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    result = np.eye(4)
    result[:3, :3] = rz @ ry @ rx
    result[:3, 3] = bone['local_position']
    return result


def bone_matrices(model):
    cache = {}
    def matrix(index):
        if index not in cache:
            b = model['bones'][index]
            local = local_matrix(b)
            cache[index] = local if b['parent'] == -1 else matrix(b['parent']) @ local
        return cache[index]
    return np.array([matrix(i) for i in range(len(model['bones']))])


def similarity_fit(source, target):
    source, target = np.asarray(source, dtype=float), np.asarray(target, dtype=float)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3 or len(source) < 3:
        raise FormatError('Alignment requires matching 3D landmark arrays')
    x, y = source - source.mean(axis=0), target - target.mean(axis=0)
    if np.linalg.matrix_rank(x) < 2:
        raise FormatError('Alignment landmarks are collinear')
    u, _, vt = np.linalg.svd(x.T @ y)
    sign = np.eye(3)
    sign[2, 2] = np.linalg.det(vt.T @ u.T)
    rotation = vt.T @ sign @ u.T
    scale = float(np.sum(y * (x @ rotation.T)) / np.sum(x * x))
    if not math.isfinite(scale) or scale <= 0:
        raise FormatError('Invalid alignment scale')
    translation = target.mean(axis=0) - scale * rotation @ source.mean(axis=0)
    return scale, rotation, translation


class Surface:
    """Exact nearest point on nondegenerate triangles, with barycentric weights."""
    def __init__(self, model):
        triangles, owners, corners = [], [], []
        for mesh in model['meshes']:
            for material in mesh['materials']:
                for triangle in material['triangles']:
                    points = np.array([mesh['vertices'][i]['position'] for i in triangle])
                    if np.linalg.norm(np.cross(points[1] - points[0], points[2] - points[0])) < 1e-10:
                        continue
                    triangles.append(points)
                    owners.append(mesh['index'])
                    corners.append((mesh, triangle))
        if not triangles:
            raise FormatError('Weight/layout donor has no nondegenerate triangles')
        self.triangles = np.array(triangles)
        self.owners = owners
        self.corners = corners
        self.a = self.triangles[:, 0]
        self.ab = self.triangles[:, 1] - self.a
        self.ac = self.triangles[:, 2] - self.a
        self.d00 = np.sum(self.ab * self.ab, axis=1)
        self.d01 = np.sum(self.ab * self.ac, axis=1)
        self.d11 = np.sum(self.ac * self.ac, axis=1)
        self.denom = self.d00 * self.d11 - self.d01 * self.d01

    def nearest(self, point):
        point = np.asarray(point)
        ap = point - self.a
        d20, d21 = np.sum(ap * self.ab, axis=1), np.sum(ap * self.ac, axis=1)
        v = (self.d11 * d20 - self.d01 * d21) / self.denom
        w = (self.d00 * d21 - self.d01 * d20) / self.denom
        bary = np.column_stack((1 - v - w, v, w))
        projection = self.a + v[:, None] * self.ab + w[:, None] * self.ac
        distances = np.sum((projection - point) ** 2, axis=1)
        distances[(bary < 0).any(axis=1)] = np.inf
        for i, j in ((0, 1), (1, 2), (2, 0)):
            a, b = self.triangles[:, i], self.triangles[:, j]
            edge = b - a
            t = np.clip(np.sum((point - a) * edge, axis=1) / np.sum(edge * edge, axis=1), 0, 1)
            p = a + t[:, None] * edge
            d = np.sum((p - point) ** 2, axis=1)
            improve = d < distances
            candidate = np.zeros_like(bary)
            candidate[:, i], candidate[:, j] = 1 - t, t
            bary[improve], distances[improve] = candidate[improve], d[improve]
        index = int(np.argmin(distances))
        return index, bary[index], float(math.sqrt(distances[index]))


def donor_bone_map(donor, target):
    target_names = {b['name']: b['index'] for b in target['bones']}
    mapping, collapsed = {}, {}
    for bone in donor['bones']:
        current = bone['index']
        while donor['bones'][current]['name'] not in target_names:
            current = donor['bones'][current]['parent']
            if current == -1:
                raise FormatError(f"No target ancestor for reference bone {bone['name']}")
        name = donor['bones'][current]['name']
        mapping[bone['index']] = target_names[name]
        if name != bone['name']:
            collapsed[bone['name']] = name
    return mapping, collapsed


def prepare(source, target, donor, *, flip_v=True, max_influences=4, max_palette=8):
    if not 1 <= max_influences <= max_palette <= 8:
        raise FormatError('Invalid PSP influence/palette budget')
    source_names = {b['name']: b['index'] for b in source['bones']}
    target_names = {b['name']: b['index'] for b in target['bones']}
    names = [n for n in LANDMARKS if n in source_names and n in target_names]
    sm, tm = bone_matrices(source), bone_matrices(target)
    src = np.array([sm[source_names[n]][:3, 3] for n in names])
    dst = np.array([tm[target_names[n]][:3, 3] for n in names])
    scale, rotation, translation = similarity_fit(src, dst)
    landmark_errors = np.linalg.norm(scale * src @ rotation.T + translation - dst, axis=1)
    donor_surface, target_surface = Surface(donor), Surface(target)
    mapping, collapsed = donor_bone_map(donor, target)
    aligned = copy.deepcopy(source)
    vertices = {}
    cache = {}
    donor_distances, initial_pruning = [], []
    for mesh in aligned['meshes']:
        for i, vertex in enumerate(mesh['vertices']):
            position = scale * rotation @ np.asarray(vertex['position']) + translation
            vertex['position'] = position.tolist()
            vertex['normal'] = (rotation @ np.asarray(vertex['normal'])).tolist()
            if flip_v:
                vertex['uv'] = [vertex['uv'][0], 1 - vertex['uv'][1]]
            # Identical seam positions receive identical transferred weights.
            key = tuple(position)
            if key not in cache:
                index, bary, distance = donor_surface.nearest(position)
                dm, triangle = donor_surface.corners[index]
                dense = {}
                for coefficient, vi in zip(bary, triangle):
                    for bone, weight in zip(dm['bone_palette'], dm['vertices'][vi]['weights']):
                        if bone not in mapping:
                            raise FormatError('Unresolved donor bone palette')
                        mapped = mapping[bone]
                        dense[mapped] = dense.get(mapped, 0) + float(coefficient * weight)
                dense = {b: w for b, w in dense.items() if w > 1e-7}
                total = sum(dense.values())
                if total <= 0:
                    raise FormatError('Weight donor produced an unweighted vertex')
                dense = {b: w / total for b, w in dense.items()}
                selected = dict(sorted(dense.items(), key=lambda x: -x[1])[:max_influences])
                kept = sum(selected.values())
                initial_pruning.append(1 - kept)
                cache[key] = {b: w / kept for b, w in selected.items()}
                donor_distances.append(distance)
            vertices[(mesh['index'], i)] = {'vertex': vertex, 'key': key}

    faces = []
    for mesh in aligned['meshes']:
        for material in mesh['materials']:
            for triangle in material['triangles']:
                ids = [(mesh['index'], i) for i in triangle]
                centroid = np.mean([vertices[v]['vertex']['position'] for v in ids], axis=0)
                nearest, _, _ = target_surface.nearest(centroid)
                faces.append({'vertices': ids, 'part': target_surface.owners[nearest],
                              'texture': material['texture_id']})

    # Make each face fit the observed <=8 palette slots, adjusting shared
    # seam weights together. Report every adjustment; never silently drop faces.
    palette_pruning = []
    for face in faces:
        keys = {vertices[v]['key'] for v in face['vertices']}
        while len(set().union(*(cache[k].keys() for k in keys))) > max_palette:
            candidates = [(w, k, b) for k in keys for b, w in cache[k].items() if len(cache[k]) > 1]
            if not candidates:
                raise FormatError('Cannot fit triangle into PSP bone palette')
            weight, key, bone = min(candidates, key=lambda x: (x[0], x[2]))
            del cache[key][bone]
            total = sum(cache[key].values())
            cache[key] = {b: w / total for b, w in cache[key].items()}
            palette_pruning.append(weight)

    buckets = {}
    for face in faces:
        support = set().union(*(cache[vertices[v]['key']].keys() for v in face['vertices']))
        bins = buckets.setdefault(face['part'], [])
        candidates = [b for b in bins if len(b['palette'] | support) <= max_palette and len(b['faces']) < 1000]
        if candidates:
            bucket = min(candidates, key=lambda b: len(b['palette'] | support))
        else:
            bucket = {'palette': set(), 'faces': []}
            bins.append(bucket)
        bucket['palette'].update(support)
        bucket['faces'].append(face)

    meshes = []
    for part, bins in sorted(buckets.items()):
        for ci, bucket in enumerate(bins):
            palette = sorted(bucket['palette'])
            remap, output_vertices, materials = {}, [], {}
            for face in bucket['faces']:
                triangle = []
                for original in face['vertices']:
                    if original not in remap:
                        record = vertices[original]
                        vertex = copy.deepcopy(record['vertex'])
                        vertex['weights'] = [cache[record['key']].get(b, 0) for b in palette]
                        vertex['source_mesh_index'] = original[0]
                        remap[original] = len(output_vertices)
                        output_vertices.append(vertex)
                    triangle.append(remap[original])
                materials.setdefault(face['texture'], []).append(triangle)
            meshes.append({'index': len(meshes), 'target_part': part, 'part_chunk': ci,
                           'bone_palette': palette, 'vertices': output_vertices,
                           'materials': [{'texture_id': tid, 'triangles': tris, 'strips': stripify(tris)}
                                         for tid, tris in sorted(materials.items())]})
    result = {'geometry_decoded': True, 'stage': 'prepared_for_review',
              'model_name': target['model_name'], 'bones': copy.deepcopy(target['bones']),
              'bone_count': target['bone_count'], 'textures': source['textures'],
              'texture_count': source['texture_count'], 'meshes': meshes,
              'mesh_count': len(meshes), 'vertex_count': sum(len(m['vertices']) for m in meshes),
              'triangle_count': sum(len(mat['triangles']) for m in meshes for mat in m['materials']),
              'uv_v_flipped': flip_v}
    if result['triangle_count'] != source['triangle_count']:
        raise FormatError('Source triangles were lost during sectioning')
    report = {'profile': 'HCTP PS2 -> SVR 2007 PSP experimental',
              'alignment': {'scale': scale, 'rotation': rotation.tolist(), 'translation': translation.tolist(),
                            'landmark_errors': dict(zip(names, landmark_errors.tolist())),
                            'landmark_rms': float(np.sqrt(np.mean(landmark_errors ** 2)))},
              'donor_bones_collapsed_to_target_ancestors': collapsed,
              'weight_transfer': {'method': 'nearest surface with barycentric interpolation',
                                  'donor_distance_p95': float(np.percentile(donor_distances, 95)),
                                  'donor_distance_max': max(donor_distances),
                                  f'max_weight_mass_removed_for_top{max_influences}': max(initial_pruning),
                                  'face_palette_adjustments': len(palette_pruning),
                                  'max_face_palette_weight_removed': max(palette_pruning, default=0)},
              'source_triangles': source['triangle_count'], 'output_triangles': result['triangle_count'],
              'output_meshes': len(meshes), 'target_parts_used': sorted(buckets),
              'target_parts_without_source_faces': sorted(set(m['index'] for m in target['meshes']) - set(buckets)),
              'max_bones_per_mesh': max(len(m['bone_palette']) for m in meshes),
              'max_influences_per_vertex': max_influences,
              'max_triangles_per_mesh': max(sum(len(mat['triangles']) for mat in m['materials']) for m in meshes),
              'limitations': ['Triangle-based section boundaries need joint review',
                              'UV flip follows tutorial and needs textured verification',
                              'Prepared meshes alone do not establish native serialization or game compatibility']}
    result['preparation_report'] = report
    return result, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('reference', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--keep-v', action='store_true', help='Keep native UV V instead of tutorial flip')
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(f'Refusing to overwrite {args.output}')
        model, report = prepare(load_hctp(args.source), load_model(args.target, psp_geometry=True),
                                load_model(args.reference, psp_geometry=True), flip_v=not args.keep_v)
        args.output.mkdir(parents=True, exist_ok=False)
        for name, value in [('prepared.json', model), ('report.json', report)]:
            (args.output / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        write_obj(model, args.output / 'prepared.obj')
        print(json.dumps(report, indent=2, allow_nan=False))
    except (OSError, FormatError) as exc:
        print(f'Preparation failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

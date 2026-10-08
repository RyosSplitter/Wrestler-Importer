"""Skeleton-weight regions, smooth normals, and PSP palette packing."""
from collections import defaultdict
import copy
import math

try:
    from .stripify import stripify
except ImportError:
    from stripify import stripify

RATIOS = {'Head': .8, 'Torso': .5, 'Arms': .35, 'Legs': .35}
DETAIL_TEXTURES = {'rvd_eye', 'bn_ha', 'bn_ha2', 'ts_naka'}
ANCHORS = {'kubi': 'Head', 'atama': 'Head', 'r_sakotsu': 'Arms', 'l_sakotsu': 'Arms',
           'r_momo': 'Legs', 'l_momo': 'Legs'}


def bone_regions(bones):
    result = {}
    for bone in bones:
        current, seen = bone['index'], set()
        region = 'Torso'
        while current != -1:
            if current in seen:
                raise ValueError('Cycle in region skeleton')
            seen.add(current)
            name = bones[current]['name']
            if name in ANCHORS:
                region = ANCHORS[name]
                break
            current = bones[current]['parent']
        result[bone['index']] = region
    return result


def weight_regions(weights, regions):
    scores = dict.fromkeys(RATIOS, 0.)
    for index, weight in enumerate(weights):
        scores[regions[index]] += weight
    if sum(scores.values()) <= 0:
        raise ValueError('Cannot classify an unweighted vertex')
    return scores


def make_regions(prepared):
    result = copy.deepcopy(prepared)
    regions = bone_regions(prepared['bones'])
    buckets = {name: {'vertices': [], 'map': {}, 'materials': defaultdict(list)} for name in RATIOS}
    for mesh in prepared['meshes']:
        dense = []
        for v in mesh['vertices']:
            w = [0.] * prepared['bone_count']
            for b, value in zip(mesh['bone_palette'], v['weights']):
                w[b] = value
            dense.append(w)
        for material in mesh['materials']:
            tid = material['texture_id']
            for tri in material['triangles']:
                scores = dict.fromkeys(RATIOS, 0.)
                for vi in tri:
                    for name, value in weight_regions(dense[vi], regions).items():
                        scores[name] += value
                region = max(scores, key=scores.get)
                bucket, indices = buckets[region], []
                for vi in tri:
                    v = copy.deepcopy(mesh['vertices'][vi])
                    v['weights'] = dense[vi]
                    v['region_strength'] = weight_regions(dense[vi], regions)[region]
                    key = tuple(tuple(v[k]) for k in ('position', 'uv', 'color', 'weights'))
                    if key not in bucket['map']:
                        bucket['map'][key] = len(bucket['vertices'])
                        bucket['vertices'].append(v)
                    indices.append(bucket['map'][key])
                bucket['materials'][tid].append(indices)
    result['meshes'] = []
    for name, bucket in buckets.items():
        if bucket['vertices']:
            result['meshes'].append({'index': len(result['meshes']), 'region': name,
                                    'bone_palette': list(range(prepared['bone_count'])),
                                    'vertices': bucket['vertices'],
                                    'materials': [{'texture_id': tid, 'triangles': faces}
                                                  for tid, faces in sorted(bucket['materials'].items())]})
    result['region_bone_map'] = regions
    result['triangle_count'] = sum(len(m['triangles']) for x in result['meshes'] for m in x['materials'])
    if result['triangle_count'] != prepared['triangle_count']:
        raise ValueError('Region classification lost source faces')
    return result


def smooth_normals(model):
    accum = defaultdict(lambda: [0., 0., 0.])
    for mesh in model['meshes']:
        for mat in mesh['materials']:
            for tri in mat['triangles']:
                a, b, c = [mesh['vertices'][i]['position'] for i in tri]
                u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
                normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
                for index in tri:
                    vertex = mesh['vertices'][index]
                    key = (tuple(vertex['position']), vertex.get('smoothing_group', 0))
                    for axis in range(3):
                        accum[key][axis] += normal[axis]
    for mesh in model['meshes']:
        for vertex in mesh['vertices']:
            n = accum[(tuple(vertex['position']), vertex.get('smoothing_group', 0))]
            length = math.sqrt(sum(x*x for x in n))
            if length < 1e-10:
                raise ValueError('Degenerate smoothing normal')
            vertex['normal'] = [x/length for x in n]


def quantize_weights(weights, denominator=32768):
    """PSP GE weights are fixed point /128 (U8) or /32768 (U16).

    Largest remainders keep the sum exact and bound error by one integer unit.
    See PPSSPP GPU/Common/VertexDecoderCommon.cpp, Step_WeightsU16Skin.
    """
    if not weights or len(weights) > 8 or any(not math.isfinite(w) or w < 0 for w in weights):
        raise ValueError('Invalid PSP weights')
    total = sum(weights)
    if total <= 0:
        raise ValueError('Unweighted vertex')
    if denominator not in (128, 32768):
        raise ValueError('Unsupported PSP weight denominator')
    scaled = [denominator*w/total for w in weights]
    integers = [math.floor(w) for w in scaled]
    remainder = denominator-sum(integers)
    order = sorted(range(len(weights)), key=lambda i: (-(scaled[i]-integers[i]), i))
    for i in order[:remainder]:
        integers[i] += 1
    return [w/denominator for w in integers]


def pack_regions(model, max_influences=4, weight_encoding='psp_u16'):
    if weight_encoding not in ('float', 'psp_u8', 'psp_u16'):
        raise ValueError('Unsupported PSP weight encoding')
    result = copy.deepcopy(model)
    cache, source_weights, removed = {}, {}, []
    for mesh in model['meshes']:
        for v in mesh['vertices']:
            key = tuple(v['position'])
            if key in cache:
                continue
            source = {b: w for b, w in enumerate(v['weights']) if w > 1e-7}
            source_weights[key] = source
            selected = dict(sorted(source.items(), key=lambda t: (-t[1], t[0]))[:max_influences])
            total = sum(selected.values())
            if total <= 0:
                raise ValueError('Unweighted decimated vertex')
            removed.append(max(0., 1-total))
            cache[key] = {b: w/total for b, w in selected.items()}
    faces = []
    for mesh in model['meshes']:
        for material in mesh['materials']:
            for tri in material['triangles']:
                keys = [tuple(mesh['vertices'][i]['position']) for i in tri]
                while len(set().union(*(cache[k] for k in keys))) > 8:
                    options = [(w, key, b) for key in keys for b, w in cache[key].items() if len(cache[key]) > 1]
                    _, key, bone = min(options)
                    del cache[key][bone]
                    total = sum(cache[key].values())
                    cache[key] = {b: w/total for b, w in cache[key].items()}
                faces.append((mesh, material['texture_id'], tri))
    quantization_error = 0.
    if weight_encoding != 'float':
        for key, weights in cache.items():
            bones = sorted(weights)
            before = [weights[b] for b in bones]
            after = quantize_weights(before, 128 if weight_encoding == 'psp_u8' else 32768)
            quantization_error = max(quantization_error, max(abs(a-b) for a, b in zip(before, after)))
            cache[key] = {b: w for b, w in zip(bones, after) if w > 0}
    bins = defaultdict(list)
    for mesh, tid, tri in faces:
        support = set().union(*(cache[tuple(mesh['vertices'][i]['position'])] for i in tri))
        corners = {tuple(tuple(mesh['vertices'][i][k]) for k in ('position', 'normal', 'uv', 'color')) for i in tri}
        candidates = [b for b in bins[mesh['region']] if len(b['palette'] | support) <= 8]
        def stride(count):
            width = {'float': 4, 'psp_u8': 1, 'psp_u16': 2}[weight_encoding]
            return 36 + 4*((width*count+3)//4)
        def cost(bucket):
            palette = bucket['palette'] | support
            return ((len(corners - bucket['corners'])) * stride(len(palette))
                    + len(bucket['corners']) * (stride(len(palette)) - stride(len(bucket['palette'])))
                    + (160 if tid not in bucket['textures'] else 0))
        new_cost = 160 + 160 + len(corners) * stride(len(support))
        if candidates and min(map(cost, candidates)) <= new_cost:
            bucket = min(candidates, key=cost)
        else:
            bucket = {'palette': set(), 'faces': [], 'corners': set(), 'textures': set()}
            bins[mesh['region']].append(bucket)
        bucket['palette'].update(support)
        bucket['corners'].update(corners)
        bucket['textures'].add(tid)
        bucket['faces'].append((mesh, tid, tri))
    meshes = []
    for region, groups in bins.items():
        for chunk, bucket in enumerate(groups):
            palette = sorted(bucket['palette'])
            vertices, mapping, materials = [], {}, defaultdict(list)
            for source, tid, tri in bucket['faces']:
                face = []
                for i in tri:
                    v = copy.deepcopy(source['vertices'][i])
                    v['weights'] = [cache[tuple(v['position'])].get(b, 0.) for b in palette]
                    key = tuple(tuple(v[k]) for k in ('position', 'normal', 'uv', 'color', 'weights'))
                    if key not in mapping:
                        mapping[key] = len(vertices)
                        vertices.append(v)
                    face.append(mapping[key])
                materials[tid].append(face)
            meshes.append({'index': len(meshes), 'region': region,
                           'target_part': {'Head': 0, 'Torso': 8, 'Arms': 9, 'Legs': 19}[region],
                           'part_chunk': chunk, 'bone_palette': palette, 'vertices': vertices,
                           'materials': [{'texture_id': t, 'triangles': faces, 'strips': stripify(faces)}
                                         for t, faces in sorted(materials.items())]})
    result.update(meshes=meshes, mesh_count=len(meshes), vertex_count=sum(len(x['vertices']) for x in meshes),
                  triangle_count=sum(len(m['triangles']) for x in meshes for m in x['materials']))
    result['weight_encoding'] = weight_encoding
    report = result['preparation_report']
    all_parts = set(report.get('target_parts_used', [])) | set(report.get('target_parts_without_source_faces', []))
    used_parts = sorted({mesh['target_part'] for mesh in meshes})
    report.update(output_triangles=result['triangle_count'], output_meshes=len(meshes),
                  target_parts_used=used_parts, target_parts_without_source_faces=sorted(all_parts-set(used_parts)),
                  max_bones_per_mesh=max(len(x['bone_palette']) for x in meshes),
                  max_influences_per_vertex=max(sum(w>0 for w in v['weights']) for x in meshes for v in x['vertices']),
                  max_triangles_per_mesh=max(sum(len(m['triangles']) for m in x['materials']) for x in meshes))
    result['preparation_report']['region_weight_packing'] = {
        'max_influences': max_influences, 'max_top_influence_mass_removed': max(removed, default=0.),
        'max_mass_removed': max((max(0., 1-sum(source_weights[k].get(b, 0.) for b in weights))
                                 for k, weights in cache.items()), default=0.),
        'weight_encoding': weight_encoding, 'max_quantization_error': quantization_error,
        'weight_sum': 1.,
        'method': 'Interpolate transferred PSP bone groups through decimation; seam weights shared'}
    return result

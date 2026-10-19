"""Reference-surface constrained decimation refinement, isolated experiment.

Only free points are projected to their original topology-domain/material surface.
No anatomical direction or wrestler-specific displacement is prescribed. Source
conflicts, multi-material seams, weights, UVs, connectivity and rig stay unchanged.
"""
import copy
from collections import defaultdict
import struct

import numpy as np

from tools.prepare_model import Surface
from tools.vertex_identity import annotate


def refine(source, reduced):
    source = annotate(copy.deepcopy(source)); result = copy.deepcopy(reduced)
    groups = defaultdict(list)
    for mesh in source['meshes']:
        for mat in mesh['materials']:
            for tri in mat['triangles']:
                domains = {tuple(mesh['vertices'][i]['skin_domain']) for i in tri}
                if len(domains) != 1:
                    raise ValueError('Source triangle crosses independent topology domains')
                groups[next(iter(domains)), mat['texture_id']].append((mesh, tri))
    surfaces = {}
    for key, rows in groups.items():
        vertices = []; faces = []
        for mesh, tri in rows:
            offset = len(vertices); vertices.extend(mesh['vertices'][i] for i in tri); faces.append([offset, offset+1, offset+2])
        surfaces[key] = Surface(dict(meshes=[dict(index=0, vertices=vertices, materials=[dict(triangles=faces)])]))
    height = np.ptp([v['position'][1] for m in result['meshes'] for v in m['vertices']])
    copies = defaultdict(list)
    for mesh in result['meshes']:
        uses = defaultdict(set)
        for mat in mesh['materials']:
            for i in {i for tri in mat['triangles'] for i in tri}:
                uses[i].add(mat['texture_id'])
        for i, v in enumerate(mesh['vertices']):
            copies[struct.pack('<3f', *v['position']), tuple(v['skin_domain'])].append((v, uses[i]))
    moved = []; held = 0; skipped = 0; unproven = 0
    for (_, domain), records in copies.items():
        tids = set().union(*(u for v, u in records))
        if len(tids) != 1 or any(v.get('skin_locked') for v, u in records):
            held += len(records); continue
        surface = surfaces.get((domain, next(iter(tids))))
        if surface is None:
            # Blender's integer provenance can inherit an adjacent material's
            # source point on collapse. It is not verified correspondence.
            # Hold such a point rather than guessing a different source layer.
            unproven += len(records); continue
        vertex = records[0][0]; p = np.array(vertex['position'])
        index, bary, distance = surface.nearest(p)
        if distance > .02 * height:
            skipped += len(records); continue
        q = bary @ surface.triangles[index]
        if np.linalg.norm(q-p) <= height*1e-7:
            continue
        q = np.asarray(q, dtype=np.float32).astype(float).tolist()
        for v, uses in records:
            v['position'] = q
        moved.append(dict(records=len(records), displacement=distance, domain=list(domain), texture_id=next(iter(tids))))
    # Projecting points can change the face plane. Recompute normal directions;
    # this affects shading, never source weights or UVs.
    normals = defaultdict(lambda: np.zeros(3))
    def normal_key(v):
        return tuple(v['skin_domain']), tuple(v['position']), v.get('smoothing_group', 0)
    for mesh in result['meshes']:
        for mat in mesh['materials']:
            for tri in mat['triangles']:
                a, b, c = [np.array(mesh['vertices'][i]['position']) for i in tri]
                normal = np.cross(b-a, c-a)
                for i in tri:
                    normals[normal_key(mesh['vertices'][i])] += normal
    for mesh in result['meshes']:
        for v in mesh['vertices']:
            normal = normals[normal_key(v)]; length = np.linalg.norm(normal)
            if length < 1e-12:
                raise ValueError('Refinement produced a degenerate source-domain normal')
            v['normal'] = (normal/length).tolist()
    # Connectivity and every vertex's non-geometric attributes must be exact.
    for a, b in zip(reduced['meshes'], result['meshes']):
        if a['materials'] != b['materials'] or a['bone_palette'] != b['bone_palette']:
            raise ValueError('Refinement changed topology/materials/palette')
        for x, y in zip(a['vertices'], b['vertices']):
            if any(x[k] != y[k] for k in ('weights', 'uv', 'color')):
                raise ValueError('Refinement changed non-geometric attributes')
    report = dict(method='Nearest original surface constrained by verified source skin domain and atlas material; shared points updated together',
        moved_groups=len(moved), moved_records=sum(x['records'] for x in moved),
        held_conflict_or_material_seam_records=held, skipped_beyond_local_bound_records=skipped,
        held_unproven_source_domain_material_records=unproven,
        maximum_displacement=max((x['displacement'] for x in moved), default=0.),
        displacement_bound_height=.02, topology_uvs_materials_weights_rig_exact=True,
        report_scope='Candidate experiment; retain only after regional/static/posed regression review', movements=moved)
    result['surface_refinement_report'] = report
    return result, report

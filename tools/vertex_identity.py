"""Source skinning provenance and conservative geometric point identity.

Position is not vertex identity. Disconnected source components and differing
effective bone influences must not share a Blender point or a packing cache.
UV/color/normal records remain corner attributes, not averaged point attributes.
This module uses only the standard library so the Blender worker can import it.
"""
from collections import defaultdict
import math
import struct


def position_key(vertex):
    return struct.pack('<3f', *vertex['position'])


def influences(vertex, palette):
    weights = vertex['weights']
    if len(weights) != len(palette) or any(not math.isfinite(w) or w < 0 for w in weights):
        raise ValueError('Invalid skinning record')
    total = sum(weights)
    if total <= 0:
        raise ValueError('Unweighted skinning record')
    # Global bone IDs, not local palette offsets; duplicates are not valid.
    if len(set(palette)) != len(palette):
        raise ValueError('Duplicate bone in skinning palette')
    return tuple((b, w / total) for b, w in sorted(zip(palette, weights)) if w > 0)


def annotate(model):
    """Add provenance once, using actual source index connectivity (no weld)."""
    if all('skin_id' in v for m in model['meshes'] for v in m['vertices']):
        return model
    if any('skin_id' in v for m in model['meshes'] for v in m['vertices']):
        raise ValueError('Incomplete source skinning provenance')
    groups = defaultdict(set)
    for mesh in model['meshes']:
        for v in mesh['vertices']:
            groups[position_key(v)].add(influences(v, mesh['bone_palette']))
    conflicts = {p for p, weights in groups.items() if len(weights) > 1}
    components = {}; edges = defaultdict(list)
    for mesh in model['meshes']:
        vertices = mesh['vertices']; parent = list(range(len(vertices)))
        def root(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]; i = parent[i]
            return i
        for mat in mesh['materials']:
            for tri in mat['triangles']:
                if any(i < 0 or i >= len(vertices) for i in tri):
                    raise ValueError('Invalid source topology index')
                for i in tri[1:]:
                    a, b = root(tri[0]), root(i)
                    parent[max(a,b)] = min(a,b)
        components[mesh['index']] = [root(i) for i in range(len(vertices))]
        for mat in mesh['materials']:
            for tri in mat['triangles']:
                attrs=[]
                for i in tri:
                    v=vertices[i]
                    weights=b''.join(struct.pack('<If',b,w) for b,w in influences(v,mesh['bone_palette']))
                    # Geometric point identity is separate from rendering
                    # corner identity: Blender stores UVs/colors per loop.
                    attrs.append((position_key(v),weights))
                for i in range(3):
                    a,b=attrs[i],attrs[(i+1)%3]
                    if a==b:continue
                    edge=(repr(mat.get('control')),repr(mat.get('flags')),tuple(sorted((a,b))))
                    edges[edge].append(((mesh['index'],root(tri[i])),a,b,tuple(sorted(attrs))))
    # Storage chunks can describe one continuous surface. Join their domains
    # only across a verified two-face manifold edge, with opposite orientation
    # and byte-identical endpoint positions/influences. UV/color/normal corners
    # are retained separately, not welded. Coincident overlays and nonmanifold
    # edges are not evidence of geometric compatibility.
    parents={ (mi,c):(mi,c) for mi,cs in components.items() for c in cs }
    def domain_root(node):
        while parents[node]!=node:
            parents[node]=parents[parents[node]];node=parents[node]
        return node
    joined=0
    for rows in edges.values():
        if len(rows)!=2:continue
        x,y=rows
        if x[1]!=y[2] or x[2]!=y[1] or x[3]==y[3]:continue
        a,b=domain_root(x[0]),domain_root(y[0])
        if a!=b:parents[max(a,b)]=min(a,b);joined+=1
    ids={}
    for mesh in model['meshes']:
        vertices=mesh['vertices']
        for i, v in enumerate(vertices):
            domain = domain_root((mesh['index'],components[mesh['index']][i]))
            key = (domain, position_key(v), influences(v, mesh['bone_palette']))
            ids.setdefault(key, len(ids))
            v['skin_domain'] = list(domain)
            v['skin_id'] = [domain[0], ids[key]]
            v['source_records'] = [[mesh['index'], i]]
            v['skin_locked'] = position_key(v) in conflicts
            if v['skin_locked']:
                v['skin_bind_position'] = list(v['position'])
                v['skin_expected'] = [list(x) for x in influences(v, mesh['bone_palette'])]
    model['source_skinning_identity'] = dict(
        conflicting_positions=len(conflicts),
        proven_manifold_component_joins=joined,
        policy='Source index-connected components; cross-chunk joins only through compatible manifold edges; distinct influences/corners retained')
    return model


def point_key(vertex, palette, mesh_index):
    """Only compatible points in the same proven topology domain may weld."""
    return (tuple(vertex.get('skin_domain', [mesh_index])), position_key(vertex),
            influences(vertex, palette))


def weight_key(vertex, palette, mesh_index):
    # Provenance identifies intended copies independently of their current
    # weights, allowing a changed copy to trigger the packing consistency check.
    identity = tuple(vertex['skin_id']) if 'skin_id' in vertex else point_key(vertex, palette, mesh_index)
    return (identity, position_key(vertex))


def validate_locked(vertex, palette, tolerance=2e-6):
    if not vertex.get('skin_locked'):
        return
    if position_key(vertex) != struct.pack('<3f', *vertex['skin_bind_position']):
        raise ValueError('Protected source skinning point moved')
    actual = dict(influences(vertex, palette)); expected = dict(vertex['skin_expected'])
    if max((abs(actual.get(b,0.) - expected.get(b,0.)) for b in set(actual)|set(expected)), default=0.) > tolerance:
        raise ValueError('Protected source skinning weights changed')


def protected_face_positions(model):
    """Attribute-precision fitting must not change any verified protected face."""
    return {tuple(mesh['vertices'][i]['position']) for mesh in model['meshes'] for mat in mesh['materials']
            for tri in mat['triangles'] if any(mesh['vertices'][i].get('skin_locked') for i in tri) for i in tri}

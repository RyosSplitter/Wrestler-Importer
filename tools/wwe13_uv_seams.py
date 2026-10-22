"""Source UV contact locks; optional region scope for Wii clothing protection."""
from collections import defaultdict
from tools.vertex_identity import position_key


def seam_positions(model, regions=None):
    """Geometric contacts with different texture corners must retain support.

    This does not weld anything or assert that coincident records share weights.
    With a region scope, inspect only those existing reducer regions. This
    retains clothing support without adding locks inside hands or faces.
    Unreferenced vertices do not introduce seam locks.
    """
    corners = defaultdict(set)
    positions = {}
    for mesh in model['meshes']:
        if regions is not None and mesh.get('region')not in regions:continue
        for material in mesh['materials']:
            for i in {i for tri in material['triangles'] for i in tri}:
                v = mesh['vertices'][i]; key = position_key(v)
                corners[key].add((material['texture_id'], *(round(x, 7) for x in v['uv'])))
                positions[key] = tuple(v['position'])
    return {positions[key] for key, values in corners.items() if len(values) > 1}

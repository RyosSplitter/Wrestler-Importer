"""Experimental UV-island atlas adapter; no vertex motion or triangle clipping.

All crops use original pixel samples (including repeat wrapping). Padding is
additional source context, not image upscaling. Conversion remains opt-in CLI
research, never a production adapter registration.
"""
from collections import defaultdict
import copy

import numpy as np

from desktop.texture_optimizer.candidates import OBSERVED_DIMENSIONS, OBSERVED_T8_DIMENSIONS


def bilinear(image, uv):
    """Normalized, repeating, texel-center sampling used for equivalence QA."""
    h, w = image.shape[:2]
    xy = np.asarray(uv, dtype=float)*[w, h]-.5
    low = np.floor(xy).astype(np.int64)
    f = xy-low
    x, y = low[..., 0], low[..., 1]
    a = image[y % h, x % w].astype(float)
    b = image[y % h, (x+1) % w].astype(float)
    c = image[(y+1) % h, x % w].astype(float)
    d = image[(y+1) % h, (x+1) % w].astype(float)
    return ((a*(1-f[..., 0, None])+b*f[..., 0, None])*(1-f[..., 1, None])
            +(c*(1-f[..., 0, None])+d*f[..., 0, None])*f[..., 1, None])


def partition(model, rgba):
    """Join triangles only across exact, nondegenerate shared UV edges.

    No assumptions about texture names, equal atlas cells or source mesh counts.
    Prefer an exact observed T8 rectangle; wider source patches can use an
    observed T4-sized source canvas and require later color/resolution fitting.
    A full source axis may repeat without bounding the UV interval to [0,1].
    Unsupported
    giant/wrapped islands fail explicitly instead of clipping their geometry.
    """
    if model['texture_count'] != 1 or rgba.dtype != np.uint8 or rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError('Atlas trial requires one decoded RGBA8 source image')
    h, w = rgba.shape[:2]
    faces = [(mi, ai, tri) for mi, mesh in enumerate(model['meshes'])
             for ai, mat in enumerate(mesh['materials']) for tri in mat['triangles']]
    if not faces:
        raise ValueError('Atlas trial requires triangles')
    parent = list(range(len(faces)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    edges = {}
    for i, (mi, ai, tri) in enumerate(faces):
        mesh = model['meshes'][mi]
        if mesh['materials'][ai]['texture_id'] != 0:
            raise ValueError('Unexpected source texture slot')
        uv = [tuple(mesh['vertices'][j]['uv']) for j in tri]
        if not np.isfinite(uv).all():
            raise ValueError('Nonfinite atlas UV')
        for j in range(3):
            if uv[j] == uv[(j+1) % 3]:
                continue  # A zero-length UV edge does not join islands.
            key = tuple(sorted((uv[j], uv[(j+1) % 3])))
            if key in edges:
                a, b = root(i), root(edges[key])
                parent[max(a, b)] = min(a, b)
            else:
                edges[key] = i
    islands = defaultdict(list)
    for i in range(len(faces)):
        islands[root(i)].append(i)
    output = copy.deepcopy(model)
    for mesh in output['meshes']:
        mesh['vertices'] = []
        mesh['materials'] = []
    crops, mappings = [], []
    vertices, materials = {}, {}
    checks = []
    for tid, indices in enumerate(islands.values()):
        uv = np.array([model['meshes'][faces[i][0]]['vertices'][j]['uv']
                       for i in indices for j in faces[i][2]])
        xy = uv*[w, h]-.5
        low = np.floor(xy.min(0)).astype(int)
        high = np.ceil(xy.max(0)).astype(int)+1
        extent = high-low
        def fits(size):
            a,b=size
            return (a >= extent[0] or a == w) and (b >= extent[1] or b == h) and a <= w and b <= h
        legal = [size for size in OBSERVED_T8_DIMENSIONS if fits(size)]
        if not legal:
            legal = [size for size in OBSERVED_DIMENSIONS if fits(size)]
        if not legal:
            raise ValueError(f'UV island {tid} footprint {extent.tolist()} needs an unvalidated crop layout; export withheld')
        cw, ch = min(legal, key=lambda x: (x[0]*x[1], x))
        xs, ys = (low[0]+np.arange(cw)) % w, (low[1]+np.arange(ch)) % h
        crop = rgba[np.ix_(ys, xs)].copy()
        crops.append(crop)
        record = dict(texture_id=tid, name=f'chart_{tid:02d}', triangles=len(indices),
            source_uv_min=uv.min(0).tolist(), source_uv_max=uv.max(0).tolist(),
            source_texel_origin=low.tolist(), sampled_footprint=extent.tolist(),
            dimensions=[cw, ch], resampling=False, pixels_from_source_exact=True,
            full_size_native_bits=[4,8] if (cw,ch) in OBSERVED_T8_DIMENSIONS else [4],
            padding='Original atlas context under repeat sampling; not an upscale')
        mappings.append(record)
        for i in indices:
            mi, ai, tri = faces[i]
            src, dst = model['meshes'][mi], output['meshes'][mi]
            key = mi, ai, tid
            if key not in materials:
                mat = copy.deepcopy(src['materials'][ai])
                mat.update(texture_id=tid, triangles=[], strips=[])
                materials[key] = mat
                dst['materials'].append(mat)
            face = []
            original_uvs, new_uvs = [], []
            for j in tri:
                vkey = mi, j, tid
                if vkey not in vertices:
                    vertex = copy.deepcopy(src['vertices'][j])
                    vertex['atlas_original_uv'] = list(vertex['uv'])
                    vertex['atlas_chart'] = tid
                    vertex['uv'] = ((np.array(vertex['uv'])*[w, h]-low)/[cw, ch]).tolist()
                    vertices[vkey] = len(dst['vertices'])
                    dst['vertices'].append(vertex)
                face.append(vertices[vkey])
                original_uvs.append(src['vertices'][j]['uv'])
                new_uvs.append(dst['vertices'][vertices[vkey]]['uv'])
            materials[key]['triangles'].append(face)
            # Corners, edges and interior samples: bilinear interpolation, not
            # just a favorable nearest-sample screenshot or same-index test.
            bary = np.array([[1,0,0], [0,1,0], [0,0,1], [.5,.5,0],
                [.5,0,.5], [0,.5,.5], [1/3]*3, [.2,.3,.5], [.7,.1,.2]])
            before = bilinear(rgba, bary@np.asarray(original_uvs))
            after = bilinear(crop, bary@np.asarray(new_uvs))
            checks.append(float(np.max(np.abs(before-after))))
    if max(checks, default=0) > 1e-7:
        raise ValueError('Atlas partition changed sampled RGBA')
    output.update(textures=[m['name'] for m in mappings], texture_count=len(mappings),
        vertex_count=sum(len(m['vertices']) for m in output['meshes']))
    # Preserve source position-record count; only used corner records are emitted.
    report = dict(islands=mappings, original_triangles=len(faces),
        output_triangles=sum(len(a['triangles']) for m in output['meshes'] for a in m['materials']),
        maximum_sample_rgba_error=max(checks, default=0), samples_per_triangle=9,
        vertices_moved=False, triangle_clipping=False, source_images_resampled=False,
        source_width=w, source_height=h, shader_equivalence='Not established; UV/sample equivalence only')
    return output, crops, report

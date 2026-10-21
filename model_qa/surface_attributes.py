"""Topology-independent UV/texture placement diagnostics in a shared bind pose.

Both surfaces use the *same original images*, isolating geometry/UV changes
from quantization. Match only within the same atlas page. Closest surfaces at
overlapping cloth/skin layers remain ambiguous: review findings are not an
instruction to weld, move, or automatically repair vertices.
"""
import numpy as np
import trimesh
from .geometry import Geometry, Surface, geometry, distribution


def _uv(model):
    return np.asarray([v['uv'] for m in model['meshes'] for v in m['vertices']], dtype=float)


def _sample(image, uv):
    # Same repeat/nearest convention as the app's offline diagnostic renderer.
    h, w = image.shape[:2]
    xy = np.floor(uv * [w, h]).astype(np.int64)
    return image[xy[:, 1] % h, xy[:, 0] % w].astype(float)


def compare(reference, candidate, images, *, samples=12000, seed=2718, rois=None):
    a, b = geometry(reference), geometry(candidate)
    if not set(b.face_textures) <= set(a.face_textures):
        raise ValueError('Candidate has atlas pages absent from the reference')
    if not set(a.face_textures) <= set(images):
        raise ValueError('Missing original atlas image')
    uv_a, uv_b = _uv(reference), _uv(candidate)
    if not np.isfinite(uv_a).all() or not np.isfinite(uv_b).all():
        raise ValueError('Nonfinite UV coordinate')
    points, ids, bary = Surface(b, a.height).sample(samples, seed)
    buv = np.einsum('ni,nij->nj', bary, uv_b[b.faces[ids]])
    distances = np.empty(samples); uv_error = np.empty(samples)
    color_squared = np.empty(samples); alpha_error = np.empty(samples)
    matched = np.empty_like(points); tables = {}
    names = np.asarray(b.face_textures)[ids]
    for name in sorted(set(names)):
        rows = np.flatnonzero(names == name)
        face_ids = np.flatnonzero(np.asarray(a.face_textures) == name)
        restricted = Geometry(a.vertices, a.faces[face_ids], a.weights, a.bone_names,
                              [name] * len(face_ids), a.vertex_records, a.model)
        closest, delta, local_ids = Surface(restricted, a.height).nearest(points[rows])
        source_faces = a.faces[face_ids[local_ids]]
        coeff = trimesh.triangles.points_to_barycentric(a.vertices[source_faces], closest)
        auv = np.einsum('ni,nij->nj', coeff, uv_a[source_faces])
        image = np.asarray(images[name]); size = [image.shape[1], image.shape[0]]
        rgb_a, rgb_b = _sample(image, auv), _sample(image, buv[rows])
        matched[rows] = closest; distances[rows] = delta
        uv_error[rows] = np.linalg.norm((auv - buv[rows]) * size, axis=1)
        color_squared[rows] = np.mean((rgb_a[:, :3] - rgb_b[:, :3]) ** 2, axis=1)
        alpha_error[rows] = np.abs(rgb_a[:, 3] - rgb_b[:, 3])

    def stats(mask):
        if not np.any(mask):
            return dict(samples=0, review=None)
        uv = distribution(uv_error[mask]); distance = distribution(distances[mask], a.height)
        # UV displacement is in original image texels, never body-height units.
        uv.pop('p95_height'); uv.pop('p99_height')
        return dict(samples=int(np.count_nonzero(mask)), surface_distance=distance,
                    source_texel_displacement=uv,
                    original_texture_placement_rgb_rmse_255=float(np.sqrt(color_squared[mask].mean())),
                    original_alpha_placement_mae_255=float(alpha_error[mask].mean()),
                    review=bool(uv['p95'] > 2 or distance['p95_height'] > .005))

    for name in sorted(set(names)):
        tables[name] = stats(names == name)
    return dict(overall=stats(np.ones(samples, bool)), textures=tables,
                regions={name: stats(roi.mask(matched)) for name, roi in (rois or {}).items()},
                source_images_used_on_both_models=True,
                comparison='Area-weighted candidate samples projected onto same-page reference triangles; no vertex-index correspondence',
                tolerances='Provisional review only: p95 > 2 original texels or surface distance > 0.5% reference height',
                limitations='No camera visibility weighting; overlapping same-page surfaces can be ambiguous. Analytical bind-space diagnostic, not in-game proof.')

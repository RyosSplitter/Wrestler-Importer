"""Read-only opacity-support QA for hair, masks and other cutout surfaces.

Global alpha MAE or total coverage can hide missing fine strands: a coarse
image can erase one strand while adding an equally sized opaque block nearby.
Report spatial recall, thin/edge recall and vanished components separately.
The cutoffs are diagnostic probes, not an emulation of the game's alpha test.
"""
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, label
from desktop.texture_optimizer.analysis import model_usage


def compare(source, candidate, uv_mask=None, *, thresholds=(64, 128, 192)):
    source = np.asarray(source); candidate = np.asarray(candidate)
    for image in (source, candidate):
        if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 4 or min(image.shape[:2]) < 1:
            raise ValueError('Nonempty uint8 RGBA images are required')
    mask = np.ones(source.shape[:2], bool) if uv_mask is None else np.asarray(uv_mask) > 0
    if mask.shape != source.shape[:2] or not mask.any():
        raise ValueError('Nonempty source-sized UV mask required')
    if not thresholds or any(type(t) is not int or not 1 <= t <= 255 for t in thresholds):
        raise ValueError('Alpha probe thresholds must be integer bytes in [1,255]')
    # A projection to the source grid for diagnosis, never an edited texture.
    resized = np.asarray(Image.fromarray(candidate).resize(
        (source.shape[1], source.shape[0]), Image.Resampling.NEAREST))
    a, b = source[:, :, 3], resized[:, :, 3]
    probes = {}
    for threshold in thresholds:
        original = a >= threshold; proposed = b >= threshold
        support = original & mask; emitted = proposed & mask
        thin = original & (distance_transform_edt(original) <= 1.5) & mask
        overlap = support & emitted; union = support | emitted
        components, count = label(original, structure=np.ones((3, 3), bool))
        sizes = np.bincount(components[mask], minlength=count + 1)
        retained = np.bincount(components[emitted & original], minlength=count + 1)
        meaningful = np.flatnonzero(sizes >= 4); meaningful = meaningful[meaningful != 0]
        vanished = meaningful[retained[meaningful] == 0]
        def fraction(n, d):
            return float(n / d) if d else None
        recall = fraction(overlap.sum(), support.sum())
        thin_recall = fraction((thin & emitted).sum(), thin.sum())
        probes[str(threshold)] = dict(
            source_visible_texels=int(support.sum()), candidate_visible_texels=int(emitted.sum()),
            support_recall=recall, support_precision=fraction(overlap.sum(), emitted.sum()),
            intersection_over_union=fraction(overlap.sum(), union.sum()),
            missing_source_texels=int((support & ~emitted).sum()),
            newly_opaque_texels=int((~support & emitted).sum()),
            source_thin_edge_texels=int(thin.sum()), thin_edge_support_recall=thin_recall,
            source_components_at_least_four_texels=len(meaningful), vanished_components=len(vanished),
            vanished_component_source_texels=int(sizes[vanished].sum()),
            review=bool((recall is not None and recall < .95) or
                        (thin_recall is not None and thin_recall < .85) or len(vanished)))
    exceeds_ceiling = bool(candidate.shape[1] > source.shape[1] or candidate.shape[0] > source.shape[0])
    return dict(source_dimensions=[source.shape[1], source.shape[0]],
                candidate_dimensions=[candidate.shape[1], candidate.shape[0]],
                source_quality_ceiling_exceeded=exceeds_ceiling,
                uv_used_source_texels=int(mask.sum()), alpha_mae=float(np.abs(a[mask].astype(float) - b[mask]).mean()),
                probes=probes, review=exceeds_ceiling or any(p['review'] for p in probes.values()),
                threshold_status='PROVISIONAL review only: support recall <95%, thin/edge recall <85%, or an entirely lost component of >=4 source texels',
                limitations='Nearest/repeat-style texture support in original UV space; actual GPU alpha cutoff, filtering, culling, camera visibility and blending are not emulated.')


def report(model, source_images, decoded_images):
    names = model.get('texture_names', model.get('textures'))
    if not set(names) <= source_images.keys() or not set(names) <= decoded_images.keys():
        raise ValueError('Missing required texture for opacity QA')
    usage = model_usage({2: dict(model, texture_names=names)}, source_images)
    rows = {name: compare(source_images[name], decoded_images[name], usage[name]['uv_mask'])
            for name in names if np.any(np.asarray(source_images[name])[:, :, 3] < 255)}
    return dict(textures=rows, coverage_available=bool(rows), review=any(r['review'] for r in rows.values()),
                mode='Read-only original opacity-support comparison; no geometry or texture correction')

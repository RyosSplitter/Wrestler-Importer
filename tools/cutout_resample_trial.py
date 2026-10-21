"""Isolated source-component support experiment for minified cutout textures.

Defaults elsewhere remain nearest-source alpha. This experiment changes only
candidate image samples, never geometry/UVs or rigging. Each rescued sample is
an actual source RGBA sample, not an invented opacity/tint. New opaque coverage
and component merging remain review findings, not automatically acceptable.
"""
import numpy as np
from PIL import Image
from scipy.ndimage import label


def minify(source, size, uv_mask=None, *, preserve_components=False):
    source = np.asarray(source)
    if source.dtype != np.uint8 or source.ndim != 3 or source.shape[2] != 4:
        raise ValueError('Source must be uint8 RGBA')
    w, h = size; sh, sw = source.shape[:2]
    if type(w) is not int or type(h) is not int or not 0 < w <= sw or not 0 < h <= sh:
        raise ValueError('Source resolution ceiling exceeded')
    used = np.ones((sh, sw), bool) if uv_mask is None else np.asarray(uv_mask) > 0
    if used.shape != (sh, sw) or not used.any(): raise ValueError('Nonempty source-sized UV mask required')
    out = np.array(Image.fromarray(source).resize(size, Image.Resampling.LANCZOS))
    out[:, :, 3] = np.array(Image.fromarray(source[:, :, 3]).resize(size, Image.Resampling.NEAREST))
    edits = []
    if preserve_components:
        yy, xx = np.indices((sh, sw)); ty = np.minimum(((yy + .5) * h / sh).astype(int), h - 1)
        tx = np.minimum(((xx + .5) * w / sw).astype(int), w - 1)
        for threshold in (192, 128, 64):
            components, count = label(source[:, :, 3] >= threshold, structure=np.ones((3, 3), bool))
            sizes = np.bincount(components[used], minlength=count + 1)
            active = out[ty, tx, 3] >= threshold
            retained = np.bincount(components[used & active], minlength=count + 1)
            for component in np.flatnonzero((sizes >= 4) & (retained == 0)):
                if component == 0: continue
                ys, xs = np.where((components == component) & used)
                # Prefer an opaque source sample close to the component centre;
                # ties follow stable source row order. Never lower an existing alpha.
                centre = np.array([ys.mean(), xs.mean()])
                distance = (ys - centre[0]) ** 2 + (xs - centre[1]) ** 2
                order = np.lexsort((xs, ys, distance, -source[ys, xs, 3].astype(int)))
                selected = next((i for i in order if source[ys[i], xs[i], 3] > out[ty[ys[i], xs[i]], tx[ys[i], xs[i]], 3]), None)
                if selected is None: continue
                y, x = int(ys[selected]), int(xs[selected]); y2, x2 = int(ty[y, x]), int(tx[y, x])
                out[y2, x2] = source[y, x]
                edits.append(dict(alpha_probe=threshold, source_component=int(component),
                                  source_visible_texels=int(sizes[component]), source_xy=[x, y],
                                  candidate_xy=[x2, y2], source_rgba=source[y, x].tolist()))
    out[out[:, :, 3] == 0] = 0
    return out, dict(source_dimensions=[sw, sh], candidate_dimensions=[w, h],
                     preserve_source_components=preserve_components, rescued_source_samples=edits,
                     policy='Nearest source alpha; optionally rescue entirely vanished >=4-texel source components at diagnostic alpha cutoffs using an original RGBA sample',
                     limitations='Minification can enlarge/merge opacity support; visual and in-game review required')

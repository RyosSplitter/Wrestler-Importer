"""Deterministic alpha/UV-aware features and reduction tests, using NumPy/SciPy.

Scores are tuning hypotheses, not trained perception or in-game compatibility.
No image names, wrestler identifiers, face detector or AI dependency is used.
"""
import math

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, sobel, maximum_filter

LUMA = np.array([.2126, .7152, .0722])


def signals(rgba):
    rgb = rgba[:, :, :3].astype(float) / 255
    # Alpha/UV occupancy is applied to feature aggregation by callers.
    lum = rgb @ LUMA
    gx, gy = sobel(lum, 1) / 8, sobel(lum, 0) / 8
    edge = np.hypot(gx, gy)
    high = np.maximum(np.abs(lum - gaussian_filter(lum, .8))-1e-12,0)
    return lum, gx, gy, edge, high


def occupied(rgba, uv_mask=None):
    mask = rgba[:, :, 3].astype(float) / 255
    if uv_mask is not None and np.any(uv_mask):
        mask *= uv_mask
    return mask


def measure(source, candidate, mask=None):
    original_shape = candidate.shape
    if candidate.shape != source.shape:
        candidate = np.asarray(Image.fromarray(candidate).resize(
            (source.shape[1], source.shape[0]), Image.Resampling.LANCZOS))
    mask = occupied(source) if mask is None else mask
    mass = max(float(mask.sum()), 1e-12)
    def mean(v): return float((v * mask).sum() / mass)
    a, ax, ay, ae, ah = signals(source)
    b, bx, by, be, bh = signals(candidate)
    ma, mb = gaussian_filter(a, 1.5), gaussian_filter(b, 1.5)
    va = np.maximum(gaussian_filter(a*a, 1.5)-ma*ma, 0)
    vb = np.maximum(gaussian_filter(b*b, 1.5)-mb*mb, 0)
    cov = gaussian_filter(a*b, 1.5)-ma*mb
    ssim = ((2*ma*mb+.01**2)*(2*cov+.03**2))/((ma*ma+mb*mb+.01**2)*(va+vb+.03**2))
    mse = mean((((source[:, :, :3].astype(float)-candidate[:, :, :3]) / 255)**2).mean(2))
    # Weighted oriented-gradient mismatch catches lines that disappear, move,
    # blur or reverse contrast. SSIM alone can reward a blurred tattoo.
    salient = mask * (1 + 4*np.minimum(ae/.08, 1))
    edge_error = float((np.hypot(ax-bx, ay-by)*salient).sum() /
                       max(float((ae*salient).sum()), .02*mass))
    strong = (ae > .025) * mask
    smass = max(float(strong.sum()), 1e-12)
    recalled = np.minimum(maximum_filter(be, size=3)/np.maximum(ae, .025), 1)
    feature_loss = float(((1-recalled)*strong).sum()/smass)
    high_error = mean(np.abs(ah-bh)) / max(mean(ah), .01)
    rmse = math.sqrt(mse)
    loss = (.22*rmse + .15*max(0, 1-mean(ssim)) +
            .30*min(edge_error, 2)/2 + .23*feature_loss + .10*min(high_error, 2)/2)
    return dict(rgb_rmse_255=rmse*255, luminance_ssim=mean(ssim),
                oriented_edge_error=edge_error, fine_feature_loss=feature_loss,
                high_frequency_error=high_error, perceptual_loss=loss,
                quality_score=max(0., 1-loss), alpha_mae=float(np.abs(
                    source[:, :, 3].astype(float)-candidate[:, :, 3]).mean()),
                alpha_exact=original_shape==source.shape and np.array_equal(source[:, :, 3], candidate[:, :, 3]),
                metric_scope='Source-sized Lanczos reconstruction, occupied-area weighted; heuristic perception')


def analyze(rgba, uv_mask=None, surface_fraction=None):
    mask = occupied(rgba, uv_mask)
    mass = max(float(mask.sum()), 1e-12)
    lum, gx, gy, edge, high = signals(rgba)
    # Suppress artificial gradients crossing fully transparent/unused areas.
    from scipy.ndimage import minimum_filter
    interior = minimum_filter(mask > 0, size=3)
    meaningful = (edge > .025) | (high > .02)
    detail_coverage = float((meaningful*mask*interior).sum()/mass)
    complexity = min(1., float(((edge+2*high)*mask*interior).sum()/mass)/.12)
    half = (max(1, rgba.shape[1]//2), max(1, rgba.shape[0]//2))
    probe = np.asarray(Image.fromarray(rgba).resize(half, Image.Resampling.LANCZOS))
    sensitivity = measure(rgba, probe, mask)['perceptual_loss']
    area_factor = 1. if surface_fraction is None else .75+.5*math.sqrt(min(surface_fraction*20, 4))
    importance = (.6+1.6*complexity+.8*detail_coverage+1.2*sensitivity)*area_factor
    visible = rgba[rgba[:, :, 3] > 0]
    useful = len(np.unique(visible, axis=0)) if len(visible) else 1
    return dict(source_dimensions=[rgba.shape[1], rgba.shape[0]], useful_source_colors=useful,
                actual_rgba_colors=len(np.unique(rgba.reshape(-1, 4), axis=0)),
                transparent_color_required=bool(np.any(rgba[:, :, 3]==0)),
                occupied_pixels=float(mask.sum()), occupied_fraction=float(mask.mean()),
                detail_score=complexity, detail_coverage=detail_coverage,
                detail_coverage_percent=detail_coverage*100,
                reduction_sensitivity=sensitivity, surface_fraction=surface_fraction,
                importance_score=importance, has_alpha=bool(np.any(rgba[:, :, 3]!=255)),
                source_quality_ceiling=dict(width=rgba.shape[1], height=rgba.shape[0],
                    useful_colors=useful, upscaling_allowed=False),
                empty_opaque_padding='Included unless verified unused by UVs; no guessed background removal')


def model_usage(models, sources):
    """Rasterize verified [0,1] UV triangles; fall back for wrapping coordinates.

    Surface share is triangle area, not camera visibility or draw-frequency.
    Controllers are used only for minimal cranial safeguards, not image identity.
    """
    result={n:dict(area=0., head_area=0., uv_mask=np.zeros(r.shape[:2], bool),
                   uv_reliable=True) for n,r in sources.items()}
    for model in models.values():
        head=set()
        for b in model['bones']:
            i=b['index'];seen=set()
            while i!=-1 and i not in seen:
                seen.add(i)
                if model['bones'][i]['name']=='atama':head.add(b['index']);break
                i=model['bones'][i]['parent']
        for mesh in model['meshes']:
            for mat in mesh['materials']:
                row=result[model['texture_names'][mat['texture_id']]]
                h,w=row['uv_mask'].shape
                for tri in mat['triangles']:
                    vs=[mesh['vertices'][i] for i in tri]
                    p=np.asarray([v['position'] for v in vs]);area=float(np.linalg.norm(np.cross(p[1]-p[0],p[2]-p[0]))*.5)
                    row['area']+=area
                    row['head_area']+=area*sum(sum(weight for bone,weight in zip(mesh['bone_palette'],v['weights']) if bone in head) for v in vs)/3
                    uv=np.asarray([v['uv'] for v in vs])
                    if not np.isfinite(uv).all() or uv.min() < -1e-6 or uv.max()>1+1e-6:
                        row['uv_reliable']=False;continue
                    xy=uv*np.array([w,h]);a,b,c=xy
                    d=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                    if abs(d)<1e-12:continue
                    lo=np.maximum(np.floor(xy.min(0)).astype(int),0)
                    hi=np.minimum(np.ceil(xy.max(0)).astype(int),[w,h])
                    xx,yy=np.meshgrid(np.arange(lo[0],hi[0])+.5,np.arange(lo[1],hi[1])+.5)
                    aa=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/d
                    bb=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/d
                    row['uv_mask'][lo[1]:hi[1],lo[0]:hi[0]]|=(aa>=-1e-7)&(bb>=-1e-7)&(aa+bb<=1+1e-7)
    total=max(sum(r['area'] for r in result.values()),1e-12)
    for row in result.values():
        row['surface_fraction']=row['area']/total
        row['head_fraction']=row['head_area']/max(row['area'],1e-12)
        if not row['uv_reliable'] or not row['uv_mask'].any():row['uv_mask']=None
    return result

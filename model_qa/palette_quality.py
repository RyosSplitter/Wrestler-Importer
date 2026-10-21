"""Read-only separation of texture resolution loss from palette/color loss.

A higher resolution can improve SSIM/edge scores while a smaller palette makes
skin shading blotchy. Compare palette error at each representation's OWN grid
against identically resampled source RGB; do not hide it in a combined score.
Thresholds request human review and are not calibrated perceptual acceptance.
"""
import numpy as np
from PIL import Image


def _image(value):
    a = np.asarray(value)
    if a.dtype != np.uint8 or a.ndim != 3 or a.shape[2] != 4 or min(a.shape[:2]) < 1:
        raise ValueError('Nonempty uint8 RGBA required')
    return a


def representation(source, candidate, uv_mask=None):
    source, candidate = _image(source), _image(candidate)
    if np.any(source[:, :, 3] != 255) or np.any(candidate[:, :, 3] != 255):
        raise ValueError('Opaque pages only; cutout alpha requires separate QA')
    mask = np.ones(source.shape[:2], bool) if uv_mask is None else np.asarray(uv_mask) > 0
    if mask.shape != source.shape[:2] or not mask.any():
        raise ValueError('Nonempty source-sized UV mask required')
    size = (candidate.shape[1], candidate.shape[0])
    target = np.asarray(Image.fromarray(source).resize(size, Image.Resampling.LANCZOS))
    used = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize(size, Image.Resampling.BOX)) > 0
    if not used.any(): raise ValueError('No occupied pixels at candidate resolution')
    delta = candidate[:, :, :3].astype(float) - target[:, :, :3].astype(float)
    per_pixel = np.sqrt(np.mean(delta ** 2, axis=2))[used]
    return dict(dimensions=list(size), used_native_texels=int(used.sum()),
                used_rgb_colors=len(np.unique(candidate[:, :, :3][used], axis=0)),
                quantization_rgb_rmse_255=float(np.sqrt(np.mean(delta[used] ** 2))),
                quantization_rgb_error_p95_255=float(np.percentile(per_pixel, 95)),
                source_resolution_ceiling_exceeded=bool(size[0] > source.shape[1] or size[1] > source.shape[0]),
                interpretation='Palette/color error versus source resized to this grid; separate from loss caused by resolution reduction')


def compare(source, baseline, candidate, uv_mask=None, *, sensitive=False):
    a = representation(source, baseline, uv_mask); b = representation(source, candidate, uv_mask)
    findings = []
    if b['source_resolution_ceiling_exceeded']: findings.append('source-resolution-ceiling-exceeded')
    if any(y < x for x, y in zip(a['dimensions'], b['dimensions'])):
        findings.append('resolution-reduced-relative-to-baseline')
    if sensitive and b['used_rgb_colors'] < a['used_rgb_colors']:
        findings.append('sensitive-page-useful-color-count-reduced')
    if b['quantization_rgb_rmse_255'] > a['quantization_rgb_rmse_255'] * 1.10 + .5:
        findings.append('native-grid-quantization-error-increased')
    return dict(baseline=a, candidate=b, findings=findings, review=bool(findings),
                tolerance_status='PROVISIONAL: RMSE increase >10% plus 0.5 RGB units; source ceiling/resolution/color-count changes reported separately',
                limitations='No semantic skin detector or runtime filtering simulation; more source detail at higher resolution can itself increase quantization demand. Findings require visual review.')

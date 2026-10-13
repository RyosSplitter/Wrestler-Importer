"""Reproduce the new Default over a frozen PSP reference, without geometry work.

python -m experiments.default_texture_quality source.pac baseline.pac new-folder
"""
import argparse
import hashlib
import json
from pathlib import Path

from desktop.adapters import adapter
from desktop.accessories import source_models, decode_dependencies
from desktop.default_textures import upgrade
from desktop.core import validate_pac
from desktop.preview import save_views
from desktop.skinning import exact_pose_checks
from desktop.texture_optimizer.candidates import read_gim
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections


def run(source, baseline, output, renders=True):
    source, baseline, output = map(Path, (source, baseline, output))
    if output.exists():
        raise FileExistsError(output)
    original, source_bytes = baseline.read_bytes(), source.read_bytes()
    native, old_images = validate_pac(original, gim_reader=read_gim)
    model, decoded = adapter('hctp').read(source)
    _, names = source_models(source, model)
    decoded = decode_dependencies(source, decoded, names)
    candidate, report = upgrade(original, decoded, output/'textures',
        progress=lambda message: print(message, flush=True))
    final, images = validate_pac(candidate, gim_reader=read_gim)
    a = {s['id']: raw for s, raw in sections(original)}
    b = {s['id']: raw for s, raw in sections(candidate)}
    assert a.keys() == b.keys()
    for section in a:
        if section != 9:
            assert a[section] == b[section]
    poses = {section: exact_pose_checks(audit_yobj(raw), audit_yobj(b[section]))
             for section, raw in a.items() if raw.startswith(b'YOBJ')}
    assert source.read_bytes() == source_bytes and baseline.read_bytes() == original
    (output/'candidate.pac').write_bytes(candidate)
    if renders:
        # Main-model renders; auxiliary native models are individually audited
        # and their complete effective motion is checked above.
        save_views(native, old_images, output/'before', resolution=512, gim_reader=read_gim)
        save_views(final, images, output/'after', resolution=512, gim_reader=read_gim)
    summary = dict(source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        baseline_sha256=hashlib.sha256(original).hexdigest(), sha256=hashlib.sha256(candidate).hexdigest(),
        before_bytes=len(original), bytes=len(candidate), model_and_rigging_exact=True,
        native_validation='passed', analytical_pose_preservation=poses,
        pixel_palette_bytes=report['pixel_palette_bytes'], pixel_palette_budget=report['pixel_palette_budget'],
        policy=report['default_policy'], texture_settings=[dict(name=t['name'],before=t['current_configuration'],
            after=t['selected_configuration'],review=t['quality_review_flags']) for t in report['textures']],
        gameplay_validation='Only the earlier fixed RVD candidate has new user-reported gameplay acceptance; these automated results are not game certification')
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source','baseline','output'):
        p.add_argument(name, type=Path)
    p.add_argument('--no-renders', action='store_true')
    args = p.parse_args()
    r = run(args.source, args.baseline, args.output, not args.no_renders)
    print('Result:', r['bytes'], 'pixels:', r['pixel_palette_bytes'],
          'automatic priorities:', r['policy']['chosen_priorities'], flush=True)

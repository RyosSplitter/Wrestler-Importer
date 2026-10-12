"""Compare regional deformation errors before/after a source-identity change.

python -m tools.source_skinning_region_review reference.json before.json
    candidate.pac report.json --samples 24000
The reference is source-derived geometry on the same verified PSP target rig.
Tolerances are the existing provisional QA profile, not game certification.
"""
import argparse
import json
from pathlib import Path

from model_qa.geometry import geometry, posed, read_model, sha
from model_qa.metrics import measure, tolerances
from model_qa.regions import regions
from model_qa.skinning_records import POSES, compare


def build(reference_path, before_path, candidate_path, output, samples=24000):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    models = [read_model(p) for p in (reference_path, before_path, candidate_path)]
    # Verify the target bind rig before interpreting comparative motion.
    compare(models[0], models[1], strict=False)
    compare(models[0], models[2])
    gs = [geometry(m) for m in models]
    rois = regions(gs[0], models[0])
    profile = json.loads((Path(__file__).resolve().parents[1] /
                         'model_qa/profiles/hctp-provisional-v1.json').read_text())
    report = dict(inputs={str(p): sha(p) for p in (reference_path, before_path, candidate_path)},
                  samples=samples, poses={}, regressions=[],
                  limitation='Source-weight control on the PSP target rig and analytical poses; not captured game animations')
    for name, controls in POSES.items():
        pg = [posed(g, controls) for g in gs]
        measurements = [measure(pg[0], pg[i], rois, gs[0].height,
                                reference_bind=gs[0], candidate_bind=gs[i],
                                count=samples)[0] for i in (1, 2)]
        a, b = measurements
        row = dict(before_overall=a['overall'], after_overall=b['overall'], regions={})
        for region in rois:
            x, y = a['regions'][region]['distance'], b['regions'][region]['distance']
            limit = tolerances(profile, region)[
                'distance_p95_height' if name == 'standing' else 'animation_extra_p95_height']
            enough = (x and y and min(x['samples'], y['samples']) >= profile['minimum_surface_samples'])
            delta = y['p95_height'] - x['p95_height'] if enough else None
            failure = not enough or delta > limit
            row['regions'][region] = dict(before=x, after=y, p95_height_regression=delta,
                                         tolerance=limit, regression_exceeds_tolerance=failure)
            if failure:
                report['regressions'].append(dict(pose=name, region=region,
                                                  error='insufficient-evidence' if not enough else 'regression'))
        report['poses'][name] = row
        print(name, 'regional comparison complete', flush=True)
    report['status'] = 'pass' if not report['regressions'] else 'fail'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'before', 'candidate', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--samples', type=int, default=24000)
    args = parser.parse_args()
    result = build(args.reference, args.before, args.candidate, args.output, args.samples)
    raise SystemExit(0 if result['status'] == 'pass' else 1)

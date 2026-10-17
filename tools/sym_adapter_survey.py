"""Read-only corpus checks for the isolated SYM atlas/bone-bound hypotheses."""
import argparse
import json
from pathlib import Path

from tools.hctp_weights import read_hctp_with_weights
from tools.psp_mesh_merge_trial import sections
from tools.sym_atlas import partition
from tools.sym_rig import bounds_probe
from tools.sym_source import read_atlas, read_ch_directory, sha


def survey(source, output):
    data = source.read_bytes()
    directory = read_ch_directory(data)
    if output.exists():
        raise FileExistsError('Refusing to replace a survey')
    rows = []
    for entry in directory['entries']:
        raw = data[entry['offset']:entry['offset']+entry['stored_bytes']]
        decoded = {r['id']: blob for r, blob in sections(raw)}
        row = dict(entry=entry['id_hex'], main_model_sha256=sha(decoded[2]) if 2 in decoded else None)
        try:
            if not {1,2} <= set(decoded):
                raise ValueError('Missing main model/atlas sections')
            model = read_hctp_with_weights(decoded[2])
            indices, palette, _ = read_atlas(decoded[1])
            bounds = bounds_probe(decoded[2], model)
            row['bounds'] = dict(active=bounds['active_bones'], enclosed=bounds['enclosing_active_bones'],
                exceptions=[v for v in bounds['bones'] if v['active_records'] and not v['enclosed_at_1e_minus_4']])
            try:
                _, crops, report = partition(model, palette[indices])
                row['atlas'] = dict(passed=True, charts=len(crops), triangles=report['output_triangles'],
                    sample_error=report['maximum_sample_rgba_error'],
                    full_t8_crop_count=sum(8 in r['full_size_native_bits'] for r in report['islands']),
                    source_canvas_only_count=sum(8 not in r['full_size_native_bits'] for r in report['islands']))
            except ValueError as exc:
                row['atlas'] = dict(passed=False, error=str(exc))
        except ValueError as exc:
            row['error'] = str(exc)
        rows.append(row)
        if len(rows) % 25 == 0:
            print('Surveyed', len(rows), flush=True)
    report = dict(source_sha256=sha(data), entries=rows,
        summary=dict(entries=len(rows), main_models_decoded=sum('bounds' in r for r in rows),
            atlas_partition_passes=sum(r.get('atlas',{}).get('passed',False) for r in rows),
            active_bones=sum(r.get('bounds',{}).get('active',0) for r in rows),
            enclosing_active_bones=sum(r.get('bounds',{}).get('enclosed',0) for r in rows)),
        scope='Original main-model geometry only; lossless source crops are not serialized PSP texture validation')
    if source.read_bytes() != data:
        raise RuntimeError('Source changed during read-only survey')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, allow_nan=False)
        f.write('\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = survey(args.source, args.out)
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()

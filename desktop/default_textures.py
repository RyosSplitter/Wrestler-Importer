"""Source-aware Default textures over the existing frozen geometry candidate.

The reference allocation is conservative native evidence, not a game heap limit.
Automatic attention uses actual lost fine detail, occupied coverage and surface
importance, never character/texture names. Legacy generation remains separate.
"""
from desktop.limits import IN_RING_MAX_PAC_BYTES
import json
from pathlib import Path

import numpy as np

from tools.pac_inspect import parse_textures
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from desktop.texture_optimizer import optimize_pac
from desktop.texture_optimizer.analysis import analyze, measure, model_usage, occupied
from desktop.texture_optimizer.candidates import read_gim

REFERENCE_PIXEL_BYTES = 34176
POLICY = 'native-reference-detail-priorities-v1'


def inspect_baseline(baseline, decoded):
    unpacked = {s['id']: raw for s, raw in sections(baseline)}
    models = {i: audit_yobj(raw) for i, raw in unpacked.items() if raw.startswith(b'YOBJ')}
    names = models[2]['texture_names']
    raw = unpacked[9]
    gims = {t['name']: raw[t['offset']:t['offset']+t['size']] for t in parse_textures(raw)}
    sources = {n: rgba for i, n, raw, rgba, details in decoded}
    if set(sources) != set(names) or set(gims) != set(names):
        raise ValueError('Default source/model/texture dependencies differ')
    pixels = 0
    for raw in unpacked.values():
        if len(raw) >= 16 and raw[4:16] == bytes.fromhex('000100000000000010000000'):
            for t in parse_textures(raw):
                if t['extension'] != 'gim':
                    raise ValueError('Unimplemented retained texture allocation')
                data = raw[t['offset']:t['offset']+t['size']]
                read_gim(data)
                pixels += len(data)-208
    return models, sources, gims, pixels


def choose_priorities(features):
    """Select at most three dominant losses; sensitive head maps have guards.

    Relative/absolute thresholds are tunable perception hypotheses. A tiny
    isolated feature need not outrank a design covering a large usable area.
    Manual Priority Selection remains available when automatic attention misses.
    """
    eligible = [f for f in features if f['head_fraction'] <= .5
                and f['fine_feature_loss'] > .1 and f['detail_coverage'] > .05
                and f['attention_score'] >= .05]
    eligible.sort(key=lambda f: (-f['attention_score'], f['name']))
    threshold = eligible[0]['attention_score']*.5 if eligible else 0.
    return [f['name'] for f in eligible[:3] if f['attention_score'] >= threshold]


def upgrade(baseline, decoded, output, *, target=IN_RING_MAX_PAC_BYTES, priority_textures=(),
            cancel=lambda: None, progress=lambda message: None):
    output = Path(output)
    models, sources, gims, existing_pixels = inspect_baseline(baseline, decoded)
    usage = model_usage(models, sources)
    features = []
    for name in models[2]['texture_names']:
        cancel()
        progress('Checking lost texture detail: '+name)
        p, c = read_gim(gims[name])
        u = usage[name]
        f = analyze(sources[name], u['uv_mask'], u['surface_fraction'])
        metrics = measure(sources[name], c[p], occupied(sources[name], u['uv_mask']))
        features.append(dict(name=name, head_fraction=u['head_fraction'],
            detail_coverage=f['detail_coverage'], importance=f['importance_score'],
            fine_feature_loss=metrics['fine_feature_loss'],
            attention_score=f['importance_score']*f['detail_coverage']*metrics['fine_feature_loss']))
    chosen = list(priority_textures) if priority_textures else choose_priorities(features)
    limit = max(REFERENCE_PIXEL_BYTES, existing_pixels)
    candidate, report = optimize_pac(baseline, decoded, output, target=target,
        max_pixel_bytes=limit, priority_textures=chosen, rebalance_priorities=bool(chosen),
        strict_source_ceilings=True, cancel=cancel, progress=progress)
    # Independent final check: a legal incumbent must not bypass source ceilings.
    for row in report['textures']:
        e = row['selected_configuration']
        h, w = sources[row['name']].shape[:2]
        visible = sources[row['name']][sources[row['name']][:,:,3] > 0]
        ceiling = max(len(np.unique(visible, axis=0)), 1)+int(np.any(sources[row['name']][:,:,3] == 0))
        if e['width'] > w or e['height'] > h or e['used_palette_colors'] > ceiling:
            raise ValueError('Default texture source-quality ceiling violated: '+row['name'])
    report['default_policy'] = dict(id=POLICY,
        priority_origin='user' if priority_textures else 'automatic-content',
        chosen_priorities=chosen, attention=features,
        attention_formula='importance * occupied detail coverage * measured incumbent fine-feature loss',
        reference_pixel_palette_bytes=REFERENCE_PIXEL_BYTES,
        legacy_pixel_palette_bytes=existing_pixels, effective_pixel_palette_bytes=limit,
        budget_basis='Lowest modeled allocation in the supplied native corpus, raised only to retain an existing larger baseline; not a measured game heap limit',
        evidence='RVD selected-texture candidate used 31808 bytes and was reported successful in SVR 2011 by the user; reference census minimum is 34176',
        detail_thresholds=dict(minimum_score=.05, minimum_coverage=.05,
                               minimum_loss=.1, relative_to_highest=.5, maximum_priorities=3))
    unresolved = []
    for row in report['textures']:
        row['selection_origin'] = report['default_policy']['priority_origin'] if row['name'] in chosen else 'allocation'
        if row['name'] in chosen and row['selected_configuration']['metrics']['fine_feature_loss'] > .25:
            row['quality_review_flags'].append('Prioritized detail still has substantial measured feature loss; inspect the preview or use manual priorities. The .25 threshold is provisional.')
            unresolved.append(row['name'])
    report['default_policy']['detail_review_textures'] = unresolved
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    html = output/'report.html'
    text = html.read_text(encoding='utf-8')
    note = ('<p>Default quality policy: independent native-reference pixel/CLUT allowance '
            '%d bytes (Legacy %d). %d %s detail priorities. Allocation is reference policy, '
            'not measured game heap capacity. See report.json for every decision.</p>' %
            (limit, existing_pixels, len(chosen), 'manual' if priority_textures else 'automatic'))
    html.write_text(text.replace('<body>', '<body>'+note, 1), encoding='utf-8')
    return candidate, report

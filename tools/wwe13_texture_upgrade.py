"""Texture-only monotonic upgrade trials from an immutable checked baseline.

Retain each existing encoded GIM as a candidate. Additional budget may buy
source-bounded upgrades, but may not fund one page by degrading another page's
combined detail/color loss. These are diagnostic heuristics, not visual proof.
"""
import json
from pathlib import Path

from tools.wwe13_wii_texture_refine import candidates
from tools.yukes_bpe import compress


def factory(work):
    work = Path(work)
    previous = json.loads((work / 'textures/report.json').read_text())
    baselines = {row['name']: row['selected'] for row in previous['textures']}

    def upgrade(model, images, contracts, progress=print):
        choices, importance, diagnostics = candidates(model, images, contracts, progress)
        for j, name in enumerate(model['textures']):
            entry = dict(baselines[name])
            raw = (work / 'textures' / (name + '.gim')).read_bytes()
            entry['individual_bpe_bytes'] = len(compress(raw))
            old_loss = entry['metrics']['perceptual_loss']
            rows = [dict(raw=raw, entry=entry)]
            for row in choices[j]:
                if row['entry']['metrics']['perceptual_loss'] < old_loss - 1e-10:
                    rows.append(row)
            rows.sort(key=lambda r: (r['entry']['individual_bpe_bytes'], r['entry']['metrics']['perceptual_loss']))
            frontier = []; loss = float('inf')
            for row in rows:
                if row['entry']['metrics']['perceptual_loss'] < loss - 1e-10:
                    frontier.append(row); loss = row['entry']['metrics']['perceptual_loss']
            choices[j] = frontier
            diagnostics[j]['baseline_upgrade_guard'] = dict(
                baseline=entry, permitted_loss_ceiling=old_loss,
                policy='Exact original GIM remains available; no page may have greater combined detail/color loss than its baseline')
            diagnostics[j]['frontier'] = [r['entry'] for r in frontier]
        return choices, importance, diagnostics

    return upgrade

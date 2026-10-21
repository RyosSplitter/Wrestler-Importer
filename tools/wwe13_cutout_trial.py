"""Texture-only, fixed-size cutout A/B experiment; never registered in the app.

Pin all other decoded baseline GIMs and reuse the existing PAC builder/validator.
No claim that preserved source opacity components emulate GPU alpha testing.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np

from desktop.texture_optimizer.analysis import analyze, measure, model_usage, occupied
from desktop.texture_optimizer.candidates import OBSERVED_T8_DIMENSIONS, encode, read_gim
from tools.cutout_resample_trial import minify
from tools.pac_inspect import parse_textures
from tools.psp_mesh_merge_trial import sections
from tools.wwe13_wii_texture_refine import run
from tools.yukes_bpe import compress


def factory(work, texture, size, *, preserve_components=False):
    work = Path(work)
    accepted = json.loads((work / 'result.json').read_text())
    data = (work / accepted['pac']).read_bytes()
    if hashlib.sha256(data).hexdigest() != accepted['sha256']:
        raise ValueError('Baseline PAC hash differs')
    table = next(raw for section, raw in sections(data) if section['id'] == 9)
    gims = {row['name']: table[row['offset']:row['offset'] + row['size']]
            for row in parse_textures(table)}
    entries = {row['name']: row['selected']
               for row in json.loads((work / 'textures/report.json').read_text())['textures']}
    if texture not in gims or tuple(size) not in OBSERVED_T8_DIMENSIONS:
        raise ValueError('Missing texture or unobserved T8 dimensions')

    def candidates(model, images, contracts, progress=print):
        if model['textures'] != list(gims):
            raise ValueError('Baseline texture bindings differ')
        usage = model_usage({2: dict(model, texture_names=model['textures'])},
                            dict(zip(model['textures'], images)))
        choices, importance, diagnostics = [], [], []
        for name, source, contract in zip(model['textures'], images, contracts):
            if name != texture:
                entry = copy.deepcopy(entries[name])
                if entry['serialized_bytes'] != len(gims[name]):
                    raise ValueError('Baseline texture report size differs')
                choices.append([dict(raw=gims[name], entry=entry)])
                importance.append(1.)
                diagnostics.append(dict(name=name, policy='Exact tested GIM pinned'))
                continue
            if not contract['cutout'] or contract['bits'] != 8:
                raise ValueError('Selected page is not an existing indexed8 cutout')
            progress('Cutout opacity support trial: ' + name)
            image, policy = minify(source, tuple(size), usage[name]['uv_mask'],
                                    preserve_components=preserve_components)
            features = analyze(source, usage[name]['uv_mask'], usage[name]['surface_fraction'])
            ceiling = min(256, features['useful_source_colors'] + int((source[:, :, 3] == 0).any()))
            row = encode(image, tuple(size), 8, max(1, ceiling))
            ix, palette = read_gim(row['raw'])
            if not np.array_equal(palette[ix][:, :, 3], image[:, :, 3]):
                raise ValueError('Serialization changed source alpha levels')
            row['entry']['metrics'] = measure(source, palette[ix], occupied(source, usage[name]['uv_mask']))
            row['entry']['source_quality_ceiling'] = features['source_quality_ceiling']
            row['entry']['opacity_sampling_experiment'] = policy
            row['entry']['individual_bpe_bytes'] = len(compress(row['raw']))
            choices.append([row]); importance.append(features['importance_score'])
            diagnostics.append(dict(name=name, analysis=features, selected=row['entry'],
                                    opacity_sampling_experiment=policy))
        return choices, importance, diagnostics
    return candidates


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('work'); p.add_argument('--base', required=True); p.add_argument('--out', required=True)
    p.add_argument('--texture', required=True); p.add_argument('--width', required=True, type=int)
    p.add_argument('--height', required=True, type=int); p.add_argument('--preserve-components', action='store_true')
    p.add_argument('--costume-role', choices=('ring', 'entrance'), default='ring')
    a = p.parse_args()
    run(a.work, a.base, a.out,
        candidate_factory=factory(a.work, a.texture, (a.width, a.height), preserve_components=a.preserve_components),
        filename='Cutout-Component-Support-Trial.pac' if a.preserve_components else 'Cutout-Nearest-Alpha-Trial.pac',
        costume_role=a.costume_role)

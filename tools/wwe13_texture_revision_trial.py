"""Explicit-config, geometry-preserving PSP texture revision experiment.

Reuse the existing encoder, BPE and PAC writer. Not registered in the app.
Layouts/UVs are unchanged. Only native texture-depth control words can differ
in the expanded YOBJ. Optional effect storage is lossless and separately proven.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from desktop.accessories import package_models
from desktop.core import base_model
from desktop.texture_optimizer.analysis import model_usage, occupied
from desktop.texture_optimizer.candidates import read_gim
from model_qa.palette_quality import compare as compare_palette
from tools.pac_inspect import parse_textures
from tools.pac_repack import texture_table
from tools.psp_effect_storage_trial import compact_effect_storage
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.sym_trial import pose_qa
from tools.wwe13_budget import budget
from tools.wwe13_pose_trial import hand_probes
from tools.wwe13_texture_format_trial import exact_indexed4, patch_regular_depths
from tools.wwe13_texture_trial import encode_occupied
from tools.wwe13_wii_trial import dump, validate_trial


def run(work, base_path, output, configuration, *, compact_effects=False,
        filename='PSP-Texture-Revision-EXPERIMENTAL.pac', costume_role='ring'):
    work, base_path, output = map(Path, (work, base_path, output))
    if Path(filename).name != filename or Path(filename).suffix.lower() != '.pac':
        raise ValueError('Output must be a PAC filename')
    if output.exists(): raise FileExistsError(output)
    accepted = json.loads((work / 'result.json').read_text())
    before = (work / accepted['pac']).read_bytes()
    if hashlib.sha256(before).hexdigest() != accepted['sha256']:
        raise ValueError('Checked baseline hash differs')
    old_raw = next(raw for s, raw in sections(before) if s['id'] == 2)
    if old_raw != (work / 'candidate.yobj').read_bytes():
        raise ValueError('Baseline model differs')
    old_native = audit_yobj(old_raw); names = old_native['texture_names']
    if len(configuration) != len(names) or {c['name'] for c in configuration} != set(names):
        raise ValueError('Exactly one explicit configuration per texture required')
    config = {c['name']: c for c in configuration}
    raw_table = next(raw for s, raw in sections(before) if s['id'] == 9)
    previous = {r['name']: raw_table[r['offset']:r['offset'] + r['size']] for r in parse_textures(raw_table)}
    images = {n: np.array(Image.open(work / 'source-images' / (n + '.png')).convert('RGBA')) for n in names}
    usage = model_usage({2: old_native}, images)
    gims, bits, changes = {}, {}, []
    for name in names:
        c = config[name]; policy = c['policy']; source = images[name]
        old_p, old_c = read_gim(previous[name]); old_rgba = old_c[old_p]
        if policy == 'preserve': encoded = previous[name]
        elif policy == 'lossless-indexed4': encoded = exact_indexed4(previous[name])
        elif policy == 'source':
            encoded = encode_occupied(source, (c['width'], c['height']), c['bits'], c['colors'],
                                       occupied(source, usage[name]['uv_mask']))['raw']
        else: raise ValueError('Unreviewed texture policy')
        p, palette = read_gim(encoded); rgba = palette[p]
        gims[name] = encoded; bits[name] = 4 if len(palette) == 16 else 8
        row = dict(name=name, policy=policy,
            before=dict(width=old_p.shape[1], height=old_p.shape[0], bits=4 if len(old_c) == 16 else 8,
                        useful_colors=len(np.unique(old_rgba.reshape(-1, 4), axis=0)), serialized_bytes=len(previous[name])),
            after=dict(width=p.shape[1], height=p.shape[0], bits=bits[name],
                       useful_colors=len(np.unique(rgba.reshape(-1, 4), axis=0)), serialized_bytes=len(encoded)),
            gim_byte_identical=encoded == previous[name], decoded_rgba_identical=np.array_equal(rgba, old_rgba),
            gim_sha256=hashlib.sha256(encoded).hexdigest())
        if source[:, :, 3].min() == 255 and rgba[:, :, 3].min() == 255:
            row['palette_qa'] = compare_palette(source, old_rgba, rgba, usage[name]['uv_mask'],
                                                 sensitive=usage[name]['head_fraction'] > .15)
        changes.append(row)
    raw, model_manifest = patch_regular_depths(old_raw, bits)
    base, target = base_model(base_path)
    original_base_sha = hashlib.sha256(base).hexdigest()
    reference_base, effect_manifest = compact_effect_storage(base) if compact_effects else (base, dict(changed=False))
    table = texture_table(names, [gims[n] for n in names], gim_reader=read_gim)
    pac = package_models(reference_base, raw, table, {})
    limits = budget(costume_role)
    if len(pac) > limits['max_pac_bytes']:
        raise ValueError(f'Actual serialized PAC exceeds budget: {len(pac)}/{limits["max_pac_bytes"]}; no output written')
    checks = json.loads((work / 'native-checks.json').read_text())
    ocular = json.loads((work / 'ocular.json').read_text())
    native, decoded, structural = validate_trial(pac, reference_base, checks['radius_changes'],
        ocular['source_controller_pivot_fit'], costume_role=costume_role)
    if decoded != gims: raise ValueError('Serialized texture payloads differ')
    memory = sum(len(g) - 208 for g in gims.values())
    base_memory = retained_memory = 0
    for s, r in sections(base):
        if len(r) >= 16 and r[4:16] == bytes.fromhex('000100000000000010000000'):
            entries = parse_textures(r)
            if all(t['extension'] == 'gim' for t in entries):
                amount = sum(t['size'] - 208 for t in entries); base_memory += amount
                if s['id'] != 9: retained_memory += amount
    if memory + retained_memory > base_memory: raise ValueError('Native pixel/CLUT envelope exceeded')
    poses = pose_qa(json.loads((work / 'packed.json').read_text()), native, target)
    hands = hand_probes(native)
    if poses['review_findings']: raise ValueError('Native analytical pose gate failed')
    for name, envelope in checks['hand_reference_envelope'].items():
        if hands['tests'][name]['maximum_triangle_area_ratio'] > envelope['limit']:
            raise ValueError('Hand analytical gate failed')
    if hashlib.sha256((work / accepted['pac']).read_bytes()).hexdigest() != accepted['sha256']:
        raise ValueError('Baseline changed while building')
    output.mkdir(parents=True)
    (output / filename).write_bytes(pac); (output / 'candidate.yobj').write_bytes(raw)
    (output / 'textures').mkdir()
    for name, gim in gims.items():
        (output / 'textures' / (name + '.gim')).write_bytes(gim)
        p, palette = read_gim(gim); Image.fromarray(palette[p]).save(output / 'textures' / (name + '.png'))
    result = dict(pac=filename, pac_bytes=len(pac), sha256=hashlib.sha256(pac).hexdigest(),
        baseline_sha256=accepted['sha256'], original_base_sha256=original_base_sha,
        experimental_base_sha256=hashlib.sha256(reference_base).hexdigest(),
        budget=limits, pixel_palette_bytes=memory + retained_memory, native_memory_envelope=base_memory,
        textures=changes, material_format_manifest=model_manifest, effect_storage=effect_manifest,
        geometry_uv_normal_weight_index_and_rig_bytes_exact=True,
        status='EXPERIMENTAL; native gates passed; comparison renders and PPSSPP validation still required')
    dump(output / 'result.json', result); dump(output / 'structural.json', structural)
    dump(output / 'native-pose-replay.json', poses); dump(output / 'native-hand-replay.json', hands)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('work'); p.add_argument('--base', required=True); p.add_argument('--out', required=True)
    p.add_argument('--configuration', required=True); p.add_argument('--compact-effects', action='store_true')
    p.add_argument('--filename', default='PSP-Texture-Revision-EXPERIMENTAL.pac')
    p.add_argument('--costume-role', choices=('ring', 'entrance'), default='ring')
    a = p.parse_args()
    r = run(a.work, a.base, a.out, json.loads(Path(a.configuration).read_text()), compact_effects=a.compact_effects,
            filename=a.filename, costume_role=a.costume_role)
    print(json.dumps({k: v for k, v in r.items() if k not in ('textures', 'material_format_manifest')}, indent=2))

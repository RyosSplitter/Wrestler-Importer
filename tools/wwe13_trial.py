"""Reproduce the isolated ch104 bundle-0 PSP compatibility candidate.

Not app integration or QA approval. Reports retain all review findings. No
accepted output is overwritten; the user supplies their own source and PSP base.
"""
from desktop.limits import IN_RING_MAX_PAC_BYTES
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image

from desktop.core import base_model, validate_pac
from desktop.native import serialize
from desktop.precision import bounded_precision
from desktop.skinning import adapt_yobj
from desktop.texture_optimizer.analysis import model_usage
from desktop.texture_optimizer.candidates import read_gim
from model_qa.pipeline import run as run_qa
from tools.jericho_hybrid_trial import pack
from tools.psp_mesh_audit import audit_yobj
from tools.sym_trial import pose_qa
from tools.vertex_identity import protected_face_positions
from tools.wwe13_adapter_trial import source_bundle, adapt_rig, ocular_transfer, chart_atlas
from tools.wwe13_texture_trial import allocate

RATIOS = dict(Head=.25, Torso=.20, Arms=.11, Legs=.10, Hands=.13, Eyes=.08, Mouth=.08, Hair=.07)


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def pad_cranial_palettes(model, target):
    """Conservative native convention, not a claimed engine minimum.

    Add only explicit zero coefficients; effective weights are unchanged.
    Existing writer rebuilds stride, vertex flags, palette and pointer metadata.
    """
    result = copy.deepcopy(model); tb = {b['name']: b['index'] for b in target['bones']}
    changes = []
    for mesh in result['meshes']:
        if len(mesh['bone_palette']) >= 3:
            continue
        names = [target['bones'][i]['name'] for i in mesh['bone_palette']]
        if not all(n in ('atama', 'd_kuchi', 'kubi') for n in names):
            raise ValueError('Unreviewed short noncranial palette')
        added = []
        for name in ('atama', 'kubi', 'd_kuchi'):
            if len(mesh['bone_palette']) >= 3:
                break
            if tb[name] not in mesh['bone_palette']:
                mesh['bone_palette'].append(tb[name]); added.append(name)
                for v in mesh['vertices']:
                    v['weights'].append(0.)
        changes.append(dict(mesh=mesh['index'], original_bones=names, added_zero_bones=added))
    return result, dict(changed_meshes=changes, effective_weights_unchanged=True,
        policy='Experimental match to observed 3–8-slot skinned reference convention; 2-slot format is not proven invalid')


def build_native(reduced, target, images):
    packed = pack(reduced, target)
    packed, precision = bounded_precision(packed, protected_face_positions(packed))
    packed, padding = pad_cranial_palettes(packed, target)
    usage = model_usage({2: dict(packed, texture_names=packed['textures'])}, dict(zip(packed['textures'], images)))
    contracts = [dict(bits=8 if usage[n]['head_fraction'] > .15 or image[:, :, 3].min() < 255 else 4,
                      cutout=bool(image[:, :, 3].min() < 255)) for n, image in zip(packed['textures'], images)]
    raw = serialize(packed, target, contracts)
    raw, scalp = adapt_yobj(raw)
    pose = pose_qa(packed, audit_yobj(raw), target)
    from tools.wwe13_pose_trial import hand_probes
    fingers = hand_probes(audit_yobj(raw))
    blocking = [f for f in pose['review_findings'] if f['kind'] in ('analytic-collapse', 'ocular-envelope-review')]
    if blocking:
        raise ValueError('Native analytical pose gate failed: ' + str(blocking))
    return packed, raw, contracts, dict(precision=precision, palette_padding=padding, scalp=scalp, poses=pose, hands=fingers)


def run(source, base_path, out, blender='/usr/bin/blender', *, samples=12000, resolution=128, qa_renders=True, hand_weighted=True):
    source, base_path, out = map(Path, (source, base_path, out))
    original = source.read_bytes(); base, target = base_model(base_path)
    if source.resolve() == base_path.resolve():
        raise ValueError('Source and base must differ')
    out.mkdir(parents=True, exist_ok=False)
    source_model, atlases, materials = source_bundle(original)
    prepared, rig = adapt_rig(source_model, target)
    prepared, ocular = ocular_transfer(source_model, prepared, target)
    charted, images, atlas_report = chart_atlas(prepared, atlases, cell=512)
    for name, value in [('source', source_model), ('prepared', prepared), ('charted', charted),
                        ('source-materials', materials), ('rig', rig), ('ocular', ocular), ('atlas', atlas_report), ('profile', RATIOS)]:
        dump(out / (name + '.json'), value)
    (out/'source-images').mkdir()
    for name, image in zip(charted['textures'], images):
        Image.fromarray(image).save(out/'source-images'/(name+'.png'))
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy(); env['BLENDER_USER_CONFIG'] = str((out/'blender-config').resolve())
    env['BLENDER_USER_EXTENSIONS'] = str((out/'blender-extensions').resolve())
    with (out/'blender.log').open('w') as log:
        subprocess.run([str(blender), '-b', '-t', '2', '--python-exit-code', '1', '--python', str(root/'tools/wwe13_reduce_trial.py'),
                        '--', str((out/'charted.json').resolve()), str((out/'reduced.json').resolve()), str((out/'profile.json').resolve()),
                        *(['--hand-weighted'] if hand_weighted else [])],
                       check=True, env=env, stdout=log, stderr=subprocess.STDOUT)
    reduced = json.loads((out/'reduced.json').read_text())
    packed, raw, contracts, native_report = build_native(reduced, target, images)
    from tools.wwe13_pose_trial import hand_probes
    reference_hands, donor_hands = hand_probes(charted), hand_probes(target)
    hand_envelope = {}
    for name in ('grip','finger-extension','wrist-flex','forearm-twist'):
        source_ratio=reference_hands['tests'][name]['maximum_triangle_area_ratio']
        donor_ratio=donor_hands['tests'][name]['maximum_triangle_area_ratio']
        observed=native_report['hands']['tests'][name]['maximum_triangle_area_ratio']
        limit=1.5*max(source_ratio,donor_ratio)+.25
        hand_envelope[name]=dict(source_maximum_area_ratio=source_ratio,native_base_maximum_area_ratio=donor_ratio,
                                candidate_maximum_area_ratio=observed,provisional_limit=limit,passes=observed<=limit)
    native_report['hand_reference_envelope']=hand_envelope
    if not all(r['passes'] for r in hand_envelope.values()):
        dump(out/'failed-hand-envelope.json',native_report)
        raise ValueError('Hand stress exceeds source/native reference envelope')
    dump(out/'packed.json', packed); dump(out/'native-checks.json', native_report); dump(out/'contracts.json', contracts)
    (out/'candidate.yobj').write_bytes(raw)
    pac, gims, textures = allocate(base, raw, packed, images, contracts, out/'textures')
    native, decoded = validate_pac(pac, base, IN_RING_MAX_PAC_BYTES, accessory_models={}, gim_reader=read_gim)
    if original != source.read_bytes() or base != base_path.read_bytes():
        raise ValueError('An input changed during experiment')
    path = out/'WWE13-Jericho-PSP-EXPERIMENTAL.pac'; path.write_bytes(pac)
    qa = run_qa(out/'charted.json', path, out/'qa', samples=samples, resolution=resolution,
                animations=True, renders=qa_renders, progress=lambda m: print(m, flush=True))
    dump(out/'result.json', dict(pac=path.name, pac_bytes=len(pac), sha256=hashlib.sha256(pac).hexdigest(),
        source_sha256=hashlib.sha256(original).hexdigest(), base_sha256=hashlib.sha256(base).hexdigest(),
        structural_checks_passed=True, native_pose_gate_passed=True, qa_review_findings=len(qa['flags']),
        status='EXPERIMENTAL compatibility candidate; NOT QA-approved or game-tested',
        app_or_accepted_outputs_changed=False))
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--blender', default='/usr/bin/blender')
    parser.add_argument('--qa-samples', type=int, default=12000)
    parser.add_argument('--qa-resolution', type=int, default=128)
    parser.add_argument('--no-qa-renders', action='store_true', help='Run all numerical/pose tests; generate textured views separately')
    parser.add_argument('--uniform-hands', action='store_true', help='A/B control: disable deformation-aware hand retention')
    a = parser.parse_args()
    print(run(a.source, a.base, a.out, a.blender, samples=a.qa_samples, resolution=a.qa_resolution,
              qa_renders=not a.no_qa_renders,hand_weighted=not a.uniform_hands))

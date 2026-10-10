"""Compare experimental reducer outputs without changing accepted artifacts.

Usage: python -m experiments.bpy.compare CASES.json OUTPUT.json
Each case names reference reduced IR, standalone result, existing target PAC,
texture manifest and reference final YOBJ. Inputs are hashed before/after.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np
from desktop.core import base_model
from desktop.native import serialize
from tools.jericho_hybrid_trial import pack
from tools.psp_mesh_audit import audit_yobj


def digest(p):
    return hashlib.file_digest(Path(p).open('rb'), 'sha256').hexdigest()


def compare(case):
    inputs = {key: Path(case[key]) for key in ('reference', 'candidate', 'base', 'textures', 'yobj')}
    hashes = {key: digest(p) for key, p in inputs.items()}
    a, b = [json.loads(inputs[k].read_text()) for k in ('reference', 'candidate')]
    _, base = base_model(inputs['base'])
    entries = json.loads(inputs['textures'].read_text())['textures']
    raw = serialize(pack(b, base), base, entries)
    native = audit_yobj(raw)
    reference_bytes = inputs['yobj'].read_bytes()
    counts = dict(meshes=native['report']['meshes'], vertices=sum(len(m['vertices']) for m in native['meshes']),
                  triangles=native['report']['triangles'], yobj_bytes=len(raw))
    equal_shape = len(a['meshes']) == len(b['meshes']) and all(len(m['vertices'])==len(n['vertices']) for m,n in zip(a['meshes'],b['meshes']))
    changes = {}; maximum = {}
    if equal_shape:
        for field in ('position', 'normal', 'uv', 'weights', 'color'):
            changes[field] = 0; maximum[field] = 0.
            for m, n in zip(a['meshes'], b['meshes']):
                for v, w in zip(m['vertices'], n['vertices']):
                    code = '<' + ('B' if field=='color' else 'f') * len(v[field])
                    changes[field] += struct.pack(code, *v[field]) != struct.pack(code, *w[field])
                    maximum[field] = max(maximum[field], float(np.max(np.abs(np.asarray(v[field])-w[field]))))
    result = dict(label=case['label'], inputs=hashes, counts=counts, exact_json_meshes=a['meshes']==b['meshes'],
        equal_attribute_array_shapes=equal_shape, changed_float32_records=changes, maximum_python_attribute_difference=maximum,
        native_structural_audit='pass', exact_final_yobj=raw==reference_bytes,
        reference_yobj_sha256=hashes['yobj'], candidate_yobj_sha256=hashlib.sha256(raw).hexdigest(),
        conclusion='Native byte identity preserves all static and analytical-pose QA inputs; no new geometric/skinning regression.' if raw==reference_bytes else 'Output differs; requires fresh QA before acceptance.')
    for key, p in inputs.items():
        if digest(p)!=hashes[key]: raise RuntimeError('Experiment changed input: '+str(p))
    return result


if __name__=='__main__':
    output = Path(sys.argv[2])
    if output.exists(): raise FileExistsError(output)
    rows = [compare(case) for case in json.loads(Path(sys.argv[1]).read_text())]
    output.write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(rows, indent=2))
    raise SystemExit(0 if all(r['exact_final_yobj'] for r in rows) else 1)

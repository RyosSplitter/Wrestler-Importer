"""Read-only check of the exact accepted PACs pinned in the developer reference.

Reads separate experiment artifacts from Git when absent in this worktree.
Does not download, modify or repack anything. A missing pinned object requires
fetching the named experiment branch before retrying.
"""
import hashlib
import json
from pathlib import Path
import subprocess

from .pac_inspect import inspect_pac
from .psp_mesh_audit import audit_yobj
from .yukes_bpe import decompress

ROOT = Path(__file__).resolve().parents[1]


def verify():
    manifest = json.loads((ROOT/'docs/hctp-psp/accepted-baselines.json').read_text())
    results = []
    for record in manifest['baselines']:
        path = ROOT/record['path']
        if path.exists():
            raw = path.read_bytes()
        else:
            process = subprocess.run(['git','show',record['commit']+':'+record['path']],
                                     cwd=ROOT,capture_output=True)
            if process.returncode:
                raise RuntimeError('Missing pinned Git artifact; fetch its experiment branch: '+record['label'])
            raw = process.stdout
        if len(raw)!=record['bytes'] or hashlib.sha256(raw).hexdigest()!=record['sha256']:
            raise ValueError('PAC identity mismatch: '+record['label'])
        container = inspect_pac(raw)
        if len(raw)>148000 or len(raw)%2048 or any(s['offset']%16 for s in container['sections']):
            raise ValueError('PAC size/alignment mismatch')
        section = next(s for s in container['sections'] if s['id']==2)
        payload = raw[section['offset']:section['offset']+section['size']]
        yobj = decompress(payload) if payload.startswith(b'BPE ') else payload
        if len(yobj)!=record['yobj_bytes'] or hashlib.sha256(yobj).hexdigest()!=record['yobj_sha256']:
            raise ValueError('YOBJ identity mismatch: '+record['label'])
        report = audit_yobj(yobj)['report']
        if any(report[key]!=value for key,value in record['counts'].items()):
            raise ValueError('Native count mismatch: '+record['label'])
        if path.exists() and path.read_bytes()!=raw:
            raise ValueError('Baseline changed during verification')
        results.append({'label':record['label'],'sha256':record['sha256'],
                        'native_checks_pass':True,'bytes':len(raw)})
    return results


if __name__=='__main__':
    print(json.dumps(verify(),indent=2))

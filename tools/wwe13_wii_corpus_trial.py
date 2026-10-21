"""Reproducible isolated corpus build + comparison QA, never app registration."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from tools.wwe13_wii_corpus import source_bundle
from tools.wwe13_wii_trial import run, dump
from tools.wwe13_wii_texture_refine import candidates
from model_qa.pipeline import run as compare


def trial(source,base,out,index=0,ratio=None,*,samples=6000,hand_floor=.5,arm_floor=None,opposed_normals=False,source_normals=False):
    source,base,out=map(Path,(source,base,out))
    ratio=(.45 if index==0 else .35)if ratio is None else ratio
    result=run(source,base,out,index,ratio=ratio,head_floor=.6,hand_floor=hand_floor,
        mouth_ratio=.6,material_only=True,texture_candidates=candidates,source_reader=source_bundle,
        atlas_options=dict(repeat_safe=True),export_face_floor=True,arm_floor=arm_floor,opposed_normals=opposed_normals,source_normals=source_normals)
    label=re.sub(r'[^A-Za-z0-9_-]+','-',source.stem).strip('-')
    name=f'{label}-variant-{index:02d}-PSP-EXPERIMENTAL.pac'
    (out/result['pac']).rename(out/name);result['pac']=name
    result['source_filename']=source.name
    result['base_sha256']=hashlib.sha256(base.read_bytes()).hexdigest()
    result['experiment_options']=dict(ratio=ratio,head_floor=.6,hand_floor=hand_floor,mouth_ratio=.6,arm_floor=arm_floor,
        material_boundaries=True,repeat_safe_atlas=True,export_face_floor=True,opposed_normals=opposed_normals,source_normals=source_normals)
    result['implementation_sha256']={name:hashlib.sha256(Path(name).read_bytes()).hexdigest()for name in (
        'tools/wwe13_wii_corpus.py','tools/wwe13_wii_trial.py','tools/wwe13_wii_model.py',
        'tools/wwe13_adapter_trial.py','tools/wwe13_reduce_trial.py','tools/blender_reduce.py',
        'tools/wwe13_wii_texture_refine.py','tools/wwe13_texture_trial.py')}
    result['status']='EXPERIMENTAL; native structural/analytical gates passed; source-fidelity QA pending; NOT game-tested'
    dump(out/'result.json',result)
    qa=compare(out/'charted.json',out/name,out/'qa',samples=samples,resolution=128,
        animations=True,renders=False,progress=lambda message:print(message,flush=True))
    result['qa']=dict(reference='Decoded Wii source in adapted PSP bind pose',
        p95_height=qa['rest']['overall']['p95_height'],flags=len(qa['flags']),
        source_fidelity_approved=not bool(qa['unresolved_review']),
        limitation='Analytical poses are not actual source or PSP game clips; no runtime validation')
    result['status']='EXPERIMENTAL; native gates passed; source-fidelity findings retained; NOT game-tested'
    if hashlib.sha256((out/name).read_bytes()).hexdigest()!=result['sha256']:
        raise ValueError('Candidate changed during comparison QA')
    dump(out/'result.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source');p.add_argument('--base',required=True);p.add_argument('--out',required=True)
    p.add_argument('--variant',type=int,default=0);p.add_argument('--ratio',type=float);p.add_argument('--samples',type=int,default=6000);p.add_argument('--hand-floor',type=float,default=.5);p.add_argument('--arm-floor',type=float);p.add_argument('--opposed-normals',action='store_true');p.add_argument('--source-normals',action='store_true')
    a=p.parse_args();print(json.dumps(trial(a.source,a.base,a.out,a.variant,a.ratio,samples=a.samples,hand_floor=a.hand_floor,arm_floor=a.arm_floor,opposed_normals=a.opposed_normals,source_normals=a.source_normals),indent=2),flush=True)

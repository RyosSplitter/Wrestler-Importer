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
from model_qa.geometry import read_model
from model_qa.surface_attributes import compare as compare_attributes
from model_qa.alpha_coverage import report as compare_alpha
from tools.psp_mesh_merge_trial import sections
from tools.pac_inspect import parse_textures
from desktop.texture_optimizer.candidates import read_gim
import numpy as np
from PIL import Image


def trial(source,base,out,index=0,ratio=None,*,samples=6000,hand_floor=.5,arm_floor=None,opposed_normals=False,source_normals=False,costume_role='ring',preserve_uv_seams=False,preserve_hand_transitions=False,uv_island_domains=False):
    source,base,out=map(Path,(source,base,out))
    ratio=(.45 if index==0 else .35)if ratio is None else ratio
    result=run(source,base,out,index,ratio=ratio,head_floor=.6,hand_floor=hand_floor,
        mouth_ratio=.6,material_only=not uv_island_domains,texture_candidates=candidates,source_reader=source_bundle,
        atlas_options=dict(repeat_safe=True),export_face_floor=True,arm_floor=arm_floor,opposed_normals=opposed_normals,source_normals=source_normals,costume_role=costume_role,preserve_uv_seams=preserve_uv_seams,preserve_hand_transitions=preserve_hand_transitions)
    label=re.sub(r'[^A-Za-z0-9_-]+','-',source.stem).strip('-')
    name=f'{label}-variant-{index:02d}-PSP-EXPERIMENTAL.pac'
    (out/result['pac']).rename(out/name);result['pac']=name
    result['source_filename']=source.name
    result['base_sha256']=hashlib.sha256(base.read_bytes()).hexdigest()
    result['experiment_options']=dict(ratio=ratio,head_floor=.6,hand_floor=hand_floor,mouth_ratio=.6,arm_floor=arm_floor,
        material_boundaries=not uv_island_domains,uv_island_domains=uv_island_domains,repeat_safe_atlas=True,export_face_floor=True,opposed_normals=opposed_normals,source_normals=source_normals,costume_role=costume_role,preserve_uv_seams=preserve_uv_seams,preserve_hand_transitions=preserve_hand_transitions)
    result['implementation_sha256']={name:hashlib.sha256(Path(name).read_bytes()).hexdigest()for name in (
        'tools/wwe13_wii_corpus.py','tools/wwe13_wii_trial.py','tools/wwe13_wii_model.py',
        'tools/wwe13_adapter_trial.py','tools/wwe13_reduce_trial.py','tools/blender_reduce.py',
        'tools/wwe13_wii_texture_refine.py','tools/wwe13_texture_trial.py')}
    result['status']='EXPERIMENTAL; native structural/analytical gates passed; source-fidelity QA pending; NOT game-tested'
    dump(out/'result.json',result)
    qa=compare(out/'charted.json',out/name,out/'qa',samples=samples,resolution=128,
        max_pac_bytes=result['budget']['max_pac_bytes'],animations=True,renders=False,progress=lambda message:print(message,flush=True))
    reference=read_model(out/'charted.json')
    images={n:np.array(Image.open(out/'source-images'/(n+'.png')))for n in reference['textures']}
    attributes=compare_attributes(reference,read_model(out/name),images,samples=max(samples,6000))
    dump(out/'qa/surface-attributes.json',attributes)
    table=next(raw for section,raw in sections((out/name).read_bytes())if section['id']==9)
    decoded={}
    for entry in parse_textures(table):
        ix,pal=read_gim(table[entry['offset']:entry['offset']+entry['size']]);decoded[entry['name']]=pal[ix]
    alpha=compare_alpha(reference,images,decoded);dump(out/'qa/opacity-support.json',alpha)
    result['qa']=dict(reference='Decoded Wii source in adapted PSP bind pose',
        p95_height=qa['rest']['overall']['p95_height'],flags=len(qa['flags']),
        source_fidelity_approved=not bool(qa['unresolved_review'])and not attributes['overall']['review']and not alpha['review'],
        opacity_support_review=alpha['review'],
        source_texture_placement_review=attributes['overall']['review'],
        source_texel_displacement_p95=attributes['overall']['source_texel_displacement']['p95'],
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
    p.add_argument('--costume-role',choices=('ring','entrance'),default='ring',help='Explicit costume role; never inferred from variant index')
    p.add_argument('--preserve-uv-seams',action='store_true')
    p.add_argument('--preserve-hand-transitions',action='store_true')
    p.add_argument('--uv-island-domains',action='store_true',help='Experimental source UV-component reducer domains; requires regional regression review')
    a=p.parse_args();print(json.dumps(trial(a.source,a.base,a.out,a.variant,a.ratio,samples=a.samples,hand_floor=a.hand_floor,arm_floor=a.arm_floor,opposed_normals=a.opposed_normals,source_normals=a.source_normals,costume_role=a.costume_role,preserve_uv_seams=a.preserve_uv_seams,preserve_hand_transitions=a.preserve_hand_transitions,uv_island_domains=a.uv_island_domains),indent=2),flush=True)

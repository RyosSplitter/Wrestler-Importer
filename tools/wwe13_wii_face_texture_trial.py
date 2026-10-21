"""Source-bounded facial texture safeguards; isolated texture-only experiment."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
from tools.wwe13_wii_texture_refine import candidates as baseline_candidates,run
from tools.wwe13_texture_trial import encode_occupied
from desktop.texture_optimizer.analysis import model_usage,occupied
from tools.yukes_bpe import compress
from desktop.texture_optimizer.candidates import read_gim
from model_qa.texture_color import head_masks,color_metrics


def candidates(model,images,contracts,progress=print):
    choices,importance,diagnostics=baseline_candidates(model,images,contracts,progress)
    uses=model_usage({2:dict(model,texture_names=model['textures'])},dict(zip(model['textures'],images)))
    for j,(name,source,contract)in enumerate(zip(model['textures'],images,contracts)):
        use=uses[name]
        if contract['cutout'] or diagnostics[j]['ocular_surface'] or use['head_fraction']<=.15:continue
        floor=min(64,min(source.shape[:2]));color_floor=min(64,diagnostics[j]['analysis']['useful_source_colors'])
        mask=occupied(source,use['uv_mask']);rows=[]
        for entry in diagnostics[j]['candidates']:
            if min(entry['width'],entry['height'])<floor or entry['requested_useful_colors']<color_floor:continue
            row=encode_occupied(source,(entry['width'],entry['height']),8,entry['requested_useful_colors'],mask)
            row['entry']['individual_bpe_bytes']=len(compress(row['raw']));rows.append(row)
        if not rows:raise ValueError('No source-bounded face safeguard candidate: '+name)
        rows.sort(key=lambda r:(r['entry']['individual_bpe_bytes'],r['entry']['metrics']['perceptual_loss']))
        frontier=[];loss=float('inf')
        for row in rows:
            if row['entry']['metrics']['perceptual_loss']<loss-1e-10:frontier.append(row);loss=row['entry']['metrics']['perceptual_loss']
        choices[j]=frontier;importance[j]=diagnostics[j]['analysis']['importance_score']*1.5
        diagnostics[j]['face_safeguard']=dict(minimum_axis=floor,minimum_requested_useful_colors=color_floor,
            policy='Restore source-bounded facial spatial/color floor after in-game discoloration feedback; no tint or upscaling')
        diagnostics[j]['frontier']=[r['entry']for r in frontier]
    return choices,importance,diagnostics


def regional_guard(work):
    """Do not pay for a better face by discoloring another cranial UV region."""
    work=Path(work);reference=json.loads((work/'charted.json').read_text())
    source_images={n:np.array(Image.open(work/'source-images'/(n+'.png')))for n in reference['textures']}
    masks=head_masks(reference,source_images);baseline={}
    previous=json.loads((work/'textures/report.json').read_text())
    entries={r['name']:r['selected']for r in previous['textures']}
    for name,mask in masks.items():
        ix,pal=read_gim((work/'textures'/(name+'.gim')).read_bytes())
        baseline[name]=color_metrics(source_images[name],pal[ix],mask)
    primary=max(masks,key=lambda n:int(masks[n].sum()))if masks else None
    prepared=json.loads((work/'prepared.json').read_text());eye_names=set()
    if prepared.get('ocular_atlas_policy',{}).get('selected_triangles',0):
        eye_tid=len(prepared['textures'])-1
        eye_names={c['name']for c in json.loads((work/'atlas.json').read_text())['charts']if c['source_texture']==eye_tid}

    def factory(model,images,contracts,progress=print):
        choices,importance,diagnostics=baseline_candidates(model,images,contracts,progress)
        uses=model_usage({2:dict(model,texture_names=model['textures'])},dict(zip(model['textures'],images)))
        for j,(name,source,contract)in enumerate(zip(model['textures'],images,contracts)):
            if name in eye_names:
                raw=(work/'textures'/(name+'.gim')).read_bytes()
                choices[j]=[dict(raw=raw,entry=entries[name])]
                diagnostics[j]['source_verified_eye_policy']='Keep existing tested eye GIM byte-identical; eye identity comes from original atlas provenance, not transferred amplitudes'
                continue
            if name not in masks or contract['cutout']:continue
            rows=[];rejected=[];floor=min(64,min(source.shape[:2]))if name==primary else 0
            for entry in diagnostics[j]['candidates']:
                if min(entry['width'],entry['height'])<floor:continue
                row=encode_occupied(source,(entry['width'],entry['height']),8,entry['requested_useful_colors'],occupied(source,uses[name]['uv_mask']))
                ix,pal=read_gim(row['raw']);metrics=color_metrics(source,pal[ix],masks[name])
                if any(metrics[k]>baseline[name][k]+.01 for k in ('delta_e76_p95','maximum_local_tile_lab_bias')):
                    rejected.append(dict(width=entry['width'],height=entry['height'],colors=entry['requested_useful_colors'],reason='Worsens an existing cranial color region',color=metrics));continue
                row['entry']['facial_color_qa']=metrics
                row['entry']['individual_bpe_bytes']=len(compress(row['raw']));rows.append(row)
            if not rows:raise ValueError('No nonregressing cranial color candidate: '+name)
            rows.sort(key=lambda r:(r['entry']['individual_bpe_bytes'],r['entry']['metrics']['perceptual_loss']))
            choices[j]=rows;importance[j]=diagnostics[j]['analysis']['importance_score']*1.5
            diagnostics[j]['regional_color_guard']=dict(primary=name==primary,minimum_axis=floor,baseline=baseline[name],rejected=rejected)
        return choices,importance,diagnostics
    return factory


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('work');p.add_argument('--base',required=True);p.add_argument('--out',required=True)
    p.add_argument('--regional-color-guard',action='store_true')
    a=p.parse_args();run(a.work,a.base,a.out,candidate_factory=regional_guard(a.work)if a.regional_color_guard else candidates,filename='HBK-WWE13-Wii-Entrance-Facial-Texture-Trial.pac')

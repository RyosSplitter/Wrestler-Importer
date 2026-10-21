"""Ring feedback texture-only experiment. Accepted YOBJ must remain byte-exact.

This is not a production-default change. Explore useful color count separately
from image dimensions while retaining the original observed T8 render contracts.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image
from desktop.texture_optimizer.analysis import analyze,model_usage,occupied,measure
from desktop.texture_optimizer.candidates import dimensions,OBSERVED_T8_DIMENSIONS,encode,read_gim
from tools.psp_mesh_merge_trial import sections
from tools.wwe13_texture_trial import encode_occupied,allocate
from tools.wwe13_wii_trial import validate_trial,dump
from tools.yukes_bpe import compress


def candidates(model,images,contracts,progress=print):
    usage=model_usage({2:dict(model,texture_names=model['textures'])},dict(zip(model['textures'],images)))
    eyes={b['index']for b in model['bones']if b['name']in ('l_eye','r_eye')}
    eye_area={n:[0.,0.]for n in model['textures']}
    for mesh in model['meshes']:
        for mat in mesh['materials']:
            row=eye_area[model['textures'][mat['texture_id']]]
            for tri in mat['triangles']:
                vs=[mesh['vertices'][i]for i in tri];ps=np.array([v['position']for v in vs]);area=float(np.linalg.norm(np.cross(ps[1]-ps[0],ps[2]-ps[0]))*.5)
                mass=sum(sum(w for b,w in zip(mesh['bone_palette'],v['weights'])if b in eyes)for v in vs)/3
                row[0]+=area*mass;row[1]+=area
    choices=[];importance=[];diagnostics=[]
    for name,source,contract in zip(model['textures'],images,contracts):
        progress('Independent resolution/color candidates: '+name,flush=True)
        use=usage[name];mask=occupied(source,use['uv_mask']);features=analyze(source,use['uv_mask'],use['surface_fraction'])
        ocular=eye_area[name][0]/max(eye_area[name][1],1e-12)>.9
        rows=[]
        for size in dimensions(source.shape[1],source.shape[0]):
            if size not in OBSERVED_T8_DIMENSIONS or min(size)<32:continue
            if ocular and size!=(source.shape[1],source.shape[0]):continue
            if contract['cutout']:
                canonical=np.array(Image.fromarray(source).resize(size,Image.Resampling.LANCZOS));canonical[:,:,3]=np.array(Image.fromarray(source[:,:,3]).resize(size,Image.Resampling.NEAREST));canonical[canonical[:,:,3]==0]=0
                ceiling=max(1,len(np.unique(source[source[:,:,3]>0],axis=0)))+int(np.any(source[:,:,3]==0))
                row=encode(canonical,size,8,min(256,ceiling));ix,pal=read_gim(row['raw'])
                if not np.array_equal(pal[ix][:,:,3],canonical[:,:,3]):raise ValueError('Alpha changed')
                row['entry']['metrics']=measure(source,pal[ix],mask);row['entry']['alpha_policy']='Source-level nearest alpha; no binary conversion'
                row['entry']['source_quality_ceiling']=dict(width=source.shape[1],height=source.shape[0],useful_colors=ceiling)
                rows.append(row)
            else:
                for colors in ((64,128,256)if ocular else(16,32,64,128,256)):
                    rows.append(encode_occupied(source,size,8,colors,mask))
        if not rows:raise ValueError('No legal representation: '+name)
        for row in rows:row['entry']['individual_bpe_bytes']=len(compress(row['raw']))
        rows.sort(key=lambda r:(r['entry']['individual_bpe_bytes'],r['entry']['metrics']['perceptual_loss']))
        frontier=[];loss=float('inf')
        for r in rows:
            if r['entry']['metrics']['perceptual_loss']<loss-1e-10:frontier.append(r);loss=r['entry']['metrics']['perceptual_loss']
        multiplier=1.5 if ocular else .65 if use['head_fraction']>.15 and not contract['cutout'] else 1.25
        choices.append(frontier);importance.append(features['importance_score']*multiplier)
        diagnostics.append(dict(name=name,analysis=features,model_usage={k:v for k,v in use.items()if k!='uv_mask'},
            ocular_surface=ocular,priority_multiplier=multiplier,candidates=[r['entry']for r in rows],frontier=[r['entry']for r in frontier],rejected=[]))
    return choices,importance,diagnostics


def run(work,base_path,out,*,candidate_factory=None,filename='HBK-WWE13-Wii-Ring-Texture-Rebalance.pac'):
    work,base_path,out=map(Path,(work,base_path,out));out.mkdir(parents=True,exist_ok=False)
    accepted=json.loads((work/'result.json').read_text());before=(work/accepted['pac']).read_bytes()
    if hashlib.sha256(before).hexdigest()!=accepted['sha256']:raise ValueError('Baseline PAC hash differs')
    raw=next(r for s,r in sections(before)if s['id']==2)
    if raw!=(work/'candidate.yobj').read_bytes():raise ValueError('Baseline YOBJ differs')
    packed=json.loads((work/'packed.json').read_text());contracts=json.loads((work/'contracts.json').read_text())
    images=[np.array(Image.open(work/'source-images'/(n+'.png')))for n in packed['textures']]
    pac,gims,report=allocate(base_path.read_bytes(),raw,packed,images,contracts,out/'textures',candidate_factory=candidate_factory or candidates)
    checks=json.loads((work/'native-checks.json').read_text());ocular=json.loads((work/'ocular.json').read_text())
    native,gims,structural=validate_trial(pac,base_path.read_bytes(),checks['radius_changes'],ocular['source_controller_pivot_fit'])
    if next(r for s,r in sections(pac)if s['id']==2)!=raw:raise ValueError('Accepted geometry changed')
    old=list(sections(before));new=list(sections(pac));unchanged=[]
    for(s,a),(t,b)in zip(old,new):
        if s['id']!=t['id']:raise ValueError('Section order differs')
        if s['id']!=9:
            if before[s['offset']:s['offset']+s['size']]!=pac[t['offset']:t['offset']+t['size']]:raise ValueError('Non-texture stored section changed')
            unchanged.append(s['id'])
    if Path(filename).name!=filename or Path(filename).suffix.lower()!='.pac':raise ValueError('Unsafe output PAC name')
    (out/filename).write_bytes(pac)
    result=dict(pac=filename,pac_bytes=len(pac),sha256=hashlib.sha256(pac).hexdigest(),baseline_sha256=accepted['sha256'],
        geometry_yobj_sha256=hashlib.sha256(raw).hexdigest(),geometry_yobj_byte_identical=True,unchanged_stored_sections=unchanged,
        source_work=str(work),structural=structural,
        limitations='Reuses accepted geometry. Wii facial/controller and source-shape review findings remain; texture quality needs visual/in-game review.')
    dump(out/'result.json',result);print(json.dumps({k:v for k,v in result.items()if k!='structural'},indent=2),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('work');p.add_argument('--base',required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.work,a.base,a.out)

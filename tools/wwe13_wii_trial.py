"""Isolated Wii ch145 conversion experiment; no production/app registration."""
import argparse,copy,hashlib,json,os,struct,subprocess
from pathlib import Path
import numpy as np
from PIL import Image
from desktop.core import base_model,validate_pac
from desktop.native import serialize
from desktop.precision import bounded_precision
from desktop.skinning import adapt_yobj
from desktop.texture_optimizer.analysis import analyze,measure,model_usage,occupied
from desktop.texture_optimizer.candidates import encode,dimensions,read_gim,OBSERVED_T8_DIMENSIONS
from tools.jericho_hybrid_trial import pack
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.sym_rig import bounds_probe
from tools.sym_trial import pose_qa
from tools.tna_obj_trial import pad_short_prepared,enclose_influences
from tools.vertex_identity import protected_face_positions
from tools.wwe13_adapter_trial import adapt_rig,ocular_transfer,chart_atlas
from tools.wwe13_pose_trial import hand_probes
from tools.wwe13_texture_trial import encode_occupied,allocate
from tools.wwe13_wii_model import source_bundle
from tools.yukes_bpe import compress


def dump(p,v):Path(p).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')


def candidates(model,images,contracts,progress=print):
    uses=model_usage({2:dict(model,texture_names=model['textures'])},dict(zip(model['textures'],images)))
    choices=[];importance=[];diagnostics=[]
    for name,source,contract in zip(model['textures'],images,contracts):
        progress('Wii texture '+name,flush=True)
        use=uses[name];mask=occupied(source,use['uv_mask']);features=analyze(source,use['uv_mask'],use['surface_fraction'])
        rows=[];rejected=[]
        for size in dimensions(source.shape[1],source.shape[0]):
            if size not in OBSERVED_T8_DIMENSIONS or min(size)<32:continue
            if not contract['cutout'] and use['head_fraction']>.15 and min(size)<min(64,min(source.shape[:2])):continue
            if contract['cutout']:
                canonical=np.array(Image.fromarray(source).resize(size,Image.Resampling.LANCZOS))
                canonical[:,:,3]=np.array(Image.fromarray(source[:,:,3]).resize(size,Image.Resampling.NEAREST))
                canonical[canonical[:,:,3]==0]=0
                ceiling=max(1,len(np.unique(source[source[:,:,3]>0],axis=0)))+int(np.any(source[:,:,3]==0))
                row=encode(canonical,size,8,min(256,ceiling))
                ix,pal=read_gim(row['raw']);rgba=pal[ix]
                if not np.array_equal(rgba[:,:,3],canonical[:,:,3]):raise ValueError('Alpha level changed during palette encode')
                row['entry']['metrics']=measure(source,rgba,mask)
                row['entry']['alpha_policy']='Source alpha levels preserved at every retained nearest-alpha sample; RGB Lanczos/per-alpha palette. No binary opacity bake.'
                row['entry']['source_quality_ceiling']=dict(width=source.shape[1],height=source.shape[0],useful_colors=ceiling)
            else:row=encode_occupied(source,size,8,256,mask)
            row['entry']['individual_bpe_bytes']=len(compress(row['raw']));rows.append(row)
        if not rows:raise ValueError('No legal Wii chart candidate '+name)
        rows.sort(key=lambda r:(r['entry']['individual_bpe_bytes'],r['entry']['metrics']['perceptual_loss']))
        frontier=[];loss=float('inf')
        for r in rows:
            if r['entry']['metrics']['perceptual_loss']<loss-1e-10:frontier.append(r);loss=r['entry']['metrics']['perceptual_loss']
        choices.append(frontier);importance.append(features['importance_score'])
        diagnostics.append(dict(name=name,analysis=features,model_usage={k:v for k,v in use.items()if k!='uv_mask'},candidates=[r['entry']for r in frontier],rejected=rejected))
    return choices,importance,diagnostics


def separate_eye_atlas(model,images):
    """Preserve the tiny original iris UV patches without upscaling the atlas."""
    out=copy.deepcopy(model);eyes={b['index']for b in model['bones']if b['name']in ('l_eye','r_eye')};selected=0;eye_tid=len(out['textures'])
    for mesh in out['meshes']:
        new=[]
        for mat in mesh['materials']:
            keep=[];eye=[]
            for tri in mat['triangles']:
                mass=sum(sum(mesh['vertices'][i]['weights'][j]for j in eyes)for i in tri)/3
                (eye if mass>.98 else keep).append(tri)
            if keep:new.append(dict(mat,triangles=keep))
            if eye:
                if mat['texture_id']!=0:raise ValueError('Unreviewed eye texture binding')
                new.append(dict(mat,texture_id=eye_tid,triangles=eye));selected+=len(eye)
        mesh['materials']=new
    if not selected:raise ValueError('No verified source eye surface')
    out['textures']=out['textures']+['wii_eyes'];out['texture_count']=len(out['textures'])
    out['ocular_atlas_policy']=dict(selected_triangles=selected,selection='Average original source eye-bone mass > .98',
        source_image='Exact duplicate binding to original color atlas, locally cropped later without resampling')
    return out,list(images)+[images[0].copy()]


def fit_ocular(source,target,rig):
    from tools.prepare_model import bone_matrices
    out=copy.deepcopy(target);world=bone_matrices(target);sw=bone_matrices(source)
    sb={b['name']:b['index']for b in source['bones']};names=('l_eye','r_eye','l_mabuta','r_mabuta');changes=[]
    wanted=world.copy()
    for b in out['bones']:
        if b['name']in names:wanted[b['index'],:3,3]=sw[sb[b['name']],:3,3]*rig['scale']+rig['translation']
    raw=bytearray(out['bone_raw'])
    for b in out['bones']:
        if b['name']not in names:continue
        i,parent=b['index'],b['parent'];local=np.linalg.inv(wanted[parent])@wanted[i]
        if np.max(np.abs(local[:3,:3]-(np.linalg.inv(world[parent])@world[i])[:3,:3]))>1e-6:raise ValueError('Ocular axes changed')
        pos=np.asarray(local[:3,3],np.float32).tolist();changes.append(dict(bone=b['name'],before=b['local_position'],after=pos))
        struct.pack_into('<3f',raw,i*80+16,*pos);b['local_position']=pos
    out['bone_raw']=bytes(raw)
    return out,changes


def split_uv_islands(model):
    out=copy.deepcopy(model);out['meshes']=[];counts=[]
    for mesh in model['meshes']:
        n=len(mesh['vertices']);parent=list(range(n))
        def root(i):
            while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
            return i
        for mat in mesh['materials']:
            for tri in mat['triangles']:
                for i in tri[1:]:a,b=root(tri[0]),root(i);parent[max(a,b)]=min(a,b)
        buckets={}
        for mat in mesh['materials']:
            for tri in mat['triangles']:buckets.setdefault(root(tri[0]),{}).setdefault(mat['texture_id'],[]).append(tri)
        counts.append(len(buckets))
        for group in buckets.values():
            used=sorted({i for fs in group.values()for t in fs for i in t});mapping={old:i for i,old in enumerate(used)}
            out['meshes'].append(dict(mesh,index=len(out['meshes']),vertices=[copy.deepcopy(mesh['vertices'][i])for i in used],
                materials=[dict(texture_id=tid,triangles=[[mapping[i]for i in t]for t in ts])for tid,ts in group.items()]))
    out['mesh_count']=len(out['meshes']);out['uv_island_protection']=dict(source_mesh_components=counts,
        policy='Independent original UV-index-connected components remain separate reducer meshes, protecting shared position boundaries; no geometry or UV changes')
    return out


def check_bone_metadata(original,candidate,radius_changes,ocular_changes=()):
    allowed=bytearray(original['bone_raw']);names={b['name']:b['index']for b in original['bones']}
    if len({r['bone']for r in ocular_changes})!=len(ocular_changes) or len({r['bone']for r in radius_changes})!=len(radius_changes):raise ValueError('Duplicate metadata manifest')
    for row in ocular_changes:
        if row['bone']not in ('l_eye','r_eye','l_mabuta','r_mabuta') or not np.isfinite(row['after']).all():raise ValueError('Unapproved ocular fit')
        if tuple(row['before'])!=struct.unpack_from('<3f',original['bone_raw'],80*names[row['bone']]+16):raise ValueError('Ocular before-state mismatch')
        struct.pack_into('<3f',allowed,80*names[row['bone']]+16,*row['after'])
    for row in radius_changes:
        i=names[row['bone']];old=struct.unpack_from('<f',allowed,80*i+76)[0]
        if old!=row['before'] or not np.isfinite(row['after']) or row['after']<max(old,row['maximum_influence_distance']):raise ValueError('Invalid nonshrinking bounds manifest')
        struct.pack_into('<f',allowed,80*i+76,row['after'])
    if candidate['bone_raw']!=bytes(allowed):raise ValueError('Unreported native skeleton metadata change')

def validate_trial(data,base,radius_changes,ocular_changes=()):
    native,gims=validate_pac(data,None,148000,accessory_models={},gim_reader=read_gim)
    _,original=base_model_bytes(base)
    check_bone_metadata(original,native,radius_changes,ocular_changes)
    old=list(sections(base));new=list(sections(data))
    if [s['id']for s,r in old]!=[s['id']for s,r in new]:raise ValueError('PAC section layout changed')
    preserved=[]
    for (s,a),(t,b) in zip(old,new):
        if s['id']not in (2,9):
            if base[s['offset']:s['offset']+s['size']]!=data[t['offset']:t['offset']+t['size']]:raise ValueError('Unrelated stored section changed')
            preserved.append(s['id'])
    raw=next(r for s,r in new if s['id']==2)
    bounds=bounds_probe(raw,dict(native,bone_count=len(native['bones'])))
    if bounds['enclosing_active_bones']!=bounds['active_bones']:raise ValueError('Influence enclosure failure')
    return native,gims,dict(pac_bytes=len(data),sector_aligned=len(data)%2048==0,unchanged_stored_sections=preserved,
        skeleton_policy='Names/parents/rotation axes/body binds/sphere centers byte-exact; four reported ocular pivot positions fit to decoded source, plus nonshrinking influence radii',ocular_changes=ocular_changes,radius_changes=radius_changes,bounds=bounds)


def base_model_bytes(base):
    # base_model is path based; recover only the independently audited model.
    return base,audit_yobj(next(r for s,r in sections(base)if s['id']==2))


def run(source,base_path,out,index,ratio=1.,head_floor=.6,hand_floor=.5,mouth_ratio=.6,material_only=False,texture_candidates=None,source_reader=None,atlas_options=None,export_face_floor=False,arm_floor=None,opposed_normals=False,source_normals=False):
    if any(not 0<v<=1 for v in (ratio,head_floor,hand_floor,mouth_ratio)):raise ValueError('Reduction ratios must be in (0,1]')
    if arm_floor is not None and not 0<arm_floor<=1:raise ValueError('Arm floor must be in (0,1]')
    source,base_path,out=map(Path,(source,base_path,out));out.mkdir(parents=True,exist_ok=False)
    data=source.read_bytes();base,target=base_model(base_path)
    original,images,decode=(source_reader or source_bundle)(data,index)
    original,images=separate_eye_atlas(original,images)
    prepared,rig=adapt_rig(original,target)
    fitted_target,eye_binds=fit_ocular(original,target,rig)
    prepared['bones']=copy.deepcopy(fitted_target['bones'])
    prepared,ocular=ocular_transfer(original,prepared,target)
    ocular['source_controller_pivot_fit']=eye_binds
    charted,images,atlas=chart_atlas(prepared,images,cell=256,**(atlas_options or {}))
    charted=split_uv_islands(charted)
    profile=dict(Head=max(head_floor,ratio),Torso=ratio,Arms=max(arm_floor or ratio,ratio),Legs=ratio,Hands=max(hand_floor,ratio),Eyes=1.,Mouth=mouth_ratio if ratio<1 else 1.,Hair=1.)
    for name,value in [('source',original),('prepared',prepared),('charted',charted),('source-materials',decode),('rig',rig),('ocular',ocular),('atlas',atlas),('profile',profile)]:dump(out/(name+'.json'),value)
    (out/'source-images').mkdir()
    for n,im in zip(charted['textures'],images):Image.fromarray(im).save(out/'source-images'/(n+'.png'))
    if ratio<1:
        env=os.environ.copy();env['BLENDER_USER_CONFIG']=str((out/'blender-config').resolve())
        with (out/'blender.log').open('w')as log:subprocess.run(['/usr/bin/blender','-b','-t','2','--python-exit-code','1','--python',str(Path('tools/wwe13_reduce_trial.py').resolve()),'--',str((out/'charted.json').resolve()),str((out/'reduced.json').resolve()),str((out/'profile.json').resolve()),'--hand-weighted','--material-boundaries' if material_only else '--uv-islands']+(['--export-face-floor']if export_face_floor else [])+(['--opposed-normals']if opposed_normals else [])+(['--source-normals']if source_normals else []),check=True,env=env,stdout=log,stderr=subprocess.STDOUT)
        reduced=json.loads((out/'reduced.json').read_text())
    else:reduced=charted
    fitted,radii=enclose_influences(fitted_target,reduced)
    packed=pad_short_prepared(pack(reduced,fitted))
    packed,precision=bounded_precision(packed,protected_face_positions(packed),divisions=65536)
    contracts=[dict(bits=8,cutout=bool(im[:,:,3].min()<255))for im in images]
    raw=serialize(packed,fitted,contracts);raw,padding=adapt_yobj(raw);native=audit_yobj(raw)
    checks=dict(precision=precision,padding=padding,poses=pose_qa(packed,native,target),hands=hand_probes(native),reference_hands=hand_probes(charted),radius_changes=radii)
    donor_hands=hand_probes(target);envelope={}
    for name in ('grip','finger-extension','wrist-flex','forearm-twist'):
        control=checks['reference_hands']['tests'][name]['maximum_triangle_area_ratio'];donor=donor_hands['tests'][name]['maximum_triangle_area_ratio'];value=checks['hands']['tests'][name]['maximum_triangle_area_ratio'];limit=1.5*max(control,donor)+.25
        envelope[name]=dict(candidate=value,source_reference=control,native_donor=donor,limit=limit,passes=value<=limit)
    checks['hand_reference_envelope']=envelope
    for name,value in [('packed',packed),('contracts',contracts),('native-checks',checks)]:dump(out/(name+'.json'),value)
    if any(f['kind']in ('analytic-collapse','ocular-envelope-review')for f in checks['poses']['review_findings']) or not all(r['passes']for r in envelope.values()):
        raise ValueError('Native analytical pose gate failed; candidate retained for diagnosis only')
    (out/'candidate.yobj').write_bytes(raw)
    print('Native model expanded',len(raw),'compressed',len(compress(raw)),flush=True)
    pac,gims,tex=allocate(base,raw,packed,images,contracts,out/'textures',candidate_factory=texture_candidates or candidates)
    final,gims,structural=validate_trial(pac,base,radii,eye_binds);dump(out/'structural.json',structural)
    filename=('HBK-WWE13-Wii-Ring'if index==0 else'HBK-WWE13-Wii-Entrance')+'-PSP-EXPERIMENTAL.pac'
    (out/filename).write_bytes(pac)
    result=dict(pac=filename,pac_bytes=len(pac),sha256=hashlib.sha256(pac).hexdigest(),source_sha256=hashlib.sha256(data).hexdigest(),variant=index,
        source_triangles=original['triangle_count'],final_triangles=sum(len(a['triangles'])for m in final['meshes']for a in m['materials']),final_vertices=sum(len(m['vertices'])for m in final['meshes']),final_meshes=len(final['meshes']),textures=len(gims),structural_checks_passed=True,
        status='EXPERIMENTAL; analytical QA pending; not game-tested',source_blood_draws_excluded=decode['excluded_effects'])
    dump(out/'result.json',result);print(json.dumps(result,indent=2),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('--base',required=True);p.add_argument('--out',required=True);p.add_argument('--variant',type=int,choices=(0,1),required=True);p.add_argument('--ratio',type=float,default=1.);p.add_argument('--head-floor',type=float,default=.6);p.add_argument('--hand-floor',type=float,default=.5);p.add_argument('--mouth-ratio',type=float,default=.6);p.add_argument('--material-only',action='store_true')
    a=p.parse_args();run(a.source,a.base,a.out,a.variant,a.ratio,a.head_floor,a.hand_floor,a.mouth_ratio,a.material_only)

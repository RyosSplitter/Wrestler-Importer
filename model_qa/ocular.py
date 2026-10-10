"""Controller compatibility probes using original-rig and PSP-baseline evidence.

Named bones are not assumed to share animation semantics. These diagnostic
rotations/translations are synthetic stress poses, not captured game animations.
"""
import copy
import json
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw
from scipy.spatial import cKDTree

from .geometry import AXES,align_reference,geometry,read_model
from .render import camera,raster
from tools.prepare_model import bone_matrices
from tools.weight_trial_review import rotation

OCULAR_NAMES=('l_eye','r_eye','l_mabuta','r_mabuta')

def probes():
    result={'rest':dict(frame='world',controls={})}
    for axis in 'xyz':
        for angle in (-25,25):
            result[f'eyes-world-{axis}-{angle}']=dict(frame='world',controls={n:dict(rotate=[axis,angle]) for n in ('l_eye','r_eye')})
    for side in ('l','r'):
        result[side+'-eye-local-turn']=dict(frame='local',controls={side+'_eye':dict(rotate=['y',25])})
        result[side+'-lid-local-close']=dict(frame='local',controls={side+'_mabuta':dict(rotate=['x',30])})
    for axis in 'xyz':
        result['ocular-local-translate-'+axis]=dict(frame='local',controls={n:dict(translate=[axis,.10]) for n in OCULAR_NAMES})
    result['eye-lid-neck-jaw']=dict(frame='local',controls={
        'l_eye':dict(rotate=['y',20]),'r_eye':dict(rotate=['y',20]),
        'l_mabuta':dict(rotate=['x',25]),'r_mabuta':dict(rotate=['x',25]),
        'kubi':dict(rotate=['y',20]),'d_kuchi':dict(rotate=['x',18])})
    # PSP has more eyebrow controllers than this HCTP source. Never invent an
    # equivalent source motion: report it as unsupported on the original rig.
    result['psp-brow-local']=dict(frame='local',controls={n:dict(rotate=['x',15]) for n in ('l_mayu_02','r_mayu_02')})
    return result

def skin(g,probe):
    rest=bone_matrices(g.model);cache={};names=set(g.bone_names)
    unsupported=sorted(set(probe['controls'])-names)
    def world(i):
        if i not in cache:
            b=g.model['bones'][i];parent=b['parent']
            local=rest[i] if parent==-1 else np.linalg.inv(rest[parent])@rest[i]
            motion=np.eye(4);control=probe['controls'].get(b['name'],{})
            if 'rotate' in control:
                r=rotation(*control['rotate'])
                if probe['frame']=='world':r=rest[i][:3,:3].T@r@rest[i][:3,:3]
                motion[:3,:3]=r
            if 'translate' in control:
                axis,amount=control['translate'];v=np.eye(3)['xyz'.index(axis)]*amount
                if probe['frame']=='world':v=rest[i][:3,:3].T@v
                motion[:3,3]=v
            cache[i]=local@motion if parent==-1 else world(parent)@local@motion
        return cache[i]
    matrices=np.array([world(i) for i in range(len(rest))])@np.linalg.inv(rest)
    homogeneous=np.column_stack((g.vertices@AXES,np.ones(len(g.vertices))))
    vertices=sum(g.weights[:,i,None]*(homogeneous@matrix.T)[:,:3] for i,matrix in enumerate(matrices))@AXES
    if not np.isfinite(vertices).all():raise ValueError('Nonfinite ocular stress pose')
    result=copy.copy(g);result.vertices=vertices
    return result,unsupported

def align_posed(g,alignment):
    result=copy.copy(g);native=g.vertices@AXES
    result.vertices=(alignment['scale']*native@np.asarray(alignment['rotation']).T+alignment['translation'])@AXES
    return result

def stats(values,height):
    a=np.asarray(values)
    return dict(samples=len(a),mean=float(a.mean()),p95=float(np.percentile(a,95)),
                maximum=float(a.max()),p95_height=float(np.percentile(a,95)/height))

def evaluate(source,previous,jaw,candidate,*,texture=None,render_folder=None):
    aligned,fit=align_reference(source,candidate)
    ref,sg=geometry(aligned),geometry(source)
    gs=[geometry(m) for m in (previous,jaw,candidate)]
    a,b,c=gs;height=ref.height
    if not np.array_equal(a.vertices,b.vertices) or not np.array_equal(b.vertices,c.vertices):
        raise ValueError('PSP topology correspondence requires equal frozen positions')
    if not np.array_equal(a.faces,b.faces) or not np.array_equal(b.faces,c.faces):
        raise ValueError('PSP topology correspondence requires equal faces')
    textures={texture} if texture else {n for n in set(b.face_textures)&set(ref.face_textures) if n.lower().endswith('_eye')}
    if not textures:raise ValueError('Specify a verified eye material/texture selector')
    ids=np.unique(b.faces[np.isin(b.face_textures,list(textures))])
    source_ids=np.unique(ref.faces[np.isin(ref.face_textures,list(textures))])
    distance,index=cKDTree(ref.vertices[source_ids]).query(b.vertices[ids])
    if distance.max()>height*1e-7:raise ValueError('Original eye-position correspondence was not verified')
    corresponding=source_ids[index]
    ocular=[i for i,n in enumerate(b.bone_names) if n in OCULAR_NAMES]
    selected=b.weights[:,ocular].sum(1)>1e-7
    jaw_ids=[i for i,n in enumerate(b.bone_names) if n=='d_kuchi' or n.startswith('d_kuchi_')]
    jaw_mask=b.weights[:,jaw_ids].sum(1)>1e-7
    tolerance=height*1e-7 # exact baseline replay; allowance only for arithmetic roundoff
    metrics={};renders=[]
    for name,probe in probes().items():
        posed_source,unsupported=skin(sg,probe);rp=align_posed(posed_source,fit)
        pa,pb,pc=[skin(g,probe)[0] for g in gs]
        bad=np.linalg.norm(pb.vertices[ids]-pa.vertices[ids],axis=1)
        fixed=np.linalg.norm(pc.vertices[ids]-pa.vertices[ids],axis=1)
        untouched=np.linalg.norm(pc.vertices[~selected]-pb.vertices[~selected],axis=1)
        jaw_delta=np.linalg.norm(pc.vertices[jaw_mask]-pb.vertices[jaw_mask],axis=1)
        metrics[name]=dict(probe=probe,unsupported_source_controllers=unsupported,
            jaw_experiment_vs_previous_eye_motion=stats(bad,height),candidate_vs_previous_eye_motion=stats(fixed,height),
            jaw_experiment_flagged=bool(bad.max()>tolerance),candidate_passes=bool(fixed.max()<=tolerance),
            outside_selected_max_delta=float(untouched.max()),jaw_preservation_max_delta=float(jaw_delta.max()),
            original_own_rig_vs_previous=stats(np.linalg.norm(rp.vertices[corresponding]-pa.vertices[ids],axis=1),height) if not unsupported else None,
            original_own_rig_vs_jaw_experiment=stats(np.linalg.norm(rp.vertices[corresponding]-pb.vertices[ids],axis=1),height) if not unsupported else None,
            original_own_rig_vs_candidate=stats(np.linalg.norm(rp.vertices[corresponding]-pc.vertices[ids],axis=1),height) if not unsupported else None)
        if untouched.max()>tolerance or jaw_delta.max()>tolerance:raise ValueError('Non-ocular or jaw motion regressed')
        if render_folder is not None and name in ('rest','eyes-world-x-25','l-eye-local-turn','l-lid-local-close','ocular-local-translate-z','eye-lid-neck-jaw'):
            folder=Path(render_folder);folder.mkdir(parents=True,exist_ok=True)
            # Controller/source-eye anchors determine the crop; no candidate fit.
            eyep=ref.vertices[source_ids];lo=eyep.min(0)-np.array([.3,.55,.3]);hi=eyep.max(0)+np.array([.3,.55,.3])
            framing_mask=np.all((ref.vertices>=lo)&(ref.vertices<=hi),axis=1)
            frame=rp.vertices[framing_mask]
            for view in ('front','left','front-left'):
                cam=camera(frame,view,420);image=Image.new('RGB',(1680,476),(24,24,24));draw=ImageDraw.Draw(image)
                labels=['Original HCTP rig','Previous PSP (jaw broken)','Jaw-fixed PSP (eyes reported bad)','Selective eye candidate']
                for i,(g,label) in enumerate(zip((rp,pa,pb,pc),labels)):
                    image.paste(Image.fromarray(raster(g,cam)['rgb']),(i*420,32));draw.text((i*420+8,10),label,fill='white')
                draw.text((8,458),name+' / '+view+' | Synthetic QA clay pose; identical cameras and lights',fill='white')
                filename=name+'-'+view+'.png';image.save(folder/filename)
                renders.append(dict(pose=name,view=view,file='renders/'+filename,camera=cam.describe()))
    return dict(status='pass' if all(m['candidate_passes'] for m in metrics.values()) else 'review',
        height=height,eye_vertex_records=len(ids),selected_records=int(selected.sum()),
        verified_original_eye_position_max_error=float(distance.max()),
        tolerance_units=tolerance,tolerance_basis='Exact replay of previous PSP ocular weights on identical geometry/rig; arithmetic allowance of 1e-7 reference height',
        correspondence='Original eye positions verified after uniform bone-landmark alignment; no unverified source vertex-index correspondence',
        poses=metrics,renders=renders,alignment=fit,
        limitation='Synthetic local/world controller probes are not SVR animation streams. Same-name source controls are diagnostic comparisons, not assumed equivalent semantics. Source comparison may favor neither PSP version in some probes; gameplay-normal PSP eyes provide the compatibility control.')

def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','previous','jaw','candidate','output'):p.add_argument('--'+n,type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    models=[read_model(args.source,source=True)]+[read_model(p) for p in (args.previous,args.jaw,args.candidate)]
    args.output.mkdir(parents=True)
    report=evaluate(*models,render_folder=args.output/'renders')
    (args.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=report['status'],poses=len(report['poses']),
        jaw_experiment_flagged=sum(m['jaw_experiment_flagged'] for m in report['poses'].values()),
        candidate_flags=sum(not m['candidate_passes'] for m in report['poses'].values())),indent=2))

if __name__=='__main__':main()

"""Read-only full-head, culling and facial-controller diagnostics.

No vertex correspondence is assumed, no input is modified, and no PAC is built.
Synthetic probes do not reproduce SVR animation streams or its runtime loader.
"""
import copy
import json
from pathlib import Path

import numpy as np

from .geometry import Surface,align_reference,geometry,read_model,sha
from .ocular import probes,skin
from .render import camera,comparison,raster,save_pair

VIEWS=('front','back','left','right','front-left','back-left')
LIMITS=dict(maximum_surface_error_height=.004,culled_reference_coverage_loss=.02)


def head_mask(g):
    """Select by complete cranial ancestry, before any pose is applied."""
    ids=[]
    for i,b in enumerate(g.model['bones']):
        chain=set();current=i
        while current!=-1:
            if current in chain:raise ValueError('Cyclic skeleton')
            chain.add(current)
            if g.model['bones'][current]['name']=='atama':ids.append(i);break
            current=g.model['bones'][current]['parent']
    if not ids:raise ValueError('Full-head checks require the atama cranial anchor')
    mask=g.weights[:,ids].sum(1)>=.5
    if mask.sum()<3:raise ValueError('Insufficient cranial support')
    return mask


def crop_head(g,mask):
    """Retain triangles touching selected vertices; never edit input records."""
    out=copy.copy(g);selected=mask[g.faces].any(1)
    out.faces=g.faces[selected];out.face_textures=np.asarray(g.face_textures)[selected].tolist()
    return out


def layout_review(model):
    """Report departures from checked native examples, not hardware limits."""
    rows=[]
    for m in model['meshes']:
        if 'base_flag' not in m or m.get('rigid'):continue
        n=len(m['bone_palette'])
        if n<3:
            rows.append(dict(mesh=m['index'],weight_slots=n,stride=m['stride'],
                bone_names=[model['bones'][i]['name'] for i in m['bone_palette']],
                severity='review',kind='unvalidated-small-skinned-palette',
                evidence='The 84 successfully audited uppercase .PAC native references contained skinned palettes of 3–8 slots; their three 1-slot meshes were rigid 0x11ff.',
                interpretation='Observed convention only. Generic PSP GE support does not establish SVR loader compatibility. This is not a proven cause or a mandatory minimum.'))
    return rows


def controller_probes(model):
    result=probes();names={b['name'] for b in model['bones']}
    for name in sorted(names):
        if name.startswith(('l_mayu','r_mayu')):
            for axis in 'xyz':
                result[name+'-local-'+axis]=dict(frame='local',controls={name:dict(rotate=[axis,25])})
    result['head-turn']=dict(frame='local',controls={'atama':dict(rotate=['y',30])})
    result['neck-turn']=dict(frame='local',controls={'kubi':dict(rotate=['y',25])})
    result['jaw-open']=dict(frame='local',controls={'d_kuchi':dict(rotate=['x',18])})
    return result


def compare_head(reference,candidate,reference_bind=None,candidate_bind=None,*,resolution=192,
                 render_folder=None,pose='rest',limits=None):
    limits=dict(LIMITS,**(limits or {}));rb=reference_bind or reference;cb=candidate_bind or candidate
    rm,cm=head_mask(rb),head_mask(cb);height=rb.height
    r,c=crop_head(reference,rm),crop_head(candidate,cm)
    # Select before posing so a spike escaping the reference ROI is still tested.
    _,dist,_=Surface(r,height).nearest(candidate.vertices[cm])
    maximum=float(dist.max()/height)
    normals=c.mesh.face_normals;_,near,ids=Surface(r,height).nearest(c.mesh.triangles_center)
    dot=np.einsum('ij,ij->i',normals,r.mesh.face_normals[ids])
    reversed_ids=np.flatnonzero((dot<-.1)&(near<height*.0015)&(c.mesh.area_faces>height**2*1e-12))
    flags=[]
    if maximum>limits['maximum_surface_error_height']:
        flags.append(dict(region='head',pose=pose,severity='review',kind='head-vertex-outlier',
                          measured=maximum,threshold=limits['maximum_surface_error_height']))
    if len(reversed_ids):
        flags.append(dict(region='head',pose=pose,severity='review',kind='opposed-nearby-head-face-winding',
                          triangles=reversed_ids.tolist(),caveat='Nearby folds/inner shells can legitimately oppose normals; inspect culled renders.'))
    views={};gallery=[]
    frame=rb.vertices[np.unique(r.faces)];worst=0.
    for view in VIEWS:
        cam=camera(frame,view,resolution)
        for cull in ('none','back','front'):
            values=comparison(raster(r,cam,cull=cull),raster(c,cam,cull=cull),cam,height)
            views[view+'-'+cull]=values
            if cull!='none' and values['source_pixels']>=100:
                loss=1-values['source_visible_coverage'];worst=max(worst,loss)
                if loss>limits['culled_reference_coverage_loss']:
                    flags.append(dict(region='head',pose=pose,severity='review',kind='culled-head-coverage-loss',
                        view=view,cull=cull,measured=loss,threshold=limits['culled_reference_coverage_loss']))
            if render_folder is not None and cull in ('none','back'):
                stem=pose+'-head-'+view+'-'+cull
                _,configuration=save_pair(render_folder,stem,r,c,cam,height,cull=cull)
                gallery.append(dict(file='renders/'+stem+'.png',pose=pose,region='head',view=view,camera=configuration))
    return dict(maximum_vertex_error_height=maximum,selected_candidate_records=int(cm.sum()),
        worst_culled_reference_coverage_loss=worst,opposed_nearby_faces=int(len(reversed_ids)),
        views=views,flags=flags,gallery=gallery,
        selection='Cranial ancestry >=50% support selected in bind space; triangles touching this support. Candidate outliers remain selected after posing.',
        limitations='Clay geometry only; alpha/material behavior and native runtime rendering are not emulated. Both winding conventions are diagnostics, not a decoded SVR cull-state rule.')


def run(source_path,candidate_path,output,*,stages=(),resolution=192):
    source_path,candidate_path,output=map(Path,(source_path,candidate_path,output))
    if output.exists():raise FileExistsError('Head QA refuses to overwrite '+str(output))
    if resolution<96:raise ValueError('At least 96-pixel renders required')
    paths=[source_path,candidate_path]+[Path(p) for _,p in stages]
    hashes={str(p.resolve()):sha(p) for p in paths}
    source=read_model(source_path,source=True);target=read_model(candidate_path)
    aligned,fit=align_reference(source,target);reference=geometry(aligned,skeleton=target);candidate=geometry(target)
    output.mkdir(parents=True);folder=output/'renders'
    rest=compare_head(reference,candidate,resolution=resolution,render_folder=folder)
    trace=[]
    for label,path in stages:
        trace.append(dict(label=label,sha256=sha(path),rest=compare_head(reference,geometry(read_model(path)),resolution=resolution)))
    motion={}
    for name,probe in controller_probes(target).items():
        a,missing=skin(reference,probe);b,missing_b=skin(candidate,probe)
        motion[name]=compare_head(a,b,reference,candidate,resolution=resolution,
            render_folder=folder if name in ('head-turn','neck-turn','jaw-open','psp-brow-local','eye-lid-neck-jaw') else None,pose=name)
        motion[name]['probe']=probe;motion[name]['unsupported_controllers']=sorted(set(missing+missing_b))
    native=layout_review(target)
    flags=rest['flags']+[f for p in motion.values() for f in p['flags']]+native
    report=dict(status='review' if flags else 'within-provisional-head-tolerances',
        mode='read-only full-head diagnostics; no automatic correction',inputs=hashes,alignment=fit,
        limits=dict(LIMITS,status='Provisional review thresholds; not calibrated runtime acceptance limits'),
        rest=rest,poses=motion,stage_trace=trace,native_layout_review=native,flags=flags,
        gameplay_status='Not validated. Passing offline metrics cannot exclude the reported SVR runtime scalp corruption.',
        reference_pose_policy='Source ancestor-mapped weights on the same PSP rig. PSP-only facial controllers intentionally test donor-transfer sensitivity, not equivalent HCTP animation semantics.')
    report['inputs_unchanged']=all(sha(p)==hashes[str(p.resolve())] for p in paths)
    if not report['inputs_unchanged']:raise ValueError('A QA input changed during inspection')
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','candidate','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--resolution',type=int,default=192);p.add_argument('--stage',action='append',default=[])
    args=p.parse_args();stages=[]
    for item in args.stage:
        label,sep,path=item.partition('=')
        if not label or not sep or not path:raise ValueError('Stage must be LABEL=TARGET_SPACE_PATH')
        stages.append((label,Path(path)))
    r=run(args.source,args.candidate,args.output,stages=stages,resolution=args.resolution)
    print(json.dumps(dict(status=r['status'],review_flags=len(r['flags']),inputs_unchanged=r['inputs_unchanged'])))


if __name__=='__main__':main()

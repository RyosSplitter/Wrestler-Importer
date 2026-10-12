"""Verify source-authorized coincident skinning using protected face correspondence.

Indices are not assumed to correspond. A face is matched by material name and
cyclic float32 position/UV corners, then its effective global bone weights are
checked. This makes intentional contacts distinguishable from changed copies.
Analytical poses are stress probes, not captured SVR animation clips.
"""
from collections import defaultdict
import struct
import numpy as np
from tools.weight_trial_review import deform

POSES = {
    'standing': {},
    'walk-left': {'l_momo':('x',30),'r_momo':('x',-25),'l_sune':('x',35),'l_ashi':('x',-15)},
    'walk-right': {'r_momo':('x',30),'l_momo':('x',-25),'r_sune':('x',35),'r_ashi':('x',-15)},
    'bend': {'koshi':('x',30),'l_momo':('x',-20),'r_momo':('x',-20)},
    'crouch': {'l_momo':('x',-55),'r_momo':('x',-55),'l_sune':('x',95),'r_sune':('x',95)},
    'toe-flex': {'l_tsumasaki':('x',35),'r_tsumasaki':('x',35),'l_ashi':('x',-20),'r_ashi':('x',-20)},
    'mouth-open': {'d_kuchi':('x',22),'u_kuchi':('x',-10),'l_kuchi':('z',10),'r_kuchi':('z',-10),'kubi':('y',20)},
}


def contact_shape_guards(model):
    """Preserve source volume in pelvic/foot regions containing skin contacts.

    A protected point alone does not protect its surrounding surface: collapse
    can remove volume while retaining that point. Use existing bone/reference
    ROIs only where a source-differing contact actually occurs. No displacement,
    weight edits, character names or hashes select these regions.
    """
    from .geometry import geometry,AXES
    from .regions import regions
    if not any(v.get('skin_locked') for m in model['meshes'] for v in m['vertices']):
        return dict(regions=[],faces=[])
    g=geometry(model);rois=regions(g,model)
    contacts=np.asarray([v['position'] for m in model['meshes'] for v in m['vertices'] if v.get('skin_locked')])@AXES
    locked=[(mesh,v) for mesh in model['meshes'] for v in mesh['vertices'] if v.get('skin_locked')]
    foot_bones={side:{b['index'] for b in model['bones'] if b['name'] in (prefix+'ashi',prefix+'tsumasaki')}
                for side,prefix in (('left','l_'),('right','r_'))}
    active=[name for name in ('pelvis','left-feet','right-feet') if rois[name].mask(contacts).any()]
    for side,bones in foot_bones.items():
        if any(sum(w for b,w in zip(mesh['bone_palette'],v['weights']) if b in bones)>1e-7 for mesh,v in locked):
            if side+'-feet' not in active:active.append(side+'-feet')
    faces=[]
    for mesh in model['meshes']:
        points=np.asarray([v['position'] for v in mesh['vertices']])@AXES
        selected=np.zeros(len(points),dtype=bool)
        for name in active:
            selected|=rois[name].mask(points)
            if name.endswith('-feet'):
                bones=foot_bones[name.split('-')[0]]
                selected|=np.array([sum(w for b,w in zip(mesh['bone_palette'],v['weights']) if b in bones)>1e-7 for v in mesh['vertices']])
        for mat in mesh['materials']:
            for ti,tri in enumerate(mat['triangles']):
                if selected[list(tri)].any():faces.append([mesh['index'],mat['texture_id'],ti])
    return dict(regions=active,faces=faces,policy='Source surfaces frozen only in bone/reference pelvic and foot ROIs containing differing source skinning contacts')


def records(model):
    names=model.get('textures',model.get('texture_names'));points=[];weights=[];ids=[];faces=[];groups=defaultdict(list)
    for mesh in model['meshes']:
        start=len(points)
        for vi,v in enumerate(mesh['vertices']):
            w=np.zeros(len(model['bones']));w[mesh['bone_palette']]=v['weights']
            if not np.isfinite(w).all() or (w<0).any() or w.sum()<=0:raise ValueError('Invalid QA skinning weights')
            weights.append(w/w.sum());points.append(v['position']);ids.append([mesh['index'],vi])
        for mat in mesh['materials']:
            for tri in mat['triangles']:
                corners=[struct.pack('<3f2f',*mesh['vertices'][i]['position'],*mesh['vertices'][i]['uv']) for i in tri]
                rotation=min(range(3),key=lambda i:tuple(corners[i:]+corners[:i]))
                key=(names[mat['texture_id']],tuple(corners[rotation:]+corners[:rotation]))
                rows=[start+i for i in tri];rows=rows[rotation:]+rows[:rotation]
                faces.append((key,rows))
                for i in rows:groups[struct.pack('<3f',*points[i])].append(i)
    groups={p:sorted(set(rows)) for p,rows in groups.items()}
    return np.asarray(points),np.asarray(weights),ids,faces,groups


def compare(reference,candidate,*,poses=None,tolerance=2e-6,strict=True):
    if [b['name'] for b in reference['bones']] != [b['name'] for b in candidate['bones']]:
        raise ValueError('Source-record QA requires the same verified target skeleton')
    from tools.prepare_model import bone_matrices
    if ([b['parent'] for b in reference['bones']] != [b['parent'] for b in candidate['bones']]
            or not np.array_equal(bone_matrices(reference),bone_matrices(candidate))):
        raise ValueError('Source-record QA requires unchanged target bind transforms')
    rp,rw,rids,rf,rg=records(reference);cp,cw,cids,cf,cg=records(candidate)
    if not np.isfinite(rp).all() or not np.isfinite(cp).all():raise ValueError('Nonfinite QA geometry')
    affected={p:rows for p,rows in rg.items() if len(rows)>1 and float(np.ptp(rw[rows],axis=0).max())>tolerance}
    affected=dict(sorted(affected.items(),key=lambda item:min(rids[i] for i in item[1])))
    lookup=defaultdict(list)
    for fi,(key,rows) in enumerate(cf):lookup[key].append((fi,rows))
    matched=defaultdict(set);issues=[];used=set();affected_faces=0
    for key,rows in rf:
        if not any(struct.pack('<3f',*rp[i]) in affected for i in rows):continue
        affected_faces+=1
        options=[(float(np.abs(rw[rows]-cw[other]).max()),fi,other) for fi,other in lookup[key] if fi not in used]
        if not options:
            issues.append(dict(kind='missing-protected-face',texture=key[0],source_records=[rids[i] for i in rows]));continue
        delta,fi,other=min(options,key=lambda x:(x[0],x[1]));used.add(fi)
        for a,b in zip(rows,other):matched[a].add(b)
        if delta>tolerance:issues.append(dict(kind='changed-source-skinning',texture=key[0],maximum_weight_delta=delta,source_records=[rids[i] for i in rows]))
    # A global maximum source gap cannot excuse a new defect at another point.
    # Any new coincident weight divergence needs a matching source branch here.
    for p,rows in cg.items():
        if len(rows)<2 or float(np.ptp(cw[rows],axis=0).max())<=tolerance:continue
        expected=rg.get(p,[])
        for i in rows:
            if not expected or min(float(np.abs(cw[i]-rw[j]).max()) for j in expected)>tolerance:
                issues.append(dict(kind='new-coincident-skinning-inconsistency',position=list(struct.unpack('<3f',p)),candidate_record=cids[i]))
    poses=poses or POSES
    posed_reference={};posed_candidate={}
    skeleton=dict(bones=candidate['bones'],bone_count=len(candidate['bones']))
    for name,pose in poses.items():
        posed_reference[name]=deform(skeleton,rp,rw,pose);posed_candidate[name]=deform(skeleton,cp,cw,pose)
        if not np.isfinite(posed_candidate[name]).all():raise ValueError('Nonfinite source-record pose: '+name)
    locations=[]
    for number,(p,rows) in enumerate(affected.items(),1):
        candidate_rows=sorted({j for i in rows for j in matched[i]})
        observed_rows=cg.get(p,[])
        pose_rows={}
        for name in poses:
            a,b=posed_reference[name],posed_candidate[name]
            errors=[float(np.linalg.norm(a[i]-b[j])) for i in rows for j in matched[i]]
            source_gap=float(np.linalg.norm(a[rows,None]-a[None,rows],axis=2).max())
            candidate_gap=float(np.linalg.norm(b[candidate_rows,None]-b[None,candidate_rows],axis=2).max()) if candidate_rows else None
            observed_gap=float(np.linalg.norm(b[observed_rows,None]-b[None,observed_rows],axis=2).max()) if observed_rows else None
            pose_rows[name]=dict(source_gap=source_gap,candidate_gap=candidate_gap,
                maximum_corresponding_motion_error=max(errors,default=None),
                observed_candidate_gap=observed_gap,observed_gap_error=abs(observed_gap-source_gap) if observed_gap is not None else None,
                gap_error=abs(candidate_gap-source_gap) if candidate_gap is not None else None)
        locations.append(dict(location=number,position=list(struct.unpack('<3f',p)),
            source_records=[dict(mesh=rids[i][0],vertex=rids[i][1],weights={candidate['bones'][b]['name']:float(rw[i,b]) for b in np.flatnonzero(rw[i])},
                                 candidate_records=[cids[j] for j in sorted(matched[i])]) for i in rows],
            matched_records=sum(bool(matched[i]) for i in rows),
            preserved_records=sum(any(float(np.abs(rw[i]-cw[j]).max())<=tolerance for j in matched[i]) for i in rows),
            required_records=len(rows),poses=pose_rows))
        locations[-1]['observed_weight_branches']=[{candidate['bones'][j]['name']:float(w[j]) for j in np.flatnonzero(w)}
                                                 for w in np.unique(cw[observed_rows],axis=0)] if observed_rows else []
        locations[-1]['source_weight_branch_count']=len(np.unique(rw[rows],axis=0))
    result=dict(status='pass' if not issues else 'fail',source_conflicting_locations=len(affected),
        protected_source_faces=affected_faces,matched_source_faces=len(used),issues=issues,locations=locations,
        weight_tolerance=tolerance,maximum_motion_error=max((v['maximum_corresponding_motion_error'] or 0. for l in locations for v in l['poses'].values()),default=0.),
        maximum_gap_error=max((v['gap_error'] or 0. for l in locations for v in l['poses'].values()),default=0.),
        maximum_observed_gap_error=max((v['observed_gap_error'] or 0. for l in locations for v in l['poses'].values()),default=0.),
        correspondence='Verified cyclic float32 position/UV/material faces; no original/native index assumption',
        limitation='Target-skeleton analytical stress poses; actual game animation and controller semantics require PPSSPP validation')
    if strict and issues:raise ValueError('Source skinning validation failed: '+issues[0]['kind'])
    return result

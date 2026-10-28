"""Read-only source-linked UV/material seam diagnostics on serialized exports.

Correspondence is fitted once in bind space, then retained through every pose.
Only virtual corner grouping is used: PAC vertices and weights are never welded.
UVs distinguish the two sides of seams using the same texture. Missing/ambiguous
coverage is reported instead of silently treating an unmeasured seam as closed.
"""
from collections import defaultdict
from itertools import combinations

import numpy as np

from .geometry import distribution
from .material_boundaries import nearest_segments

LIMITS = dict(edge_maximum_height=.003, gap_extra_height=.0002,
              correspondence_height=.003, correspondence_uv=.035)
STRESS_POSES = {
    'seam-wrist-flex': {'l_te':('z',35),'r_te':('z',-35)},
    'seam-forearm-twist': {'l_kote':('x',50),'r_kote':('x',-50)},
    'seam-knee-flex': {'l_sune':('x',95),'r_sune':('x',95)},
}


def inventory(g, height):
    meshes = {m['index']: m for m in g.model['meshes']}
    uv = np.array([meshes[m]['vertices'][v]['uv'] for m,v in g.vertex_records], dtype=float)
    if not np.isfinite(uv).all():
        raise ValueError('Nonfinite UV in export seam audit')
    keys = [tuple(p) for p in np.rint(g.vertices/(height*1e-7)).astype(np.int64)]
    entries = defaultdict(list)
    contacts = defaultdict(dict)
    for texture,tri in zip(g.face_textures,g.faces):
        for i in tri:
            signature = (texture, *np.round(uv[i],7))
            # Keep all records, including same-UV contacts with distinct weights.
            contacts[keys[i]][(int(i),signature)] = (int(i),texture,uv[i])
        for a,b in zip(tri,np.roll(tri,-1)):
            if keys[a] == keys[b]:
                continue
            ka,kb = (keys[a],tuple(np.round(uv[a],7))), (keys[b],tuple(np.round(uv[b],7)))
            entries[(texture,tuple(sorted((ka,kb))))].append((int(a),int(b)))
    # Equal position+UV+material corners are virtually joined, independent of
    # native palette splits, record ordering and mesh indices.
    edges = defaultdict(list)
    for (texture,_),rows in entries.items():
        if len(rows)==1:
            edges[texture].append(rows[0])
    groups = []
    for values in contacts.values():
        rows = list(values.values())
        unique = {}
        for i,texture,coords in rows:
            # Weight-equivalent aliases have the same motion; don't multiply
            # contacts merely because a native palette split duplicates them.
            key = (texture,*np.round(coords,7),*np.round(g.weights[i],7))
            unique.setdefault(key,(i,texture,coords))
        if len(unique)>1:
            groups.append(list(unique.values()))
    return dict(uv=uv, edges={n:np.array(v,dtype=int) for n,v in edges.items()}, contacts=groups)


def match_side(point,texture,uv,g,inv,height):
    edges = inv['edges'].get(texture)
    if edges is None or not len(edges):
        return None
    segments = g.vertices[edges];delta = segments[:,1]-segments[:,0]
    length = np.einsum('ij,ij->i',delta,delta)
    t = np.clip(np.divide(np.einsum('ij,ij->i',point-segments[:,0],delta),length,
                         out=np.zeros(len(edges)),where=length>1e-20),0,1)
    positions = segments[:,0]+t[:,None]*delta
    uvs = inv['uv'][edges[:,0]]*(1-t[:,None])+inv['uv'][edges[:,1]]*t[:,None]
    distances = np.linalg.norm(positions-point,axis=1)/height
    uv_errors = np.linalg.norm(uvs-uv,axis=1)
    valid = (distances<=LIMITS['correspondence_height']) & (uv_errors<=LIMITS['correspondence_uv'])
    if not valid.any():
        return None
    score = distances+uv_errors*.01
    score[~valid] = np.inf
    j = int(np.argmin(score))
    return dict(edge=edges[j].tolist(),t=float(t[j]),distance_height=float(distances[j]),uv_error=float(uv_errors[j]))


def prepare(reference,candidate,height):
    if not np.isfinite(height) or height<=0:
        raise ValueError('Export seam audit requires a positive reference height')
    a,b = inventory(reference,height),inventory(candidate,height)
    contacts=[];missing=defaultdict(int)
    for rows in a['contacts']:
        position=reference.vertices[rows[0][0]]
        matched=[]
        for i,texture,uv in rows:
            side=match_side(position,texture,uv,candidate,b,height)
            if side is None:
                missing[texture]+=1
            matched.append(side)
        pairs=[]
        for x,y in combinations(range(len(rows)),2):
            if matched[x] is None or matched[y] is None:
                continue
            # Same UV/material but different source weight branches cannot be
            # identified just by UV distance. Do not invent correspondence.
            if rows[x][1]==rows[y][1] and np.allclose(rows[x][2],rows[y][2],atol=1e-7,rtol=0):
                missing[rows[x][1]]+=1
                continue
            if matched[x]['edge']==matched[y]['edge'] and abs(matched[x]['t']-matched[y]['t'])<1e-7:
                missing[rows[x][1]]+=1
                continue
            pairs.append(dict(source=[rows[x][0],rows[y][0]],candidate=[matched[x],matched[y]],
                              textures=sorted({rows[x][1],rows[y][1]})))
        if pairs:
            contacts.append(dict(position=position.tolist(),pairs=pairs))
    return dict(reference=a,candidate=b,contacts=contacts,height=height,
                source_contact_locations=len(a['contacts']),unmatched_sides=dict(missing))


def point_on_edge(vertices,side):
    a,b=vertices[side['edge']]
    return a*(1-side['t'])+b*side['t']


def measure(plan,reference,candidate,pose='rest'):
    height=plan['height'];networks={};findings=[]
    for texture in sorted(set(plan['reference']['edges'])|set(plan['candidate']['edges'])):
        ae=plan['reference']['edges'].get(texture,[]);be=plan['candidate']['edges'].get(texture,[])
        row=dict(source_edges=len(ae),candidate_edges=len(be),maximum_height=None)
        if not len(ae) or not len(be):
            row['status']='coverage-changed'
        else:
            a,b=reference.vertices[ae],candidate.vertices[be]
            # Endpoints plus quarter, middle and three-quarter points catch
            # interior cracks and bends hidden by sparse endpoint checks.
            ap=np.concatenate([a[:,0]*(1-t)+a[:,1]*t for t in (0,.25,.5,.75,1)])
            bp=np.concatenate([b[:,0]*(1-t)+b[:,1]*t for t in (0,.25,.5,.75,1)])
            forward,reverse=nearest_segments(ap,b),nearest_segments(bp,a)
            distances=np.r_[forward,reverse]
            row.update(status='measured',distance=distribution(distances,height),
                       maximum_height=float(distances.max()/height),
                       worst_source_point=ap[int(np.argmax(forward))].tolist(),
                       worst_candidate_point=bp[int(np.argmax(reverse))].tolist())
        networks[texture]=row
        if row['status']=='coverage-changed' or row['maximum_height']>LIMITS['edge_maximum_height']:
            findings.append(dict(region='seam:'+texture,pose=pose,kind='export-seam-edge-drift',severity='review',
                seam_texture=texture,coverage=row['status'],maximum_height=row['maximum_height'],
                tolerance=LIMITS['edge_maximum_height'],position=row.get('worst_source_point')))
    worst=[];flagged=0;maximum=0.
    for number,contact in enumerate(plan['contacts']):
        for pair in contact['pairs']:
            i,j=pair['source']
            source_gap=float(np.linalg.norm(reference.vertices[i]-reference.vertices[j]))
            a,b=[point_on_edge(candidate.vertices,s) for s in pair['candidate']]
            gap=float(np.linalg.norm(a-b));extra=max(0.,gap-source_gap)/height
            maximum=max(maximum,extra)
            if extra>LIMITS['gap_extra_height']:
                flagged+=1
                worst.append(dict(location=number,position=contact['position'],posed_position=reference.vertices[i].tolist(),source_gap=source_gap,candidate_gap=gap,
                                  extra_height=extra,textures=pair['textures']))
    # Retain a bounded worst-location list; numeric coverage totals remain exact.
    worst=sorted(worst,key=lambda r:(-r['extra_height'],r['location']))[:24]
    for texture in sorted({t for r in worst for t in r['textures']}):
        r=next(r for r in worst if texture in r['textures'])
        findings.append(dict(region='seam:'+texture,pose=pose,kind='export-seam-local-opening',severity='review',
            seam_texture=texture,position=r['posed_position'],extra_height=r['extra_height'],
            source_gap=r['source_gap'],candidate_gap=r['candidate_gap'],tolerance=LIMITS['gap_extra_height']))
    if pose=='rest':
        for texture,count in sorted(plan['unmatched_sides'].items()):
            findings.append(dict(region='seam:'+texture,pose=pose,kind='export-seam-unmeasured-coverage',
                severity='review',seam_texture=texture,unmatched_sides=count,position=None))
    return dict(pose=pose,networks=networks,source_contact_locations=plan['source_contact_locations'],
                matched_contact_locations=len(plan['contacts']),
                matched_pairs=sum(len(c['pairs']) for c in plan['contacts']),
                unmatched_sides=plan['unmatched_sides'],flagged_pairs=flagged,maximum_extra_gap_height=maximum,
                worst_locations=worst,flags=findings)


def summary(rest,poses):
    results=[rest,*poses.values()];flags=[f for r in results for f in r['flags']]
    return dict(schema='psp-export-seams/1',review_findings=len(flags),
        status='review required' if flags else 'within provisional measured tolerances',
        source_contact_locations=rest['source_contact_locations'],matched_contact_locations=rest['matched_contact_locations'],
        unmatched_sides=sum(rest['unmatched_sides'].values()),poses_checked=len(results),
        maximum_extra_gap_height=max(r['maximum_extra_gap_height'] for r in results),
        limits=LIMITS,rest=rest,poses=poses,
        limitations=['Read-only diagnostics: no geometry, UV, normals, textures or weights are changed.',
            'UV/material boundaries include same-texture islands. Equal corners are virtually joined across native palette splits.',
            'Correspondence is fixed in bind space; each matched source contact pair is compared locally in every pose.',
            'Changed atlases, unmatched sides and ambiguous same-UV weight branches require separate review; coverage is not proof of closure.',
            'Finite boundary samples and analytical poses do not certify every crack, texture-color continuity or game animation.'])


def compare_models(reference,candidate,poses,*,height=None,progress=lambda message:None):
    from .geometry import geometry,posed
    a,b=geometry(reference),geometry(candidate)
    if a.bone_names!=b.bone_names:
        raise ValueError('Export seam reference must use the verified target rig')
    plan=prepare(a,b,height or a.height);rest=measure(plan,a,b);motion={}
    names=set(a.bone_names)
    skipped=[]
    for name,controls in dict(poses,**STRESS_POSES).items():
        if not set(controls)<=names:
            skipped.append(name)
            continue
        progress('Checking export seams: '+name)
        motion[name]=measure(plan,posed(a,controls),posed(b,controls),name)
    result=summary(rest,motion);result['skipped_poses']=skipped
    return result


def brief(report,path):
    return {key:report[key] for key in ('status','review_findings','matched_contact_locations','unmatched_sides','poses_checked')} | {'report':str(path)}

"""Material-edge drift and shared skin seam checks, independent of topology.

Small accessory corners can disappear in whole-body area percentiles. Query
every boundary endpoint and midpoint against the other boundary's segments,
and retain the maximum as well as percentiles. Within each model, verified
bind-position aliases track shared material seams under analytical poses.
"""
from collections import defaultdict

import numpy as np

from .geometry import distribution

DEFAULT_LIMITS = {
    'maximum_height': .003,
    'p95_height': .0015,
    'animation_extra_maximum_height': .002,
    'seam_extra_height': .0002,
    'per_texture': {},
    'status': 'Provisional review floors; matched texture names do not prove equivalent materials',
}


def boundaries(bind, height):
    # Virtual geometric grouping only; the actual model is never welded.
    keys = np.rint(bind.vertices/(height*1e-7)).astype(np.int64)
    keys = [tuple(k) for k in keys]
    uses = defaultdict(set)
    edges = defaultdict(lambda: defaultdict(list))
    for texture, tri in zip(bind.face_textures, bind.faces):
        for i in tri: uses[keys[i]].add(texture)
        for a,b in zip(tri,np.roll(tri,-1)):
            if keys[a] != keys[b]:
                edges[texture][tuple(sorted((keys[a],keys[b])))].append((int(a),int(b)))
    result = {}
    for texture, entries in edges.items():
        pairs = [v[0] for v in entries.values() if len(v)==1]
        points = {keys[i] for pair in pairs for i in pair}
        aliases = defaultdict(list)
        for i,key in enumerate(keys):
            if key in points and len(uses[key])>1: aliases[key].append(i)
        result[texture] = dict(edges=np.asarray(pairs,dtype=int).reshape(-1,2),
            shared_aliases=[ids for ids in aliases.values() if len(ids)>1])
    return result


def edge_samples(vertices, edges):
    segments = vertices[edges]
    return np.concatenate((segments[:,0],segments[:,1],segments.mean(1))),segments


def nearest_segments(points, segments):
    if not len(segments): raise ValueError('No boundary segments to query')
    result=[]
    for offset in range(0,len(points),128):
        p=points[offset:offset+128,None,:];best=np.full(len(p),np.inf)
        for start in range(0,len(segments),512):
            s=segments[start:start+512];a=s[:,0];d=s[:,1]-a
            length=np.einsum('ij,ij->i',d,d)
            t=np.clip(np.divide(np.einsum('nij,ij->ni',p-a,d),length,
                       out=np.zeros((len(p),len(s))),where=length>1e-20),0,1)
            distances=np.linalg.norm(p-(a+t[:,:,None]*d),axis=2)
            best=np.minimum(best,distances.min(1))
        result.append(best)
    return np.concatenate(result)


def seam_gap(vertices, groups):
    return max((float(np.linalg.norm(vertices[ids]-vertices[ids[0]],axis=1).max())
                for ids in groups),default=0.)


def measure(reference,candidate,height,reference_bind=None,candidate_bind=None):
    rb,cb=reference_bind or reference,candidate_bind or candidate
    a,b=boundaries(rb,height),boundaries(cb,height)
    result={}
    for texture in sorted(set(a)|set(b)):
        ae=a.get(texture,{}).get('edges',[]);be=b.get(texture,{}).get('edges',[])
        row=dict(source_edges=len(ae),candidate_edges=len(be),distance=None,
            source_shared_seam_groups=len(a.get(texture,{}).get('shared_aliases',[])),
            candidate_shared_seam_groups=len(b.get(texture,{}).get('shared_aliases',[])),
            source_seam_gap=seam_gap(reference.vertices,a.get(texture,{}).get('shared_aliases',[])),
            candidate_seam_gap=seam_gap(candidate.vertices,b.get(texture,{}).get('shared_aliases',[])))
        if texture not in a or texture not in b:
            row['status']='unmatched-material'
        elif not len(ae) or not len(be):
            row['status']='closed-or-no-boundary' if len(ae)==len(be)==0 else 'boundary-coverage-changed'
        else:
            ap,asegments=edge_samples(reference.vertices,ae);bp,bsegments=edge_samples(candidate.vertices,be)
            forward,reverse=nearest_segments(ap,bsegments),nearest_segments(bp,asegments)
            row.update(status='measured',distance=distribution(np.r_[forward,reverse],height),
                source_to_candidate=distribution(forward,height),candidate_to_source=distribution(reverse,height),
                maximum_height=float(max(forward.max(),reverse.max())/height),
                worst_candidate_point=bp[int(np.argmax(reverse))].tolist(),
                worst_reference_point=ap[int(np.argmax(forward))].tolist(),
                reference_camera_points=np.unique(asegments.reshape(-1,3),axis=0).tolist())
        result[texture]=row
    return dict(materials=result,reference_height=height,method='All material boundary endpoints/midpoints to exact line segments; no source/native vertex-index matching',
        seam_method='Within-model bind-coincident records shared by different materials; virtual grouping at 1e-7 reference height',
        limitations=['Texture-name matching is evidence for comparison, not proof of identical rendering semantics',
                    'Intentional LOD changes, overlays and changed texture atlases require human review',
                    'Boundary sampling does not certify interior geometry or all real game animation poses'])


def detect(result,profile,pose='rest',rest=None,height=1.):
    limits=dict(DEFAULT_LIMITS,**profile.get('material_boundaries',{}));flags=[]
    for texture,row in result['materials'].items():
        bound=dict(limits,**limits.get('per_texture',{}).get(texture,{}));evidence=[]
        if row['distance']:
            if pose=='rest':
                for key,value in (('maximum_height',row['maximum_height']),('p95_height',row['distance']['p95_height'])):
                    if value>bound[key]:evidence.append(dict(metric=key,value=value,tolerance=bound[key]))
            else:
                old=(rest or {}).get('materials',{}).get(texture,{})
                if old.get('distance'):
                    extra=max(0.,row['maximum_height']-old['maximum_height'])
                    if extra>bound['animation_extra_maximum_height']:
                        evidence.append(dict(metric='animation_extra_maximum_height',value=extra,tolerance=bound['animation_extra_maximum_height']))
        extra=max(0.,row['candidate_seam_gap']-row['source_seam_gap'])/height
        if extra>bound['seam_extra_height']:
            evidence.append(dict(metric='seam_extra_height',value=extra,tolerance=bound['seam_extra_height']))
        if evidence or row['status'] in ('boundary-coverage-changed','unmatched-material'):
            flags.append(dict(region='material:'+texture,texture=texture,pose=pose,
                kind='material-boundary-drift' if pose=='rest' else 'material-boundary-pose-or-seam-drift',
                severity='review',evidence=evidence,coverage_status=row['status'],
                interpretation='Small material/accessory edge or seam differs from source; human review required, no automatic model edit'))
    return flags

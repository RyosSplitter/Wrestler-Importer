"""Bidirectional distances, signed depth, curvature and review flags."""
import numpy as np
from .geometry import Surface, curvature, distribution, topology


DEFAULT_PROFILE = {
    'version':1,'status':'Provisional review tolerances; not a game correctness certificate',
    'distance_p95_height':.0015,'distance_p99_height':.004,
    'depth_absolute_p95_height':.003,'inward_depth_p95_height':.002,
    'edge_distance_p95_height':.002,'animation_extra_p95_height':.002,
    'minimum_surface_samples':60,'minimum_render_pixels':100,
    'calibration_cases':[], 'regional':{},
}


def evaluated_points(surface, bind, count, seed):
    points, faces, bary=Surface(bind, bind.height).sample(count, seed)
    current=np.einsum('ni,nij->nj',bary,surface.vertices[surface.faces[faces]])
    return current,points,faces


def measure(reference,candidate,rois,height,reference_bind=None,candidate_bind=None,count=16000,with_curvature=False):
    rb=reference_bind or reference;cb=candidate_bind or candidate
    rs,cs=Surface(reference,height),Surface(candidate,height)
    rp,rbind,rfaces=evaluated_points(reference,rb,count,2718)
    cp,cbind,cfaces=evaluated_points(candidate,cb,count,3141)
    closest,forward,target_ids=cs.nearest(rp)
    _,reverse,_=rs.nearest(cp)
    vertex_closest,vertex_error,vertex_face=rs.nearest(candidate.vertices)
    normal_delta=np.einsum('ij,ij->i',closest-rp,reference.mesh.face_normals[rfaces])
    normal_dot=np.einsum('ij,ij->i',reference.mesh.face_normals[rfaces],candidate.mesh.face_normals[target_ids])
    overall=distribution(np.concatenate((forward,reverse)),height)
    per_region={}
    curvature_points=None
    if with_curvature:
        sample_ids=np.linspace(0,len(rp)-1,min(800,len(rp))).astype(int)
        curvature_points=rbind[sample_ids]
        cr=curvature(reference,rp[sample_ids],height)
        cc=curvature(candidate,closest[sample_ids],height)
    for name,roi in rois.items():
        a,b=roi.mask(rbind),roi.mask(cbind)
        values=np.concatenate((forward[a],reverse[b]))
        report=dict(distance=distribution(values,height),source_to_candidate=distribution(forward[a],height),
                    candidate_to_source=distribution(reverse[b],height),roi=roi.describe())
        vi=np.flatnonzero(roi.mask(cb.vertices))
        worst_vertices=vi[np.argsort(vertex_error[vi])[-6:][::-1]]
        report['worst_candidate_vertex_records']=[dict(mesh=candidate.vertex_records[i][0],vertex=candidate.vertex_records[i][1],
            position=candidate.vertices[i].tolist(),surface_distance=float(vertex_error[i]),nearest_reference_triangle=int(vertex_face[i])) for i in worst_vertices]
        if a.any():
            report['normal_directed_displacement']=dict(p05=float(np.percentile(normal_delta[a],5)),p95=float(np.percentile(normal_delta[a],95)),
                caveat='Relative to original triangle winding; not assumed to be a closed-surface inside/outside test')
            report['surface_normal_angle_degrees_p95']=float(np.percentile(np.degrees(np.arccos(np.clip(abs(normal_dot[a]),0,1))),95))
            ids=np.flatnonzero(a);worst=ids[np.argsort(forward[ids])[-6:][::-1]]
            report['worst_reference_samples']=[dict(position=rp[i].tolist(),distance=float(forward[i]),source_texture=reference.face_textures[rfaces[i]]) for i in worst]
        if a.sum()>=30 and b.sum()>=30:
            sa=np.percentile(rp[a],99,axis=0)-np.percentile(rp[a],1,axis=0)
            sb=np.percentile(cp[b],99,axis=0)-np.percentile(cp[b],1,axis=0)
            report['proportions']=dict(source_width_height_depth=sa.tolist(),candidate_width_height_depth=sb.tolist(),
                ratios=np.divide(sb,sa,out=np.ones(3),where=sa>1e-8).tolist(),
                method='1st-to-99th percentile area-weighted surface spans; approximate region proportions, not vertex-index landmarks')
            report['distance']['p95_reference_region_width_fraction']=float(report['distance']['p95']/sa[0]) if sa[0]>1e-8 else None
        if with_curvature:
            selected=roi.mask(curvature_points)
            report['curvature_change']=distribution(abs(cc[selected]-cr[selected]))
            report['curvature_caveat']='Integrated mean curvature over radius 1.2% of height; topology changes affect this diagnostic'
        per_region[name]=report
    results=dict(overall=overall,regions=per_region,reference_topology=topology(reference,height),candidate_topology=topology(candidate,height),
                 maximum_vertex_surface_error=distribution(vertex_error,height),distance_method='Deterministic area-weighted bidirectional triangle-surface distance; no vertex-index matching',
                 sample_seed=[2718,3141],samples_each_direction=count)
    heat=dict(vertex_error=vertex_error,vertex_source_triangle=vertex_face,vertex_source_closest=vertex_closest)
    return results,heat


def influence_groups(g,rois,height,count=16000):
    roots=[]
    for i,bone in enumerate(g.model['bones']):
        chain=set();current=i
        while current>=0:
            if current in chain:raise ValueError('Cyclic rig hierarchy')
            chain.add(current);current=g.model['bones'][current]['parent']
        names={g.model['bones'][j]['name'] for j in chain}
        roots.append('cranial' if 'atama' in names else 'neck' if 'kubi' in names else 'body')
    surface=Surface(g,height);points,ids,bary=surface.sample(count,1618)
    interpolated=np.einsum('ni,nij->nj',bary,g.weights[g.faces[ids]])
    groups={name:interpolated[:,np.array(roots)==name].sum(1) for name in ('cranial','neck','body')}
    report={}
    for name in ('face','jaw','chin','neck'):
        mask=rois[name].mask(points)
        report[name]=dict(samples=int(mask.sum()),mean_influence_mass={k:float(v[mask].mean()) if mask.any() else None for k,v in groups.items()},
                         method='Area-weighted surface weights classified by bone ancestry; diagnostic only')
    return report


def tolerances(profile,region):
    return dict(profile,**profile.get('regional',{}).get(region,{}))


def detect(results,profile,pose='rest',rest=None):
    flags=[]
    for region,r in results['regions'].items():
        limits=tolerances(profile,region);dist=r['distance'];evidence=[]
        if not dist or dist['samples']<limits['minimum_surface_samples']:
            flags.append(dict(region=region,pose=pose,severity='insufficient-evidence',kind='coverage',reason='Too few area-weighted region samples'))
            continue
        if pose=='rest':
            for metric in ('distance_p95_height','distance_p99_height'):
                key=metric.replace('distance_','');value=dist[key]
                if value>limits[metric]:evidence.append(dict(metric=metric,value=value,tolerance=limits[metric]))
        else:
            baseline=rest['regions'][region]['distance']
            if baseline:
                extra=max(0.,dist['p95_height']-baseline['p95_height'])
                if extra>limits['animation_extra_p95_height']:
                    evidence.append(dict(metric='animation_extra_p95_height',value=extra,tolerance=limits['animation_extra_p95_height'],rest_p95_height=baseline['p95_height']))
        for view,m in r.get('views',{}).items():
            if m['common_surface_pixels']<limits['minimum_render_pixels']:continue
            for metric in ('inward_depth_p95_height','depth_absolute_p95_height','edge_distance_p95_height'):
                value=m.get(metric)
                if pose=='rest' and value is not None and value>limits[metric]:evidence.append(dict(metric=metric,view=view,value=value,tolerance=limits[metric]))
        if evidence:
            ratio=max(e['value']/e['tolerance'] for e in evidence)
            kind='pose-dependent-deformation' if pose!='rest' else 'surface-shape'
            if pose=='rest' and any(e['metric']=='inward_depth_p95_height' for e in evidence):kind='surface-recession-or-concavity'
            flags.append(dict(region=region,pose=pose,kind=kind,severity='high-review' if ratio>=3 else 'review',evidence=evidence,
                interpretation='Suspicious relative to this profile; intentional rig/LOD changes and open surfaces require human review'))
    a,b=results['reference_topology'],results['candidate_topology']
    for key in ('degenerate_triangles','duplicate_geometric_faces','nonmanifold_edges','geometric_components'):
        if b[key]>a[key]:flags.append(dict(region='whole-model',pose=pose,kind=key,severity='review',source=a[key],candidate=b[key],
            interpretation='Increase relative to original; preserve legitimate overlays rather than automatically welding'))
    if pose!='rest' and 'candidate_seams' in results:
        source_gap=results['source_seams']['maximum_gap'];candidate_gap=results['candidate_seams']['maximum_gap']
        if candidate_gap>source_gap+results['reference_height']*.0002:
            flags.append(dict(region='whole-model',pose=pose,kind='coincident-rest-seam-opening',severity='review',source_gap=source_gap,candidate_gap=candidate_gap,
                interpretation='More opening than source-weight control; intentional mouth contacts still require review'))
    return flags


def calibrate(controls):
    """Controls are independently chosen trusted regions, never defective cases."""
    profile=dict(DEFAULT_PROFILE,regional={},calibration_cases=[])
    for label,report,selected in controls:
        profile['calibration_cases'].append(dict(label=label,inputs=report['inputs'],trusted_regions=selected))
        for name in selected:
            data=report['rest']['regions'][name];baseline=data['distance']
            if baseline is None or baseline['samples']<DEFAULT_PROFILE['minimum_surface_samples']:
                raise ValueError('Insufficient trusted calibration samples: '+name)
            thresholds=profile['regional'].setdefault(name,{})
            for key,value in [('distance_p95_height',baseline['p95_height']),('distance_p99_height',baseline['p99_height'])]:
                thresholds[key]=max(thresholds.get(key,0),DEFAULT_PROFILE[key],value*1.5)
            for metric in ('depth_absolute_p95_height','inward_depth_p95_height','edge_distance_p95_height'):
                values=[v[metric] for v in data.get('views',{}).values() if v.get(metric) is not None and v['common_surface_pixels']>=DEFAULT_PROFILE['minimum_render_pixels']]
                if values:thresholds[metric]=max(thresholds.get(metric,0),DEFAULT_PROFILE[metric],max(values)*1.5)
    profile['calibration_method']='Trusted converted regions: 1.5x observed error envelope, with explicit height-relative engineering floors'
    profile['animation_calibration']='No verified animation clips available; animation limits remain provisional engineering floors'
    profile['limitations']=['Small selected-region calibration set; not a statistical guarantee across games or body types',
                            'Do not calibrate using a defect under test or claim an accepted model is defect-free everywhere']
    return profile

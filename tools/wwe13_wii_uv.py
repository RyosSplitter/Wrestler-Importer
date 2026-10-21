"""Rejected ch145 wedge repair experiment; NOT used by the selected pipeline.

Experimental post-decimation UV resampling, geometry/weights unchanged.

Interpolate from the nearest original triangle within the SAME verified source
UV topology domain and material. Never query a different anatomical/UV layer.
"""
import copy
from collections import defaultdict
import numpy as np
from tools.prepare_model import Surface
from tools.vertex_identity import annotate


def restore_uv(source,reduced):
    source=annotate(copy.deepcopy(source));out=copy.deepcopy(reduced);groups=defaultdict(list)
    for mesh in source['meshes']:
        for mat in mesh['materials']:
            for tri in mat['triangles']:
                domains={tuple(mesh['vertices'][i]['skin_domain'])for i in tri}
                if len(domains)!=1:raise ValueError('Triangle crosses source UV domain')
                groups[next(iter(domains)),mat['texture_id']].append((mesh,tri))
    surfaces={}
    for key,rows in groups.items():
        vertices=[];faces=[]
        for mesh,tri in rows:
            start=len(vertices);vertices.extend(mesh['vertices'][i]for i in tri);faces.append([start,start+1,start+2])
        try:surfaces[key]=Surface(dict(meshes=[dict(index=0,vertices=vertices,materials=[dict(triangles=faces)])]))
        except ValueError:pass  # geometric zero-area source component is retained as-is
    moved=held=0;maximum=0.;max_distance=0.
    for mesh in out['meshes']:
        tids=defaultdict(set)
        for mat in mesh['materials']:
            for t in mat['triangles']:
                for i in t:tids[i].add(mat['texture_id'])
        for i,v in enumerate(mesh['vertices']):
            if len(tids[i])!=1:held+=1;continue
            surface=surfaces.get((tuple(v['skin_domain']),next(iter(tids[i]))))
            if surface is None:held+=1;continue
            index,bary,distance=surface.nearest(v['position']);owner,tri=surface.corners[index]
            uv=bary@np.array([owner['vertices'][j]['uv']for j in tri]);delta=float(np.linalg.norm(uv-v['uv']))
            maximum=max(maximum,delta);max_distance=max(max_distance,distance)
            if delta>1e-7:moved+=1
            v['uv']=np.asarray(uv,np.float32).tolist()
    for a,b in zip(reduced['meshes'],out['meshes']):
        if a['materials']!=b['materials']or a['bone_palette']!=b['bone_palette']:raise ValueError('UV transfer changed topology')
        for x,y in zip(a['vertices'],b['vertices']):
            if any(x[k]!=y[k]for k in ('position','normal','weights','color')):raise ValueError('UV transfer changed geometry/skin')
    report=dict(changed_corner_records=moved,held_records=held,maximum_uv_delta=maximum,maximum_source_distance=max_distance,
        method='Barycentric original UV resampling on nearest source triangle in identical verified UV component and material',
        positions_normals_weights_topology_exact=True)
    out['uv_restoration_report']=report
    return out,report

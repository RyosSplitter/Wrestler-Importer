"""Isolated source-surface decimation guard replay; writes YOBJ, never a PAC.

The Blender profile freezes original posterior materials before reduction.
Replay only that guarded patch into the accepted model, preserving unrelated
later fixes. Boundary correspondence is verified by original topology, not an
outward-displacement heuristic. This conservative policy trades faces for shape.
"""
import argparse
from collections import Counter,defaultdict
import copy
import json
from pathlib import Path
import struct

import numpy as np

from .lance_anatomy_restore import boundary,oriented_face_key,position_key
from .prepare_model import Surface
from .psp_mesh_audit import audit_yobj,digest
from .psp_mesh_merge import write_model
from .psp_mesh_merge_trial import sections,write_json
from .stripify import stripify


POSTERIOR=('l-pan2','l-se1')


def replay(baseline,guarded):
    guarded=copy.deepcopy(guarded)
    before=audit_yobj(baseline);after=copy.deepcopy(before)
    names=before['texture_names'];tids={names.index(n) for n in POSTERIOR}
    protected=[m for m in guarded['meshes'] if m.get('region')=='Preserved']
    source=dict(guarded,meshes=protected)
    if {source['textures'][a['texture_id']] for m in protected for a in m['materials']}!=set(POSTERIOR):
        raise ValueError('Guarded worker did not preserve exactly the posterior source materials')
    raw={m['index']:bytearray(m['raw_vertices']) for m in after['meshes']}
    source_rows=defaultdict(list);source_edges=defaultdict(set)
    for m in protected:
        for a in m['materials']:
            tid=a['texture_id']
            for vi in {i for t in a['triangles'] for i in t}:
                v=m['vertices'][vi];source_rows[position_key(v['position'])].append((tid,v))
            for edge in boundary(source,tid):
                source_edges[edge[0]].add(edge[1]);source_edges[edge[1]].add(edge[0])
    changes=[];alias={};superior_boundary={}
    # A collapsed boundary anchor can be identified from its two unchanged
    # neighbours in the original boundary graph. Tiny prior rounding edits are
    # matched only below 1e-5 of height. No nearest-volume displacement is used.
    height=np.ptp(np.array([v['position'] for m in guarded['meshes'] for v in m['vertices']])[:,1])
    for tid in tids:
        se,ce=boundary(source,tid),boundary(before,tid)
        sv={p for e in se for p in e};cv={p for e in ce for p in e}
        sn,cn=defaultdict(set),defaultdict(set)
        for a,b in se:sn[a].add(b);sn[b].add(a)
        for a,b in ce:cn[a].add(b);cn[b].add(a)
        for bad in cv-sv:
            if bad in alias:continue
            bp=np.array(struct.unpack('<3f',bad))
            small=sorted((np.linalg.norm(bp-np.array(struct.unpack('<3f',good))),good) for good in sv-cv)
            if small and small[0][0]<height*1e-5:good=small[0][1];reason='verified source boundary rounding correspondence'
            else:
                choices=[good for good in sv-cv if sn[good]==cn[bad]]
                if len(choices)!=1:raise ValueError('No unique original boundary-topology correspondence')
                good=choices[0];reason='original boundary anchor identified by both unchanged edge neighbours'
                if struct.unpack('<3f',good)[1]<-5:
                    # This is the superior seam into the retained neck/head,
                    # outside the posterior pelvis target. Keep its accepted
                    # geometry rather than pulling an unrelated neck corner.
                    superior_boundary[good]=bad
                    continue
            alias[bad]=(good,reason)
    for m in protected:
        for v in m['vertices']:
            key=position_key(v['position'])
            if key in superior_boundary:v['position']=list(struct.unpack('<3f',superior_boundary[key]))
    affected=set();moved=[]
    for m in after['meshes']:
        for vi,v in enumerate(m['vertices']):
            key=position_key(v['position'])
            if key not in alias:continue
            good,reason=alias[key];offset=vi*m['stride']+4*m['weight_slots']
            raw[m['index']][offset+24:offset+36]=good
            moved.append(dict(mesh=m['index'],vertex=vi,before=v['position'],after=list(struct.unpack('<3f',good)),reason=reason))
            v['position']=list(struct.unpack('<3f',good));affected.add(good)
    # Keep existing seam weight bits; new interior source vertices use the
    # original input-to-decimation weights. The guard does not re-run transfer.
    existing=defaultdict(list)
    for m in after['meshes']:
        for v in m['vertices']:
            w=np.zeros(len(after['bones']));w[m['bone_palette']]=v['weights'];existing[position_key(v['position'])].append(w)
    def source_weight(key,v):
        rows=existing.get(key)
        if rows:
            if any(np.max(abs(w-rows[0]))>2e-6 for w in rows):raise ValueError('Conflicting existing seam weights')
            return rows[0]
        return np.array(v['weights'])
    original_faces=Counter(oriented_face_key(m,t) for m in protected for a in m['materials'] for t in a['triangles'])
    caches=defaultdict(dict);added=[];patch=[]
    for tid in tids:
        candidates=[(m,mi) for m in after['meshes'] for mi,a in enumerate(m['materials']) if a['texture_id']==tid]
        surfaces={(m['index'],mi):Surface(dict(meshes=[dict(m,materials=[copy.deepcopy(m['materials'][mi])])])) for m,mi in candidates}
        faces=defaultdict(list)
        for sm in protected:
            for a in sm['materials']:
                if a['texture_id']!=tid:continue
                for t in a['triangles']:
                    vs=[sm['vertices'][i] for i in t];ws=[source_weight(position_key(v['position']),v) for v in vs]
                    center=np.mean([v['position'] for v in vs],axis=0);options=[]
                    for m,mi in candidates:
                        if any(w[b]>1e-7 for w in ws for b in range(len(w)) if b not in m['bone_palette']):continue
                        _,_,distance=surfaces[m['index'],mi].nearest(center);options.append((distance,m['index'],mi))
                    if not options:raise ValueError('Source guard exceeds existing posterior palettes')
                    _,owner,mi=min(options);m=after['meshes'][owner];indices=[]
                    for v,w in zip(vs,ws):
                        key=(position_key(v['position']),tuple(v['uv']))
                        if key not in caches[owner]:
                            matching=[i for i,x in enumerate(m['vertices']) if position_key(x['position'])==key[0] and np.linalg.norm(np.array(x['uv'])-v['uv'])<1e-5]
                            if matching:index=matching[0]
                            else:
                                record=copy.deepcopy(v);record.update(position=list(struct.unpack('<3f',key[0])),weights=w[m['bone_palette']].tolist())
                                record['color']=[*record['color'][:3],255]
                                data=struct.pack('<'+'f'*len(m['bone_palette'])+'2f4B3f3f',*record['weights'],*record['uv'],*record['color'],*record['normal'],*record['position'])
                                if len(data)!=m['stride']:raise ValueError('Unexpected posterior vertex stride')
                                index=len(m['vertices']);m['vertices'].append(record);raw[owner]+=data
                                added.append(dict(mesh=owner,vertex=index,texture=names[tid],position=record['position']))
                            caches[owner][key]=index
                        indices.append(caches[owner][key]);affected.add(key[0])
                    faces[owner,mi].append(indices);patch.append(dict(mesh=owner,material=mi,source_mesh=sm['index'],source_triangle=t))
        for m,mi in candidates:
            a=m['materials'][mi];ts=faces[m['index'],mi]
            if not ts:raise ValueError('Guard would leave an empty native material')
            h=a['strip_headers'][0]
            if h[:8]!=bytes.fromhex('0300000000000000'):raise ValueError('Unknown posterior primitive state')
            a['triangles']=ts;a['strips']=stripify(ts);a['strip_headers']=[h]*len(a['strips'])
    accum=defaultdict(lambda:np.zeros(3))
    for m in after['meshes']:
        for a in m['materials']:
            for t in a['triangles']:
                ps=np.array([m['vertices'][i]['position'] for i in t]);n=np.cross(ps[1]-ps[0],ps[2]-ps[0])
                for p in ps:accum[position_key(p)]+=n
    normals=[]
    for m in after['meshes']:
        for vi,v in enumerate(m['vertices']):
            key=position_key(v['position']);n=accum[key]
            if key in affected and np.linalg.norm(n)>1e-10:
                n=n/np.linalg.norm(n);offset=vi*m['stride']+4*m['weight_slots']+12
                raw[m['index']][offset:offset+12]=struct.pack('<3f',*n);v['normal']=n.tolist();normals.append([m['index'],vi])
        m['raw_vertices']=bytes(raw[m['index']])
    result=write_model(after,[[i] for i in range(len(after['meshes']))]);checked=audit_yobj(result)
    actual=Counter(oriented_face_key(m,t) for m in checked['meshes'] for a in m['materials'] if a['texture_id'] in tids for t in a['triangles'])
    if actual!=original_faces:raise ValueError('Guarded posterior is not the original source triangle surface')
    moved_set={(x['mesh'],x['vertex']) for x in moved};normal_set=set(map(tuple,normals))
    for a,b in zip(before['meshes'],checked['meshes']):
        for vi in range(len(a['vertices'])):
            x=a['raw_vertices'][vi*a['stride']:(vi+1)*a['stride']];y=b['raw_vertices'][vi*b['stride']:(vi+1)*b['stride']];o=4*a['weight_slots']
            if x[:o+12]!=y[:o+12]:raise ValueError('Existing weights, UV or colors changed')
            if (a['index'],vi) not in moved_set and x[o+24:]!=y[o+24:]:raise ValueError('Unrelated position changed')
            if (a['index'],vi) not in normal_set and x[o+12:o+24]!=y[o+12:o+24]:raise ValueError('Unrelated normal changed')
        for x,y in zip(a['materials'],b['materials']):
            if x['texture_id'] not in tids and x['strips']!=y['strips']:raise ValueError('Unrelated topology changed')
    return result,dict(policy='Freeze original source posterior faces before decimation; no budget redistribution to unrelated anatomy',
        posterior_materials=POSTERIOR,source_faces_preserved=len(list(original_faces.elements())),added_records=added,boundary_correspondence=moved,normal_records=normals,
        retained_superior_seam=[dict(source_position=list(struct.unpack('<3f',a)),retained_position=list(struct.unpack('<3f',b)),reason='Existing upper neck boundary outside posterior-pelvis target retained') for a,b in superior_boundary.items()],
        existing_weight_uv_color_bits_preserved=True,unrelated_triangle_sequences_preserved=True,pac_written=False,
        guarded_reduction_report=guarded['reduction_report'],baseline_yobj_sha256=digest(baseline),candidate_yobj_sha256=digest(result))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',required=True,type=Path);p.add_argument('--guarded',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    raw=next(r for s,r in sections(a.baseline.read_bytes()) if s['id']==2)
    result,report=replay(raw,json.loads(a.guarded.read_text()));a.output.mkdir(parents=True)
    (a.output/'candidate.yobj').write_bytes(result);write_json(a.output/'experiment.json',report)


if __name__=='__main__':main()

"""Pinned source-surface restoration of Lance Storm's posterior torso and trunks.

This is a local asset experiment, not a new automatic conversion policy. Original
HCTP faces replace decimated posterior faces; the existing PSP rig and old
weight records stay intact except for four copies of a relocated boundary
anchor, which recover that source point's weights. Four lost shared boundary points are restored on
adjacent materials, and one collapsed upper-back anchor returns to its source.
"""
import argparse
import copy
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from .hctp_weights import load_hctp_with_weights
from .lance_abs_fix import reference_model
from .lance_waist_fix import SOURCE_SHA256, position_key
from .lance_waist_mirror import triangles
from .lance_rear_waist_fix import dense, posed_view
from .pac_inspect import inspect_pac, parse_textures
from .pac_repack import replace_sections
from .prepare_model import Surface
from .psp_mesh_audit import audit_yobj, digest
from .psp_mesh_merge import write_model
from .psp_mesh_merge_trial import sections, write_preview, write_json, dump_audit
from .texture_convert import read_gim
from .weight_trial_review import deform, skin_matrices
from .yukes_bpe import compress, decompress

BASE_SHA256='f90f7532da39b283bdc9e1cae97aa91b1c3745aec728ea536bf4d538ddbdc844'
BACK=(4,7)


def face_key(mesh, tri):
    return tuple(sorted(position_key(mesh['vertices'][i]['position']) for i in tri))


def oriented_face_key(mesh, tri):
    p=tuple(position_key(mesh['vertices'][i]['position']) for i in tri)
    return min(p,p[1:]+p[:1],p[2:]+p[:2])


def boundary(model, tid):
    counts=Counter()
    for m in model['meshes']:
        for a in m['materials']:
            if a['texture_id']!=tid:continue
            for t in a['triangles']:
                p=[position_key(m['vertices'][i]['position']) for i in t]
                for i,j in ((0,1),(1,2),(2,0)):counts[tuple(sorted((p[i],p[j])))]+=1
    return {e for e,n in counts.items() if n==1}


def source_records(reference, before):
    names={b['name']:b['index'] for b in before['bones']}
    mapping={}
    def mapped(index):
        if index in mapping:return mapping[index]
        b=index
        while reference['bones'][b]['name'] not in names:
            b=reference['bones'][b]['parent']
            if b<0:raise ValueError('Weighted source bone has no PSP ancestor')
        mapping[index]=names[reference['bones'][b]['name']]
        return mapping[index]
    rows=defaultdict(list)
    for m in reference['meshes']:
        for a in m['materials']:
            for vi in {i for t in a['triangles'] for i in t}:
                v=m['vertices'][vi];w=np.zeros(len(before['bones']))
                for b,x in zip(m['bone_palette'],v['weights']):
                    if x:w[mapped(b)]+=x
                w/=w.sum()
                rows[position_key(v['position'])].append(dict(vertex=v,texture=a['texture_id'],weights=w))
    return rows


def repair(raw, reference):
    before=audit_yobj(raw);model=copy.deepcopy(before);src=source_records(reference,before)
    old_dense=defaultdict(list)
    for m in before['meshes']:
        for v in m['vertices']:
            w=np.zeros(len(before['bones']))
            for b,x in zip(m['bone_palette'],v['weights']):w[b]=x
            old_dense[position_key(v['position'])].append(w)
    raw_vertices={m['index']:bytearray(m['raw_vertices']) for m in model['meshes']}
    changes=[];added=[];patch_faces=[];split_faces=[];affected=set();caches=defaultdict(dict)

    def original_for(key,tid):
        rows=[r for r in src[key] if r['texture']==tid]
        if not rows:raise ValueError('Missing material-specific source corner')
        if any(np.linalg.norm(np.array(r['vertex']['uv'])-rows[0]['vertex']['uv'])>1e-5 for r in rows):raise ValueError('Ambiguous source UV seam')
        return rows[0]

    # A collapsed upper-back boundary point prevents the original back patch
    # joining the retained chest material. Recover its exact source anchor on
    # every old vertex copy, restoring that source point's mapped weights too.
    sa=boundary(reference,7);ba=boundary(before,7)
    sk={p for e in sa for p in e};bk={p for e in ba for p in e}
    extra=bk-sk;missing=sk-bk
    if len(extra)!=1:raise ValueError('Unexpected nonoriginal back boundary')
    upper=[p for p in missing if struct.unpack('<3f',p)[1]<-5]
    if len(upper)!=1:raise ValueError('Unexpected upper-back source boundary')
    bad=next(iter(extra));good=upper[0]
    good_weight=src[good][0]['weights']
    if any(np.max(np.abs(r['weights']-good_weight))>1e-6 for r in src[good]):raise ValueError('Conflicting original upper-back anchor weights')
    for m in model['meshes']:
        uses=defaultdict(set)
        for a in m['materials']:
            for i in {j for t in a['triangles'] for j in t}:uses[i].add(a['texture_id'])
        for vi,v in enumerate(m['vertices']):
            if position_key(v['position'])!=bad:continue
            rows=[original_for(good,t) for t in uses[vi] if any(r['texture']==t for r in src[good])]
            if not uses[vi]:raise ValueError('Unused collapsed upper-back record')
            # The converter also assigned this shared anchor to one neck
            # corner. Keep that corner's existing UV; only its position joins
            # the original back/chest boundary again.
            if not rows and uses[vi]!={11}:raise ValueError('Unexpected upper-back adjacent material')
            uv=rows[0]['vertex']['uv'] if rows else v['uv']
            if any(np.linalg.norm(np.array(r['vertex']['uv'])-uv)>1e-5 for r in rows):raise ValueError('Upper-back material UVs conflict')
            offset=vi*m['stride']+4*m['weight_slots']
            local=[float(good_weight[b]) for b in m['bone_palette']]
            if abs(sum(local)-1)>1e-6:raise ValueError('Source upper-back weights cannot fit existing palette')
            raw_vertices[m['index']][vi*m['stride']:offset]=struct.pack('<'+'f'*len(local),*local)
            raw_vertices[m['index']][offset:offset+8]=struct.pack('<2f',*uv)
            raw_vertices[m['index']][offset+24:offset+36]=good
            fields=['position','weights']+(['uv'] if list(uv)!=list(v['uv']) else [])
            changes.append(dict(mesh=m['index'],vertex=vi,fields=fields,before_position=list(v['position']),after_position=list(struct.unpack('<3f',good)),before_uv=list(v['uv']),after_uv=list(uv),
                before_bone_weights={before['bones'][b]['name']:float(x) for b,x in zip(m['bone_palette'],v['weights']) if x},
                after_bone_weights={before['bones'][b]['name']:float(x) for b,x in enumerate(good_weight) if x},reason='original shared upper-back patch boundary and its source weight profile'))
            v['position']=struct.unpack('<3f',good);v['uv']=uv;v['weights']=local;affected.add(good)
    old_dense[good]=[good_weight]

    def weights(key):
        rows=old_dense.get(key) or [r['weights'] for r in src[key]]
        if any(np.max(np.abs(r-rows[0]))>2e-6 for r in rows):raise ValueError('Conflicting seam skin weights')
        return rows[0]

    def vertex(m,tid,key,donor):
        ref=original_for(key,tid);uv=ref['vertex']['uv'];cache=(tid,key,tuple(uv))
        if cache in caches[m['index']]:return caches[m['index']][cache]
        # Reuse existing corner and its UV/weight bits where compatible.
        for vi,v in enumerate(m['vertices']):
            if position_key(v['position'])==key and np.linalg.norm(np.array(v['uv'])-uv)<1e-5:
                caches[m['index']][cache]=vi;return vi
        w=weights(key)
        if any(x>1e-7 and b not in m['bone_palette'] for b,x in enumerate(w)):raise ValueError('Required source weight outside existing palette')
        local=[float(w[b]) for b in m['bone_palette']]
        p=struct.unpack('<3f',key);v=copy.deepcopy(donor);v.update(position=p,uv=uv,normal=ref['vertex']['normal'],weights=local)
        record=struct.pack('<'+'f'*len(local),*local)+struct.pack('<2f4B3f3f',*uv,*donor['color'],*v['normal'],*p)
        if len(record)!=m['stride']:raise ValueError('Unexpected vertex stride')
        vi=len(m['vertices']);m['vertices'].append(v);raw_vertices[m['index']]+=record;caches[m['index']][cache]=vi
        added.append(dict(mesh=m['index'],vertex=vi,texture=before['texture_names'][tid],position=list(p),uv=list(uv),weight_origin='unchanged current vertex at same position' if key in old_dense else 'original HCTP bone-name mapping',bone_weights={before['bones'][b]['name']:float(x) for b,x in enumerate(w) if x}))
        affected.add(key);return vi

    # Restore changed posterior triangles, retaining every already-correct face.
    replacements=defaultdict(list);removed=defaultdict(set);common_counts={}
    for tid in BACK:
        source=[];current=[]
        for m in reference['meshes']:
            for a in m['materials']:
                if a['texture_id']==tid:source.extend((m,t,face_key(m,t)) for t in a['triangles'])
        for m in model['meshes']:
            for mi,a in enumerate(m['materials']):
                if a['texture_id']==tid:current.extend((m,mi,t,face_key(m,t)) for t in a['triangles'])
        ka={k for m,t,k in source};kb={k for m,mi,t,k in current};common_counts[str(tid)]=len(ka&kb)
        for m,mi,t,k in current:
            if k not in ka:removed[(m['index'],mi)].add(tuple(t))
        candidates=[(m,mi) for m in before['meshes'] for mi,a in enumerate(m['materials']) if a['texture_id']==tid]
        surfaces={m['index']:Surface(dict(meshes=[dict(m,materials=[m['materials'][mi]])])) for m,mi in candidates}
        for sm,t,key in source:
            if key in kb:continue
            keys=[position_key(sm['vertices'][i]['position']) for i in t];ws=[weights(k) for k in keys]
            choices=[];center=np.mean([struct.unpack('<3f',k) for k in keys],axis=0)
            for cm,mi in candidates:
                if any(x>1e-7 and b not in cm['bone_palette'] for w in ws for b,x in enumerate(w)):continue
                idx,bary,distance=surfaces[cm['index']].nearest(center)
                donor_mesh,donor_tri=surfaces[cm['index']].corners[idx]
                choices.append((distance,cm['index'],mi,donor_mesh['vertices'][donor_tri[0]]))
            if not choices:raise ValueError('No compatible original posterior palette')
            _,owner,mi,donor=min(choices,key=lambda r:(r[0],r[1]));m=model['meshes'][owner]
            tri=tuple(vertex(m,tid,k,donor) for k in keys);replacements[(owner,mi)].append(tri)
            patch_faces.append(dict(mesh=owner,material=mi,triangle=list(tri),source_mesh=sm['index'],source_triangle=list(t),texture=before['texture_names'][tid]))
            affected.update(keys)

    # Four original side boundary vertices are shared with retained materials.
    # Split only their adjacent collapsed triangles; no front surface rebuild.
    edge_points={}
    for tid,adjacent in ((4,2),(7,6)):
        se=boundary(reference,tid);ce=boundary(model,tid)
        sv={p for e in se for p in e};cv={p for e in ce for p in e}
        neighbors=defaultdict(set)
        for a,b in se:neighbors[a].add(b);neighbors[b].add(a)
        for key in sv-cv:
            if key==good:continue
            ns=neighbors[key]
            if len(ns)!=2 or not ns<=cv:raise ValueError('Expected isolated missing side boundary anchor')
            edge=frozenset(ns)
            if tuple(sorted(ns)) not in ce:raise ValueError('Missing collapsed side boundary edge')
            edge_points[(adjacent,edge)]=key
    if len(edge_points)!=4:raise ValueError('Unexpected side boundary restoration scope')

    strip_changes=[]
    for m in model['meshes']:
        for mi,a in enumerate(m['materials']):
            tid=a['texture_id'];new=[];headers=[];inserted=False;owner=(m['index'],mi)
            for si,(strip,h) in enumerate(zip(a['strips'],a['strip_headers'])):
                ts=triangles(strip);out=[];changed=False
                for t in ts:
                    if t in removed[owner]:
                        changed=True
                        if not inserted:out+=replacements[owner];inserted=True
                        continue
                    keys=[position_key(m['vertices'][i]['position']) for i in t]
                    edge=None
                    for i in range(3):
                        key=edge_points.get((tid,frozenset((keys[i],keys[(i+1)%3]))))
                        if key:edge=(i,key);break
                    if edge is None:out.append(t);continue
                    changed=True;i,key=edge;vi=vertex(m,tid,key,m['vertices'][t[i]])
                    faces=[(t[i],vi,t[(i+2)%3]),(vi,t[(i+1)%3],t[(i+2)%3])];out+=faces
                    split_faces.append(dict(mesh=m['index'],material=mi,before=list(t),after=[list(q) for q in faces],source_boundary_point=list(struct.unpack('<3f',key))))
                    affected.update(keys+[key])
                if changed:
                    if len(ts)!=len(strip)-2:raise ValueError('Affected strip contains degenerate restarts')
                    if h[:8]!=bytes.fromhex('0300000000000000'):raise ValueError('Unknown selected primitive state')
                    new.extend([list(t) for t in out]);headers.extend([h]*len(out));strip_changes.append(dict(mesh=m['index'],material=mi,strip=si))
                else:new.append(strip);headers.append(h)
            if not inserted and replacements[owner]:
                h=a['strip_headers'][0];new.extend([list(t) for t in replacements[owner]]);headers.extend([h]*len(replacements[owner]))
            a['strips']=new;a['strip_headers']=headers;a['triangles']=[t for strip in new for t in triangles(strip)]
    if len(split_faces)!=4:raise ValueError('Side boundary point did not split exactly one adjacent face')

    # Recalculate shared smooth normals only at restored surfaces and their joins.
    normal_sum=defaultdict(lambda:np.zeros(3))
    for m in model['meshes']:
        for a in m['materials']:
            for t in a['triangles']:
                ps=np.array([m['vertices'][i]['position'] for i in t]);n=np.cross(ps[1]-ps[0],ps[2]-ps[0])
                for p in ps:normal_sum[position_key(p)]+=n
    normal_changes=[];bounds_changes=[]
    for m in model['meshes']:
        for vi,v in enumerate(m['vertices']):
            key=position_key(v['position'])
            if key not in affected:continue
            n=normal_sum[key];length=np.linalg.norm(n)
            if length<1e-10:raise ValueError('Restored normal cannot normalize')
            n=n/length;offset=vi*m['stride']+4*m['weight_slots']+12
            raw_vertices[m['index']][offset:offset+12]=struct.pack('<3f',*n)
            if vi<len(before['meshes'][m['index']]['vertices']):normal_changes.append(dict(mesh=m['index'],vertex=vi,before=list(v['normal']),after=n.tolist()))
            v['normal']=n.tolist()
        m['raw_vertices']=bytes(raw_vertices[m['index']])
        cx,cy,cz,radius=struct.unpack_from('<4f',m['raw_header'],48)
        needed=max(math.dist((cx,cy,cz),v['position']) for v in m['vertices'])
        if needed>radius:
            enlarged=np.nextafter(np.float32(needed),np.float32(np.inf)).item();header=bytearray(m['raw_header']);struct.pack_into('<f',header,60,enlarged);m['raw_header']=bytes(header)
            bounds_changes.append(dict(mesh=m['index'],before_radius=radius,after_radius=enlarged))
    result=write_model(model,[[i] for i in range(len(model['meshes']))]);after=audit_yobj(result)
    # Exact local-scope checks, including weight bits for all preexisting records.
    allowed={(r['mesh'],r['vertex']) for r in changes};normals={(r['mesh'],r['vertex']) for r in normal_changes}
    for a,b in zip(before['meshes'],after['meshes']):
        if a['bone_palette']!=b['bone_palette'] or a['opaque']!=b['opaque']:raise ValueError('Native palette/opaque mesh state changed')
        for vi in range(len(a['vertices'])):
            old=a['raw_vertices'][vi*a['stride']:(vi+1)*a['stride']];new=b['raw_vertices'][vi*b['stride']:(vi+1)*b['stride']];o=4*a['weight_slots']
            if (a['index'],vi) not in allowed and old[:o]!=new[:o]:raise ValueError('Unrelated existing weights changed')
            if old[o+8:o+12]!=new[o+8:o+12]:raise ValueError('Existing color/alpha changed')
            if (a['index'],vi) not in allowed and (old[o:o+8]!=new[o:o+8] or old[o+24:]!=new[o+24:]):raise ValueError('Unrelated position or UV changed')
            if (a['index'],vi) not in normals and old[o+12:o+24]!=new[o+12:o+24]:raise ValueError('Unrelated normal changed')
        for mi,(ma,mb) in enumerate(zip(a['materials'],b['materials'])):
            if ma['raw'][:132]!=mb['raw'][:132]:raise ValueError('Material state changed')
            if not removed[(a['index'],mi)] and not replacements[(a['index'],mi)] and not any(r['mesh']==a['index'] and r['material']==mi for r in split_faces):
                if ma['strips']!=mb['strips']:raise ValueError('Unrelated index sequence changed')
                if [h[:8] for h in ma['strip_headers']]!=[h[:8] for h in mb['strip_headers']]:raise ValueError('Unrelated primitive state changed')
    for key in ('bone_raw','texture_raw','model_descriptor_raw'):
        if before[key]!=after[key]:raise ValueError(key+' changed')
    reference_hashes={}
    for tid in BACK:
        source=Counter(oriented_face_key(m,t) for m in reference['meshes'] for a in m['materials'] if a['texture_id']==tid for t in a['triangles'])
        corrected=Counter(oriented_face_key(m,t) for m in after['meshes'] for a in m['materials'] if a['texture_id']==tid for t in a['triangles'])
        if source!=corrected:raise ValueError('Posterior surface is not the original HCTP triangle surface')
        if boundary(reference,tid)!=boundary(after,tid):raise ValueError('Original posterior surface boundary mismatch')
        reference_hashes[str(tid)]=digest(b''.join(b''.join(face) for face in sorted(source.elements())))
        for m in after['meshes']:
            for mat in m['materials']:
                if mat['texture_id']!=tid:continue
                for vi in {i for t in mat['triangles'] for i in t}:
                    v=m['vertices'][vi];w=np.zeros(len(after['bones']))
                    for b,x in zip(m['bone_palette'],v['weights']):w[b]=x
                    reference_weight=original_for(position_key(v['position']),tid)['weights']
                    if np.max(np.abs(w-reference_weight))>2e-6:raise ValueError('Recovered posterior point does not retain original source skinning')
    return result,dict(added_vertex_records=added,moved_boundary_records=changes,normal_records=normal_changes,bounds_changes=bounds_changes,
        restored_faces=patch_faces,adjacent_boundary_splits=split_faces,changed_strips=strip_changes,unchanged_source_faces=common_counts,
        existing_weight_bits_preserved_except_four_relocated_upper_back_copies=True,source_posterior_triangle_surfaces_exact=True,
        source_posterior_oriented_face_hashes=reference_hashes,source_posterior_mapped_weights_match=True)


def animation_checks(model,patch):
    ps,ws=dense(model);groups=defaultdict(list);offsets={};offset=0
    for m in model['meshes']:
        offsets[m['index']]=offset
        for vi,v in enumerate(m['vertices']):
            x,y,z=v['position']
            if -6.1<y<1.0 and abs(x)<2.8:groups[position_key(v['position'])].append(offset+vi)
        offset+=len(m['vertices'])
    poses={'rest':{},'standing':{'l_ninoude':('z',70),'r_ninoude':('z',-70)},
        'forward-bend':{'koshi':('x',-35),'mune':('x',-20)},
        'crouch':{'l_momo':('x',50),'r_momo':('x',50),'l_sune':('x',-95),'r_sune':('x',-95),'koshi':('x',-20),'mune':('x',-10)},
        'side-bend':{'koshi':('z',20),'mune':('z',15)},'waist-twist':{'koshi':('y',30),'mune':('y',15)}}
    names={b['name'] for b in model['bones']}
    if any(k not in names for p in poses.values() for k in p):raise ValueError('Analytical pose references an absent PSP bone')
    for i in range(16):
        swing=math.sin(2*math.pi*i/16)
        poses['walk-%02d'%i]={'l_momo':('x',25*swing),'r_momo':('x',-25*swing),'l_sune':('x',-40*max(0,-swing)),'r_sune':('x',-40*max(0,swing))}
    results={};faces=[(r['mesh'],r['triangle']) for r in patch['restored_faces']]+[(r['mesh'],t) for r in patch['adjacent_boundary_splits'] for t in r['after']]
    for name,pose in poses.items():
        posed=deform(dict(bones=model['bones'],bone_count=len(model['bones'])),ps,ws,pose);mats=skin_matrices(dict(bones=model['bones']),pose)
        gap=max(float(np.max(np.abs(posed[rows]-posed[rows[0]]))) for rows in groups.values() if len(rows)>1)
        if gap>2e-6:raise ValueError('Local seam weight mismatch under '+name+': '+str(gap))
        cosines=[];areas=[]
        for mi,t in faces:
            rows=np.array(t)+offsets[mi];p=ps[rows];q=posed[rows];n=np.cross(p[1]-p[0],p[2]-p[0]);pn=np.cross(q[1]-q[0],q[2]-q[0])
            expected=np.einsum('n,nij->ij',ws[rows].mean(0),mats[:,:3,:3])@n
            cosine=float(np.dot(pn,expected)/(np.linalg.norm(pn)*np.linalg.norm(expected)));area=float(np.linalg.norm(pn)/np.linalg.norm(n))
            if not np.isfinite(cosine) or cosine<=0 or area<1e-6:raise ValueError('Restored face folds/collapses in '+name)
            cosines.append(cosine);areas.append(area)
        results[name]=dict(max_shared_position_gap=gap,minimum_skinned_normal_cosine=min(cosines),minimum_area_ratio=min(areas))
    return results,poses


def surface_comparison(reference,before,after):
    surfaces={}
    for label,model in [('before',before),('after',after)]:
        for tid in BACK:
            meshes=[dict(m,materials=[a for a in m['materials'] if a['texture_id']==tid]) for m in model['meshes'] if any(a['texture_id']==tid for a in m['materials'])]
            surfaces[label,tid]=Surface(dict(meshes=meshes))
    rows=defaultdict(list)
    barys=((1,0,0),(0,1,0),(0,0,1),(1/3,1/3,1/3),(.5,.5,0),(.5,0,.5),(0,.5,.5))
    for m in reference['meshes']:
        for a in m['materials']:
            tid=a['texture_id']
            if tid not in BACK:continue
            for t in a['triangles']:
                points=np.array([m['vertices'][i]['position'] for i in t])
                for bary in barys:
                    p=np.array(bary)@points;x,y,z=p
                    if not(-5.8<y<1.7 and abs(x)<3 and z<-.5):continue
                    region='rear-pelvis' if y>-.6 else 'rear-hip' if y>-1.9 else 'lower-back'
                    values={}
                    for label in ('before','after'):
                        s=surfaces[label,tid];idx,b,d=s.nearest(p);q=b@s.triangles[idx]
                        values[label]=dict(distance=d,inward_z=float(q[2]-p[2]))
                    rows[region].append(values)
    stats={}
    for region,samples in rows.items():
        stats[region]=dict(samples=len(samples))
        for label in ('before','after'):
            distances=[s[label]['distance'] for s in samples]
            stats[region][label]=dict(maximum_surface_distance=float(max(distances)),p95_surface_distance=float(np.percentile(distances,95)),maximum_inward_z=float(max(s[label]['inward_z'] for s in samples)))
        if stats[region]['after']['maximum_surface_distance']>5e-7:raise ValueError('Restored anatomy sample misses original surface')
    return stats


def detail_view(model,angle):
    """Viewing-only torso/pelvis selection, not a truncated replacement model."""
    selected=copy.deepcopy(model);meshes=[]
    a=np.radians(angle);rotation=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]])
    for m in selected['meshes']:
        mats=[]
        for mat in m['materials']:
            if mat['texture_id'] not in (2,4,5,6,7,8):continue
            faces=[t for t in mat['triangles'] if all(-4.9<v['position'][1]<1.6 and abs(v['position'][0])<2.8 for v in (m['vertices'][i] for i in t))]
            if faces:mats.append(dict(mat,triangles=faces))
        if not mats:continue
        indices=sorted({i for mat in mats for t in mat['triangles'] for i in t});mapping={old:new for new,old in enumerate(indices)}
        vertices=[m['vertices'][i] for i in indices]
        for v in vertices:v['position']=(rotation@v['position']).tolist();v['normal']=(rotation@v['normal']).tolist()
        for mat in mats:mat['triangles']=[tuple(mapping[i] for i in t) for t in mat['triangles']]
        meshes.append(dict(m,vertices=vertices,materials=mats))
    selected['meshes']=meshes;return selected


def run(source_path,base_path,output):
    if output.exists():raise FileExistsError('Refusing to overwrite output')
    source=source_path.read_bytes();base=base_path.read_bytes()
    if digest(source)!=SOURCE_SHA256 or digest(base)!=BASE_SHA256:raise ValueError('Inputs do not match pinned assets')
    original=next(r for s,r in sections(base) if s['id']==2);before=audit_yobj(original)
    reference,alignment=reference_model(load_hctp_with_weights(source_path),before)
    fixed,patch=repair(original,reference);after=audit_yobj(fixed);checks,poses=animation_checks(after,patch)
    comparisons=surface_comparison(reference,before,after)
    packed=compress(fixed)
    if decompress(packed)!=fixed:raise ValueError('Model compression round trip failed')
    pac=replace_sections(base,{2:packed})
    if len(pac)>148000 or len(pac)%2048:raise ValueError('PSP budget/alignment exceeded: '+str(len(pac)))
    old=inspect_pac(base)['sections'];new=inspect_pac(pac)['sections']
    if len(old)!=len(new):raise ValueError('PAC section count changed')
    for a,b in zip(old,new):
        if a['id']!=b['id'] or b['offset']%16:raise ValueError('PAC section order/alignment changed')
        if a['id']!=2 and base[a['offset']:a['offset']+a['size']]!=pac[b['offset']:b['offset']+b['size']]:raise ValueError('Unrelated raw PAC payload changed')
    if next(r for s,r in sections(pac) if s['id']==2)!=fixed:raise ValueError('PAC model differs from preview')
    output.mkdir(parents=True);preview=output/'preview';preview.mkdir();audit=output/'audit';audit.mkdir()
    filename='1800-PSP-hybrid-source-pelvis-restored.pac';(output/filename).write_bytes(pac)
    for label,data,model in [('before',original,before),('source-pelvis-restored',fixed,after)]:
        (preview/(label+'.yobj')).write_bytes(data);write_preview(model,preview/(label+'.obj'));dump_audit(model,audit,label,len(base) if label=='before' else len(pac))
        for view,angle in [('front',0),('rear',180),('side',90),('three-quarter',135)]:write_preview(posed_view(model,{},angle),preview/(label+'-'+view+'.obj'))
        for view,angle in [('rear',180),('side',90)]:write_preview(detail_view(model,angle),preview/(label+'-detail-'+view+'.obj'))
        for pose_name in ('standing','forward-bend','crouch','walk-04'):
            write_preview(posed_view(model,poses[pose_name],135),preview/(label+'-'+pose_name+'.obj'))
    for view,angle in [('front',0),('rear',180),('side',90)]:
        m=copy.deepcopy(reference);a=np.radians(angle);rotation=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]])
        for mesh in m['meshes']:
            for v in mesh['vertices']:v['position']=(rotation@v['position']).tolist();v['normal']=(rotation@v['normal']).tolist()
        write_preview(m,preview/('hctp-reference-'+view+'.obj'))
    for view,angle in [('rear',180),('side',90)]:write_preview(detail_view(reference,angle),preview/('hctp-reference-detail-'+view+'.obj'))
    textures={}
    for section,raw in sections(base):
        if section['id'] in (8,9):
            for e in parse_textures(raw):textures[e['name']]=raw[e['offset']:e['offset']+e['size']]
    mtl=[]
    for i,name in enumerate(before['texture_names']):
        gim=textures[name];pixels,palette=read_gim(gim);(preview/(name+'.gim')).write_bytes(gim);Image.fromarray(palette[pixels]).save(preview/(name+'.png'))
        mtl+=['newmtl texture_%d'%i,'Kd 0.984 0.984 1.000','Ks 0.502 0.502 0.502','map_Kd '+name+'.png']
    (preview/'preview.mtl').write_text('\n'.join(mtl)+'\n')
    keys=('meshes','vertices','triangles','indices','strips','textures','material_records','bones')
    report=dict(status='Source posterior geometry restored; actual PPSSPP animation validation pending',filename=filename,
        source_sha256=digest(source),baseline_sha256=digest(base),pac_sha256=digest(pac),alignment=alignment,patch=patch,
        before=dict(pac_bytes=len(base),model_bytes=len(original),stored_model_bytes=next(s['size'] for s in old if s['id']==2),**{k:before['report'][k] for k in keys}),
        after=dict(pac_bytes=len(pac),model_bytes=len(fixed),stored_model_bytes=len(packed),**{k:after['report'][k] for k in keys}),
        analytical_pose_checks=checks,pose_definitions=poses,source_surface_comparison=comparisons,
        hctp_original=dict(pac_bytes=len(source),vertices=sum(len(m['vertices']) for m in reference['meshes']),triangles=sum(len(a['triangles']) for m in reference['meshes'] for a in m['materials'])),
        preview_equals_final_model=True,all_unrelated_pac_payloads_byte_identical=True,
        cause='Resting posterior surface flattened by decimation; source rear-trunks and back-torso triangles restore lost curvature. A rim-only repair was insufficient.',
        animation_limit='Synthetic poses on the existing PSP skeleton; no game ISO/save-state was available. These checks do not establish game animation or crash correctness.')
    write_json(output/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=run(a.source,a.base,a.output);print(json.dumps(dict(before=r['before'],after=r['after'],added=len(r['patch']['added_vertex_records']),moved=len(r['patch']['moved_boundary_records'])),indent=2))

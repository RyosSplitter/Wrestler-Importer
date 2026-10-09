"""Recover the original curved rear waistband and its corresponding skin weights.

Pinned asset trial. Six source seam points are restored on both torso and trunks.
Existing rear seam positions retain their original geometry; their stale collapse
weights are replaced by the original source-to-PSP bone-name mapping.
"""
import argparse
import copy
from collections import defaultdict
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from .hctp_weights import load_hctp_with_weights
from .lance_abs_fix import reference_model
from .lance_waist_fix import SOURCE_SHA256, position_key
from .lance_waist_mirror import triangles
from .pac_inspect import inspect_pac, parse_textures
from .pac_repack import replace_sections
from .psp_mesh_audit import audit_yobj, digest
from .psp_mesh_merge import write_model
from .psp_mesh_merge_trial import sections, write_preview, write_json, dump_audit
from .texture_convert import read_gim
from .weight_trial_review import deform, skin_matrices, POSES
from .yukes_bpe import compress, decompress

BASE_SHA256='8e59fec71768b1c19bb890ceb1f66fd9735a60f8c0087b3f8a1b1b6a882335b0'
BEND_POSES={**POSES,'forward-bend':{'koshi':('x',35),'mune':('x',20)},
            'backward-bend':{'koshi':('x',-25),'mune':('x',-15)},
            'waist-twist':{'koshi':('y',30),'mune':('y',20)},
            'side-bend':{'koshi':('z',25),'mune':('z',15)}}


def source_references(reference,before):
    owners=defaultdict(set);records=defaultdict(list);area=defaultdict(lambda:np.zeros(3))
    names={b['name']:b['index'] for b in before['bones']}
    for mesh in reference['meshes']:
        for mat in mesh['materials']:
            tid=mat['texture_id']
            for vi in {i for tri in mat['triangles'] for i in tri}:
                v=mesh['vertices'][vi];key=position_key(v['position']);owners[key].add(tid)
                records[key].append((mesh,v,tid))
            for tri in mat['triangles']:
                ps=np.array([mesh['vertices'][i]['position'] for i in tri]);n=np.cross(ps[1]-ps[0],ps[2]-ps[0])
                for p in ps:area[position_key(p)]+=n
    back={before['texture_names'].index(n) for n in ('l-mune2','l-pan1')}
    result={}
    for key,ts in owners.items():
        if not back<=ts:continue
        p=struct.unpack('<3f',key)
        if not(-1.95<p[1]<-1.65 and abs(p[0])<1.8):raise ValueError('Unexpected reference waist extent')
        dense_rows=[];uvs=defaultdict(list)
        for mesh,v,tid in records[key]:
            dense=np.zeros(len(before['bones']))
            for b,w in zip(mesh['bone_palette'],v['weights']):
                if not w:continue
                while reference['bones'][b]['name'] not in names:
                    b=reference['bones'][b]['parent']
                    if b<0:raise ValueError('Source waist bone cannot map to PSP')
                dense[names[reference['bones'][b]['name']]]+=w
            dense/=dense.sum();dense_rows.append(dense);uvs[tid].append(v['uv'])
        if any(np.max(np.abs(dense-dense_rows[0]))>1e-6 for dense in dense_rows):raise ValueError('Inconsistent source seam weights')
        for tid,rows in uvs.items():
            if max(np.linalg.norm(np.array(row)-rows[0]) for row in rows)>1e-5:raise ValueError('Ambiguous original waist UVs')
        n=area[key];n/=np.linalg.norm(n)
        result[key]=dict(position=p,weights=dense_rows[0],normal=n,uv={tid:rows[0] for tid,rows in uvs.items()})
    if len(result)!=9:raise ValueError('Expected nine original back waistband anchors')
    return result


def repair(raw,references):
    before=audit_yobj(raw);model=copy.deepcopy(before)
    original_keys={position_key(v['position']) for mesh in before['meshes'] for v in mesh['vertices']}
    missing={k:v for k,v in references.items() if k not in original_keys}
    if len(missing)!=6:raise ValueError('Expected six missing source seam points')
    center=min(references,key=lambda k:abs(references[k]['position'][0]))
    left=max(references,key=lambda k:references[k]['position'][0])
    right=min(references,key=lambda k:references[k]['position'][0])
    chains={}
    for corner in (left,right):
        side=1 if references[corner]['position'][0]>0 else -1
        keys=[center]+sorted([k for k in missing if references[k]['position'][0]*side>0],key=lambda k:abs(references[k]['position'][0]))+[corner]
        chains[frozenset((center,corner))]=keys
    added=[];changed=[];strip_changes=[];new_triangles=[]
    def weights_for(mesh,ref):
        if any(w and b not in mesh['bone_palette'] for b,w in enumerate(ref['weights'])):raise ValueError('Existing palette cannot store source waist weights')
        return [ref['weights'][b] for b in mesh['bone_palette']]
    for mesh in model['meshes']:
        raw_vertices=bytearray(mesh['raw_vertices']);n_old=len(mesh['vertices']);cache={}
        for mi,mat in enumerate(mesh['materials']):
            tid=mat['texture_id'];new_strips=[];new_headers=[]
            for si,(strip,header) in enumerate(zip(mat['strips'],mat['strip_headers'])):
                ts=triangles(strip);replacement=[];did_change=False
                for tri in ts:
                    keys=[position_key(mesh['vertices'][vi]['position']) for vi in tri];edge=None
                    if before['texture_names'][tid] in ('l-mune2','l-pan1'):
                        for i in range(3):
                            pair=frozenset((keys[i],keys[(i+1)%3]))
                            if pair in chains:edge=(i,chains[pair]);break
                    if edge is None:replacement.append(tri);continue
                    did_change=True;i,chain=edge
                    if chain[0]!=keys[i]:chain=list(reversed(chain))
                    indices=[tri[i]]
                    for key in chain[1:-1]:
                        cache_key=(tid,key)
                        if cache_key not in cache:
                            ref=references[key];donor=mesh['vertices'][tri[i]]
                            weights=weights_for(mesh,ref)
                            record=struct.pack('<'+'f'*len(weights),*weights)+struct.pack('<2f4B3f3f',*ref['uv'][tid],*donor['color'],*ref['normal'],*ref['position'])
                            if len(record)!=mesh['stride']:raise ValueError('Vertex stride mismatch')
                            vi=len(mesh['vertices']);v=copy.deepcopy(donor)
                            v.update(position=ref['position'],weights=weights,normal=ref['normal'].tolist(),uv=ref['uv'][tid])
                            mesh['vertices'].append(v);raw_vertices+=record;cache[cache_key]=vi
                            added.append(dict(mesh=mesh['index'],vertex=vi,position=list(ref['position']),texture=before['texture_names'][tid]))
                        indices.append(cache[cache_key])
                    indices.append(tri[(i+1)%3]);third=tri[(i+2)%3]
                    faces=[(a,b,third) for a,b in zip(indices,indices[1:])]
                    old_ps=np.array([mesh['vertices'][vi]['position'] for vi in tri]);old_n=np.cross(old_ps[1]-old_ps[0],old_ps[2]-old_ps[0])
                    for face in faces:
                        ps=np.array([mesh['vertices'][vi]['position'] for vi in face]);n=np.cross(ps[1]-ps[0],ps[2]-ps[0])
                        if np.linalg.norm(n)<1e-10 or np.dot(n,old_n)<=0:raise ValueError('Restored rear face degenerates or flips')
                    replacement+=faces;new_triangles.append(dict(mesh=mesh['index'],material=mi,before=list(tri),after=[list(t) for t in faces]))
                if did_change:
                    # Preserve each untouched triangle's winding/order. The
                    # selected strip is split into independent triangle strips
                    # using its existing opaque rendering flags.
                    if len(ts)!=len(strip)-2:raise ValueError('Affected strip contains degenerate restart indices')
                    new_strips.extend([list(t) for t in replacement]);new_headers.extend([header]*len(replacement))
                    strip_changes.append(dict(mesh=mesh['index'],material=mi,original_strip=si))
                else:new_strips.append(strip);new_headers.append(header)
            mat['strips']=new_strips;mat['strip_headers']=new_headers
            mat['triangles']=[t for strip in new_strips for t in triangles(strip)]
        for vi,v in enumerate(mesh['vertices'][:n_old]):
            key=position_key(v['position'])
            if key not in references:continue
            ref=references[key];weights=weights_for(mesh,ref);start=vi*mesh['stride'];offset=4*mesh['weight_slots']
            old_dense=np.zeros(len(before['bones']))
            for b,w in zip(mesh['bone_palette'],v['weights']):old_dense[b]=w
            raw_vertices[start:start+offset]=struct.pack('<'+'f'*len(weights),*weights)
            raw_vertices[start+offset+12:start+offset+24]=struct.pack('<3f',*ref['normal'])
            changed.append(dict(mesh=mesh['index'],vertex=vi,position=list(v['position']),
                before_bone_weights={before['bones'][b]['name']:float(w) for b,w in enumerate(old_dense) if w},
                after_bone_weights={before['bones'][b]['name']:float(w) for b,w in enumerate(ref['weights']) if w}))
            v['weights']=weights;v['normal']=ref['normal'].tolist()
        mesh['raw_vertices']=bytes(raw_vertices)
    if len(added)!=12 or len(new_triangles)!=4 or len(strip_changes)!=4:raise ValueError('Unexpected restoration scope')
    result=write_model(model,[[i] for i in range(len(model['meshes']))]);after=audit_yobj(result)
    allowed={(r['mesh'],r['vertex']) for r in changed}
    for a,b in zip(before['meshes'],after['meshes']):
        if a['bone_palette']!=b['bone_palette'] or a['opaque']!=b['opaque'] or a['raw_header'][48:]!=b['raw_header'][48:]:raise ValueError('Palette/mesh metadata/bounds changed')
        for vi in range(len(a['vertices'])):
            aa=a['raw_vertices'][vi*a['stride']:(vi+1)*a['stride']];bb=b['raw_vertices'][vi*b['stride']:(vi+1)*b['stride']];offset=4*a['weight_slots']
            if (a['index'],vi) in allowed:
                if aa[offset:offset+12]!=bb[offset:offset+12] or aa[offset+24:]!=bb[offset+24:]:raise ValueError('Existing UV/color/position changed')
            elif aa!=bb:raise ValueError('Unrelated vertex changed')
        for ma,mb in zip(a['materials'],b['materials']):
            if ma['raw'][:132]!=mb['raw'][:132]:raise ValueError('Material rendering properties changed')
    for key in ('bone_raw','texture_raw','model_descriptor_raw'):
        if before[key]!=after[key]:raise ValueError(key+' changed')
    replaced={(r['mesh'],r['material'],tuple(r['before'])) for r in new_triangles}
    added_faces={(r['mesh'],r['material'],tuple(t)) for r in new_triangles for t in r['after']}
    for a,b in zip(before['meshes'],after['meshes']):
        for mi,(ma,mb) in enumerate(zip(a['materials'],b['materials'])):
            old=[t for t in ma['triangles'] if (a['index'],mi,t) not in replaced]
            new=[t for t in mb['triangles'] if (a['index'],mi,t) not in added_faces]
            if old!=new:raise ValueError('Unrelated triangles or ordered draw sequence changed')
    return result,dict(added_vertex_records=added,changed_weight_normal_records=changed,
        changed_strips=strip_changes,replaced_triangles=new_triangles,
        original_positions_uvs_colors_materials_skeleton_palettes_preserved=True,
        front_mirror_geometry_preserved=True,
        note='Local rear seam weights intentionally restored to corresponding source values mapped onto the existing PSP bones.')


def dense(model):
    ps=np.array([v['position'] for m in model['meshes'] for v in m['vertices']]);ws=np.zeros((len(ps),len(model['bones'])));row=0
    for m in model['meshes']:
        for v in m['vertices']:
            for b,w in zip(m['bone_palette'],v['weights']):ws[row,b]=w
            row+=1
    return ps,ws


def pose_checks(model,patch):
    ps,ws=dense(model);groups=defaultdict(list)
    for i,p in enumerate(ps):
        if -1.95<p[1]<-1.65 and abs(p[0])<1.8 and p[2]<.1:groups[position_key(p)].append(i)
    result={}
    offsets={};offset=0
    for mesh in model['meshes']:offsets[mesh['index']]=offset;offset+=len(mesh['vertices'])
    for name,pose in BEND_POSES.items():
        posed=deform(dict(bones=model['bones'],bone_count=len(model['bones'])),ps,ws,pose)
        gap=max(float(np.max(np.abs(posed[rows]-posed[rows[0]]))) for rows in groups.values())
        if gap!=0:raise ValueError('Recovered rear seam separates in '+name)
        matrices=skin_matrices(dict(bones=model['bones']),pose);cosines=[]
        for change in patch['replaced_triangles']:
            for tri in change['after']:
                rows=np.array(tri)+offsets[change['mesh']];p=ps[rows];q=posed[rows]
                n=np.cross(p[1]-p[0],p[2]-p[0]);pn=np.cross(q[1]-q[0],q[2]-q[0])
                rotation=np.einsum('n,nij->ij',ws[rows].mean(0),matrices[:,:3,:3]);expected=rotation@n
                cosine=float(np.dot(pn,expected)/(np.linalg.norm(pn)*np.linalg.norm(expected)))
                if not np.isfinite(cosine) or cosine<=0:raise ValueError('Rear patch folds/inverts in '+name)
                cosines.append(cosine)
        result[name]=dict(rear_seam_gap=gap,minimum_rest_vs_skinned_face_normal_cosine=min(cosines))
    return result


def curve_comparison(before,after,references):
    ps_a,ws_a=dense(before);ps_b,ws_b=dense(after)
    rows_a={position_key(p):i for i,p in enumerate(ps_a)};rows_b={position_key(p):i for i,p in enumerate(ps_b)}
    keys=sorted(references,key=lambda k:references[k]['position'][0])
    expected_positions=np.array([references[k]['position'] for k in keys]);expected_weights=np.array([references[k]['weights'] for k in keys])
    center=min(keys,key=lambda k:abs(references[k]['position'][0]));pairs=[(keys[0],center),(center,keys[-1])]
    bones=dict(bones=after['bones'],bone_count=len(after['bones']));stats={}
    for name,pose in BEND_POSES.items():
        expected=deform(bones,expected_positions,expected_weights,pose)
        a=deform(bones,ps_a,ws_a,pose);b=deform(bones,ps_b,ws_b,pose)
        distances=[]
        for p in expected:
            candidates=[]
            for start,end in pairs:
                s=a[rows_a[start]];e=a[rows_a[end]];edge=e-s
                t=np.clip(np.dot(p-s,edge)/np.dot(edge,edge),0,1);candidates.append(np.linalg.norm(p-(s+t*edge)))
            distances.append(min(candidates))
        error=float(np.max(np.linalg.norm(b[[rows_b[k] for k in keys]]-expected,axis=1)))
        if error>1e-6:raise ValueError('Restored seam no longer follows the source skinning profile')
        stats[name]=dict(before_maximum_distance_to_source_seam_samples=float(max(distances)),after_maximum_source_seam_sample_error=error)
    return stats


def posed_view(model,pose,angle):
    result=copy.deepcopy(model);ps,ws=dense(model);bones=dict(bones=model['bones'],bone_count=len(model['bones']))
    posed=deform(bones,ps,ws,pose);matrices=skin_matrices(bones,pose)
    a=np.radians(angle);rotation=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]]);row=0
    for mesh in result['meshes']:
        for v in mesh['vertices']:
            blend=np.einsum('n,nij->ij',ws[row],matrices[:,:3,:3]);n=blend@v['normal'];n/=np.linalg.norm(n)
            v['position']=(rotation@posed[row]).tolist();v['normal']=(rotation@n).tolist();row+=1
    return result


def run(source_path,base_path,output):
    if output.exists():raise FileExistsError('Refusing to overwrite output')
    source_bytes=source_path.read_bytes();base=base_path.read_bytes()
    if digest(source_bytes)!=SOURCE_SHA256 or digest(base)!=BASE_SHA256:raise ValueError('Input does not match pinned assets')
    original=next(raw for s,raw in sections(base) if s['id']==2);before=audit_yobj(original)
    reference,alignment=reference_model(load_hctp_with_weights(source_path),before);refs=source_references(reference,before)
    fixed,patch=repair(original,refs);after=audit_yobj(fixed);poses=pose_checks(after,patch);curves=curve_comparison(before,after,refs)
    packed=compress(fixed)
    if decompress(packed)!=fixed:raise ValueError('Compression round trip failed')
    pac=replace_sections(base,{2:packed})
    if len(pac)>148000 or len(pac)%2048:raise ValueError('PAC size/alignment failed')
    for a,b in zip(inspect_pac(base)['sections'],inspect_pac(pac)['sections']):
        if a['id']!=b['id'] or b['offset']%16:raise ValueError('PAC section order/alignment changed')
        if a['id']!=2 and base[a['offset']:a['offset']+a['size']]!=pac[b['offset']:b['offset']+b['size']]:raise ValueError('Unrelated PAC section changed')
    if next(raw for s,raw in sections(pac) if s['id']==2)!=fixed:raise ValueError('Preview/final PAC mismatch')
    output.mkdir(parents=True);preview=output/'preview';preview.mkdir();audit=output/'audit';audit.mkdir()
    name='1800-PSP-hybrid-rear-waist-restored.pac';(output/name).write_bytes(pac)
    for label,data,model in [('before',original,before),('rear-waist-fixed',fixed,after)]:
        (preview/(label+'.yobj')).write_bytes(data);write_preview(model,preview/(label+'.obj'));dump_audit(model,audit,label,len(pac))
        for view,pose,angle in [('rear-rest',{},180),('rear-bend',BEND_POSES['forward-bend'],150)]:
            write_preview(posed_view(model,pose,angle),preview/(label+'-'+view+'.obj'))
    textures={}
    for section,raw in sections(base):
        if section['id'] in (8,9):
            for e in parse_textures(raw):textures[e['name']]=raw[e['offset']:e['offset']+e['size']]
    mtl=[]
    for i,name in enumerate(before['texture_names']):
        gim=textures[name];pixels,palette=read_gim(gim);(preview/(name+'.gim')).write_bytes(gim);Image.fromarray(palette[pixels]).save(preview/(name+'.png'))
        mtl.extend(['newmtl texture_%d'%i,'Kd 0.984 0.984 1.000','Ks 0.502 0.502 0.502','map_Kd '+name+'.png'])
    (preview/'preview.mtl').write_text('\n'.join(mtl)+'\n')
    report=dict(status='Rear seam restored; PPSSPP validation pending',filename='1800-PSP-hybrid-rear-waist-restored.pac',
        baseline_sha256=digest(base),source_sha256=digest(source_bytes),pac_sha256=digest(pac),patch=patch,pose_checks=poses,source_curve_comparison=curves,
        before=dict(pac_bytes=len(base),model_bytes=len(original),stored_model_bytes=next(s['size'] for s in inspect_pac(base)['sections'] if s['id']==2),**{k:before['report'][k] for k in ('meshes','vertices','triangles','indices','strips','textures','material_records','bones')}),
        after=dict(pac_bytes=len(pac),model_bytes=len(fixed),stored_model_bytes=len(packed),**{k:after['report'][k] for k in ('meshes','vertices','triangles','indices','strips','textures','material_records','bones')}),
        preview_equals_final_model=True,preserved_pac_sections=[8,9])
    write_json(output/'report.json',report);return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--base',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();r=run(args.source,args.base,args.output);print(json.dumps(dict(before=r['before'],after=r['after'],weight_records=len(r['patch']['changed_weight_normal_records'])),indent=2))

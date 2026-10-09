"""Restore the missing left waistband point from the existing right contour.

Pinned controlled repair: two seam vertex records, two additional triangles,
and one existing left lower-abdomen point mirrored from its right counterpart.
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
from .pac_inspect import inspect_pac, parse_textures
from .pac_repack import replace_sections
from .prepare_model import Surface
from .psp_mesh_audit import audit_yobj, digest
from .psp_mesh_merge import write_model
from .psp_mesh_merge_trial import sections, write_json, write_preview, dump_audit
from .weight_trial_review import POSES, deform
from .yukes_bpe import compress, decompress
from .texture_convert import read_gim

BASE_SHA256='e701ed84ea9388fab76c60259c07f72182dc71273a9120ed6db601068f88e41b'


def triangles(strip):
    return [t for i in range(len(strip)-2)
            if len(set(t:=(strip[i],strip[i+2],strip[i+1]) if i%2 else tuple(strip[i:i+3])))==3]


def repair(raw,reference,alignment):
    before=audit_yobj(raw);model=copy.deepcopy(before)
    axis=np.array(alignment['rotation'])[:,0];center=np.array(alignment['translation'])
    def mirror(p):
        p=np.array(p);return p-2*np.dot(p-center,axis)*axis
    def mirror_normal(n):
        n=np.array(n);n=n-2*np.dot(n,axis)*axis;return n/np.linalg.norm(n)
    def uv_for(tid,p,old):
        ms=[dict(m,materials=[a for a in m['materials'] if a['texture_id']==tid])
            for m in reference['meshes'] if any(a['texture_id']==tid for a in m['materials'])]
        surface=Surface(dict(meshes=ms));idx,bary,d=surface.nearest(p)
        if d>.15:raise ValueError('Mirrored UV reference too far away')
        mesh,tri=surface.corners[idx]
        return bary@np.array([mesh['vertices'][i]['uv'] for i in tri])
    src=before['meshes'][53]['vertices'][6]
    new_position=struct.unpack('<3f',struct.pack('<3f',*mirror(src['position'])))
    new_normal=mirror_normal(src['normal'])
    names={b['name']:b['index'] for b in before['bones']}
    mirrored_weights={}
    for bone,w in zip(before['meshes'][53]['bone_palette'],src['weights']):
        name=before['bones'][bone]['name']
        swap=('r_'+name[2:]) if name.startswith('l_') else ('l_'+name[2:]) if name.startswith('r_') else name
        mirrored_weights[names[swap]]=w
    added=[]
    for mi,donor_vi in [(53,6),(55,11)]:
        mesh=model['meshes'][mi];v=copy.deepcopy(mesh['vertices'][donor_vi]);tid=mesh['materials'][0]['texture_id']
        if any(w and b not in mesh['bone_palette'] for b,w in mirrored_weights.items()):raise ValueError('Mirror bone absent from existing palette')
        uv=uv_for(tid,new_position,v['uv'])
        weights=[mirrored_weights.get(b,0.) for b in mesh['bone_palette']]
        record=struct.pack('<'+'f'*len(weights),*weights)+struct.pack('<2f4B3f3f',*uv,*v['color'],*new_normal,*new_position)
        if len(record)!=mesh['stride']:raise ValueError('New vertex stride mismatch')
        v.update(position=new_position,normal=list(new_normal),uv=list(uv),weights=weights)
        vi=len(mesh['vertices']);mesh['vertices'].append(v);mesh['raw_vertices']+=record
        added.append(dict(mesh=mi,vertex=vi,position=list(new_position),texture=before['texture_names'][tid],
                          mirrored_from_mesh=53,mirrored_from_vertex=6))
    p53=added[0]['vertex'];p55=added[1]['vertex']
    mat=model['meshes'][53]['materials'][0]
    if mat['strips'][2]!=[5,6,7,8,18,21,23,22,24] or mat['strips'][13]!=[21,8,22,6]:raise ValueError('Unexpected torso patch topology')
    # Keep the right-side strip prefix and its original winding untouched.
    # Replace the collapsed left fan by the right fan's corresponding layout.
    mat['strips'][2]=[5,6,7,8,18,21,23]
    mat['strips'][13]=[21,8,p53,6]
    mat['strips'].insert(3,[21,p53,23,22,24]);mat['strip_headers'].insert(3,mat['strip_headers'][2])
    mat=model['meshes'][55]['materials'][0]
    if mat['strips'][6]!=[11,8,15,6]:raise ValueError('Unexpected trunks patch topology')
    mat['strips'][6]=[11,8,p55,15]
    mat['strips'].insert(7,[8,6,15]);mat['strip_headers'].insert(7,mat['strip_headers'][6])
    # Match the existing left lower-abdominal point to its retained right
    # counterpart. All original copies move together, retaining their weights.
    old_p=position_key(before['meshes'][53]['vertices'][23]['position'])
    donor=before['meshes'][53]['vertices'][5]
    moved_position=struct.unpack('<3f',struct.pack('<3f',*mirror(donor['position'])))
    moved=[]
    normal_sources={position_key(before['meshes'][53]['vertices'][left]['position']):right
                    for left,right in [(21,7),(22,17),(24,4)]}
    normal_changes=[]
    for mesh in model['meshes']:
        uses=defaultdict(set)
        for mat in mesh['materials']:
            for vi in {i for tri in mat['triangles'] for i in tri}:uses[vi].add(mat['texture_id'])
        records=bytearray(mesh['raw_vertices'])
        for vi,v in enumerate(mesh['vertices']):
            key=position_key(v['position'])
            if key in normal_sources:
                right=normal_sources[key];normal=mirror_normal(before['meshes'][53]['vertices'][right]['normal'])
                start=vi*mesh['stride']+4*mesh['weight_slots']+12
                records[start:start+12]=struct.pack('<3f',*normal);v['normal']=list(normal)
                normal_changes.append(dict(mesh=mesh['index'],vertex=vi,mirrored_from_mesh=53,mirrored_from_vertex=right))
            if position_key(v['position'])!=old_p:continue
            if len(uses[vi])!=1:raise ValueError('Moved vertex requires ambiguous UVs')
            tid=next(iter(uses[vi]));uv=uv_for(tid,moved_position,v['uv']);normal=mirror_normal(donor['normal'])
            start=vi*mesh['stride']+4*mesh['weight_slots']
            records[start:start+8]=struct.pack('<2f',*uv)
            records[start+12:start+36]=struct.pack('<3f3f',*normal,*moved_position)
            v.update(position=moved_position,uv=list(uv),normal=list(normal))
            moved.append(dict(mesh=mesh['index'],vertex=vi,position=list(moved_position),
                              mirrored_from_mesh=53,mirrored_from_vertex=5))
        mesh['raw_vertices']=bytes(records)
        for mat in mesh['materials']:mat['triangles']=[tri for strip in mat['strips'] for tri in triangles(strip)]
    if len(moved)!=1:raise ValueError('Unexpected moved vertex scope')
    bounds=[]
    for mesh in model['meshes']:
        header=bytearray(mesh['raw_header']);c=np.array(struct.unpack_from('<3f',header,48));radius=struct.unpack_from('<f',header,60)[0]
        needed=max(np.linalg.norm(np.array(v['position'])-c) for v in mesh['vertices'])
        if needed>radius:
            new=float(np.float32(needed+.001));struct.pack_into('<f',header,60,new)
            bounds.append(dict(mesh=mesh['index'],before=radius,after=new))
        mesh['raw_header']=bytes(header)
    result=write_model(model,[[i] for i in range(len(model['meshes']))]);after=audit_yobj(result)
    # Existing records outside the explicit one-point patch remain byte exact.
    normal_keys={(r['mesh'],r['vertex']) for r in normal_changes}
    for a,b in zip(before['meshes'],after['meshes']):
        if a['bone_palette']!=b['bone_palette'] or a['opaque']!=b['opaque']:raise ValueError('Existing palette/opaque mesh state changed')
        for vi in range(len(a['vertices'])):
            aa=a['raw_vertices'][vi*a['stride']:(vi+1)*a['stride']]
            bb=b['raw_vertices'][vi*b['stride']:(vi+1)*b['stride']]
            if (a['index'],vi)!=(53,23):
                if (a['index'],vi) in normal_keys:
                    start=4*a['weight_slots']+12
                    if aa[:start]!=bb[:start] or aa[start+12:]!=bb[start+12:]:raise ValueError('Non-normal original fields changed')
                elif aa!=bb:raise ValueError('Unrelated original vertex changed')
            elif aa[:4*a['weight_slots']]!=bb[:4*b['weight_slots']] or aa[4*a['weight_slots']+8:4*a['weight_slots']+12]!=bb[4*b['weight_slots']+8:4*b['weight_slots']+12]:
                raise ValueError('Existing weight or color bits changed')
        for ma,mb in zip(a['materials'],b['materials']):
            if ma['raw'][:132]!=mb['raw'][:132]:raise ValueError('Material render state changed')
    if before['bone_raw']!=after['bone_raw'] or before['texture_raw']!=after['texture_raw'] or before['model_descriptor_raw']!=after['model_descriptor_raw']:
        raise ValueError('Skeleton/texture names/model descriptor changed')
    # Every previous triangle survives in order except these four faces, which
    # are explicitly replaced by six faces in the same two material records.
    replaced={(53,0):{(21,22,23),(21,8,22),(8,6,22)},(55,0):{(11,8,15)}}
    new_faces={(53,0):{(21,p53,23),(p53,22,23),(21,8,p53),(8,6,p53)},
               (55,0):{(11,8,p55),(8,15,p55)}}
    for a,b in zip(before['meshes'],after['meshes']):
        for mi,(ma,mb) in enumerate(zip(a['materials'],b['materials'])):
            key=(a['index'],mi)
            old=[tri for tri in ma['triangles'] if tri not in replaced.get(key,set())]
            new=[tri for tri in mb['triangles'] if tri not in new_faces.get(key,set())]
            if old!=new:raise ValueError('Unrelated triangles/draw order changed')
    for mesh in after['meshes']:
        old=before['meshes'][mesh['index']]
        for mi,(ma,mb) in enumerate(zip(old['materials'],mesh['materials'])):
            for tri in mb['triangles']:
                ps=np.array([mesh['vertices'][i]['position'] for i in tri]);n=np.cross(ps[1]-ps[0],ps[2]-ps[0])
                if np.linalg.norm(n)<1e-10:raise ValueError('Geometrically degenerate triangle')
                # Existing front faces have negative Z cross products in the
                # native Y-down coordinates; retain that winding convention.
                if tri in new_faces.get((mesh['index'],mi),set()) and n[2]>=0:raise ValueError('New front-face winding inverted')
    # Both new seam copies must coincide under the same PSP bone animation.
    positions=np.array([v['position'] for m in after['meshes'] for v in m['vertices']]);weights=np.zeros((len(positions),len(after['bones'])));row=0
    seam_rows=[]
    for mesh in after['meshes']:
        for vi,v in enumerate(mesh['vertices']):
            for bone,w in zip(mesh['bone_palette'],v['weights']):weights[row,bone]=w
            if (mesh['index'],vi) in {(a['mesh'],a['vertex']) for a in added}:seam_rows.append(row)
            row+=1
    poses={}
    for name,pose in POSES.items():
        p=deform(dict(bones=after['bones'],bone_count=len(after['bones'])),positions,weights,pose)
        distance=float(np.max(np.abs(p[seam_rows]-p[seam_rows[0]])))
        if distance!=0:raise ValueError('New seam separates in '+name)
        poses[name]=distance
    return result,dict(added_vertex_records=added,moved_vertex_records=moved,mirrored_normal_records=normal_changes,bounds_changed=bounds,
        reflection_plane=dict(point=center.tolist(),normal=axis.tolist()),new_seam_pose_separation=poses,
        replaced_faces={str(k):list(v) for k,v in replaced.items()},new_faces={str(k):list(v) for k,v in new_faces.items()},
        original_weight_bits_palettes_materials_textures_skeleton_preserved=True,
        unrelated_original_vertices_and_ordered_triangles_preserved=True)


def run(source_path,base_path,output):
    if output.exists():raise FileExistsError('Refusing to overwrite output')
    base=base_path.read_bytes()
    if digest(base)!=BASE_SHA256 or digest(source_path.read_bytes())!=SOURCE_SHA256:raise ValueError('Input does not match pinned assets')
    original=next(raw for s,raw in sections(base) if s['id']==2);before=audit_yobj(original)
    reference,alignment=reference_model(load_hctp_with_weights(source_path),before)
    fixed,patch=repair(original,reference,alignment);packed=compress(fixed)
    if decompress(packed)!=fixed:raise ValueError('Compression round trip failed')
    pac=replace_sections(base,{2:packed})
    if len(pac)>148000 or len(pac)%2048:raise ValueError('PAC budget/alignment failed')
    for a,b in zip(inspect_pac(base)['sections'],inspect_pac(pac)['sections']):
        if a['id']!=b['id'] or b['offset']%16:raise ValueError('PAC section alignment/order changed')
        if a['id']!=2 and base[a['offset']:a['offset']+a['size']]!=pac[b['offset']:b['offset']+b['size']]:raise ValueError('Unrelated PAC section changed')
    if next(raw for s,raw in sections(pac) if s['id']==2)!=fixed:raise ValueError('Final PAC/preview mismatch')
    output.mkdir(parents=True);preview=output/'preview';preview.mkdir();audit=output/'audit';audit.mkdir()
    name='1800-PSP-hybrid-mirrored-left-waist.pac';(output/name).write_bytes(pac)
    after=audit_yobj(fixed)
    for label,data,model in [('before',original,before),('waist-mirrored',fixed,after)]:
        (preview/(label+'.yobj')).write_bytes(data);write_preview(model,preview/(label+'.obj'));dump_audit(model,audit,label,len(pac))
    textures={}
    for section,raw in sections(base):
        if section['id'] in (8,9):
            for e in parse_textures(raw):textures[e['name']]=raw[e['offset']:e['offset']+e['size']]
    mtl=[]
    for i,name in enumerate(before['texture_names']):
        gim=textures[name];pixels,palette=read_gim(gim);(preview/(name+'.gim')).write_bytes(gim)
        Image.fromarray(palette[pixels]).save(preview/(name+'.png'))
        mtl.extend(['newmtl texture_%d'%i,'Kd 0.984 0.984 1.000','Ks 0.502 0.502 0.502','map_Kd '+name+'.png'])
    (preview/'preview.mtl').write_text('\n'.join(mtl)+'\n')
    report=dict(status='Left waist contour mirrored; PPSSPP test pending',patch=patch,filename='1800-PSP-hybrid-mirrored-left-waist.pac',
        baseline_sha256=digest(base),pac_sha256=digest(pac),
        before=dict(pac_bytes=len(base),model_bytes=len(original),stored_model_bytes=next(s['size'] for s in inspect_pac(base)['sections'] if s['id']==2),
                    **{k:before['report'][k] for k in ('meshes','vertices','triangles','indices','strips','textures','material_records','bones')}),
        after=dict(pac_bytes=len(pac),model_bytes=len(fixed),stored_model_bytes=len(packed),
                    **{k:after['report'][k] for k in ('meshes','vertices','triangles','indices','strips','textures','material_records','bones')}),
        preview_equals_final_pac_model=True,preserved_pac_sections=[8,9])
    write_json(output/'report.json',report);return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--base',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();r=run(args.source,args.base,args.output);print(json.dumps(dict(before=r['before'],after=r['after']),indent=2))

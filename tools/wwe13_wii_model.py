"""Bounded sample Wii GCTC reader; preserve raw skin coefficients and padding.

INFERRED: three-bone coefficients describe successive lerps, supported by
shared-position/palette-order evidence; source runtime is not yet verified.
Geometry, bone names and draw/material ownership remain source-derived.
"""
import copy
import struct

import numpy as np

from tools.wwe13_inspect import checked,unpack
from tools.wwe13_wii_inspect import read_model_header,read_pach,decode_tpl,digest
from tools.pac_inspect import parse_textures
from tools.prepare_model import bone_matrices


def blend_weights(width,a=0,b=0):
    if width not in (1,2,3) or not 0<=a<=4096 or not 0<=b<=4096:
        raise ValueError('Unsupported Wii blend coefficients')
    a,b=a/4096,b/4096
    if width==1:return [1.]
    if width==2:
        if b:raise ValueError('Unexpected second two-bone coefficient')
        return [1-a,a]
    return [(1-a)*(1-b),a*(1-b),b]


def read_model(payload):
    header=read_model_header(payload);raw=payload[24:header['declared_yobj_bytes']+24]
    u=lambda a:unpack(raw,'>I',a)[0]
    pcap=unpack(raw,'>H',0x48)[0];group_count,draw_count=raw[0x4e:0x50]
    if (raw[0x4c],raw[0x4d],raw[0x50],raw[0x51])!=(2,7,10,0):
        raise ValueError('Unobserved fixed-point attribute convention')
    if not 0<draw_count<=header['material_count']:raise ValueError('Invalid material/draw table counts')
    color_count,uv_count=unpack(raw,'>2H',0x70)
    pp,gp,dp,cp,tp=[u(a)+8 for a in (0x54,0x5c,0x60,0x68,0x6c)]
    packed=np.frombuffer(checked(raw,pp,pcap*12),dtype='>i2').reshape(-1,6)
    uv=np.frombuffer(checked(raw,tp,uv_count*4),dtype='>i2').reshape(-1,2)/1024
    colors=np.frombuffer(checked(raw,cp,color_count*4),dtype=np.uint8).reshape(-1,4)
    checked(raw,gp,group_count*20);checked(raw,dp,draw_count*8)
    groups=[];skin=[];materials=[];used=set();used_materials=set();index_max=[0,0,0];expected=dp+draw_count*8
    for i in range(draw_count):
        a=dp+i*8;mid=raw[a];count=unpack(raw,'>H',a+2)[0];ptr=u(a+4)+8
        if mid>=header['material_count'] or mid in used_materials or ptr!=expected:raise ValueError('Unreviewed/overlapping draw layout')
        used_materials.add(mid)
        strips=[]
        for j in range(count):
            n=u(ptr);ptr+=4
            if not 3<=n<=16384:raise ValueError('Unbounded/invalid strip')
            corners=np.frombuffer(checked(raw,ptr,n*6),dtype='>u2').reshape(-1,3).astype(int);ptr+=n*6
            if any(corners[:,k].max()>=limit for k,limit in enumerate((pcap,color_count,uv_count))):
                raise ValueError('Source corner outside its position/color/UV buffer')
            index_max=np.maximum(index_max,corners.max(0)).tolist();used.update(corners[:,0].tolist());strips.append(corners.tolist())
        expected=ptr
        a=u(28)+8+mid*20;state=u(a+16)+8;state_raw=checked(raw,state,72)
        tid=unpack(raw,'>H',state+70)[0]
        if tid>=header['texture_slot_count']:raise ValueError('Material texture slot outside table')
        materials.append(dict(source_material=mid,source_state_hex=state_raw.hex(),
            source_header_hex=checked(raw,a,20).hex(),texture=header['texture_slots'][tid],
            texture_slot=tid,source_strips=strips))
    # Unused all-zero records are padding, not vertices to be assigned weights.
    zero=set(np.flatnonzero((packed==0).all(1)).tolist())
    if used&zero or set(range(pcap))-used!=zero:raise ValueError('Unclassified source position allocation')
    actual=sorted(used);cursor=0;weights={};group_ids={};raw_codes={}
    for i in range(group_count):
        bones0,bones1,bones2,width,n,wp=unpack(raw,'>4H2I',gp+i*20)
        slots=[bones0,bones1,bones2]
        if not 1<=width<=3 or any(b>=header['bone_count']for b in slots[:width]) or any(b!=65535 for b in slots[width:]):
            raise ValueError('Invalid Wii source palette')
        if len(set(slots[:width]))!=width or not 0<n<=128 or cursor+n>len(actual):raise ValueError('Invalid source skin group')
        codes=np.zeros((n,2),int)if width==1 else np.frombuffer(checked(raw,wp+8,n*4),dtype='>u2').reshape(-1,2).astype(int)
        for index,code in zip(actual[cursor:cursor+n],codes):
            ws=blend_weights(width,*code.tolist());dense=np.zeros(header['bone_count']);dense[slots[:width]]=ws
            weights[index]=dense.tolist();group_ids[index]=i;raw_codes[index]=code.tolist()
        groups.append(dict(index=i,bones=slots[:width],vertices=n,weight_pointer=wp+8,
            raw_opaque_tail=checked(raw,gp+i*20+16,4).hex()))
        cursor+=n
    if cursor!=len(actual):raise ValueError('Source skinning does not cover referenced positions')
    result=dict(header,meshes=[],textures=sorted({m['texture']for m in materials}),geometry_decoded=True)
    texture_ids={n:i for i,n in enumerate(result['textures'])};normal_lengths=[];agreements=[]
    for mat in materials:
        vertices=[];lookup={};triangles=[]
        for strip in mat['source_strips']:
            indices=[]
            for position,ci,ti in strip:
                key=position,ci,ti
                if key not in lookup:
                    normal=-packed[position,[4,5,3]]/4096;length=np.linalg.norm(normal)
                    if not .998<length<1.002:raise ValueError('Invalid referenced packed normal')
                    normal_lengths.append(float(length));lookup[key]=len(vertices)
                    vertices.append(dict(position=(packed[position,:3]/128).tolist(),normal=(normal/length).tolist(),
                        uv=uv[ti].tolist(),color=colors[ci].tolist(),weights=weights[position],
                        source_position_index=position,source_skin_group=group_ids[position],raw_blend_coefficients=raw_codes[position]))
                indices.append(lookup[key])
            for j in range(len(indices)-2):
                a,b,c=indices[j:j+3]
                if j%2:b,c=c,b
                if len({vertices[k]['source_position_index']for k in (a,b,c)})==3:triangles.append([a,b,c])
        ps=np.array([v['position']for v in vertices]);ns=np.array([v['normal']for v in vertices]);faces=np.array(triangles)
        cross=np.cross(ps[faces[:,1]]-ps[faces[:,0]],ps[faces[:,2]]-ps[faces[:,0]])
        valid=np.linalg.norm(cross,axis=1)>1e-10;dots=np.einsum('ij,ij->i',cross,ns[faces].mean(1))
        agreements.append(dict(material=mat['source_material'],texture=mat['texture'],triangles=len(triangles),
            normal_winding_agreement=float((dots[valid]>0).mean()),degenerate_geometric_triangles=int((~valid).sum())))
        # Attribute-indexed strips are the source topology, not inferred meshes.
        result['meshes'].append(dict(index=len(result['meshes']),bone_palette=list(range(header['bone_count'])),vertices=vertices,
            role='Hair'if mat['texture']=='trans'else'Blood'if mat['texture'].startswith('blood')else'Body',
            source_material=mat['source_material'],source_state_hex=mat['source_state_hex'],
            materials=[dict(texture_id=texture_ids[mat['texture']],triangles=triangles)]))
    result.update(mesh_count=len(result['meshes']),vertex_count=sum(len(m['vertices'])for m in result['meshes']),
        triangle_count=sum(len(a['triangles'])for m in result['meshes']for a in m['materials']),texture_count=len(texture_ids),
        source_skinning_decoded=True,source_decode_report=dict(position_capacity=pcap,referenced_positions=len(actual),
        zero_unreferenced_padding=sorted(zero),skin_groups=groups,winding=agreements,
        unused_material_records=[dict(index=i,header_hex=checked(raw,u(28)+8+i*20,20).hex()) for i in range(header['material_count']) if i not in used_materials],
        normal_length_range=[min(normal_lengths),max(normal_lengths)],positions_divisor=128,normal_divisor=4096,normal_axes="[-stored4,-stored5,-stored3]; all tested source triangle windings agree",uv_divisor=1024,
        weight_interpretation='Successive matrix lerps: 2 bones [1-a,a]; 3 bones [(1-a)(1-b),a(1-b),b]; a,b=u16/4096',
        classification='Strongly supported by cross-variant shared-position/palette-order evidence; source runtime not independently emulated'))
    return result


def source_bundle(data,index=0):
    if digest(data)!="feeea42460893cf577b3aa2ffadb239462538be18e822e33d051e096445df542" or index not in (0,1):
        raise ValueError("Experimental reader is restricted to inspected ch145 sample and variants 0/1")
    start=(0x4000,0x48000)[index];pach=read_pach(data,start);sections={s['id']:s['raw']for s in pach['sections']}
    decoded=[read_model(sections[s])for s in (2,10000)];bones=[];names={};origin={}
    for sid,m in zip((2,10000),decoded):
        for b in m['bones']:
            parent=m['bones'][b['parent']]['name']if b['parent']>=0 else None
            if b['name']not in names:
                names[b['name']]=len(bones);bones.append(dict(b,index=len(bones),parent=-1));origin[b['name']]=parent
    for b in bones:b['parent']=names[origin[b['name']]]if origin[b['name']]is not None else -1
    unified=bone_matrices(dict(bones=bones));maximum=0.
    for m in decoded:
        bm=bone_matrices(m)
        for b in m['bones']:maximum=max(maximum,float(np.max(np.abs(bm[b['index']]-unified[names[b['name']]]))))
    if maximum>1e-6:raise ValueError('Body/trans bind mismatch')
    textures={};texture_details=[];table=sections[9]
    for entry in parse_textures(table):
        rgba,details=decode_tpl(checked(table,entry['offset'],entry['size']));textures[entry['name']]=rgba
        texture_details.append(dict(name=entry['name'],**details))
    meshes=[];excluded=[]
    for sid,m in zip((2,10000),decoded):
        mapping=[names[b['name']]for b in m['bones']]
        for mesh in m['meshes']:
            if mesh['role']=='Blood':
                excluded.append(dict(section=sid,material=mesh['source_material'],triangles=sum(len(a['triangles'])for a in mesh['materials']),
                    reason='Dynamic source blood draw; ordinary PSP serialization would make it always visible. Not approximated as body geometry.'))
                continue
            out=copy.deepcopy(mesh);out['index']=len(meshes);out['source_section']=sid;out['bone_palette']=list(range(len(bones)))
            for v in out['vertices']:
                dense=np.zeros(len(bones));dense[mapping]=v['weights'];v['weights']=dense.tolist();v['source_color']=v['color'];v['color']=[255]*4
            for mat in out['materials']:mat['texture_id']=0 if mesh['role']=='Body'else 1
            meshes.append(out)
    result=dict(bones=bones,bone_count=len(bones),meshes=meshes,mesh_count=len(meshes),
        textures=['wii_color','wii_trans'],texture_count=2,geometry_decoded=True,source_skinning_decoded=True,
        triangle_count=sum(len(a['triangles'])for m in meshes for a in m['materials']),vertex_count=sum(len(m['vertices'])for m in meshes))
    return result,[textures['color'],textures['trans']],dict(bundle=index,source_sha256=digest(data),
        models=[dict(section=s,decode=m['source_decode_report'],triangles=m['triangle_count'],vertices=m['vertex_count'])for s,m in zip((2,10000),decoded)],
        common_bind_maximum_difference=maximum,excluded_effects=excluded,source_textures=texture_details,
        vertex_alpha_policy='White opaque native vertex tint; source shader color bytes retained in provenance; alpha retained in trans texture')

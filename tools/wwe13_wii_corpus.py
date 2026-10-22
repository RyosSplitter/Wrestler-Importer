"""Bounded Wii corpus experiments, deliberately separate from app support.

Discover aligned PACH containers rather than assuming HBK offsets. An unknown
auxiliary model is an error, never permission to silently discard that model.
Source blend semantics and dynamic hair/blood limitations remain experimental.
"""
import copy
import re
import struct
import numpy as np
from tools.wwe13_inspect import checked
from tools.wwe13_wii_inspect import MAX_INPUT, MAX_EXPANSION, read_pach, decode_tpl, digest
from tools.wwe13_wii_model import read_model
from tools.pac_inspect import parse_textures
from tools.prepare_model import bone_matrices


def bundles(data):
    if len(data)>MAX_INPUT or checked(data,0,4)!=b'EPK8':
        raise ValueError('Expected bounded Wii EPK8 input')
    offsets=[m.start()for m in re.finditer(b'PACH',data)if m.start()%2048==0]
    if not 0<len(offsets)<=32:raise ValueError('No bounded aligned PACH containers')
    result=[];end=0;expanded=0
    for offset in offsets:
        if offset<end:raise ValueError('Overlapping PACH candidates')
        b=read_pach(data,offset);end=b['end']
        expanded+=sum(s['expanded_bytes']for s in b['sections'])
        if expanded>2*MAX_EXPANSION:raise ValueError('Corpus input expansion bound exceeded')
        result.append(b)
    return result


def read_corpus_model(payload):
    """Decode observed two/three-packet layouts without moving source data.

    Packet headers contain absolute offsets relative to the same YOBJ
    origin. Reusing the single-packet decoder on a private header view retains
    its index/normal/weight checks. The input payload is never changed.
    Edge has two packet headers; Road Dogg has three in both body and cutout.
    The low root field and 0x38 agree in each observed layout. Other counts and
    mismatches are rejected, and every packet must pass the bounded reader.
    """
    version=struct.unpack_from('>I',checked(payload,32,4))[0]
    count=struct.unpack_from('>I',checked(payload,80,4))[0]
    if version==0x70001:
        if count!=1:raise ValueError('Unreviewed multi-packet Wii layout')
        return read_model(payload)
    if count not in (2,3) or version!=0x70000+count:
        raise ValueError('Unreviewed multi-packet Wii layout')
    checked(payload,24+64,64*count);packets=[]
    for index in range(count):
        view=bytearray(payload)
        struct.pack_into('>I',view,32,0x70001);struct.pack_into('>I',view,80,1)
        view[24+64:24+128]=payload[24+64+64*index:24+128+64*index]
        packets.append(read_model(bytes(view)))
    result=copy.deepcopy(packets[0]);result['meshes']=[]
    result['textures']=sorted({t for p in packets for t in p['textures']})
    tids={t:i for i,t in enumerate(result['textures'])}
    for index,p in enumerate(packets):
        if p['bones']!=result['bones']:raise ValueError('Packet skeleton tables differ')
        for m in p['meshes']:
            mesh=copy.deepcopy(m);mesh.update(index=len(result['meshes']),source_packet=index)
            for v in mesh['vertices']:v['source_packet']=index
            for a in mesh['materials']:a['texture_id']=tids[p['textures'][a['texture_id']]]
            result['meshes'].append(mesh)
    result.update(version=f'0x{version:08x}',mesh_count=len(result['meshes']),texture_count=len(result['textures']),
        triangle_count=sum(p['triangle_count']for p in packets),vertex_count=sum(p['vertex_count']for p in packets))
    result['source_decode_report']=dict(packet_count=count,source_root_field=f'0x{version:08x}',
        packet_header_offsets=[64+64*i for i in range(count)],packets=[p['source_decode_report']for p in packets],
        private_header_view_only=True,source_payload_unchanged=True,
        limitation='Observed two/three-packet headers decoded; other version/count layouts remain unsupported')
    return result


def source_bundle(data,index=0):
    found=bundles(data)
    if not isinstance(index,int) or not 0<=index<len(found):raise ValueError('Variant outside discovered containers')
    pach=found[index];sections={s['id']:s['raw']for s in pach['sections']}
    if 2 not in sections or 9 not in sections:raise ValueError('Missing source body or texture table')
    decoded=[]
    for sid,raw in sections.items():
        if raw.startswith(b'DUMY'):
            if sid not in (2,10000):raise ValueError('Unreviewed auxiliary source model section '+str(sid))
            decoded.append((sid,read_corpus_model(raw)))
    if not decoded or decoded[0][0]!=2:raise ValueError('Main body must precede auxiliary geometry')
    bones=[];names={};origins={}
    for sid,m in decoded:
        for b in m['bones']:
            parent=m['bones'][b['parent']]['name']if b['parent']>=0 else None
            if b['name']not in names:
                names[b['name']]=len(bones);bones.append(dict(b,index=len(bones),parent=-1));origins[b['name']]=parent
            elif origins[b['name']]!=parent:raise ValueError('Shared source bone parent differs: '+b['name'])
    for b in bones:b['parent']=names[origins[b['name']]]if origins[b['name']]is not None else -1
    unified=bone_matrices(dict(bones=bones));maximum=0.
    for sid,m in decoded:
        bm=bone_matrices(m)
        for b in m['bones']:maximum=max(maximum,float(np.max(np.abs(bm[b['index']]-unified[names[b['name']]]))))
    if maximum>1e-6:raise ValueError('Source body/auxiliary bind mismatch')
    textures={};details=[];table=sections[9]
    for entry in parse_textures(table):
        name=entry['name'].lower()
        if name in textures:raise ValueError('Case-ambiguous source texture names')
        rgba,info=decode_tpl(checked(table,entry['offset'],entry['size']))
        textures[name]=rgba;details.append(dict(name=entry['name'],**info))
    used={m['textures'][a['texture_id']].lower()for _,m in decoded for mesh in m['meshes']for a in mesh['materials']if mesh['role']!='Blood'}
    if not used<= {'color','trans'} or 'color'not in used or not used<=textures.keys():
        raise ValueError('Unreviewed or missing source texture binding: '+str(sorted(used)))
    order=[n for n in ('color','trans')if n in used];tids={n:i for i,n in enumerate(order)}
    meshes=[];excluded=[]
    for sid,m in decoded:
        mapping=[names[b['name']]for b in m['bones']]
        for mesh in m['meshes']:
            if mesh['role']=='Blood':
                excluded.append(dict(section=sid,material=mesh['source_material'],triangles=sum(len(a['triangles'])for a in mesh['materials']),
                    reason='Source dynamic blood overlay is not an ordinary static draw; runtime blood remains unimplemented.'))
                continue
            out=copy.deepcopy(mesh);out.update(index=len(meshes),source_section=sid,bone_palette=list(range(len(bones))))
            for v in out['vertices']:
                dense=np.zeros(len(bones));dense[mapping]=v['weights'];v['weights']=dense.tolist()
                v['source_color']=v['color'];v['color']=[255]*4
            for a in out['materials']:a['texture_id']=tids[m['textures'][a['texture_id']].lower()]
            meshes.append(out)
    result=dict(bones=bones,bone_count=len(bones),meshes=meshes,mesh_count=len(meshes),textures=['wii_'+n for n in order],texture_count=len(order),
        geometry_decoded=True,source_skinning_decoded=True,triangle_count=sum(len(a['triangles'])for m in meshes for a in m['materials']),
        vertex_count=sum(len(m['vertices'])for m in meshes))
    return result,[textures[n]for n in order],dict(bundle=index,bundle_offset=pach['offset'],source_sha256=digest(data),
        models=[dict(section=s,decode=m['source_decode_report'],triangles=m['triangle_count'],vertices=m['vertex_count'])for s,m in decoded],
        common_bind_maximum_difference=maximum,excluded_effects=excluded,source_textures=details,
        discovery='Aligned bounded PACH candidates; EPK8 directory semantics still unknown',
        vertex_alpha_policy='White native tint; source shader color bytes retained as provenance; source trans texture alpha retained')


def verified_source_bundle(data,index=0):
    """App boundary: audit the reference itself before any rig/geometry stage."""
    from model_qa.wii_source_encoding import verify
    model,images,report=source_bundle(data,index)
    report['source_encoding_audit']=verify(data,index,model)
    return model,images,report

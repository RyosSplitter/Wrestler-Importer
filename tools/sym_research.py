"""Bounded, read-only source-format research; NOT a SYM decoder/converter.

Record a supplied file's bytes and test existing HCTP/PSP contracts independently.
Neither a filename, declared title nor successful parsing proves a game's format.
Unknown archive variants remain unknown. Nothing here is imported by the app.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct

from tools.pac_inspect import FormatError, inspect_pac, parse_textures
from tools.yobj_read import Reader, read_yobj
from tools.yukes_bpe import decompress


@dataclass(frozen=True)
class Limits:
    max_input: int = 32*1024*1024
    max_expanded: int = 64*1024*1024
    max_nodes: int = 128
    max_depth: int = 6
    max_geometry_records: int = 250000
    max_texture_pixels: int = 4*1024*1024
    max_total_pixels: int = 16*1024*1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def signatures(data, maximum=64):
    """Potential offsets only. Payload bytes can contain false signature hits."""
    result=[]
    for name,magic in (('PAC',b'PAC '),('DPAC',b'DPAC'),('BPE',b'BPE '),
                       ('YOBJ',b'YOBJ'),('RTX3',b'RTX3'),('TIM2',b'TIM2'),('PSP GIM',b'MIG.00.1PSP')):
        start=0
        for _ in range(maximum):
            offset=data.find(magic,start)
            if offset<0:break
            result.append(dict(signature=name,offset=offset));start=offset+1
    return sorted(result,key=lambda r:(r['offset'],r['signature']))[:maximum]


def geometry_preflight(data, metadata, limits):
    """Bound work BEFORE invoking the existing HCTP source-record decoder."""
    reader=Reader(data);reader.limit=metadata['declared_end'];start=reader.u32(36)+8
    work=0;meshes=[]
    for i in range(metadata['mesh_count']):
        a=start+64*i;groups,materials,gp,mp=reader.unpack('<4I',a)
        count=reader.u32(a+40)
        if not 0<count<=160 or not 0<groups<=160 or not 0<materials<=256:
            raise FormatError('Does not match bounded HCTP mesh/group/material contract')
        reader.check(gp+8,groups*32);reader.check(mp+8,materials*208)
        group_vertices=sum(reader.u32(gp+8+j*32) for j in range(groups))
        if group_vertices!=count:raise FormatError('HCTP group counts do not cover source vertices')
        work+=groups+materials+count
        group_fields=[dict(index=j,header_hex=data[gp+8+j*32:gp+8+(j+1)*32].hex(),
            words=list(reader.unpack('<8I',gp+8+j*32))) for j in range(groups)]
        material_fields=[]
        for j in range(materials):
            material_fields.append(dict(index=j,offset=mp+8+j*208,
                raw_hex=data[mp+8+j*208:mp+8+(j+1)*208].hex(),
                texture_slot_candidate=reader.u32(mp+8+j*208+40),
                shader_word_candidate=reader.u32(mp+8+j*208+36),
                interpretation='Offsets from HCTP/related PS2 evidence; SYM meanings not confirmed'))
            strips,sp=reader.unpack('<2I',mp+8+j*208+196)
            if strips>4096:raise FormatError('Draw packet count exceeds research limit')
            work+=strips
            if work>limits.max_geometry_records:raise FormatError('Geometry work exceeds research limit')
            reader.check(sp+8,strips*16)
            for k in range(strips):
                count_c=reader.u32(sp+8+k*16+8);work+=count_c
                if work>limits.max_geometry_records:raise FormatError('Corner records exceed research limit')
        meshes.append(dict(mesh=i,header_hex=data[a:a+64].hex(),source_vertex_count=count,
            group_count=groups,material_count=materials,vif_pointer_relative=reader.u32(a+28),
            position_normal_packet_count=reader.u32(a+32),vif_qwords=reader.u32(a+36),
            groups=group_fields,materials=material_fields))
    return meshes


def tim2_headers(data):
    """Conventional little-endian TIM2 format-0 headers, metadata only.

    No pixel unswizzling, palette decode, mip interpretation or alpha repair.
    Format-1/other alignments are rejected instead of guessed.
    """
    if len(data)<16 or data[:4]!=b'TIM2':raise FormatError('Truncated TIM2 header')
    version,alignment,count=struct.unpack_from('<BBH',data,4)
    if alignment!=0:raise FormatError('TIM2 picture alignment variant needs investigation')
    if not 0<count<=64:raise FormatError('Invalid/research-limited TIM2 picture count')
    cursor=16;pictures=[]
    for i in range(count):
        if cursor+48>len(data):raise FormatError('Truncated TIM2 picture header')
        total,clut,image,header,colors,picture_format,mips,clut_type,image_type,width,height=struct.unpack_from('<IIIHH4BHH',data,cursor)
        if (header<48 or total<header+image+clut or cursor+total>len(data)
                or not width or not height):raise FormatError('Invalid TIM2 picture allocation')
        pictures.append(dict(index=i,offset=cursor,total_bytes=total,header_bytes=header,
            image_bytes=image,clut_bytes=clut,declared_colors=colors,width=width,height=height,
            picture_format=picture_format,mipmap_count=mips,clut_type=clut_type,image_type=image_type,
            gs_tex0_hex=data[cursor+24:cursor+32].hex(),
            data_alignment_relative_16=(cursor+header)%16==0))
        cursor+=total
    return dict(version=version,alignment_variant=alignment,picture_count=count,pictures=pictures,
                trailing_bytes=len(data)-cursor,pixels_decoded=False,
                interpretation='Generic TIM2 format-0 header interpretation; not verified on SYM')


def probe(data, *, declared_game='unknown', source_name='input', limits=None):
    limits=limits or Limits()
    if declared_game not in ('unknown','sym','hctp','psp'):raise ValueError('Unknown provenance label')
    if len(data)>limits.max_input:raise ValueError('Input exceeds research size limit')
    if min(limits.max_nodes,limits.max_depth,limits.max_geometry_records,limits.max_texture_pixels,limits.max_total_pixels)<=0 or limits.max_expanded<0:
        raise ValueError('Invalid research resource limits')
    report=dict(schema='ps2psp.sym-research/1',source=dict(name=source_name,bytes=len(data),sha256=sha(data),declared_game=declared_game),
        verified_source_game='UNKNOWN',conversion_supported=False,source_bytes_modified=False,
        scope='Read-only signatures and existing-contract probes; no SYM support or game compatibility certified',
        signature_hits=signatures(data),nodes=[],limits=vars(limits),findings=[])
    expanded=0;pixels_used=0

    def visit(raw,path,depth,file_offset=None):
        nonlocal expanded,pixels_used
        if depth>limits.max_depth or len(report['nodes'])>=limits.max_nodes:
            report['findings'].append(dict(path=path,status='REVIEW',message='Research depth/node limit reached; inventory incomplete'))
            return
        node=dict(path=path,file_offset=file_offset,bytes=len(raw),sha256=sha(raw),head_hex=raw[:16].hex())
        report['nodes'].append(node)
        try:
            if raw.startswith(b'PAC '):
                node['kind']='PAC'
                if len(raw)>=8 and struct.unpack_from('<I',raw,4)[0]>limits.max_nodes:
                    raise FormatError('PAC section table exceeds research node limit')
                info=inspect_pac(raw)
                node['known_container_contract']='HCTP/PSP u16 ID + u24 table-relative offset + u24 size'
                node['sections']=[{k:s[k] for k in ('index','id','offset','size','kind','sha256')} for s in info['sections']]
                node['duplicate_section_ids']=len({s['id'] for s in info['sections']})!=len(info['sections'])
                node['trailing_bytes']=info['trailing_bytes']
                for s in info['sections']:
                    if len(report['nodes'])>=limits.max_nodes:
                        report['findings'].append(dict(path=path,status='REVIEW',message='Node limit reached; remaining sections not probed'));break
                    visit(raw[s['offset']:s['offset']+s['size']],path+f"/section[{s['index']},id={s['id']}]",depth+1,
                          None if file_offset is None else file_offset+s['offset'])
            elif raw.startswith(b'BPE '):
                node['kind']='BPE';remaining=min(limits.max_input,limits.max_expanded-expanded)
                decoded=decompress(raw,max_output=remaining);expanded+=len(decoded)
                node['expanded_bytes']=len(decoded);node['expanded_sha256']=sha(decoded)
                visit(decoded,path+'/decoded',depth+1)
            elif raw.startswith(b'YOBJ'):
                node['kind']='YOBJ';reader=Reader(raw)
                if len(raw)<72:raise FormatError('Truncated YOBJ header')
                mesh_count,bone_count,texture_count=reader.unpack('<3I',24)
                if mesh_count>512 or bone_count>512 or texture_count>1024:
                    raise FormatError('YOBJ header exceeds research count limits')
                common=read_yobj(raw)
                mesh_start=reader.u32(36)+8
                if (sum(reader.u32(mesh_start+64*i+40) for i in range(mesh_count))>limits.max_geometry_records
                        or sum(reader.u32(mesh_start+64*i+4) for i in range(mesh_count))>4096):
                    raise FormatError('YOBJ vertex/material records exceed research limits')
                node['common_header_contract']='Existing HCTP/PSP interpretation accepted; source title remains unknown'
                node['header_hex']=raw[:72].hex()
                node['counts']={k:common[k] for k in ('mesh_count','bone_count','texture_count')}
                node['model_name']=common['model_name'];node['texture_names']=common['textures']
                node['bones']=common['bones'];node['declared_model_end']=common['declared_end']
                node['layout_probes']={}
                try:
                    fields=geometry_preflight(raw,common,limits)
                    node['hctp_family_candidate_mesh_fields']=fields
                    from tools.hctp_weights import read_hctp_with_weights
                    model=read_hctp_with_weights(raw)
                    node['layout_probes']['hctp_weighted']=dict(passed=True,
                        contract='Existing HCTP groups/corners + rigid/0x280 VIF weights; not independently verified for SYM',
                        weight_lane_and_controller_semantics='UNKNOWN for SYM; normalized sums do not establish correct bone assignment',
                        vertices=model['vertex_count'],source_vertices=model['source_vertex_count'],triangles=model['triangle_count'],
                        mesh_fields=fields,weight_report=model['source_weight_report'])
                except (ValueError,struct.error) as exc:node['layout_probes']['hctp_weighted']=dict(passed=False,error=str(exc))
                try:
                    from tools.psp_mesh_audit import audit_yobj
                    native=audit_yobj(raw)
                    node['layout_probes']['psp']=dict(passed=True,contract='Existing native PSP structure; not a title identifier',
                        vertices=native['report']['vertices'],triangles=native['report']['triangles'])
                except (ValueError,struct.error) as exc:node['layout_probes']['psp']=dict(passed=False,error=str(exc))
            elif raw.startswith(b'RTX3'):
                node['kind']='RTX3'
                if len(raw)<64:raise FormatError('Truncated RTX3 header')
                tex0=struct.unpack_from('<Q',raw,8)[0]
                width,height=1<<((tex0>>26)&15),1<<((tex0>>30)&15);pixels=width*height
                node['registers']=dict(tex0_hex=f'{tex0:016x}',width=width,height=height,
                    psm=(tex0>>20)&63,cpsm=(tex0>>51)&15,csm=(tex0>>55)&1,csa=(tex0>>56)&31)
                if pixels>limits.max_texture_pixels or pixels_used+pixels>limits.max_total_pixels:
                    raise FormatError('Texture exceeds research pixel budget; metadata retained')
                pixels_used+=pixels
                from app.ps2_textures import read_rtx3
                rgba,details=read_rtx3(raw);node['existing_rtx3_decoder']=dict(passed=True,details=details)
                import numpy as np
                alpha=rgba[:,:,3];lo,hi=int(alpha.min()),int(alpha.max())
                node['decoded_alpha']=dict(minimum=lo,maximum=hi,unique_values=int(len(np.unique(alpha))),
                    zero_pixels=int((alpha==0).sum()),opaque_pixels=int((alpha==255).sum()),
                    intermediate_pixels=int(((alpha>0)&(alpha<255)).sum()),modified=False,
                    interpretation='Decoded channel statistics only; SYM material alpha semantics UNKNOWN')
                if lo!=hi and hi<200:node['alpha_review']='Variable low alpha: investigate GS/material semantics; do not force opacity automatically'
            elif raw.startswith(b'TIM2'):
                node['kind']='TIM2';node['header_probe']=tim2_headers(raw)
            elif len(raw)>=16 and raw[4:16]==struct.pack('<3I',0x100,0,16):
                node['kind']='named_texture_table'
                if struct.unpack_from('<I',raw)[0]>limits.max_nodes:raise FormatError('Texture table exceeds research node limit')
                entries=parse_textures(raw)
                node['entries']=entries
                for t in entries:
                    if len(report['nodes'])>=limits.max_nodes:
                        report['findings'].append(dict(path=path,status='REVIEW',message='Node limit reached; remaining textures not probed'));break
                    visit(raw[t['offset']:t['offset']+t['size']],path+f"/texture[{t['index']}]",depth+1,
                          None if file_offset is None else file_offset+t['offset'])
            else:
                node['kind']='UNKNOWN';node['signature_hits']=signatures(raw)
                if raw.startswith(b'DPAC'):node['note']='DPAC-like signature only; archive layout not decoded or reinterpreted as PAC'
        except (ValueError,struct.error) as exc:
            node['probe_error']=str(exc)
            report['findings'].append(dict(path=path,status='REVIEW',message=str(exc)))
    visit(data,'root',0,0)
    report['resources']=dict(nodes=len(report['nodes']),expanded_bytes=expanded,decoded_texture_pixels=pixels_used)
    report['next_gate']='Obtain documented original SYM models, verify each source layer independently, then establish the SYM adapter/profile and source-reference QA before enabling export'
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--declared-game',choices=('unknown','sym','hctp','psp'),default='unknown')
    args=parser.parse_args()
    if args.source.stat().st_size>Limits().max_input:parser.error('Input exceeds 32 MiB research limit')
    data=args.source.read_bytes();report=probe(data,declared_game=args.declared_game,source_name=args.source.name)
    text=json.dumps(report,indent=2,allow_nan=False)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf-8') as f:f.write(text)
    else:print(text,end='')
    return 0


if __name__=='__main__':raise SystemExit(main())

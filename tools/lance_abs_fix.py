"""Pinned, in-place abdomen UV and normal repair on the waist-fixed Lance PAC.

Reference attributes come from the original HCTP surface in the already used
PSP alignment. No geometry, topology, weights or texture payloads are changed.
This is a controlled asset repair, not an automatic conversion pipeline rule.
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
from .lance_waist_fix import SOURCE_SHA256, aligned_source
from .pac_inspect import inspect_pac, parse_textures
from .pac_repack import replace_sections
from .prepare_model import Surface
from .psp_mesh_audit import audit_yobj, digest
from .psp_mesh_merge_trial import sections, write_preview, write_json, dump_audit
from .texture_convert import read_gim
from .yukes_bpe import compress, decompress

BASE_SHA256='3d6540488e41b11532992ba9cd6072aab42c091a4b1bd4f51b430a44e3b3b89d'


def reference_model(source, target):
    _,alignment=aligned_source(source,target)
    aligned=copy.deepcopy(source)
    rotation=np.array(alignment['rotation']);translation=np.array(alignment['translation'])
    for mesh in aligned['meshes']:
        for v in mesh['vertices']:
            v['position']=(alignment['scale']*rotation@v['position']+translation).tolist()
            v['normal']=(rotation@v['normal']).tolist()
    return aligned,alignment


def normal_blend(position):
    x,y,z=position
    # Smoothly taper at the front abdominal region boundary. The existing
    # waistband junction positions/UVs and distant shading remain intact.
    return float(np.clip((-1.9-y)/.55,0,1)*np.clip((y+5.8)/.55,0,1)*
                 np.clip((2.9-abs(x))/.55,0,1)*np.clip((z-.25)/.5,0,1))


def repair(raw,reference):
    before=audit_yobj(raw);out=bytearray(raw);allowed=set();uv_records=[];normal_records=[]
    if any(m['base_flag']!=0x17ff or m['rigid'] for m in before['meshes']):
        raise ValueError('Expected audited float-weight format')
    surfaces={}
    for tid in range(len(before['texture_names'])):
        ms=[dict(m,materials=[a for a in m['materials'] if a['texture_id']==tid])
            for m in reference['meshes'] if any(a['texture_id']==tid for a in m['materials'])]
        surfaces[tid]=Surface(dict(meshes=ms))
    global_surface=Surface(reference);normal_cache={}
    def patch(address,value):
        out[address:address+len(value)]=value;allowed.update(range(address,address+len(value)))
    for mesh,r in zip(before['meshes'],before['report']['mesh_reports']):
        uses=defaultdict(set)
        for mat in mesh['materials']:
            for vi in {i for tri in mat['triangles'] for i in tri}:uses[vi].add(mat['texture_id'])
        for vi,v in enumerate(mesh['vertices']):
            p=v['position'];x,y,z=p
            address=r['vertex_buffer_start']+vi*mesh['stride']+4*mesh['weight_slots']
            if -5.9<y<-2.07 and abs(x)<2.8 and z>.3 and vi in uses:
                candidates=[]
                for tid in sorted(uses[vi]):
                    surface=surfaces[tid];idx,bary,distance=surface.nearest(p)
                    donor,tri=surface.corners[idx]
                    uv=bary@np.array([donor['vertices'][i]['uv'] for i in tri])
                    if distance>.15:raise ValueError('Abdominal UV reference is too far away')
                    candidates.append((tid,uv,distance,donor['index'],tri,bary))
                if max(np.linalg.norm(c[1]-candidates[0][1]) for c in candidates)>1e-5:
                    raise ValueError('Shared vertex requires conflicting material UVs')
                tid,uv,distance,donor_mesh,tri,bary=candidates[0]
                delta=float(np.linalg.norm(uv-v['uv']))
                if delta>1e-5:
                    patch(address,struct.pack('<2f',*uv))
                    uv_records.append(dict(mesh=mesh['index'],vertex=vi,texture=before['texture_names'][tid],
                        before_uv=v['uv'],after_uv=list(struct.unpack('<2f',struct.pack('<2f',*uv))),
                        source_surface_distance=distance,uv_displacement=delta,
                        source_mesh=donor_mesh,source_triangle=tri,barycentric=bary.tolist()))
            blend=normal_blend(p)
            if blend==0:continue
            key=struct.pack('<3f',*p)
            if key not in normal_cache:
                idx,bary,distance=global_surface.nearest(p);donor,tri=global_surface.corners[idx]
                normal=bary@np.array([donor['vertices'][i]['normal'] for i in tri])
                normal/=np.linalg.norm(normal);normal_cache[key]=(normal,distance)
            normal,distance=normal_cache[key]
            if distance>.15:raise ValueError('Abdominal normal reference is too far away')
            final=(1-blend)*np.array(v['normal'])+blend*normal;final/=np.linalg.norm(final)
            patch(address+12,struct.pack('<3f',*final))
            normal_records.append(dict(mesh=mesh['index'],vertex=vi,blend=blend,
                before_normal=v['normal'],after_normal=list(struct.unpack('<3f',struct.pack('<3f',*final))),
                source_surface_distance=distance))
    if len(uv_records)!=3 or len(normal_records)!=82:raise ValueError('Unexpected controlled patch scope')
    result=bytes(out);after=audit_yobj(result)
    changed={i for i,(a,b) in enumerate(zip(raw,result)) if a!=b}
    if len(raw)!=len(result) or not changed<=allowed:raise ValueError('Unexpected binary modification')
    for a,b in zip(before['meshes'],after['meshes']):
        if a['raw_header']!=b['raw_header'] or a['raw_palette_header']!=b['raw_palette_header'] or a['materials']!=b['materials']:
            raise ValueError('Mesh metadata / materials / primitives changed')
        for vi,(av,bv) in enumerate(zip(a['vertices'],b['vertices'])):
            start=vi*a['stride'];count=a['weight_slots']*4
            if a['raw_vertices'][start:start+count]!=b['raw_vertices'][start:start+count]:raise ValueError('Weight bits changed')
            if av['position']!=bv['position'] or av['color']!=bv['color']:raise ValueError('Position or color/alpha changed')
    if before['header']!=after['header'] or before['bone_raw']!=after['bone_raw'] or before['model_descriptor_raw']!=after['model_descriptor_raw']:
        raise ValueError('Header / skeleton / descriptor changed')
    if before['report']['allocations']!=after['report']['allocations'] or before['report']['relocation_locations']!=after['report']['relocation_locations']:
        raise ValueError('Allocations / relocations changed')
    return result,dict(uv_records=uv_records,normal_records=normal_records,changed_bytes=len(changed),
        geometry_weight_bits_palettes_textures_materials_indices_colors_alpha_skeleton_headers_layout_preserved=True)


def detail_preview(model):
    # Include entire triangles touching the abdomen. Selection outlines are
    # cropped geometry for inspection, not holes in the full exported model.
    result=copy.deepcopy(model)
    for m in result['meshes']:
        mats=[]
        for mat in m['materials']:
            triangles=[tri for tri in mat['triangles'] if
                any(-5.9<v['position'][1]<-2.07 and abs(v['position'][0])<2.8 and v['position'][2]>.3
                    for v in [m['vertices'][i] for i in tri]) and
                np.mean([m['vertices'][i]['position'][2] for i in tri])>.3]
            if triangles:mats.append(dict(mat,triangles=triangles))
        m['materials']=mats
        used=sorted({i for mat in mats for tri in mat['triangles'] for i in tri});mapping={v:i for i,v in enumerate(used)}
        for mat in mats:mat['triangles']=[[mapping[i] for i in tri] for tri in mat['triangles']]
        m['vertices']=[m['vertices'][i] for i in used]
    result['meshes']=[m for m in result['meshes'] if m['vertices']]
    return result


def run(source_path,base_path,output):
    if output.exists():raise FileExistsError('Refusing to overwrite output directory')
    source_data=source_path.read_bytes();base=base_path.read_bytes()
    if digest(source_data)!=SOURCE_SHA256 or digest(base)!=BASE_SHA256:raise ValueError('Input does not match pinned source/baseline')
    original=next(raw for s,raw in sections(base) if s['id']==2);before=audit_yobj(original)
    source=load_hctp_with_weights(source_path)
    if source['textures']!=before['texture_names']:raise ValueError('Source texture identities differ')
    reference,alignment=reference_model(source,before)
    fixed,patch_report=repair(original,reference);packed=compress(fixed)
    if decompress(packed)!=fixed:raise ValueError('BPE round trip failed')
    pac=replace_sections(base,{2:packed})
    if len(pac)>148*1024 or len(pac)%2048:raise ValueError('PAC budget / alignment invalid')
    for a,b in zip(inspect_pac(base)['sections'],inspect_pac(pac)['sections']):
        if a['id']!=b['id'] or b['offset']%16:raise ValueError('PAC section order/alignment changed')
        if a['id']!=2 and base[a['offset']:a['offset']+a['size']]!=pac[b['offset']:b['offset']+b['size']]:raise ValueError('Unrelated PAC data changed')
    if next(raw for s,raw in sections(pac) if s['id']==2)!=fixed:raise ValueError('Final model / preview mismatch')
    after=audit_yobj(fixed)
    output.mkdir(parents=True);preview=output/'preview';preview.mkdir();audit=output/'audit';audit.mkdir()
    name='1800-PSP-hybrid-waist-abs-fix.pac';(output/name).write_bytes(pac)
    (preview/'before.yobj').write_bytes(original);(preview/'abs-fixed.yobj').write_bytes(fixed)
    for label,model in [('before',before),('abs-fixed',after),('source-reference',reference)]:
        write_preview(model,preview/(label+'.obj'));write_preview(detail_preview(model),preview/('detail-'+label+'.obj'))
    textures={}
    for section,raw in sections(base):
        if section['id'] in (8,9):
            for entry in parse_textures(raw):textures[entry['name']]=raw[entry['offset']:entry['offset']+entry['size']]
    mtl=[]
    for i,name in enumerate(before['texture_names']):
        if Path(name).name!=name:raise ValueError('Unsafe texture filename')
        gim=textures[name];pixels,palette=read_gim(gim)
        (preview/(name+'.gim')).write_bytes(gim);Image.fromarray(palette[pixels]).save(preview/(name+'.png'))
        mtl.extend(['newmtl texture_%d'%i,'Kd 0.984 0.984 1.000','Ks 0.502 0.502 0.502','map_Kd '+name+'.png'])
    (preview/'preview.mtl').write_text('\n'.join(mtl)+'\n',encoding='ascii')
    dump_audit(before,audit,'before',len(base));dump_audit(after,audit,'after',len(pac))
    report=dict(status='Experimental visual correction; PPSSPP validation pending',filename='1800-PSP-hybrid-waist-abs-fix.pac',
        source_sha256=digest(source_data),baseline_sha256=digest(base),pac_sha256=digest(pac),patch=patch_report,
        readonly_source_alignment=alignment,
        before=dict(pac_bytes=len(base),expanded_model_bytes=len(original),stored_model_bytes=next(s['size'] for s in inspect_pac(base)['sections'] if s['id']==2)),
        after=dict(pac_bytes=len(pac),expanded_model_bytes=len(fixed),stored_model_bytes=len(packed)),
        unchanged_counts={k:before['report'][k] for k in ('meshes','vertices','triangles','textures','material_records','indices','strips','bones')},
        preserved_pac_sections=[8,9],preview_equals_final_model=True,
        notes=['Preserves prior four-junction waistband repair.',
               'Corrects local mapping/shading distortion; does not enforce perfectly mirrored anatomy.',
               'Original-reference OBJ uses unchanged current PSP textures for a resolution-matched comparison.',
               'Diagnostic cropped OBJ boundaries are not missing geometry in the full model.',
               'No new runtime stability claim; original intermittent crashes are not diagnosed by this visual repair.'])
    write_json(output/'report.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path);parser.add_argument('--base',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();report=run(args.source,args.base,args.output)
    print(json.dumps(dict(before=report['before'],after=report['after'],counts=report['unchanged_counts'],
        uv_records=len(report['patch']['uv_records']),normal_records=len(report['patch']['normal_records'])),indent=2))

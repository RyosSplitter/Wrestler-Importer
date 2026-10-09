"""Localized source-reference waistband seam repair for the audited Lance trial.

Positions/UVs at four collapsed material junctions and their one-ring normals
are patched in place. Indices, skin weights, palettes and allocations stay fixed.
This is a pinned controlled experiment, not a general automatic model repair.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from .hctp_weights import load_hctp_with_weights
from .pac_inspect import inspect_pac, parse_textures
from .pac_repack import replace_sections
from .prepare_model import LANDMARKS, bone_matrices, similarity_fit
from .psp_mesh_audit import audit_yobj, digest
from .psp_mesh_merge_trial import dump_audit, sections, write_json, write_preview
from .texture_convert import read_gim
from .yukes_bpe import compress, decompress


SOURCE_SHA256='fe1073d97e9301c62226d611d174324d74cb5223669f3bbeed8a6660bcb80495'
BASE_SHA256={
    '04ff929f8621a768f7c7d3f0a9c2c6e680a587857ee0532044c8dc64880014b0',
    '4f97dd464c9cafe119c8a4afecdabdc58c18bd014e20d2d7007f663ce60fd9db',
}


def position_key(position):
    return struct.pack('<3f',*position)


def aligned_source(source, target):
    sb={b['name']:b['index'] for b in source['bones']}
    tb={b['name']:b['index'] for b in target['bones']}
    sm=bone_matrices(source);tm=bone_matrices(dict(bones=target['bones']))
    names=[n for n in LANDMARKS if n in sb and n in tb]
    scale,rotation,translation=similarity_fit([sm[sb[n]][:3,3] for n in names],
                                             [tm[tb[n]][:3,3] for n in names])
    references=defaultdict(lambda:defaultdict(list))
    for mesh in source['meshes']:
        for material in mesh['materials']:
            tid=material['texture_id']
            for vi in {i for tri in material['triangles'] for i in tri}:
                v=mesh['vertices'][vi]
                p=scale*rotation@v['position']+translation
                references[position_key(p)][tid].append(v['uv'])
    return references,dict(scale=scale,rotation=rotation.tolist(),translation=translation.tolist(),landmarks=names)


def repair(yobj, references):
    before=audit_yobj(yobj)
    if any(m['base_flag']!=0x17ff or m['rigid'] for m in before['meshes']):
        raise ValueError('Expected audited float-weight body format')
    owners=defaultdict(set);uses={}
    for mesh in before['meshes']:
        vi_materials=defaultdict(set)
        for material in mesh['materials']:
            for vi in {i for tri in material['triangles'] for i in tri}:
                vi_materials[vi].add(material['texture_id'])
                owners[position_key(mesh['vertices'][vi]['position'])].add(material['texture_id'])
        uses[mesh['index']]=vi_materials
    # Model coordinates: y increases toward feet. This ROI contains only the
    # upper trunks / waist; face, arms, chest and legs are excluded.
    pants={before['texture_names'].index(n) for n in ('l-pan1','l-pan2')}
    moves={}
    junctions=[]
    for key,materials in owners.items():
        p=np.array(struct.unpack('<3f',key))
        if not (-2.9<p[1]<-.4 and abs(p[0])<2.8 and len(materials)>1 and materials & pants):continue
        if key in references:continue
        candidates=[k for k,m in references.items() if materials<=set(m)]
        if not candidates:raise ValueError('No original same-material seam junction')
        target=min(candidates,key=lambda k:np.linalg.norm(np.array(struct.unpack('<3f',k))-p))
        distance=float(np.linalg.norm(np.array(struct.unpack('<3f',target))-p))
        if distance>1.0:raise ValueError('Reference junction too far from local patch')
        moves[key]=target
        junctions.append(dict(before_position=p.tolist(),after_position=list(struct.unpack('<3f',target)),
                              material_textures=[before['texture_names'][t] for t in sorted(materials)],
                              displacement=distance))
    if len(moves)!=4:raise ValueError('Expected exactly four audited collapsed waistband junctions')
    out=bytearray(yobj);changed=[];allowed=set();affected_positions=set()
    def patch(address,raw):
        out[address:address+len(raw)]=raw;allowed.update(range(address,address+len(raw)))
    for mesh,r in zip(before['meshes'],before['report']['mesh_reports']):
        for vi,v in enumerate(mesh['vertices']):
            key=position_key(v['position'])
            if key not in moves:continue
            target=moves[key];tids=uses[mesh['index']][vi]
            choices=[]
            for tid in tids:
                uv=min(references[target][tid],key=lambda uv:np.linalg.norm(np.array(uv)-v['uv']))
                choices.append(struct.pack('<2f',*uv))
            if not choices or len(set(choices))!=1:
                raise ValueError('A shared vertex requires conflicting UVs; do not guess or split topology')
            suffix=r['vertex_buffer_start']+vi*mesh['stride']+4*mesh['weight_slots']
            patch(suffix,choices[0]);patch(suffix+24,target)
            changed.append(dict(mesh=mesh['index'],vertex=vi,before_position=v['position'],
                                after_position=list(struct.unpack('<3f',target)),before_uv=v['uv'],
                                after_uv=list(struct.unpack('<2f',choices[0])),textures=sorted(tids)))
        for material in mesh['materials']:
            for tri in material['triangles']:
                if any(position_key(mesh['vertices'][vi]['position']) in moves for vi in tri):
                    affected_positions.update(moves.get(position_key(mesh['vertices'][vi]['position']),
                                                        position_key(mesh['vertices'][vi]['position'])) for vi in tri)
    interim=audit_yobj(bytes(out));accum=defaultdict(lambda:np.zeros(3));area_stats=[]
    for mesh in interim['meshes']:
        for material in mesh['materials']:
            for tri in material['triangles']:
                ps=np.array([mesh['vertices'][i]['position'] for i in tri]);normal=np.cross(ps[1]-ps[0],ps[2]-ps[0])
                if np.linalg.norm(normal)<1e-10:raise ValueError('Patch leaves degenerate triangle')
                if any(position_key(p) in affected_positions for p in ps):area_stats.append(float(np.linalg.norm(normal)/2))
                for p in ps:accum[position_key(p)]+=normal
    normal_records=[]
    for mesh,r in zip(interim['meshes'],interim['report']['mesh_reports']):
        for vi,v in enumerate(mesh['vertices']):
            key=position_key(v['position'])
            if key not in affected_positions:continue
            normal=accum[key];length=np.linalg.norm(normal)
            if length<1e-10:raise ValueError('Degenerate patch normal')
            address=r['vertex_buffer_start']+vi*mesh['stride']+4*mesh['weight_slots']+12
            patch(address,struct.pack('<3f',*(normal/length)))
            normal_records.append(dict(mesh=mesh['index'],vertex=vi))
    # Preserve each culling sphere unless the changed geometry needs expansion.
    bounds_changed=[];mesh_array=struct.unpack_from('<I',out,36)[0]+8
    for mesh in audit_yobj(bytes(out))['meshes']:
        center=np.array(struct.unpack_from('<3f',out,mesh_array+mesh['index']*64+48))
        address=mesh_array+mesh['index']*64+60;old=struct.unpack_from('<f',out,address)[0]
        required=max(float(np.linalg.norm(np.array(v['position'])-center)) for v in mesh['vertices'])
        if required>old:
            radius=np.float32(required+.001)
            if radius<required:radius=np.nextafter(radius,np.float32(np.inf))
            patch(address,struct.pack('<f',radius));bounds_changed.append(dict(mesh=mesh['index'],before=old,after=float(radius)))
    result=bytes(out);after=audit_yobj(result)
    changes={i for i,(a,b) in enumerate(zip(yobj,result)) if a!=b}
    if len(yobj)!=len(result) or not changes<=allowed:raise ValueError('Unexpected binary changes')
    for a,b in zip(before['meshes'],after['meshes']):
        if a['bone_palette']!=b['bone_palette'] or a['flag']!=b['flag'] or len(a['vertices'])!=len(b['vertices']):raise ValueError('Palette/layout changed')
        for av,bv in zip(a['materials'],b['materials']):
            if av['raw']!=bv['raw'] or av['strips']!=bv['strips'] or av['strip_headers']!=bv['strip_headers']:raise ValueError('Render state / ordered indices changed')
        for vi in range(len(a['vertices'])):
            aa=a['raw_vertices'][vi*a['stride']:vi*a['stride']+4*a['weight_slots']]
            bb=b['raw_vertices'][vi*b['stride']:vi*b['stride']+4*b['weight_slots']]
            if aa!=bb:raise ValueError('Weight bits changed')
            if a['vertices'][vi]['color']!=b['vertices'][vi]['color']:raise ValueError('Vertex color/alpha changed')
    if before['header']!=after['header'] or before['bone_raw']!=after['bone_raw'] or before['model_descriptor_raw']!=after['model_descriptor_raw']:raise ValueError('Skeleton/header/descriptor changed')
    if before['report']['allocations']!=after['report']['allocations'] or before['report']['relocation_locations']!=after['report']['relocation_locations']:raise ValueError('Offsets/allocations/relocations changed')
    return result,dict(junctions=junctions,changed_position_uv_records=changed,
                       changed_normal_records=normal_records,bounds_changed=bounds_changed,
                       expanded_yobj_changed_bytes=len(changes),affected_triangle_min_area=min(area_stats),
                       scope='Four shared waistband material junctions and one-ring normals',
                       indices_materials_strip_metadata_bone_palettes_weight_bits_color_alpha_headers_offsets_allocations_relocations_identical=True)


def run(source_path,base_path,output):
    if output.exists():raise FileExistsError('Refusing to overwrite output directory')
    source_bytes=source_path.read_bytes();base=base_path.read_bytes()
    if digest(source_bytes)!=SOURCE_SHA256 or digest(base) not in BASE_SHA256:raise ValueError('Input does not match pinned source/baseline')
    original=next(raw for s,raw in sections(base) if s['id']==2)
    before=audit_yobj(original);source=load_hctp_with_weights(source_path)
    if source['textures']!=before['texture_names']:raise ValueError('Reference texture identities differ')
    reference,alignment=aligned_source(source,before)
    fixed,patch_report=repair(original,reference);packed=compress(fixed)
    if decompress(packed)!=fixed:raise ValueError('BPE round trip failed')
    pac=replace_sections(base,{2:packed})
    if len(pac)>148*1024:raise ValueError('PAC exceeds budget')
    for a,b in zip(inspect_pac(base)['sections'],inspect_pac(pac)['sections']):
        if a['id']!=b['id'] or b['offset']%16:raise ValueError('PAC section order/alignment changed')
        if a['id']!=2 and base[a['offset']:a['offset']+a['size']]!=pac[b['offset']:b['offset']+b['size']]:raise ValueError('Unrelated PAC data changed')
    if next(raw for s,raw in sections(pac) if s['id']==2)!=fixed or len(pac)%2048:raise ValueError('Final PAC validation failed')
    output.mkdir(parents=True);preview=output/'preview';preview.mkdir();audit=output/'audit';audit.mkdir()
    name='1800-PSP-hybrid-waist-seam-fix.pac' if before['report']['meshes']==57 else '1800-PSP-hybrid-merged-waist-seam-fix.pac'
    (output/name).write_bytes(pac)
    (preview/'before.yobj').write_bytes(original);(preview/'waist-fixed.yobj').write_bytes(fixed)
    write_preview(before,preview/'before.obj');write_preview(audit_yobj(fixed),preview/'waist-fixed.obj')
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
    dump_audit(before,audit,'before',len(base));dump_audit(audit_yobj(fixed),audit,'waist-fixed',len(pac))
    report=dict(status='Experimental localized visual repair; PPSSPP validation pending',
                source_sha256=digest(source_bytes),baseline_sha256=digest(base),pac_sha256=digest(pac),pac_filename=name,
                alignment_of_readonly_reference=alignment,patch=patch_report,
                before=dict(pac_bytes=len(base),expanded_yobj_bytes=len(original),stored_model_bytes=next(s['size'] for s in inspect_pac(base)['sections'] if s['id']==2)),
                after=dict(pac_bytes=len(pac),expanded_yobj_bytes=len(fixed),stored_model_bytes=len(packed)),
                unchanged_counts={k:before['report'][k] for k in ('meshes','vertices','triangles','textures','material_records','indices','strips','bones')},
                unchanged_pac_sections=[8,9],preview_yobj_equals_final_decompressed_pac=True,
                weights='Existing PSP float weight bytes unchanged; no source weights copied or new rig applied')
    write_json(output/'report.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--base',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=run(args.source,args.base,args.output)
    print(json.dumps(dict(before=report['before'],after=report['after'],counts=report['unchanged_counts'],
                          changed_junctions=len(report['patch']['junctions']),report=str(args.output/'report.json')),indent=2))


if __name__=='__main__':main()

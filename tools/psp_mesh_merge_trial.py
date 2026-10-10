"""Reproduce the isolated Lance mesh-buffer trial; never overwrites an output.

python -m tools.psp_mesh_merge_trial --input BEFORE.pac --provenance parts.json
    --output NEW_DIRECTORY [--reference label=PATH.pac ...]
The provenance file pins the audited input YOBJ hash and original target parts.
"""
import argparse
import csv
import itertools
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from .pac_inspect import inspect_pac, parse_textures
from .pac_repack import replace_sections
from .psp_mesh_audit import audit_yobj, digest
from .psp_mesh_merge import compatible, plan, rebuild, verify
from .texture_convert import read_gim
from .weight_trial_review import POSES, deform
from .yukes_bpe import compress, decompress


def write_json(path, value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def sections(data):
    for s in inspect_pac(data)['sections']:
        raw = data[s['offset']:s['offset']+s['size']]
        yield s, decompress(raw) if raw.startswith(b'BPE ') else raw


def dump_audit(model, folder, label, pac_size=None):
    report = dict(model['report'],bone_records=model['bones'],pac_bytes=pac_size)
    write_json(folder/(label+'.json'),report)
    columns = ['mesh','vertices','triangles','indices','material_records','vertex_flag','vertex_stride',
               'weight_format','weight_slots','active_influences','weight_sum_range',
               'bone_palette_zero_based','bone_names','bounds','opaque_mesh_metadata_hex','separation_rules']
    with (folder/(label+'-meshes.csv')).open('w',encoding='utf-8',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for mesh in report['mesh_reports']:
            writer.writerow({k:json.dumps(mesh[k],ensure_ascii=False) if isinstance(mesh[k],(list,dict)) else mesh[k] for k in columns})
    columns = ['mesh','material','vertex_buffer_vertices','referenced_vertices','triangles','indices','strips',
               'texture_id','texture','material_control','index_format','vertex_flag','vertex_stride',
               'weight_format','weight_slots','bone_palette_zero_based','bone_names','opaque_render_state_hex','strip_metadata']
    with (folder/(label+'-submeshes.csv')).open('w',encoding='utf-8',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for mesh in report['mesh_reports']:
            for material in mesh['submeshes']:
                row = dict(mesh,**material)
                writer.writerow({k:json.dumps(row[k],ensure_ascii=False) if isinstance(row[k],(list,dict)) else row[k] for k in columns})
    with (folder/(label+'-vertex-weights.csv')).open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f);writer.writerow(['mesh','vertex','palette_zero_based','weight_slots','nonzero_bone_weights'])
        for mesh in model['meshes']:
            for vi,v in enumerate(mesh['vertices']):
                writer.writerow([mesh['index'],vi,json.dumps(mesh['bone_palette']),json.dumps(v['weights']),
                                 json.dumps([[b,w] for b,w in zip(mesh['bone_palette'],v['weights']) if w])])


def write_preview(model, path):
    # Proper rotation (x,z,-y), identical for both exports; preserves winding.
    lines=['# Native decoded rest geometry; OBJ has no PSP skin/render state','mtllib preview.mtl']
    offset=0
    for mesh in model['meshes']:
        lines.append('g native_mesh_%02d'%mesh['index'])
        for v in mesh['vertices']:
            x,y,z=v['position'];lines.append('v %.9g %.9g %.9g'%(x,z,-y))
        for v in mesh['vertices']:lines.append('vt %.9g %.9g'%tuple(v['uv']))
        for v in mesh['vertices']:
            x,y,z=v['normal'];lines.append('vn %.9g %.9g %.9g'%(x,z,-y))
        for material in mesh['materials']:
            lines.append('usemtl texture_%d'%material['texture_id'])
            for triangle in material['triangles']:
                lines.append('f '+' '.join('%d/%d/%d'%((offset+i+1,)*3) for i in triangle))
        offset+=len(mesh['vertices'])
    path.write_text('\n'.join(lines)+'\n',encoding='ascii',newline='\n')


def pose_validation(a,b):
    def dense(model):
        positions=np.array([v['position'] for m in model['meshes'] for v in m['vertices']])
        weights=np.zeros((len(positions),len(model['bones'])));row=0
        for mesh in model['meshes']:
            for v in mesh['vertices']:
                for bone,w in zip(mesh['bone_palette'],v['weights']):weights[row,bone]=w
                row+=1
        return positions,weights
    pa,wa=dense(a);pb,wb=dense(b)
    if not np.array_equal(pa,pb) or not np.array_equal(wa,wb):raise ValueError('Dense positions/weights differ')
    values={}
    for name,pose in POSES.items():
        aa=deform(dict(bones=a['bones'],bone_count=len(a['bones'])),pa,wa,pose)
        bb=deform(dict(bones=b['bones'],bone_count=len(b['bones'])),pb,wb,pose)
        maximum=float(np.max(np.abs(aa-bb)))
        if maximum!=0:raise ValueError('Analytical LBS changed in '+name)
        values[name]=dict(maximum_position_component_difference=maximum)
    return values


def run(input_path, provenance_path, output, references=()):
    if output.exists():raise FileExistsError('Output directory already exists')
    pac=input_path.read_bytes();original_pac=inspect_pac(pac)
    models=[raw for s,raw in sections(pac) if s['id']==2 and raw.startswith(b'YOBJ')]
    if len(models)!=1:raise ValueError('Expected one main PSP model')
    before=models[0];source=audit_yobj(before)
    provenance=json.loads(provenance_path.read_text());parts=provenance['parts']
    if digest(before)!=provenance['source_yobj_sha256']:
        raise ValueError('Input does not match the verified body-part provenance')
    groups=plan(source,parts);after=rebuild(before,groups,parts)
    validation=verify(before,after,groups);target=audit_yobj(after)
    poses=pose_validation(source,target)
    packed=compress(after)
    if decompress(packed)!=after:raise ValueError('BPE round trip failed')
    rebuilt=replace_sections(pac,{2:packed});final_pac=inspect_pac(rebuilt)
    if len(rebuilt)>148*1024:raise ValueError('PAC exceeds 148 KiB')
    unchanged=[]
    for a,b in zip(original_pac['sections'],final_pac['sections']):
        if a['id']!=b['id'] or b['offset']%16:raise ValueError('PAC order/alignment changed')
        if a['id']!=2:
            if pac[a['offset']:a['offset']+a['size']]!=rebuilt[b['offset']:b['offset']+b['size']]:
                raise ValueError('Unrelated PAC payload changed')
            unchanged.append(a['id'])
    if len(rebuilt)%2048:raise ValueError('PAC final alignment failed')
    # Audit the final decompressed PAC payload, not just an intermediate file.
    final_model=next(raw for s,raw in sections(rebuilt) if s['id']==2)
    if final_model!=after:raise ValueError('Preview/final PAC models disagree')
    verify(before,final_model,groups)
    output.mkdir(parents=True)
    audits=output/'audit';audits.mkdir();preview=output/'preview';preview.mkdir()
    (output/'1800-PSP-hybrid-compatible-mesh-merge.pac').write_bytes(rebuilt)
    (preview/'before.yobj').write_bytes(before);(preview/'optimized.yobj').write_bytes(after)
    write_preview(source,preview/'before.obj');write_preview(target,preview/'optimized.obj')
    mtl=[]
    for i,name in enumerate(source['texture_names']):
        if Path(name).name!=name:raise ValueError('Unsafe texture filename')
        mtl.extend(['newmtl texture_%d'%i,'Kd 0.984 0.984 1.000','Ks 0.502 0.502 0.502','map_Kd '+name+'.png'])
    (preview/'preview.mtl').write_text('\n'.join(mtl)+'\n',encoding='ascii')
    textures={}
    for s,raw in sections(pac):
        if s['id'] not in (8,9):continue
        for t in parse_textures(raw):textures[t['name']]=raw[t['offset']:t['offset']+t['size']]
    for name in source['texture_names']:
        gim=textures[name];pixels,palette=read_gim(gim)
        Image.fromarray(palette[pixels]).save(preview/(name+'.png'))
        (preview/(name+'.gim')).write_bytes(gim)
    dump_audit(source,audits,'lance-before',len(pac));dump_audit(target,audits,'lance-optimized',len(rebuilt))
    pair_report=[]
    for i,j in itertools.combinations(range(len(source['meshes'])),2):
        reasons=compatible([source['meshes'][i],source['meshes'][j]],[parts[i],parts[j]])
        pair_report.append(dict(meshes=[i,j],reasons_to_keep_separate=reasons,
                                directly_compatible_under_conservative_policy=not reasons))
    write_json(audits/'lance-pair-compatibility.json',pair_report)
    reference_report=[]
    for label,path in references:
        raw_pac=path.read_bytes();pr=inspect_pac(raw_pac)
        for s,raw in sections(raw_pac):
            if not raw.startswith(b'YOBJ'):continue
            ref=audit_yobj(raw);name=label+'-section-'+str(s['id'])
            dump_audit(ref,audits,name,len(raw_pac))
            reference_report.append(dict(label=name,pac_sha256=digest(raw_pac),yobj_sha256=digest(raw),
                                          **{k:ref['report'][k] for k in ('meshes','vertices','triangles','textures','material_records','strips','indices','expanded_bytes')}))
    def summary(model,container):
        return dict(**{k:model['report'][k] for k in ('meshes','vertices','triangles','textures','material_records','strips','indices','expanded_bytes')},
                    pac_bytes=len(container),pac_sha256=digest(container),
                    model_stored_bytes=next(s['size'] for s in inspect_pac(container)['sections'] if s['id']==2),
                    unique_texture_materials=len(model['texture_names']),
                    obj_nonempty_group_material_combinations=sum(len(set(mat['texture_id'] for mat in mesh['materials'] if mat['triangles'])) for mesh in model['meshes']))
    merge_map=[]
    for new,group in enumerate(groups):
        merge_map.append(dict(output_mesh=new,original_meshes_zero_based=group,target_part=parts[group[0]],
                              **{k:target['report']['mesh_reports'][new][k] for k in ('vertices','triangles','indices','vertex_stride','bone_palette_zero_based','bounds')}))
    report=dict(status='Experimental; PSP runtime validation required',
                source_input_filename=input_path.name,source_yobj_sha256=digest(before),output_yobj_sha256=digest(after),
                before=summary(source,pac),after=summary(target,rebuilt),merge_map=merge_map,
                native_references=reference_report,validation=validation,analytical_pose_validation=poses,
                unchanged_pac_sections_byte_identical=unchanged,
                preview_yobj_equals_decompressed_final_pac=True,
                field_changes=['Mesh header and descriptor counts','Layout pointers, sizes, alignment and POF0 relocation locations',
                               'Merged vertex-buffer lengths, GE weight-slot counts/strides and bone palettes',
                               'Existing weight bytes permuted by bone identity with zero-only extra slots',
                               'Local indices offset within merged vertex buffers; global ordered indices unchanged',
                               'Merged culling spheres expanded to enclose all original spheres; other bounds unchanged',
                               'Section 2 BPE bytes, PAC section table offsets/sizes, zero padding'],
                uncertainties=['Unknown opaque metadata copied; complete engine semantics are undocumented',
                               'Mesh-count changes may affect undocumented engine assumptions despite static and LBS equivalence',
                               'Noesis/OBJ cannot validate PSP render state, game animations or runtime memory safety',
                               'No cause of stretched turnbuckles or intermittent crashes established'])
    write_json(output/'report.json',report);write_json(output/'provenance.json',provenance)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--provenance',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--reference',action='append',default=[])
    args=parser.parse_args()
    references=[]
    for value in args.reference:
        label,path=value.split('=',1)
        if not label.replace('-','').isalnum():raise ValueError('Invalid reference label')
        references.append((label,Path(path)))
    report=run(args.input,args.provenance,args.output,references)
    print(json.dumps(dict(before=report['before'],after=report['after'],merged=[m for m in report['merge_map'] if len(m['original_meshes_zero_based'])>1]),indent=2))


if __name__=='__main__':main()

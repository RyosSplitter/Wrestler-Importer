"""Isolated zero-weight slot-padding control; no converter changes.

Use to test a native-layout hypothesis, not to impose an unproven loader limit.
Only explicitly selected float-weight meshes are edited. Every effective weight,
attribute and oriented primitive must remain exact after native serialization.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np

from desktop.core import validate_pac
from desktop.texture_optimizer.candidates import read_gim
from model_qa.geometry import geometry,posed
from model_qa.ocular import skin
from model_qa.head import controller_probes
from model_qa.pipeline import POSES
from tools.pac_inspect import inspect_pac
from tools.pac_repack import replace_sections
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge import write_model,verify
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress,decompress


def pad_mesh(mesh,bones,slots):
    if mesh.get('rigid') or mesh['base_flag']!=0x17ff:
        raise ValueError('Control supports only float32 skinned vertices')
    palette=mesh['bone_palette'];old=len(palette)
    if not old<slots<=8:raise ValueError('Padding needs more slots, at most eight')
    if len(bones)<slots:raise ValueError('Not enough distinct existing bones')
    extras=[]
    for b in palette:
        parent=bones[b]['parent'];seen=set()
        while parent!=-1:
            if parent in seen:raise ValueError('Cyclic skeleton')
            seen.add(parent)
            if parent not in palette and parent not in extras:extras.append(parent)
            parent=bones[parent]['parent']
    extras += [i for i in range(len(bones)) if i not in palette and i not in extras]
    extras=extras[:slots-old];result=copy.deepcopy(mesh)
    result['bone_palette']=palette+extras;result['weight_slots']=slots
    result['stride']=36+4*slots
    raw=[]
    for i,v in enumerate(result['vertices']):
        v['weights']=list(v['weights'])+[0.]*len(extras)
        before=mesh['raw_vertices'][i*mesh['stride']:(i+1)*mesh['stride']]
        raw.append(before[:4*old]+bytes(4*len(extras))+before[4*old:])
    result['raw_vertices']=b''.join(raw)
    return result


def exact_pose_checks(before,after):
    a,b=geometry(before),geometry(after)
    if not np.array_equal(a.vertices,b.vertices) or not np.array_equal(a.faces,b.faces) or not np.array_equal(a.weights,b.weights):
        raise ValueError('Effective geometry/topology/weights changed')
    result={}
    for name,controls in POSES.items():
        x,y=posed(a,controls),posed(b,controls)
        delta=float(np.abs(x.vertices-y.vertices).max())
        if delta:raise ValueError('Body analytical motion changed')
        result[name]=delta
    cranial={}
    for name,probe in controller_probes(before).items():
        x,_=skin(a,probe);y,_=skin(b,probe)
        delta=float(np.abs(x.vertices-y.vertices).max())
        if delta:raise ValueError('Head analytical motion changed')
        cranial[name]=delta
    return dict(status='pass',effective_positions_faces_dense_weights_exact=True,
        body_pose_maximum_component_deltas=result,head_probe_maximum_component_deltas=cranial,
        limitation='Exact analytical LBS replay; cannot prove SVR runtime interpretation.')


def build(input_path,output,meshes,slots=3):
    input_path,output=map(Path,(input_path,output))
    if output.exists():raise FileExistsError(output)
    data=input_path.read_bytes();original={s['id']:raw for s,raw in sections(data)}
    model=audit_yobj(original[2]);changed=copy.deepcopy(model)
    if len(set(meshes))!=len(meshes) or not meshes or any(i<0 or i>=len(model['meshes']) for i in meshes):
        raise ValueError('Explicit, unique existing mesh IDs required')
    for i in meshes:changed['meshes'][i]=pad_mesh(changed['meshes'][i],changed['bones'],slots)
    groups=[[i] for i in range(len(changed['meshes']))]
    yobj=write_model(changed,groups);preservation=verify(original[2],yobj,groups)
    native=audit_yobj(yobj);poses=exact_pose_checks(model,native)
    for i,(old,new) in enumerate(zip(model['meshes'],native['meshes'])):
        if i not in meshes and (old['raw_vertices']!=new['raw_vertices'] or
                old['bone_palette']!=new['bone_palette'] or old['stride']!=new['stride'] or old['flag']!=new['flag']):
            raise ValueError('Unselected mesh vertex layout changed')
    attempts=[];candidate=None
    for symbols in (200,220):
        payload=compress(yobj,max_distinct=symbols)
        if decompress(payload)!=yobj:raise ValueError('BPE round trip changed YOBJ')
        pac=replace_sections(data,{2:payload})
        attempts.append(dict(symbols=symbols,pac_bytes=len(pac),model_stored_bytes=len(payload)))
        if candidate is None or len(pac)<len(candidate):candidate=pac
        if len(pac)<=148000:break
    if len(candidate)>148000:raise ValueError('Control exceeds PAC budget; no geometry/texture fallback allowed')
    validate_pac(candidate,data,gim_reader=read_gim)
    after={s['id']:raw for s,raw in sections(candidate)}
    a,b=inspect_pac(data),inspect_pac(candidate)
    stored={s['id']:data[s['offset']:s['offset']+s['size']] for s in a['sections']}
    newstored={s['id']:candidate[s['offset']:s['offset']+s['size']] for s in b['sections']}
    if set(original)!=set(after) or any(original[i]!=after[i] or stored[i]!=newstored[i] for i in original if i!=2):
        raise ValueError('Unrelated stored/decoded PAC section changed')
    if input_path.read_bytes()!=data:raise ValueError('Input changed')
    output.mkdir(parents=True);pac_path=output/'Rock-scalp-three-slot-CONTROL.pac'
    pac_path.write_bytes(candidate);(output/'candidate.yobj').write_bytes(yobj)
    digest=lambda raw:hashlib.sha256(raw).hexdigest()
    report=dict(status='structurally-valid isolated control; PPSSPP outcome unknown',
        input_sha256=digest(data),candidate_sha256=digest(candidate),
        original_bytes=len(data),candidate_bytes=len(candidate),packaging_attempts=attempts,
        original_decoded_yobj_bytes=len(original[2]),candidate_decoded_yobj_bytes=len(yobj),
        change='Only selected mesh palettes/weight-slot count/stride; extra weights zero. Required YOBJ/PAC offsets, size fields, relocation and compression rebuilt.',
        meshes=[dict(mesh=i,old_palette=model['meshes'][i]['bone_palette'],new_palette=native['meshes'][i]['bone_palette'],
            old_stride=model['meshes'][i]['stride'],new_stride=native['meshes'][i]['stride'],
            old_flag=hex(model['meshes'][i]['flag']),new_flag=hex(native['meshes'][i]['flag'])) for i in meshes],
        preservation=preservation,poses=poses,
        original_counts={k:model['report'][k] for k in ('meshes','vertices','triangles')},
        candidate_counts={k:native['report'][k] for k in ('meshes','vertices','triangles')},
        all_non_model_sections_stored_and_decoded_exact=True,
        unselected_mesh_vertex_bytes_palettes_strides_flags_exact=True,
        section_sha256_before={str(i):digest(v) for i,v in original.items()},
        section_sha256_after={str(i):digest(v) for i,v in after.items()},
        psp_structure_alignment_offsets_palettes_indices_weights_pass=True,
        hypothesis='Single-slot float skinning may be interpreted differently by the SVR loader. Native sample convention supports testing, not proof of a hard three-slot minimum.',
        no_production_converter_changes=True,input_preserved=True)
    (output/'experiment.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/(pac_path.name+'.sha256')).write_text(report['candidate_sha256']+'  '+pac_path.name+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--mesh',action='append',type=int,required=True);p.add_argument('--slots',type=int,default=3)
    a=p.parse_args();r=build(a.input,a.output,a.mesh,a.slots)
    print(json.dumps({k:r[k] for k in ('status','candidate_bytes','candidate_sha256','meshes')}))

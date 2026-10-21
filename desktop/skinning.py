"""Exact single-slot skinning layout adaptation, separate from geometry processing.

Only one-slot float32 skinned buffers are padded. Added bone weights are zero;
this is an SVR compatibility policy, not a generic PSP hardware restriction.
"""
from desktop.limits import IN_RING_MAX_PAC_BYTES
import copy
import hashlib

import numpy as np

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



def adapt_yobj(raw):
    model=audit_yobj(raw)
    selected=[m['index'] for m in model['meshes']
              if not m['rigid'] and m['base_flag']==0x17ff and len(m['bone_palette'])==1]
    if not selected:return raw,dict(changed_meshes=[],added_vertex_buffer_bytes=0)
    changed=copy.deepcopy(model)
    for i in selected:changed['meshes'][i]=pad_mesh(model['meshes'][i],model['bones'],3)
    groups=[[i] for i in range(len(model['meshes']))]
    result=write_model(changed,groups)
    preservation=verify(raw,result,groups);native=audit_yobj(result)
    for i,(old,new) in enumerate(zip(model['meshes'],native['meshes'])):
        if i not in selected and (old['raw_vertices']!=new['raw_vertices'] or
                old['bone_palette']!=new['bone_palette'] or old['stride']!=new['stride'] or old['flag']!=new['flag']):
            raise ValueError('Unselected mesh vertex layout changed')
    pose_report=exact_pose_checks(model,native)
    return result,dict(changed_meshes=[dict(mesh=i,
        old_palette=model['meshes'][i]['bone_palette'],new_palette=native['meshes'][i]['bone_palette'],
        old_stride=model['meshes'][i]['stride'],new_stride=native['meshes'][i]['stride'],
        old_flag=hex(model['meshes'][i]['flag']),new_flag=hex(native['meshes'][i]['flag']),
        vertices=len(model['meshes'][i]['vertices'])) for i in selected],
        added_vertex_buffer_bytes=sum(8*len(model['meshes'][i]['vertices']) for i in selected),
        original_decoded_bytes=len(raw),decoded_bytes=len(result),
        preservation=preservation,poses=pose_report,
        unselected_mesh_layouts_exact=True)


def apply_single_slot_compatibility(data,*,max_bytes=IN_RING_MAX_PAC_BYTES,cancel=lambda:None):
    """Adapt an already fitted PAC without texture/geometry budget fallbacks.

    Existing packaging/compression code is reused. If layout overhead cannot fit,
    export is withheld rather than sacrificing the established conversion.
    """
    cancel()
    before={s['id']:raw for s,raw in sections(data)}
    changes={};models=[]
    for section,raw in before.items():
        if not raw.startswith(b'YOBJ'):continue
        cancel();adapted,report=adapt_yobj(raw)
        if adapted!=raw:
            changes[section]=adapted;models.append(dict(section=section,**report))
    attempts=[];candidate=data
    if changes:
        candidate=None
        for symbols in (200,220):
            cancel();payloads={}
            for section,raw in changes.items():
                cancel();payloads[section]=compress(raw,max_distinct=symbols)
                if decompress(payloads[section])!=raw:raise ValueError('Compatibility BPE round trip changed a model')
            trial=replace_sections(data,payloads)
            attempts.append(dict(max_distinct=symbols,pac_bytes=len(trial)))
            if candidate is None or len(trial)<len(candidate):candidate=trial
            if len(candidate)<=max_bytes:break
    if len(candidate)>max_bytes:
        raise ValueError('Single-slot skinning compatibility exceeds the PAC budget. Export withheld; geometry and textures were not reduced. Disable the compatibility option only for an explicit A/B test.')
    if len(candidate)%2048:raise ValueError('Compatibility PAC alignment failed')
    after={s['id']:raw for s,raw in sections(candidate)}
    def stored(raw):
        return {s['id']:raw[s['offset']:s['offset']+s['size']] for s in inspect_pac(raw)['sections']}
    a,b=stored(data),stored(candidate)
    if before.keys()!=after.keys():raise ValueError('Compatibility model set changed')
    for section,raw in before.items():
        if section in changes:
            if after[section]!=changes[section]:raise ValueError('Compatibility model payload changed')
        elif raw!=after[section] or a[section]!=b[section]:raise ValueError('Unrelated PAC payload changed')
    digest=lambda raw:hashlib.sha256(raw).hexdigest()
    return candidate,dict(enabled=True,status='pass',policy='One-slot float32 skinned buffers padded to three with exact zero weights; two-slot and rigid layouts unchanged.',
        changed_models=models,changed_meshes=sum(len(m['changed_meshes']) for m in models),
        added_vertex_buffer_bytes=sum(m['added_vertex_buffer_bytes'] for m in models),
        original_bytes=len(data),bytes=len(candidate),max_pac_bytes=max_bytes,
        input_sha256=digest(data),sha256=digest(candidate),packaging_attempts=attempts,
        unrelated_stored_and_decoded_sections_exact=True,
        limitation='Rock control visually accepted by user in SVR 2011 PSP; general loader semantics and expanded runtime memory limits remain unknown.')

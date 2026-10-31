"""Patch UV float pairs only; all geometry, skinning and native state stay exact."""
import struct
import numpy as np


def patch(raw,uv):
    from model_creator.native import audit_yobj
    model=audit_yobj(raw);uv=np.asarray(uv,dtype=np.float32)
    count=sum(len(m['vertices']) for m in model['meshes'])
    if uv.shape!=(count,2) or not np.isfinite(uv).all() or np.max(np.abs(uv))>1024:raise ValueError('Invalid native UV edits')
    out=bytearray(raw);allowed=set();offset=0
    for mesh,row in zip(model['meshes'],model['report']['mesh_reports']):
        if mesh['rigid'] or mesh['base_flag']!=0x17ff:raise ValueError('Unsupported UV vertex layout')
        for i in range(len(mesh['vertices'])):
            address=row['vertex_buffer_start']+i*mesh['stride']+4*mesh['weight_slots']
            if not np.array_equal(uv[offset+i],mesh['vertices'][i]['uv']):
                out[address:address+8]=struct.pack('<2f',*uv[offset+i]);allowed.update(range(address,address+8))
        offset+=len(mesh['vertices'])
    result=bytes(out);after=audit_yobj(result)
    changed={i for i,(a,b) in enumerate(zip(raw,result)) if a!=b}
    if len(result)!=len(raw) or not changed<=allowed:raise ValueError('UV edit changed unrelated native bytes')
    actual=np.array([v['uv'] for m in after['meshes'] for v in m['vertices']],np.float32)
    if not np.array_equal(actual,uv):raise ValueError('Native UV readback differs from preview')
    return result,dict(native_readback=True,geometry_topology_weights_bones_materials_exact=True,changed_bytes=len(changed),edited_records=len(allowed)//8)


def commit(raw,baseline,textures,recipe):
    from .document import Document,signature
    doc=Document(baseline,textures);doc.restore(recipe)
    result,proof=patch(raw,doc.uv)
    canonical=doc.recipe()
    proof.update(signature=signature(canonical) if canonical else None,baseline_sha256=doc.sha256,changed_textures=[n for n in textures if doc.textures[n]!=textures[n]])
    return result,doc.textures,proof

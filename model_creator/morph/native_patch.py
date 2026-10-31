"""Whitelisted in-place native edits; topology/UV/weights/render state stay exact."""
import hashlib
import struct

import numpy as np


def patch(raw,positions,normals):
    from model_creator.native import audit_yobj
    before=audit_yobj(raw);out=bytearray(raw);allowed=set();offset=0;bounds=[]
    positions,normals=np.asarray(positions,dtype=float),np.asarray(normals,dtype=float)
    count=sum(len(m['vertices']) for m in before['meshes'])
    if positions.shape!=(count,3) or normals.shape!=(count,3) or not np.isfinite(positions).all() or not np.isfinite(normals).all():
        raise ValueError('Morph worker returned invalid native attributes')
    def write(address,data):out[address:address+len(data)]=data;allowed.update(range(address,address+len(data)))
    mesh_table=8+struct.unpack_from('<I',raw,36)[0]
    for mesh,row in zip(before['meshes'],before['report']['mesh_reports']):
        if mesh['rigid'] or mesh['base_flag']!=0x17ff:raise ValueError('Unsupported morph vertex layout')
        length=len(mesh['vertices']);points=positions[offset:offset+length]
        for vi in range(length):
            suffix=row['vertex_buffer_start']+vi*mesh['stride']+4*mesh['weight_slots']
            write(suffix+12,struct.pack('<3f',*normals[offset+vi]))
            write(suffix+24,struct.pack('<3f',*points[vi]))
        address=mesh_table+mesh['index']*64+48
        center=np.array(struct.unpack_from('<3f',raw,address));radius=struct.unpack_from('<f',raw,address+12)[0]
        required=float(np.linalg.norm(points-center,axis=1).max())
        if required>radius:
            enlarged=np.float32(required+.001)
            write(address+12,struct.pack('<f',enlarged));bounds.append(dict(mesh=mesh['index'],before=radius,after=float(enlarged)))
        offset+=length
    result=bytes(out);after=audit_yobj(result)
    changed={i for i,(a,b) in enumerate(zip(raw,result)) if a!=b}
    if len(raw)!=len(result) or not changed<=allowed:raise ValueError('Morph changed bytes outside positions, normals or mesh bounds')
    if before['bone_raw']!=after['bone_raw']:raise ValueError('Morph changed native bones')
    for a,b in zip(before['meshes'],after['meshes']):
        if a['bone_palette']!=b['bone_palette'] or a['flag']!=b['flag'] or len(a['vertices'])!=len(b['vertices']):raise ValueError('Morph changed native layout')
        for x,y in zip(a['materials'],b['materials']):
            if x['raw']!=y['raw'] or x['strips']!=y['strips'] or x['strip_headers']!=y['strip_headers']:raise ValueError('Morph changed indices/material state')
        for x,y in zip(a['vertices'],b['vertices']):
            if any(x[k]!=y[k] for k in ('uv','color','weights')):raise ValueError('Morph changed UV/color/weights')
    return result,dict(native_readback=True,topology_uv_weights_materials_bones_exact=True,
                       changed_bytes=len(changed),mesh_bounds_expanded=bounds,
                       baseline_sha256=hashlib.sha256(raw).hexdigest(),sha256=hashlib.sha256(result).hexdigest())

"""Adapt prepared geometry to the existing audited native float-weight writer.

No extracted third-party executable or bytecode is used. Opaque native metadata
comes only from the locally selected user's PSP base.
"""
import copy
import math
import struct
from tools.psp_materials import regular_template,REGULAR_CONTROLS
from tools.psp_mesh_merge import write_model
from tools.psp_mesh_audit import audit_yobj

def serialize(prepared,base,textures):
    result=copy.deepcopy(base)
    result['texture_raw']=b''.join(name.encode('ascii').ljust(16,b'\0') for name in prepared['textures'])
    if any(len(n.encode('ascii'))>15 for n in prepared['textures']): raise ValueError('A texture name is too long for PSP.')
    result['texture_names']=prepared['textures']
    header=bytearray(result['header']);struct.pack_into('<I',header,32,len(prepared['textures']));result['header']=bytes(header)
    rows=[]
    templates=[[m['raw'] for m in mesh['materials']] for mesh in base['meshes']]
    for mesh in prepared['meshes']:
        donor=base['meshes'][mesh['target_part']]
        palette=mesh['bone_palette']
        if not 1<=len(palette)<=8 or len(mesh['vertices'])>65535: raise ValueError('PSP draw-buffer capacity exceeded.')
        raw=b''.join(struct.pack('<'+'f'*len(palette)+'2f4B6f',*v['weights'],*v['uv'],
                                *v['color'],*v['normal'],*v['position']) for v in mesh['vertices'])
        row=copy.deepcopy(donor)
        row.update(index=len(rows),bone_palette=palette,weight_slots=len(palette),
                   base_flag=0x17ff,rigid=False,stride=36+4*len(palette),
                   vertices=copy.deepcopy(mesh['vertices']),raw_vertices=raw)
        header=bytearray(row['raw_header'])
        center=[(min(v['position'][i] for v in mesh['vertices'])+max(v['position'][i] for v in mesh['vertices']))/2 for i in range(3)]
        radius=max(math.dist(v['position'],center) for v in mesh['vertices'])+.001
        struct.pack_into('<4f',header,48,*center,radius);row['raw_header']=bytes(header)
        materials=[]
        for mat in mesh['materials']:
            info=textures[mat['texture_id']]
            record=bytearray(regular_template(templates,mesh['target_part'],info['bits']))
            struct.pack_into('<H',record,22,mat['texture_id'])
            struct.pack_into('<I',record,24,REGULAR_CONTROLS[info['bits']]|(0x110 if info['cutout'] else 0))
            strip_header=next(h for d in base['meshes'] for m in d['materials'] for h in m['strip_headers']
                              if h[:8]==bytes.fromhex('0300000000000000'))
            materials.append(dict(raw=bytes(record),texture_id=mat['texture_id'],
                                  strips=mat['strips'],triangles=mat['triangles'],
                                  strip_headers=[strip_header]*len(mat['strips'])))
        row['materials']=materials;rows.append(row)
    result['meshes']=rows
    out=write_model(result,[[i] for i in range(len(rows))])
    checked=audit_yobj(out)
    if checked['bone_raw']!=base['bone_raw']: raise ValueError('PSP skeleton changed during writing.')
    if len(prepared['meshes'])!=len(checked['meshes']):raise ValueError('Serialized mesh count differs.')
    # Independent decoded attribute/triangle verification, not just bounds checks.
    for source,native in zip(prepared['meshes'],checked['meshes']):
        if len(source['vertices'])!=len(native['vertices']) or len(source['materials'])!=len(native['materials']):raise ValueError('Serialized record count differs.')
        if source['bone_palette']!=native['bone_palette']: raise ValueError('Serialized palette differs.')
        for a,b in zip(source['vertices'],native['vertices']):
            for name in ('position','normal','uv','weights'):
                expected=struct.pack('<'+'f'*len(a[name]),*a[name])
                actual=struct.pack('<'+'f'*len(b[name]),*b[name])
                if expected!=actual: raise ValueError('Serialized '+name+' differs.')
            if tuple(a['color'])!=tuple(b['color']):raise ValueError('Serialized colors differ.')
        from collections import Counter
        def oriented(t):return min(tuple(t[i:]+t[:i]) for i in range(3))
        for a,b in zip(source['materials'],native['materials']):
            if Counter(oriented(list(t)) for t in a['triangles'])!=Counter(oriented(list(t)) for t in b['triangles']):
                raise ValueError('Serialized triangle orientation differs.')
    return out

"""Procedural Wii/GCTC/TPL contract fixture on a development-only PSP rig.

Flat colored panels replace wrestler geometry and textures. Rig is supplied by
the CI caller and excluded from the distributable; not evidence of game safety.
"""
from pathlib import Path
import struct
import numpy as np
from desktop.core import base_model
from tools.prepare_model import bone_matrices
from tools.yukes_bpe import compress


def source_bones(target):
    names={'root':'Bip Pelvis','koshi':'Bip Spine','mune':'Bip Spine1','kubi':'Bip Neck','atama':'Bip Head'}
    for side in ('l','r'):
        for suffix,part in [('sakotsu','Clavicle'),('ninoude','UpperArm'),('kote','Forearm'),('te','Hand'),('momo','Thigh'),('sune','Calf'),('ashi','Foot'),('tsumasaki','Toe0')]:
            names[side+'_'+suffix]='Bip '+side.upper()+' '+part
        for digit in range(5):
            for segment in range(3):names[f'{side}_yubi{digit}{segment}']=f'Bip {side.upper()} Finger{digit}'+(str(segment) if segment else '')
    return [dict(b,name=names.get(b['name'],b['name']),local_position=(np.array(b['local_position'])*10).tolist()) for b in target['bones']]


def yobj(target):
    bones=source_bones(target);positions=bone_matrices(dict(bones=bones))[:,:3,3]
    byname={b['name']:b['index'] for b in bones}
    panels=[]
    panel_names=['Bip Pelvis','Bip Spine','Bip Spine1','Bip Head','Bip L UpperArm','Bip R UpperArm','Bip L Forearm','Bip R Forearm','Bip L Hand','Bip R Hand','Bip L Thigh','Bip R Thigh','Bip L Calf','Bip R Calf','Bip L Foot','Bip R Foot','l_eye','r_eye']
    panel_names += [f'Bip {side} Finger{digit}' for side in ('L','R') for digit in range(5)]
    for name in panel_names:
        center=positions[byname[name]]+np.array([0,0,-1.])
        radius=.15 if name.endswith('_eye') else 3. if 'Finger' in name else .7
        panels.append((byname[name],[center+[-radius,-radius,0],center+[radius,-radius,0],center+[-radius,radius,0],center+[radius,radius,0]]))
    raw=bytearray(128)
    def alloc(value,align=4):
        raw.extend(bytes((-len(raw))%align));p=len(raw);raw.extend(value);return p
    packed=[]
    for bone,points in panels:
        packed.extend(struct.pack('>6h',*np.rint(np.array(point)*128).astype(int),-4096,0,0) for point in points)
    pp=alloc(b''.join(packed));groups=alloc(bytes(20*len(panels)))
    for i,(bone,points) in enumerate(panels):struct.pack_into('>4H2I',raw,groups+20*i,bone,65535,65535,1,4,0)
    draw=alloc(bytes(16));split=len(panels)-10
    for mid,indices in [(0,range(split)),(1,range(split,len(panels)))]:
        strips=alloc(b''.join(struct.pack('>I',4)+b''.join(struct.pack('>3H',i*4+j,0,j) for j in range(4)) for i in indices))
        struct.pack_into('>BBHI',raw,draw+8*mid,mid,0,len(indices),strips-8)
    color=alloc(bytes([255]*4));uv=alloc(struct.pack('>8h',128,128,384,128,128,384,384,384))
    materials=alloc(bytes(40))
    for mid in range(2):
        state=alloc(bytes(72));struct.pack_into('>I',raw,materials+20*mid+16,state-8);struct.pack_into('>H',raw,state+70,mid)
    bp=alloc(bytes(len(bones)*80))
    for i,b in enumerate(bones):
        a=bp+80*i;encoded=b['name'].encode('ascii')
        if len(encoded)>15:raise ValueError('Procedural bone name too long')
        raw[a:a+16]=encoded.ljust(16,b'\0');struct.pack_into('>3f',raw,a+16,*b['local_position']);struct.pack_into('>3f',raw,a+32,*b['rotation']);struct.pack_into('>i',raw,a+48,b['parent'])
    tp=alloc(b'color'.ljust(16,b'\0')+b'trans'.ljust(16,b'\0'));label=alloc(b'procedural'.ljust(16,b'\0'));footer=alloc(bytes(8)+b'GCTC'+bytes(4))
    raw[:4]=b'YOBJ';struct.pack_into('>3I',raw,4,len(raw)-8,0x70001,64)
    struct.pack_into('>6I',raw,16,len(bones),bp-8,2,materials-8,2,tp-8)
    struct.pack_into('>I',raw,48,footer-8);struct.pack_into('>I',raw,60,label-8)
    struct.pack_into('>H',raw,0x48,4*len(panels));raw[0x4c:0x52]=bytes([2,7,len(panels),2,10,0])
    for offset,pointer in [(0x54,pp),(0x5c,groups),(0x60,draw),(0x68,color),(0x6c,uv)]:struct.pack_into('>I',raw,offset,pointer-8)
    struct.pack_into('>2H',raw,0x70,1,4)
    return b'DUMY\0\0\0\x10'+bytes(16)+bytes(raw)


def tpl():
    header=bytearray(64);struct.pack_into('>5I',header,0,0x20af30,1,12,20,0)
    struct.pack_into('>2H2I',header,20,64,64,14,64)
    blocks=struct.pack('>2H4B',0xf800,0x07e0,0x1b,0x1b,0x1b,0x1b)*256
    return bytes(header)+blocks


def create(base_path,output):
    _,target=base_model(base_path);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    image=tpl();table=bytearray(struct.pack('<4I',2,0x100,0,16))
    for i,name in enumerate(('color','trans')):table+=name.encode().ljust(16,b'\0')+b'tpl\0'+struct.pack('<3I',len(image),80+i*len(image),0)
    table=bytes(table)+image+image
    payloads=[(2,compress(yobj(target))),(9,compress(table))]
    head=bytearray(b'PACH'+struct.pack('<I',len(payloads)));body=bytearray()
    for sid,data in payloads:
        body.extend(bytes((-len(body))%4));head+=struct.pack('<3I',sid,len(body),len(data));body+=data
    packet=bytes(head+body);packet+=bytes((-len(packet))%2048)
    raw=b'EPK8'+bytes(2044)+packet+packet
    path=output/'procedural-wii.pac';path.write_bytes(raw);return path


if __name__=='__main__':
    import sys
    print(create(sys.argv[1],sys.argv[2]))

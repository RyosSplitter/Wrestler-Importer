"""Procedural CI geometry/TIM2 atlas on a locally supplied PSP development rig.

No wrestler mesh or game texture is copied. These are modified format-contract
fixtures, not original JBI assets or evidence of title-wide game compatibility.
"""
import copy
from pathlib import Path
import struct

import numpy as np
from scipy.spatial.transform import Rotation

from desktop.core import base_model
from tools.generate_conformance_fixtures import pac
from tools.portable_fixture import encode
from tools.prepare_model import bone_matrices
from tools.yukes_bpe import compress


def source_rig(target):
    matrices=bone_matrices(target);keep=[];names={}
    for b in target['bones']:
        name=b['name']
        if '_yubi' in name:
            digit=int(name[-2]);segment=int(name[-1])
            if (digit==0 and segment==0) or (digit!=0 and segment==2):continue
            name=name[:-1]+str(1 if (segment==1 if digit==0 else segment==0) else 0)
        keep.append(b['index']);names[b['index']]=name
    mapping={old:i for i,old in enumerate(keep)};bones=[]
    for old in keep:
        b=target['bones'][old];parent=b['parent']
        while parent!=-1 and parent not in mapping:parent=target['bones'][parent]['parent']
        local=matrices[old] if parent==-1 else np.linalg.inv(matrices[parent])@matrices[old]
        bones.append(dict(index=mapping[old],name=names[old],parent=mapping[parent] if parent!=-1 else -1,
            local_position=local[:3,3].tolist(),rotation=Rotation.from_matrix(local[:3,:3]).as_euler('xyz').tolist()))
    return bones


def mesh(bones,panels):
    vertices=[];materials=[];triangles=[]
    byname={b['name']:b['index'] for b in bones};count=len(bones)
    for name,points in panels:
        start=len(vertices)
        normal=np.cross(np.asarray(points[1])-points[0],np.asarray(points[2])-points[0]);normal/=np.linalg.norm(normal)
        for point,uv in zip(points,[(0.,0.),(1.,0.),(0.,1.),(1.,1.)]):
            w=np.zeros(count);w[byname[name]]=1.
            vertices.append(dict(position=np.asarray(point).tolist(),normal=normal.tolist(),uv=list(uv),color=[255]*4,weights=w.tolist()))
        triangles += [[start,start+1,start+2],[start+1,start+3,start+2]]
    return dict(index=0,bone_palette=list(range(count)),vertices=vertices,
                materials=[dict(texture_id=0,triangles=triangles,strips=[])])


def atlas(variant=0):
    width,height=128,64
    y,x=np.indices((height,width));pixels=((x//8+y//8)%2).astype(np.uint8).tobytes()
    colors=[(40,160,80,128),(220,200,70,128)] if variant==0 else [(90,70,180,128),(200,150,220,128)]
    palette=b''.join(bytes(colors[i%2]) for i in range(256))
    tex0=(19<<20)|(7<<26)|(6<<30)
    header=struct.pack('<IIIHH4BHH',48+len(pixels)+len(palette),len(palette),len(pixels),48,256,0,1,3,5,width,height)+struct.pack('<Q',tex0)+bytes(16)
    return b'TIM2'+struct.pack('<BBH',4,0,1)+bytes(8)+header+pixels+palette


def costume(target,*,pads=True,variant=0):
    bones=source_rig(target);model=dict(bones=bones,bone_count=len(bones),textures=['atlas'],texture_count=1)
    matrices=bone_matrices(model);byname={b['name']:b['index'] for b in bones}
    def panel(name,center,width=.25,height=.3):
        p=np.asarray(center)
        return name,[p+[-width,-height,0.],p+[width,-height,0.],p+[-width,height,0.],p+[width,height,0.]]
    panels=[]
    for name in ['koshi','mune','atama','l_ninoude','r_ninoude','l_kote','r_kote','l_momo','r_momo','l_sune','r_sune','l_ashi','r_ashi']:
        point=matrices[byname[name],:3,3].copy();point[2]-=.2
        panels.append(panel(name,point,.45 if name in ('koshi','mune','atama') else .2,.5))
    for side,sign in [('l',1),('r',-1)]:
        panels.append(panel(side+'_te',matrices[byname[side+'_te'],:3,3]+[sign*.3,0.,0.],.2,.15))
        for digit in range(5):
            for suffix in (1,0):
                name=side+'_yubi'+str(digit)+str(suffix)
                point=matrices[byname[name],:3,3]+[sign*.1,0.,0.]
                panels.append(panel(name,point,.05,.05))
    main=dict(model,meshes=[mesh(bones,panels)])
    rows=[(1,compress(atlas(variant))),(2,compress(encode(main))),(50,b'PROCEDURAL JBI FORMAT FIXTURE')]
    if pads:
        for sid,side in [(6,'l'),(7,'r')]:
            point=matrices[byname[side+'_kote'],:3,3]+[0.,0.,-.4]
            pad=dict(model,meshes=[mesh(bones,[panel(side+'_kote',point,.3,.4)])])
            rows.append((sid,compress(encode(pad))))
    return pac(rows)


def create(base_path,output):
    _,target=base_model(base_path);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    entries=[('0000',costume(target)),('0100',costume(target,pads=False,variant=1))]
    for name,raw in entries:(output/(name+'.pac')).write_bytes(raw)
    payloads=[raw+b'\0'*((-len(raw))%2048) for _,raw in entries]
    raw=bytearray(0x4000+sum(map(len,payloads)));raw[:4]=b'DPAC'
    struct.pack_into('<3I',raw,4,8+4*len(entries),sum(map(len,payloads)),7)
    raw[0x800:0x804]=b'EMD ';struct.pack_into('<HH',raw,0x804,0x8000|len(entries),0)
    cursor=0x4000
    for i,((name,entry),allocation) in enumerate(zip(entries,payloads)):
        struct.pack_into('<HH',raw,0x808+i*4,int(name,16),len(entry)//256)
        raw[cursor:cursor+len(allocation)]=allocation;cursor+=len(allocation)
    path=output/'CH.pac';path.write_bytes(raw)
    return path


if __name__=='__main__':
    import sys
    print(create(Path(sys.argv[1]),Path(sys.argv[2])))

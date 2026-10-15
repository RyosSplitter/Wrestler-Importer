"""Original asset-free extruded-block humanoids for CI and frozen self-checks."""
import copy
import struct

import numpy as np

from tools.generate_conformance_fixtures import vectors, pac
from tools.pac_repack import texture_table
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge import write_model
from tools.stripify import stripify
from desktop.texture_optimizer.candidates import write_gim, read_gim


def pair():
    spec=[('root',None),('koshi','root'),('mune','koshi'),('kubi','mune'),('atama','kubi'),('atama_d','atama'),
          ('d_kuchi','atama'),('l_eye','atama'),('r_eye','atama'),('l_mabuta','atama'),('r_mabuta','atama'),
          ('l_sakotsu','mune'),('l_ninoude','l_sakotsu'),('l_kote','l_ninoude'),('l_te','l_kote'),
          ('r_sakotsu','mune'),('r_ninoude','r_sakotsu'),('r_kote','r_ninoude'),('r_te','r_kote'),
          ('l_momo','root'),('l_sune','l_momo'),('l_ashi','l_sune'),('r_momo','root'),('r_sune','r_momo'),('r_ashi','r_sune')]
    points=[];faces=[];normals=[]
    def quad(corners,normal):
        i=len(points);points.extend(corners);normals.extend([normal]*4);faces.extend([[i,i+1,i+2],[i,i+2,i+3]])
    for z,n in ((-.7,(0,0,-1)),(.7,(0,0,1))):
        for lo,hi,bottom,top in ((-.7,.7,-9,-6.2),(-5,5,-6.2,-5),(-1.5,1.5,-5,8)):
            cs=[(lo,bottom,z),(hi,bottom,z),(hi,top,z),(lo,top,z)]
            quad(cs if z>0 else list(reversed(cs)),n)
    outline=[(-.7,-9),(.7,-9),(.7,-6.2),(5,-6.2),(5,-5),(1.5,-5),(1.5,8),(-1.5,8),(-1.5,-5),(-5,-5),(-5,-6.2),(-.7,-6.2)]
    for (x,y),(xx,yy) in zip(outline,outline[1:]+outline[:1]):
        normal=np.array([yy-y,x-xx,0.]);normal/=np.linalg.norm(normal)
        quad([(x,y,-.7),(xx,yy,-.7),(xx,yy,.7),(x,y,.7)],normal.tolist())
    results=[]
    for variant in (0,1):
        m=audit_yobj(vectors()['psp-quad.yobj']);order=spec if not variant else [spec[0]]+list(reversed(spec[1:]))
        names=[n for n,_ in order];records=bytearray()
        for name,parent in order:
            r=bytearray(80);r[:16]=name.encode().ljust(16,b'\0');struct.pack_into('<4f',r,16,.1*variant if name=='atama' else 0,0,0,1)
            struct.pack_into('<i',r,48,-1 if parent is None else names.index(parent));records.extend(r)
        m['bone_raw']=bytes(records);header=bytearray(m['header']);struct.pack_into('<I',header,28,len(order));m['header']=bytes(header)
        mesh=m['meshes'][0];vertices=[]
        for p,n in zip(points,normals):
            p=list(p);p[2]*=1-.05*variant
            vertices.append(dict(position=p,normal=n,uv=[p[0]/10+.5,p[1]/17+.5],color=[255]*4,weights=[1.,0.]))
        mesh.update(vertices=vertices,bone_palette=[names.index('root'),names.index('koshi')],weight_slots=2,stride=44)
        mesh['raw_vertices']=b''.join(struct.pack('<4f4B6f',*v['weights'],*v['uv'],*v['color'],*v['normal'],*v['position']) for v in vertices)
        mat=mesh['materials'][0];strips=stripify(faces);mat.update(strips=strips,triangles=copy.deepcopy(faces),strip_headers=[mat['strip_headers'][0]]*len(strips))
        raw=write_model(m,[[0]])
        colors=np.zeros((16,4),np.uint8);colors[:,3]=255;colors[0,:3]=(60,180,100) if variant==0 else (170,110,60)
        gim=write_gim(np.zeros((32,32),np.uint8),colors,4)
        table=texture_table(['skin'],[gim],gim_reader=read_gim)
        results.append(pac([(2,raw),(8,b'original synthetic opaque data'),(9,table)]))
    return results

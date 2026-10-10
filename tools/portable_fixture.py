"""CI-only modified HCTP containers reconstructed from existing reference IR.

Not original game PACs and not distributed inside the portable application.
Geometry/weights come from the explicitly selected development fixture; textures
are generated checkerboards. This does not certify original-container coverage.
"""
import json
from pathlib import Path
import struct
from tools.generate_conformance_fixtures import Layout,pac

def encode(model):
    chunks=[]
    for mesh in model['meshes']:
        faces=[(a['texture_id'],t) for a in mesh['materials'] for t in a['triangles']]
        used={};vertices=[];mats={}
        def flush():
            if vertices:chunks.append((list(vertices),{k:list(v) for k,v in mats.items()}))
        for tid,t in faces:
            if len(set(t)-used.keys())+len(vertices)>160:flush();used={};vertices=[];mats={}
            tri=[]
            for i in t:
                if i not in used:
                    used[i]=len(vertices);v=dict(mesh['vertices'][i]);v['support']=[(b,w) for b,w in zip(mesh['bone_palette'],v['weights']) if w>0];vertices.append(v)
                tri.append(used[i])
            mats.setdefault(tid,[]).append(tri)
        flush()
    f=Layout();mh=f.alloc(bytes(64*len(chunks)));f.u32(24,len(chunks));f.u32(28,len(model['bones']));f.u32(32,len(model['textures']));f.ptr(36,mh)
    for mi,(vertices,mats) in enumerate(chunks):
        a=mh+64*mi;group=f.alloc(bytes(32*len(vertices)))
        pos=f.alloc(b''.join(struct.pack('<4f',*v['position'],1) for v in vertices));normal=f.alloc(b''.join(struct.pack('<4f',*v['normal'],0) for v in vertices))
        for i,v in enumerate(vertices):
            support=v['support']
            if not 1<=len(support)<=4:raise ValueError('CI source fixture exceeds four influences.')
            g=group+32*i;f.u32(g,1);f.u32(g+4,len(support));f.ptr(g+8,pos+16*i);f.ptr(g+12,normal+16*i)
            for j,(b,w) in enumerate(support):f.u32(g+16+4*j,b+1)
        material=f.alloc(bytes(208*len(mats)))
        for mat_index,(tid,triangles) in enumerate(mats.items()):
            ma=material+208*mat_index;strip=f.alloc(bytes(16*len(triangles)));f.u32(ma+40,tid);f.u32(ma+196,len(triangles));f.ptr(ma+200,strip)
            for j,t in enumerate(triangles):
                corners=f.alloc(b''.join(struct.pack('<3fI4f',*vertices[i]['uv'],1,i,*[c/255 for c in vertices[i]['color']]) for i in t))
                sa=strip+16*j;f.u32(sa,3);f.u32(sa+4,3);f.u32(sa+8,3);f.ptr(sa+12,corners)
        packet=bytearray()
        for vi,v in enumerate(vertices):
            if len(v['support'])==1:continue
            packet+=struct.pack('<4I',0,0,0,0x6c010280+vi)
            packet+=struct.pack('<4f',*([w for b,w in v['support']]+[0]*(4-len(v['support']))))
        weight=f.alloc(packet);f.u32(a,len(vertices));f.u32(a+4,len(mats));f.ptr(a+8,group);f.ptr(a+12,material);f.ptr(a+28,weight)
        f.u32(a+32,2*len(vertices)+2);f.u32(a+36,len(packet)//16);f.u32(a+40,len(vertices))
    bones=bytearray(80*len(model['bones']))
    for b in model['bones']:
        a=b['index']*80;name=b['name'].encode('ascii');bones[a:a+len(name)]=name
        struct.pack_into('<4f',bones,a+16,*b.get('world_position',b['local_position']),1)
        struct.pack_into('<3f',bones,a+32,*b['rotation']);struct.pack_into('<i',bones,a+48,b['parent']);struct.pack_into('<3f',bones,a+64,*b['local_position'])
    f.ptr(40,f.alloc(bones));f.ptr(44,f.alloc(b''.join(n.encode('ascii').ljust(16,b'\0') for n in model['textures'])))
    descriptor=bytearray(32);descriptor[:7]=b'fixture';struct.pack_into('<I',descriptor,24,len(chunks));f.ptr(48,f.alloc(descriptor))
    return f.finish()

def checker():
    tex=bytearray(64);tex[:4]=b'RTX3';pixels=bytes([0,1,2,3])*1024;palette=b''.join(bytes((30+i%210,80+i%150,110+i%100,128)) for i in range(256))
    struct.pack_into('<I',tex,4,56+len(pixels)+len(palette));struct.pack_into('<Q',tex,8,(19<<20)|(6<<26)|(6<<30));struct.pack_into('<2I',tex,36,len(pixels),56)
    return bytes(tex)+pixels+palette

def create(model,output):
    names=model['textures'];payloads=[checker() for n in names];table=bytearray(struct.pack('<4I',len(names),0x100,0,16));offset=16+32*len(names)
    for name,raw in zip(names,payloads):
        table+=name.encode('ascii').ljust(16,b'\0')+b'txc\0'+struct.pack('<3I',len(raw),offset,0);offset+=len(raw)
    Path(output).write_bytes(pac([(2,encode(model)),(9,bytes(table)+b''.join(payloads)),(50,b'CI MODIFIED CONTAINER')]))

def create_with_accessories(model,output):
    """CI-only original quads exercising real left/right role contracts.

    Uses existing development IR solely for its rig; pad geometry/UVs and pixels
    are generated. Independent indices deliberately differ from the main rig.
    """
    import copy
    from tools.pac_inspect import inspect_pac
    create(model,output);original=Path(output).read_bytes()
    entries=[(s['id'],original[s['offset']:s['offset']+s['size']]) for s in inspect_pac(original)['sections']]
    names=model['textures']+['fixture_pad'];payloads=[checker() for n in names]
    table=bytearray(struct.pack('<4I',len(names),0x100,0,16));offset=16+32*len(names)
    for name,raw in zip(names,payloads):
        table+=name.encode('ascii').ljust(16,b'\0')+b'txc\0'+struct.pack('<3I',len(raw),offset,0);offset+=len(raw)
    entries=[(i,bytes(table)+b''.join(payloads) if i==9 else raw) for i,raw in entries]
    pads=[]
    for section,side,sign in ((6,'l',1),(7,'r',-1)):
        names={b['name']:b for b in model['bones']}
        active=[names[side+'_ninoude']['index'],names[side+'_kote']['index']]
        used=set(active)
        for i in active:
            while i!=-1:used.add(i);i=model['bones'][i]['parent']
        old=sorted(used);mapping={i:j for j,i in enumerate(old)}
        bones=[]
        for i in old:
            b=copy.deepcopy(model['bones'][i]);b['index']=mapping[i]
            b['parent']=mapping[b['parent']] if b['parent']!=-1 else -1;bones.append(b)
        vertices=[dict(position=[sign*(4.5+x*.5),-6+y*.5,.8],normal=[0,0,1],
                       uv=[x,y],color=[255]*4,weights=list(w))
                  for (x,y),w in zip(((0,0),(1,0),(0,1),(1,1)),((1.,0.),(.75,.25),(.25,.75),(0.,1.)))]
        pad=dict(bones=bones,textures=['fixture_pad'],meshes=[dict(index=0,bone_palette=[mapping[i] for i in active],vertices=vertices,
                 materials=[dict(texture_id=0,triangles=[[0,1,2],[1,3,2]])])])
        pads.append((section,encode(pad)))
    Path(output).write_bytes(pac(list(reversed(pads))+entries))

if __name__=='__main__':
    import sys
    create(json.loads(Path(sys.argv[1]).read_text()),sys.argv[2])

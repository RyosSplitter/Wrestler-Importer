"""Read-only EPK8/PACH and Wii YOBJ-header/TPL research, not a converter.

Wii geometry packets, skinning records and draw semantics remain undecoded.
Never pass this header layout through a PSP or Xbox 360 geometry reader.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

import numpy as np
from PIL import Image, ImageDraw

from tools.pac_inspect import parse_textures
from tools.wwe13_inspect import checked, unpack, name
from tools.yobj_read import _validate_hierarchy
from tools.yukes_bpe import decompress

MAX_INPUT = 64*1024*1024
MAX_EXPANSION = 64*1024*1024


def digest(data):return hashlib.sha256(data).hexdigest()
def dump(path, value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def read_pach(data, start):
    if checked(data,start,4)!=b'PACH':raise ValueError('Missing PACH')
    count,=unpack(data,'<I',start+4)
    if not 0<count<=1024:raise ValueError('Unbounded PACH count')
    checked(data,start+8,count*12);origin=start+8+count*12
    end=origin;ids=set();rows=[];total=0
    for i in range(count):
        ident,relative,size=unpack(data,'<3I',start+8+i*12);address=origin+relative
        if ident in ids or address<end or address%4 or size<16:raise ValueError('Invalid/overlapping PACH section')
        ids.add(ident);packed=checked(data,address,size);raw=decompress(packed,max_output=MAX_EXPANSION)
        total+=len(raw)
        if total>MAX_EXPANSION:raise ValueError('Cumulative expansion bound exceeded')
        rows.append(dict(id=ident,offset=address,stored_bytes=size,expanded_bytes=len(raw),sha256=digest(raw),raw=raw))
        end=address+size
    return dict(offset=start,payload_origin=origin,end=end,sections=rows)


def read_model_header(data):
    if checked(data,0,8)!=b'DUMY\0\0\0\x10' or any(checked(data,8,16)):
        raise ValueError('Unsupported DUMY prefix')
    raw=data[24:]
    if checked(raw,0,4)!=b'YOBJ':raise ValueError('Missing Wii YOBJ')
    if unpack(raw,'>2I',8)!=(0x70001,64):raise ValueError('Unobserved Wii YOBJ version/header')
    end=unpack(raw,'>I',4)[0]+8;body=checked(raw,0,end)
    bone_count,bone_ptr,material_count,material_ptr,texture_count,texture_ptr=unpack(body,'>6I',16)
    if not 0<bone_count<=1024 or not 0<texture_count<=256 or not 0<material_count<=256:
        raise ValueError('Unbounded Wii model tables')
    checked(body,bone_ptr+8,bone_count*80);checked(body,texture_ptr+8,texture_count*16)
    checked(body,material_ptr+8,material_count*20)
    bones=[]
    for i in range(bone_count):
        a=bone_ptr+8+80*i;parent=unpack(body,'>i',a+48)[0]
        local=unpack(body,'>3f',a+16);rotation=unpack(body,'>3f',a+32)
        if not -1<=parent<bone_count or not np.isfinite((*local,*rotation)).all():raise ValueError('Invalid Wii bone record')
        bones.append(dict(index=i,name=name(body,a),parent=parent,local_position=local,rotation=rotation))
    _validate_hierarchy(bones)
    if len({b['name']for b in bones})!=bone_count or any(not b['name']for b in bones):raise ValueError('Ambiguous Wii bone names')
    textures=[name(body,texture_ptr+8+i*16)for i in range(texture_count)]
    label_ptr=unpack(body,'>I',60)[0];label=name(body,label_ptr+8)
    packet_ptr=unpack(body,'>I',48)[0]
    if checked(body,packet_ptr+16,4)!=b'GCTC':raise ValueError('Unobserved Wii packet footer')
    return dict(version='0x00070001',prefix_bytes=24,declared_yobj_bytes=end,trailing_bytes=len(raw)-end,
        label=label,bone_count=bone_count,bones=bones,material_count=material_count,
        texture_slot_count=texture_count,texture_slots=textures,
        packet_footer=packet_ptr+16,geometry_packet_region_bytes=packet_ptr-64,
        geometry_decoded=False,vertex_count=None,triangle_count=None,mesh_count=None,
        limitations=['Material count is not mesh count','Vertex buffers, indices, bone palettes and weights are not yet decoded',
                    'Header tables and hierarchy validation do not establish animation compatibility'])


def rgb565(v):
    r,g,b=v>>11,(v>>5)&63,v&31
    return [(r<<3)|(r>>2),(g<<2)|(g>>4),(b<<3)|(b>>2),255]


def decode_palette(raw, count, fmt):
    values=np.frombuffer(checked(raw,0,count*2),dtype='>u2').astype(np.uint32)
    if fmt==2:
        out=np.empty((count,4),np.uint8);opaque=(values&0x8000)!=0
        r,g,b=(values>>10)&31,(values>>5)&31,values&31
        alpha=(values>>12)&7
        out[:,0]=np.where(opaque,(r<<3)|(r>>2),((values>>8)&15)*17)
        out[:,1]=np.where(opaque,(g<<3)|(g>>2),((values>>4)&15)*17)
        out[:,2]=np.where(opaque,(b<<3)|(b>>2),(values&15)*17)
        out[:,3]=np.where(opaque,255,(alpha<<5)|(alpha<<2)|(alpha>>1))
        return out
    raise ValueError('Unobserved Wii CLUT format')


def decode_tpl(data):
    if checked(data,0,4)!=b'\x00\x20\xaf\x30':raise ValueError('Missing TPL signature')
    count,table=unpack(data,'>2I',4)
    if count!=1:raise ValueError('Research supports one-image TPL only')
    image,pal=unpack(data,'>2I',table)
    height,width,fmt,pixels=unpack(data,'>2H2I',image)
    checked(data,image,36)
    if not 0<width<=2048 or not 0<height<=2048 or width*height>4*1024*1024:
        raise ValueError('Unbounded TPL dimensions')
    formats={8:('C4',8,8,32,4),9:('C8',8,4,32,8),14:('CMPR',8,8,32,4)}
    if fmt not in formats:raise ValueError('Unobserved Wii texture format')
    label,bw,bh,block,bits=formats[fmt];pw=(width+bw-1)//bw*bw;ph=(height+bh-1)//bh*bh
    payload=checked(data,pixels,pw*ph*bits//8);out=np.zeros((ph,pw,4),np.uint8);entries=0;palette_fmt=None
    if fmt in (8,9):
        if not pal:raise ValueError('Missing indexed TPL palette')
        entries=unpack(data,'>H',pal)[0];palette_fmt,palette_at=unpack(data,'>2I',pal+4)
        if not 0<entries<=1<<bits:raise ValueError('Invalid palette capacity')
        palette=decode_palette(checked(data,palette_at,entries*2),entries,palette_fmt)
    elif pal:
        raise ValueError('Unexpected CMPR palette header')
    cursor=0
    for y in range(0,ph,bh):
        for x in range(0,pw,bw):
            b=payload[cursor:cursor+block];cursor+=block
            if fmt in (8,9):
                indices=np.frombuffer(b,np.uint8)
                if fmt==8:
                    p=np.empty(64,np.uint8);p[::2]=indices>>4;p[1::2]=indices&15
                else:p=indices
                if int(p.max())>=entries:raise ValueError('TPL index outside CLUT')
                out[y:y+bh,x:x+bw]=palette[p.reshape(bh,bw)]
            else:
                for k,(dx,dy) in enumerate(((0,0),(4,0),(0,4),(4,4))):
                    c0,c1=struct.unpack_from('>2H',b,8*k);a=np.array(rgb565(c0),int);c=np.array(rgb565(c1),int)
                    colors=[a,c,(2*a+c)//3,(a+2*c)//3] if c0>c1 else [a,c,(a+c)//2,np.zeros(4,int)]
                    for row,selector in enumerate(b[8*k+4:8*k+8]):
                        for column in range(4):
                            out[y+dy+row,x+dx+column]=colors[(selector>>(6-2*column))&3]
    rgba=out[:height,:width].copy()
    return rgba,dict(width=width,height=height,format=label,format_id=fmt,bits_per_pixel=bits,
        block_dimensions=[bw,bh],pixel_payload_bytes=len(payload),palette_entries=entries,palette_format=palette_fmt,
        palette_format_name='RGB5A3'if palette_fmt==2 else None,encoded_bytes=len(data),
        source_alpha_levels=np.unique(rgba[:,:,3]).tolist(),rgba_sha256=digest(rgba.tobytes()),
        reserved_image_tail_hex=checked(data,image+32,4).hex(),scope='Decoded observed C4/C8/RGB5A3/CMPR only; no mipmap inference')


def inspect(path, output):
    path,output=map(Path,(path,output));data=path.read_bytes()
    if len(data)>MAX_INPUT or checked(data,0,4)!=b'EPK8':raise ValueError('Expected bounded EPK8 input')
    output.mkdir(parents=True,exist_ok=False)
    roots=[m.start()for m in re.finditer(b'PACH',data)if m.start()%2048==0]
    if not 0<len(roots)<=32:raise ValueError('No bounded aligned PACH candidates')
    bundles=[];gallery=[];end=0;total_expansion=0
    for k,offset in enumerate(roots):
        if offset<end:raise ValueError('Top-level PACH candidates overlap')
        bundle=read_pach(data,offset);end=bundle['end'];folder=output/f'bundle-{k}';folder.mkdir()
        total_expansion+=sum(s['expanded_bytes']for s in bundle['sections'])
        if total_expansion>128*1024*1024:raise ValueError('Whole-input expansion bound exceeded')
        sections=[];texture_names=set();models=[];images=[]
        for row in bundle['sections']:
            raw=row.pop('raw');(folder/f"section-{row['id']}.bin").write_bytes(raw)
            if raw.startswith(b'DUMY'):
                row['model_header']=read_model_header(raw);models.append(row['model_header'])
            if row['id']==9:
                tex=[]
                for entry in parse_textures(raw):
                    name_=entry['name']
                    if not re.fullmatch('[A-Za-z0-9_-]+',name_) or name_ in texture_names:raise ValueError('Unsafe/duplicate texture name')
                    texture_names.add(name_)
                    if entry['extension']!='tpl':raise ValueError('Unexpected texture extension')
                    tpl=checked(raw,entry['offset'],entry['size']);rgba,info=decode_tpl(tpl)
                    (folder/(name_+'.tpl')).write_bytes(tpl);Image.fromarray(rgba).save(folder/(name_+'.png'))
                    tex.append(dict(entry,**info));images.append((name_,rgba));gallery.append((k,name_,rgba))
                row['textures']=tex
            sections.append(row)
        if any(set(m['texture_slots'])-texture_names for m in models):raise ValueError('Wii model references absent texture')
        bundles.append(dict(bundle,sections=sections,model_count=len(models),texture_assets=len(texture_names)))
    sheet=Image.new('RGB',(4*300,((len(gallery)+3)//4)*332),(55,55,55));draw=ImageDraw.Draw(sheet)
    for i,(bundle,name_,rgba) in enumerate(gallery):
        im=Image.fromarray(rgba);im.thumbnail((288,288),Image.Resampling.NEAREST)
        bg=Image.new('RGBA',im.size,(100,100,100,255));bg.alpha_composite(im)
        x,y=(i%4)*300,(i//4)*332;sheet.paste(bg.convert('RGB'),(x+6,y+24));draw.text((x+6,y+4),f'Variant {bundle}: {name_}',fill='white')
    sheet.save(output/'texture-contact-sheet.png')
    report=dict(input_bytes=len(data),input_sha256=digest(data),signature='EPK8',bundles=bundles,
        all_bpe_sections_decoded=True,geometry_decoded=False,game_and_platform='WWE 13 Wii per user; not authenticated by filename alone',
        source_unchanged=data==path.read_bytes(),classification=dict(
        confirmed=['Two-stage bounded PACH extraction/BPE expansion','Wii YOBJ header/bone hierarchy','Observed TPL pixel/CLUT formats'],
        inferred=['GCTC region contains Wii geometry/draw packets','trans model/texture carries hair or other alpha surfaces'],
        unknown=['Vertex/triangle/mesh counts','Source bone palettes and weights','Exact ring/entrance roles','EPK8 root-directory field semantics','PSP compatibility']))
    dump(output/'inventory.json',report)
    (output/'README.txt').write_text('WWE 13 Wii ch145 read-only research\n\nTextures are decoded source TPL previews, not converted PSP assets.\nThe YOBJ header/bones can be inspected; geometry and skin weights remain undecoded.\nMaterial/texture-slot counts are NOT mesh counts.\nNo PAC/model was converted or changed.\n')
    print(json.dumps(dict(input_bytes=len(data),bundles=len(bundles),bpe_sections=sum(len(b['sections'])for b in bundles),
        models=sum(b['model_count']for b in bundles),geometry_decoded=False,report=str(output/'inventory.json')),indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();inspect(a.source,a.out)

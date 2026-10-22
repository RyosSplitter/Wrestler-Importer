"""Offline layered texture documents. Native model/UV/skinning bytes are immutable.

No image-generation service, network client, executable project format or new
dependency is used. Paint/art layers are separate from the original indexed GIM.
"""
from dataclasses import dataclass, field
import copy
import io
import json
import math
from pathlib import Path
import struct
import zipfile

import numpy as np
from PIL import Image, ImageDraw

from desktop.edit_folder import publish_new
from desktop.limits import IN_RING_MAX_PAC_BYTES
from desktop.texture_optimizer.candidates import read_gim
from desktop.workspace import digest
from tools.pac_inspect import inspect_pac, parse_textures
from tools.pac_repack import rewrite_sections
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress, decompress

SCHEMA = 'psp-model-suite.retexture/1'
MAX_PIXELS = 4_194_304
MAX_PROJECT_BYTES = 128 * 1024 * 1024


def png(image):
    out = io.BytesIO(); image.save(out, format='PNG'); return out.getvalue()


def read_image(data):
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > MAX_PIXELS:
            raise ValueError('Image exceeds the 4-megapixel editing limit.')
        image.load()
        return image.convert('RGBA')


def full_quad(size):
    w, h = size
    return [[0., 0.], [float(w), 0.], [float(w), float(h)], [0., float(h)]]


def warp(image, quad, size):
    """Inverse homography: UV canvas -> imported art, TL/TR/BR/BL corners."""
    q = np.asarray(quad, float)
    if q.shape != (4, 2) or not np.isfinite(q).all():
        raise ValueError('Invalid layer corners.')
    def cross2(a,b):return a[0]*b[1]-a[1]*b[0]
    cross = cross2(q[1]-q[0], q[2]-q[1])
    turns = [cross2(q[(i+1)%4]-q[i], q[(i+2)%4]-q[(i+1)%4]) for i in range(4)]
    if abs(float(cross)) < 1e-5 or not (all(v > 0 for v in turns) or all(v < 0 for v in turns)):
        raise ValueError('Keep layer corners in a convex, non-crossing quadrilateral.')
    rows, values = [], []
    for (x,y),(u,v) in zip(q, full_quad(image.size)):
        rows += [[x,y,1,0,0,0,-u*x,-u*y], [0,0,0,x,y,1,-v*x,-v*y]]
        values += [u,v]
    try: coefficients = np.linalg.solve(rows, values)
    except np.linalg.LinAlgError as exc: raise ValueError('Layer warp is singular.') from exc
    return image.transform(size, Image.Transform.PERSPECTIVE, coefficients,
                           Image.Resampling.BICUBIC, fillcolor=(0,0,0,0))


@dataclass
class Layer:
    name: str
    image: Image.Image
    quad: list
    opacity: float = 1.
    visible: bool = True
    paint: bool = False


@dataclass
class Texture:
    index: int
    section: int
    name: str
    raw: bytes
    original: Image.Image
    editable: bool
    layers: list = field(default_factory=list)
    selection: Image.Image = None
    protection: Image.Image = None

    def __post_init__(self):
        self.selection = Image.new('L', self.original.size, 255)
        self.protection = Image.new('L', self.original.size, 0)

    def allowed(self):
        a=np.asarray(self.selection, float)/255
        return a*(1-np.asarray(self.protection, float)/255)

    def composite(self):
        result=self.original.copy()
        for layer in self.layers:
            if not layer.visible: continue
            overlay=layer.image.copy() if layer.paint else warp(layer.image, layer.quad, result.size)
            alpha=np.asarray(overlay.getchannel('A'),float)*layer.opacity
            overlay.putalpha(Image.fromarray(np.rint(alpha).clip(0,255).astype(np.uint8)))
            result=Image.alpha_composite(result,overlay)
        # Protection is persistent across all layers, including imported art.
        result=Image.composite(self.original,result,self.protection)
        # The first milestone edits color only: original cutout alpha is locked.
        result.putalpha(self.original.getchannel('A'))
        return result

    def paint_layer(self):
        if self.layers and self.layers[-1].paint: return self.layers[-1]
        if len(self.layers)>=64:raise ValueError('Up to 64 layers per texture.')
        layer=Layer('Paint',Image.new('RGBA',self.original.size),full_quad(self.original.size),paint=True)
        self.layers.append(layer);return layer

    def stroke(self, start, end, color, radius, opacity=1., erase=False):
        if not self.editable: raise ValueError('This texture is read-only.')
        layer=self.paint_layer(); mask=Image.new('L',self.original.size)
        d=ImageDraw.Draw(mask);width=max(1,int(radius*2))
        d.line([tuple(start),tuple(end)],fill=255,width=width)
        for x,y in (start,end):d.ellipse((x-radius,y-radius,x+radius,y+radius),fill=255)
        alpha=np.asarray(mask,float)*self.allowed()*float(opacity)
        if erase:
            old=np.asarray(layer.image).copy();old[:,:,3]=np.rint(old[:,:,3]*(1-alpha/255)).astype(np.uint8)
            layer.image=Image.fromarray(old)
        else:
            overlay=Image.new('RGBA',self.original.size,tuple(color[:3])+(255,))
            overlay.putalpha(Image.fromarray(np.rint(alpha).clip(0,255).astype(np.uint8)))
            layer.image=Image.alpha_composite(layer.image,overlay)

    def recolor(self, color):
        if not self.editable: raise ValueError('This texture is read-only.')
        if len(self.layers)>=64:raise ValueError('Up to 64 layers per texture.')
        current=self.composite();hsv=np.asarray(current.convert('HSV')).copy()
        target=np.asarray(Image.new('RGB',(1,1),tuple(color[:3])).convert('HSV'))[0,0]
        allowed=self.allowed();valid=(allowed>0)&(np.asarray(current)[:,:,3]>0)
        if not valid.any(): raise ValueError('Selection contains no visible, unprotected pixels.')
        median=max(1.,float(np.median(hsv[:,:,2][valid])))
        hsv[:,:,0]=target[0];hsv[:,:,1]=target[1]
        hsv[:,:,2]=np.rint(hsv[:,:,2].astype(float)*float(target[2])/median).clip(0,255).astype(np.uint8)
        rgb=Image.fromarray(hsv,'HSV').convert('RGBA')
        rgb.putalpha(Image.fromarray(np.rint(allowed*255).astype(np.uint8)))
        self.layers.append(Layer('Recolor (shading retained)',rgb,full_quad(rgb.size),paint=True))

    def import_layer(self, image, name='Imported artwork'):
        if not self.editable: raise ValueError('This texture is read-only.')
        if len(self.layers)>=64:raise ValueError('Up to 64 layers per texture.')
        image=image.convert('RGBA')
        if image.width*image.height>MAX_PIXELS:raise ValueError('Image exceeds editing limit.')
        w,h=self.original.size;scale=min(w*.6/image.width,h*.6/image.height)
        iw,ih=image.width*scale,image.height*scale;x,y=(w-iw)/2,(h-ih)/2
        layer=Layer(name,image,[[x,y],[x+iw,y],[x+iw,y+ih],[x,y+ih]])
        self.layers.append(layer);return layer


def encode_edit(raw, image, color_limit=256):
    """Pin original colors outside the edit. Preserve GIM headers and allocation.

    Recoloring one area must not requantize skin/eyes sharing its atlas. Full T4
    palettes can consequently restrict new colors: report the actual loss.
    """
    from desktop.edit_folder import replace_gim_pixels
    ix,pal=read_gim(raw);before=pal[ix];rgba=np.asarray(image.convert('RGBA'))
    if rgba.shape!=before.shape:raise ValueError('Texture dimensions changed.')
    if not np.array_equal(rgba[:,:,3],before[:,:,3]):raise ValueError('Original texture alpha is locked.')
    changed=np.any(rgba!=before,axis=2)
    if not changed.any():return raw,dict(changed=False,serialized_bytes=len(raw),rgb_rmse=0.)
    if type(color_limit)is not int or not 1<=color_limit<=256:raise ValueError('Invalid artwork color limit.')
    revised=ix.copy();colors=pal.copy();capacity=len(pal)
    pinned=set(np.unique(ix[~changed]).tolist());free=[i for i in range(capacity)if i not in pinned]
    # Preserve source alpha exactly, with separate palettes for each alpha level.
    levels=np.unique(rgba[:,:,3][changed]);unused=list(free)
    for level in levels:
        mask=changed&(rgba[:,:,3]==level);values=rgba[mask,:3]
        permitted=[i for i in pinned if colors[i,3]==level]
        remaining_levels=sum(not any(colors[i,3]==a for i in pinned)for a in levels if a>level)
        slots=min(len(unused)-remaining_levels,color_limit,len(np.unique(values,axis=0)))
        if slots>0:
            q=Image.fromarray(values[None,:,:]).quantize(colors=slots,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
            table=np.asarray(q.getpalette(),np.uint8).reshape(-1,3)[:slots]
            ids=unused[:slots];unused=unused[slots:]
            colors[ids,:3]=table;colors[ids,3]=level;permitted+=ids
        if not permitted:raise ValueError('Protected colors leave no palette slot for this alpha level.')
        ids=np.asarray(permitted,np.uint8);best=np.empty(len(values),np.uint8)
        for start in range(0,len(values),4096):
            distance=(values[start:start+4096,None,:].astype(float)-colors[ids,:3][None,:,:].astype(float))**2
            best[start:start+4096]=ids[distance.sum(2).argmin(1)]
        revised[mask]=best
    # Reuse the existing exact-header writer after supplying <=capacity RGBA.
    encoded,_=replace_gim_pixels(raw,colors[revised])
    ni,nc=read_gim(encoded);decoded=nc[ni]
    if len(encoded)!=len(raw) or not np.array_equal(decoded[~changed],before[~changed]):
        raise ValueError('Unedited texels or texture allocation changed.')
    if not np.array_equal(decoded[:,:,3],before[:,:,3]):raise ValueError('Alpha changed during encoding.')
    error=float(np.sqrt(np.mean((decoded[changed,:3].astype(float)-rgba[changed,:3])**2)))
    return encoded,dict(changed=True,serialized_bytes=len(encoded),edited_texels=int(changed.sum()),
                        pinned_palette_slots=len(pinned),available_new_palette_slots=len(free),
                        artwork_color_limit=color_limit,used_palette_colors=len(np.unique(ni)),
                        rgb_rmse=error,unchanged_texels_exact=True,alpha_exact=True)


class Document:
    def __init__(self,data,source='Wrestler.pac'):
        if len(data)>32*1024*1024:raise ValueError('PAC exceeds the 32 MiB editor limit.')
        self.original=bytes(data);self.source=str(source);self.sha256=digest(data)
        self.container=inspect_pac(data);self.sections=list(sections(data))
        if len({s['id']for s,r in self.sections})!=len(self.sections):raise ValueError('Duplicate PAC sections.')
        self.models=[];self.textures=[];self.references=[];self.undo_stack=[];self.redo_stack=[]
        self.revision=0;self.dirty=False;self.saved_path=None;self.color_limit=256
        for s,raw in self.sections:
            if raw.startswith(b'YOBJ'):
                self.models.append((s['id'],audit_yobj(raw)))
            if len(raw)>=16 and raw[4:16]==struct.pack('<3I',0x100,0,16):
                for t in parse_textures(raw):
                    image=raw[t['offset']:t['offset']+t['size']]
                    try:ix,pal=read_gim(image)
                    except ValueError:continue
                    if ix.size>MAX_PIXELS:raise ValueError('Native texture exceeds editing limit.')
                    edit=s['id']==9 and t['name'].casefold()not in ('blood','blood_b','bandage')
                    self.textures.append(Texture(len(self.textures),s['id'],t['name'],image,Image.fromarray(pal[ix]),edit))
        if not self.models:raise ValueError('No supported native PSP YOBJ model found.')
        if not self.textures:raise ValueError('No supported indexed PSP textures found.')
        self.max_bytes=max(IN_RING_MAX_PAC_BYTES,len(data))

    def checkpoint(self):
        self.undo_stack.append(copy.deepcopy([(t.layers,t.selection,t.protection)for t in self.textures]))
        # Bound history by count AND image bytes (native + imported artwork).
        def cost(state):return sum(sum(l.image.width*l.image.height*4 for l in ls)+sel.width*sel.height*2 for ls,sel,prot in state)
        while len(self.undo_stack)>1 and (len(self.undo_stack)>20 or sum(map(cost,self.undo_stack))>64*1024*1024):self.undo_stack.pop(0)
        self.redo_stack.clear()

    def touch(self):self.revision+=1;self.dirty=True

    def undo(self,redo=False):
        stack=self.redo_stack if redo else self.undo_stack;other=self.undo_stack if redo else self.redo_stack
        if not stack:return False
        other.append(copy.deepcopy([(t.layers,t.selection,t.protection)for t in self.textures]))
        for t,(layers,sel,prot)in zip(self.textures,stack.pop()):t.layers,t.selection,t.protection=layers,sel,prot
        self.touch();return True

    def texture_for(self,model,name):
        matches=[t for t in self.textures if t.name.casefold()==name.casefold()]
        primary=[t for t in matches if t.section==9];chosen=primary or matches
        if len(chosen)!=1:raise ValueError('Missing or ambiguous model texture: '+name)
        return chosen[0]

    def images_for(self,model,encoded=False,color_limit=256):
        images={}
        for name in model['texture_names']:
            t=self.texture_for(model,name);image=t.composite()
            if encoded:
                raw,_=encode_edit(t.raw,image,color_limit);ix,pal=read_gim(raw);image=Image.fromarray(pal[ix])
            images[name]=np.asarray(image)
        return images

    def candidate(self,color_limit=None):
        color_limit=self.color_limit if color_limit is None else color_limit
        tables={};reports=[]
        for t in self.textures:
            if not t.editable:continue
            raw,r=encode_edit(t.raw,t.composite(),color_limit);reports.append(dict(index=t.index,name=t.name,**r))
            if not r['changed']:continue
            original=next(raw for s,raw in self.sections if s['id']==t.section)
            table=tables.setdefault(t.section,bytearray(original))
            matches=[r for r in parse_textures(original)if r['name']==t.name]
            if len(matches)!=1:raise ValueError('Ambiguous texture table entry.')
            row=matches[0];table[row['offset']:row['offset']+row['size']]=raw
        replacements={}
        for sid,table in tables.items():
            s=next(s for s,r in self.sections if s['id']==sid)
            prior=self.original[s['offset']:s['offset']+s['size']];raw=bytes(table)
            payload=min((compress(raw),compress(raw,max_distinct=220)),key=len)if prior.startswith(b'BPE ')else raw
            if payload.startswith(b'BPE ')and decompress(payload)!=raw:raise ValueError('Compression round trip failed.')
            replacements[sid]=payload
        if replacements:
            cursor=self.container['payload_start']
            for s in sorted(self.container['sections'],key=lambda s:s['offset']):
                if any(self.original[cursor:s['offset']]):raise ValueError('Unclassified nonzero PAC gap cannot be discarded.')
                cursor=s['offset']+s['size']
            if any(self.original[cursor:]):raise ValueError('Unclassified nonzero PAC trailer cannot be discarded.')
        candidate=rewrite_sections(self.original,replacements)if replacements else self.original
        checked=inspect_pac(candidate);after=list(sections(candidate))
        if [s['id']for s,r in after]!=[s['id']for s,r in self.sections]:raise ValueError('Section order changed.')
        for (a,raw),(b,revised)in zip(self.sections,after):
            if a['id']not in replacements and (a['sha256']!=b['sha256']or raw!=revised):raise ValueError('Unrelated PAC/model payload changed.')
            if a['id']in replacements and revised!=bytes(tables[a['id']]):raise ValueError('Final table differs.')
        if replacements and (len(candidate)%2048 or any(s['offset']%16 for s in checked['sections'])):raise ValueError('PAC alignment failed.')
        report=dict(bytes=len(candidate),max_pac_bytes=self.max_bytes,fits=len(candidate)<=self.max_bytes,
                    sha256=digest(candidate),original_sha256=self.sha256,original_bytes=len(self.original),
                    changed_sections=sorted(replacements),textures=reports,
                    all_model_payloads_exact=True,unrelated_stored_sections_exact=True,
                    texture_allocation_unchanged=True,unedited_round_trip_exact=candidate==self.original,
                    structural_validation='PAC tables/offsets/alignment, exact native model payloads, checked GIM round trips',
                    gameplay_validation='Not performed; test edited appearance in PPSSPP.')
        return candidate,report

    def export(self,destination,color_limit=None):
        destination=Path(destination)
        if destination.suffix.casefold()!='.pac' or destination.resolve()==Path(self.source).resolve():raise ValueError('Choose a NEW .pac filename.')
        if destination.exists():raise ValueError('Existing PACs are never overwritten.')
        candidate,report=self.candidate(color_limit)
        if not report['fits']:raise ValueError(f"Edited PAC is {report['bytes']:,} / {self.max_bytes:,} bytes. Reduce edited colors or simplify artwork, then preview again. No PAC written.")
        sidecar=destination.with_name(destination.name+'.report.json')
        if sidecar.exists():raise ValueError('A report already exists for this filename.')
        publish_new(sidecar,(json.dumps(report,indent=2)+'\n').encode())
        try:publish_new(destination,candidate)
        except Exception:sidecar.unlink(missing_ok=True);raise
        return report

    def save(self,path):
        path=Path(path)
        if path.suffix.casefold()!='.pspret':raise ValueError('Use a .pspret project filename.')
        if path.exists():raise ValueError('Choose a new project filename; existing projects are kept.')
        files={'original.pac':self.original};rows=[]
        for t in self.textures:
            prefix=f'textures/{t.index}';layers=[]
            files[prefix+'-selection.png']=png(t.selection);files[prefix+'-protection.png']=png(t.protection)
            for i,l in enumerate(t.layers):
                name=prefix+f'-layer-{i}.png';files[name]=png(l.image)
                layers.append(dict(name=l.name,image=name,quad=l.quad,opacity=l.opacity,visible=l.visible,paint=l.paint))
            rows.append(dict(index=t.index,layers=layers))
        for i,(name,image)in enumerate(self.references):files[f'references/{i}.png']=png(image)
        metadata=dict(schema=SCHEMA,source_name=Path(self.source).name,source_sha256=self.sha256,textures=rows,
                      references=[name for name,image in self.references],artwork_color_limit=self.color_limit)
        metadata['hashes']={name:digest(data)for name,data in files.items()}
        files['project.json']=(json.dumps(metadata,allow_nan=False)+'\n').encode()
        if sum(map(len,files.values()))>MAX_PROJECT_BYTES:raise ValueError('Project exceeds the 128 MiB limit.')
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED)as archive:
            for name,data in files.items():archive.writestr(name,data)
        publish_new(path,out.getvalue());self.saved_path=str(path);self.dirty=False

    @classmethod
    def load(cls,path):
        path=Path(path)
        if path.stat().st_size>MAX_PROJECT_BYTES:raise ValueError('Project exceeds size limit.')
        with zipfile.ZipFile(path)as archive:
            infos=archive.infolist();names=[i.filename for i in infos]
            if len(names)>1024 or len(set(names))!=len(names)or sum(i.file_size for i in infos)>MAX_PROJECT_BYTES:
                raise ValueError('Project archive exceeds limits or has duplicate entries.')
            meta=json.loads(archive.read('project.json'))
            if meta.get('schema')!=SCHEMA:raise ValueError('Unsupported retexture project.')
            hashes=meta['hashes']
            if set(names)!={'project.json',*hashes}:raise ValueError('Unexpected project entries.')
            files={name:archive.read(name)for name in hashes}
            if any(digest(files[n])!=s for n,s in hashes.items()):raise ValueError('Project asset checksum mismatch.')
        doc=cls(files['original.pac'],Path(meta['source_name']).name)
        limit=meta.get('artwork_color_limit',256)
        if type(limit)is not int or not 1<=limit<=256:raise ValueError('Invalid project palette setting.')
        doc.color_limit=limit
        if doc.sha256!=meta['source_sha256']or len(meta['textures'])!=len(doc.textures):raise ValueError('Project source mismatch.')
        total_pixels=0
        for t,row in zip(doc.textures,meta['textures']):
            if row['index']!=t.index or len(row['layers'])>64:raise ValueError('Invalid texture/layer index.')
            prefix=f'textures/{t.index}'
            for key in ('selection','protection'):
                image=read_image(files[prefix+'-'+key+'.png']).convert('L')
                if image.size!=t.original.size:raise ValueError('Mask dimensions differ.')
                setattr(t,key,image)
            for l in row['layers']:
                image=read_image(files[l['image']]);total_pixels+=image.width*image.height
                if total_pixels>16*MAX_PIXELS:raise ValueError('Too many layer pixels.')
                if not isinstance(l['name'],str)or len(l['name'])>256 or type(l['visible'])is not bool or type(l['paint'])is not bool:
                    raise ValueError('Invalid layer metadata.')
                opacity=l['opacity']
                if not isinstance(opacity,(int,float))or not math.isfinite(opacity)or not 0<=opacity<=1:raise ValueError('Invalid opacity.')
                if l['paint']:
                    if image.size!=t.original.size or l['quad']!=full_quad(image.size):raise ValueError('Invalid paint layer dimensions.')
                else:warp(Image.new('RGBA',(1,1)),l['quad'],(1,1))
                if not t.editable:raise ValueError('Read-only texture has edit layers.')
                t.layers.append(Layer(l['name'],image,l['quad'],opacity,l['visible'],l['paint']))
        if len(meta['references'])>12:raise ValueError('Too many reference images.')
        for i,name in enumerate(meta['references']):doc.references.append((str(name)[:256],read_image(files[f'references/{i}.png'])))
        doc.saved_path=str(path);doc.dirty=False
        return doc

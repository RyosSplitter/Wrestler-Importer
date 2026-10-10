"""Observed indexed GIM contracts, strict source ceilings and scored candidates."""
import struct

import numpy as np
from PIL import Image

from tools.texture_convert import _block, _image_header
from .analysis import measure

# Dimension pairs observed across the supplied 2,008 native SVR 2011 images.
# This is a conservative whitelist, not a universal PSP hardware limit.
OBSERVED_DIMENSIONS = {(128,128),(128,16),(128,256),(128,32),(128,64),
    (16,16),(16,32),(16,64),(256,128),(256,256),(256,32),(32,128),
    (32,16),(32,32),(32,64),(32,8),(64,128),(64,16),(64,256),(64,32),
    (64,64),(8,8)}
OBSERVED_T8_DIMENSIONS = {(32,8),(32,32),(32,64),(32,128),(64,16),
    (64,32),(64,64),(64,128),(128,32),(128,64),(128,128)}


def read_gim(data):
    """Decode the observed narrow padded layout, with checked block bounds."""
    if len(data)<128 or data[:12]!=b'MIG.00.1PSP\0':raise ValueError('Missing GIM signature')
    if struct.unpack_from('<I',data,20)[0]+16!=len(data):raise ValueError('GIM length mismatch')
    fmt,order,w,h,bits=struct.unpack_from('<5H',data,68)
    if (fmt,bits) not in ((4,4),(5,8)) or order!=1 or not w or not h or w&(w-1) or h&(h-1):raise ValueError('Unsupported indexed GIM')
    pitch=((w*bits+7)//8+15)//16*16;ph=(h+7)//8*8
    start=64+struct.unpack_from('<I',data,92)[0]
    end=48+struct.unpack_from('<I',data,52)[0]
    if start!=128 or end!=start+pitch*ph or end+80>len(data):raise ValueError('GIM pixel bounds mismatch')
    if struct.unpack_from('<5H',data,end+20)!=(3,0,1<<bits,1,32):raise ValueError('Unsupported RGBA CLUT')
    if end+80+(1<<bits)*4!=len(data) or end+struct.unpack_from('<I',data,end+4)[0]!=len(data):raise ValueError('GIM palette bounds mismatch')
    y,x=np.indices((ph,pitch));address=((y//8)*(pitch//16)+x//16)*128+(y%8)*16+x%16
    packed=np.frombuffer(data[start:end],np.uint8)[address]
    if bits==8:p=packed[:h,:w].copy()
    else:
        p=np.empty((ph,pitch*2),np.uint8);p[:,::2]=packed&15;p[:,1::2]=packed>>4;p=p[:h,:w].copy()
    c=np.frombuffer(data[end+80:],np.uint8).reshape(1<<bits,4).copy()
    return p,c


def write_gim(indices,palette,bits):
    h,w=indices.shape
    if bits not in (4,8) or (w,h) not in OBSERVED_DIMENSIONS:raise ValueError('Dimensions outside native evidence whitelist')
    if bits==8 and (w,h) not in OBSERVED_T8_DIMENSIONS:raise ValueError('Indexed8 dimension/format combination not observed in native SVR 2011 corpus')
    if indices.dtype!=np.uint8 or palette.dtype!=np.uint8 or palette.shape!=(1<<bits,4) or indices.max()>=1<<bits:raise ValueError('Invalid indices/CLUT')
    pitch=((w*bits+7)//8+15)//16*16;ph=(h+7)//8*8
    plane=np.zeros((ph,pitch),np.uint8)
    if bits==8:plane[:h,:w]=indices
    else:
        plane[:h,:w//2]=indices[:,::2]|(indices[:,1::2]<<4)
    y,x=np.indices((ph,pitch));address=((y//8)*(pitch//16)+x//16)*128+(y%8)*16+x%16
    pixels=np.zeros(plane.size,np.uint8);pixels[address]=plane
    image=_block(4,80+pixels.size)+_image_header(4 if bits==4 else 5,1,w,h,bits,pixels.size)+pixels.tobytes()
    pal=_block(5,80+palette.size)+_image_header(3,0,1<<bits,1,32,palette.size,palette=True)+palette.tobytes()
    size=48+len(image)+len(pal)
    raw=b'MIG.00.1PSP\0\0\0\0\0'+_block(2,size-16)+_block(3,size-32)+image+pal
    p,c=read_gim(raw)
    if not np.array_equal(p,indices) or not np.array_equal(c,palette):raise ValueError('GIM roundtrip failed')
    return raw


def dimensions(w,h):
    """Uniform downscales preserve source aspect; rectangular sources stay so."""
    return sorted((size for size in OBSERVED_DIMENSIONS if size[0]<=w and size[1]<=h and size[0]*h==size[1]*w),key=lambda s:(s[0]*s[1],s))


def encode(source,size,bits,color_limit,mask=None):
    h,w=source.shape[:2]
    if size[0]>w or size[1]>h:raise ValueError('Source resolution ceiling exceeded')
    if size not in dimensions(w,h):raise ValueError('Unobserved dimensions or changed aspect ratio')
    if bits==8 and size not in OBSERVED_T8_DIMENSIONS:raise ValueError('Indexed8 dimension/format combination not observed in native SVR 2011 corpus')
    useful=np.unique(source[source[:,:,3]>0],axis=0)
    ceiling=max(len(useful),1)+int(np.any(source[:,:,3]==0))
    count=min(color_limit,ceiling,1<<bits)
    if count<1:raise ValueError('Empty palette')
    alpha=bool(np.any(source[:,:,3]!=255))
    target=np.asarray(Image.fromarray(source).resize(size,Image.Resampling.LANCZOS))
    if alpha:
        if np.any(source[:,:,3]<128) and size!=(w,h):raise ValueError('Alpha cutout safeguard: source resolution required')
        # Keep alpha in its own channel, never averaged into RGB quantization.
        # Cutout images keep every source alpha sample; near-opaque images may
        # reduce resolution with nearest alpha (no invented alpha levels).
        canonical=target.copy()
        canonical[:,:,3]=np.asarray(Image.fromarray(source[:,:,3]).resize(size,Image.Resampling.NEAREST))
        canonical[canonical[:,:,3]==0]=0
        colors,inverse=np.unique(canonical.reshape(-1,4),axis=0,return_inverse=True)
        if len(colors)<=count:
            p=inverse.reshape(target.shape[:2]).astype(np.uint8);c=np.zeros((1<<bits,4),np.uint8);c[:len(colors)]=colors
            choices=[('Exact visible RGBA',p,c)]
        else:
            levels,counts=np.unique(canonical[:,:,3],return_counts=True)
            if not np.any(source[:,:,3]<128) and len(levels)>max(1,count//2):
                # Near-opaque PS2 maps can have many alpha levels but a fixed
                # PSP T4 contract. Quantize those levels to SOURCE levels only;
                # every sample remains on the opaque side of the cutout test.
                # Cutout alpha is never processed through this lossy path.
                axis=canonical[:,:,3]
                representatives=np.unique(np.quantile(axis,[0,.33,.67,1],method='nearest')).astype(np.uint8)
                nearest=np.abs(axis.astype(int)[:,:,None]-representatives.astype(int)).argmin(2)
                canonical[:,:,3]=representatives[nearest]
                levels,counts=np.unique(canonical[:,:,3],return_counts=True)
            if len(levels)>count:raise ValueError('Alpha levels exceed immutable palette capacity')
            allocation=np.ones(len(levels),int)
            for _ in range(count-len(levels)):
                candidates=[j for j,level in enumerate(levels) if level>0]
                if not candidates:break
                j=max(candidates,key=lambda j:counts[j]/(allocation[j]+1));allocation[j]+=1
            c=np.zeros((1<<bits,4),np.uint8);p=np.zeros(target.shape[:2],np.uint8);offset=0
            for level,capacity in zip(levels,allocation):
                pixels=canonical[:,:,3]==level;values=canonical[pixels,:3]
                q=Image.fromarray(values[None,:,:]).quantize(colors=int(capacity),method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
                rgbc=np.asarray(q.getpalette(),np.uint8).reshape(-1,3)
                used=int(np.asarray(q).max())+1
                c[offset:offset+used,:3]=rgbc[:used];c[offset:offset+used,3]=level
                p[pixels]=np.asarray(q).reshape(-1)+offset;offset+=used
            choices=[('RGB quantized per exact alpha level',p,c)]
    else:
        choices=[]
        colors,inverse=np.unique(target.reshape(-1,4),axis=0,return_inverse=True)
        if len(colors)<=count:
            c=np.zeros((1<<bits,4),np.uint8);c[:len(colors)]=colors
            choices.append(('Exact resized colors',inverse.reshape(target.shape[:2]).astype(np.uint8),c))
        else:
            rgb=Image.fromarray(target[:,:,:3])
            for method in (Image.Quantize.MEDIANCUT,Image.Quantize.MAXCOVERAGE,Image.Quantize.FASTOCTREE):
                q=rgb.quantize(colors=count,method=method,dither=Image.Dither.NONE)
                p=np.asarray(q,np.uint8);rgbc=np.asarray(q.getpalette(),np.uint8).reshape(-1,3)
                c=np.zeros((1<<bits,4),np.uint8);c[:len(rgbc),:3]=rgbc;c[:,3]=255
                choices.append((str(method),p,c))
    results=[]
    for method,p,c in choices:
        rgba=c[p];metric=measure(source,rgba,mask)
        results.append((metric['perceptual_loss'],method,p,c,metric))
    _,method,p,c,metric=min(results,key=lambda r:(r[0],r[1]))
    raw=write_gim(p,c,bits)
    used=len(np.unique(c[p].reshape(-1,4),axis=0))
    if used>ceiling:raise ValueError('Source useful color ceiling exceeded')
    return dict(raw=raw,entry=dict(width=size[0],height=size[1],bits=bits,palette_entries=1<<bits,
        requested_useful_colors=count,used_palette_colors=used,quantizer=method,
        serialized_bytes=len(raw),pixel_palette_bytes=len(raw)-208,
        metrics=metric,source_quality_ceiling=dict(width=w,height=h,useful_colors=ceiling),
        fully_preserved=metric['rgb_rmse_255']==0 and metric['alpha_exact']))


def generate(source,analysis,required_bits,baseline_rgba=None,head_sensitive=False):
    rows=[];rejected=[];seen=set()
    w,h=source.shape[1],source.shape[0]
    baseline=measure(source,baseline_rgba,analysis['mask']) if baseline_rgba is not None else None
    minimum_axis=min(*baseline_rgba.shape[:2],h,w) if head_sensitive and baseline_rgba is not None else 0
    cranial_color_floor=min(analysis['useful_source_colors'],len(np.unique(baseline_rgba.reshape(-1,4),axis=0))) if head_sensitive and baseline_rgba is not None else 0
    for size in dimensions(w,h):
        for bits in (4,8):
            limits=(16,) if bits==4 else (16,256)
            for colors in limits:
                config=dict(width=size[0],height=size[1],bits=bits,useful_color_limit=colors)
                if bits!=required_bits:
                    rejected.append(dict(**config,reason='Would change immutable YOBJ material rendering contract'));continue
                if min(size)<minimum_axis:
                    rejected.append(dict(**config,reason='Cranial sampling floor from current/source minimum axis'));continue
                if min(colors,analysis['useful_source_colors'])<cranial_color_floor:
                    rejected.append(dict(**config,reason='Cranial useful-color floor from current/source actual usage'));continue
                try:row=encode(source,size,bits,colors,analysis['mask'])
                except ValueError as exc:rejected.append(dict(**config,reason=str(exc)));continue
                m=row['entry']['metrics']
                # Protect a localized facial/detail regression while optimizing
                # aggregate quality; hypotheses require visual/game calibration.
                if baseline and head_sensitive and (m['perceptual_loss']>baseline['perceptual_loss']+.025 or
                   m['luminance_ssim']<baseline['luminance_ssim']-.02):
                    rejected.append(dict(**config,reason='Baseline detail/cranial regression safeguard',metrics=m));continue
                if row['raw'] in seen:continue
                seen.add(row['raw']);rows.append(row)
    rows.sort(key=lambda r:(r['entry']['serialized_bytes'],r['entry']['metrics']['perceptual_loss'],r['entry']['width'],r['entry']['bits']))
    # Only useful diminishing-return options; actual whole-PAC byte effects are
    # measured later, so equal GIM cost with different compression stays.
    if not rows:raise ValueError('No legal source-bounded candidate passes minimum safeguards')
    return rows,rejected

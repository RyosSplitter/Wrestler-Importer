"""Reproduce Rock texture-only trials; never runs geometry or weight processing.

python -m experiments.texture_quality.trial --source SOURCE_PS2.pac
  --baseline EXISTING_PSP.pac --output NEW_DIR
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw

from app.ps2_textures import read_source
from desktop.preview import render
from tools.psp_mesh_merge_trial import write_preview
from tools.texture_convert import read_gim,write_gim8
from .frozen import FrozenPac,digest
from .metrics import compare,encode


def dimensions(width,height,bits,halves=0):
    """Uniform power-of-two changes; satisfy the existing writer's block rules."""
    minimum=32 if bits==4 else 16
    w,h=width,height
    for _ in range(halves):
        if w//2>=minimum and h//2>=8:w//=2;h//=2
    while w<minimum or h<8:w*=2;h*=2
    if w>512 or h>512 or w%minimum or h%8:raise ValueError('Dimensions outside existing swizzled writer subset')
    return w,h


def reference_gims(decoded):
    # Exact source colors on frozen PSP geometry. Repeat small pixels to meet
    # writer pitch minimums; nearest sampling produces the same source image.
    result={}
    for i,n,raw,rgba,details in decoded:
        colors,inverse=np.unique(rgba.reshape(-1,4),axis=0,return_inverse=True)
        if len(colors)>256:raise ValueError('Reference preview cannot encode >256 exact source colors')
        p=inverse.reshape(rgba.shape[:2]).astype(np.uint8);palette=np.zeros((256,4),dtype=np.uint8);palette[:len(colors)]=colors
        while p.shape[1]<16 or p.shape[0]<8:p=np.repeat(np.repeat(p,2,0),2,1)
        result[n]=write_gim8(p,palette)
    return result


def save_candidate(output,label,frozen,gims,entries,*,renders=True):
    folder=output/label;folder.mkdir()
    pac,report=frozen.build(gims)
    report.update(label=label,textures=entries,
                  mean_ssim=float(np.mean([e['metrics']['luminance_ssim'] for e in entries])),
                  mean_rgb_rmse_255=float(np.mean([e['metrics']['rgb_rmse_255'] for e in entries])))
    preview=folder/'preview';preview.mkdir()
    mtls=[]
    for i,name in enumerate(frozen.names):
        raw=gims[name];p,c=read_gim(raw)
        (preview/(name+'.gim')).write_bytes(raw);Image.fromarray(c[p]).save(preview/(name+'.png'))
        mtls.extend(['newmtl texture_%d'%i,'Kd 1 1 1','map_Kd '+name+'.png'])
    (preview/'preview.mtl').write_text('\n'.join(mtls)+'\n');write_preview(frozen.preview,preview/'output.obj')
    from tools.psp_mesh_merge_trial import sections
    for s,raw in sections(pac):
        if raw.startswith(b'YOBJ'):(preview/('section-%d.yobj'%s['id'])).write_bytes(raw)
    if report['export_eligible']:
        filename='Rock-'+label+'-EXPERIMENTAL.pac'
        (folder/filename).write_bytes(pac);(folder/(filename+'.sha256')).write_text(report['sha256']+'  '+filename+'\n')
        report['pac_file']=filename
    else:
        (folder/'NOT-FOR-INJECTION.txt').write_text('PAC export withheld: this configuration exceeds the policy size or observed native texture envelope. See report.json. Geometry was not reduced to force a fit.\n')
        report['pac_file']=None
    if renders:
        for view in ('front','back','left','front-left'):
            render(frozen.preview,gims,view,768,1.7).save(folder/(view+'.png'))
    (folder/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


def panels(output,decoded,candidates):
    folder=output/'comparisons';folder.mkdir(exist_ok=True)
    labels=[r['label'] for r in candidates]
    for i,name,raw,rgba,details in decoded:
        if min(rgba.shape[:2])<16:continue
        canvas=Image.new('RGB',(256*(len(labels)+1),294),(40,40,40));draw=ImageDraw.Draw(canvas)
        images=[rgba]+[np.asarray(Image.open(output/label/'preview'/(name+'.png')).convert('RGBA')) for label in labels]
        for col,(label,im) in enumerate(zip(['Source']+labels,images)):
            canvas.paste(Image.fromarray(im).convert('RGB').resize((256,256),Image.Resampling.NEAREST),(col*256,38))
            draw.text((col*256+6,6),label,fill='white');draw.text((col*256+6,21),'%dx%d'%(im.shape[1],im.shape[0]),fill='white')
        canvas.save(folder/(name+'.png'))
    for view in ('front','back','left','front-left'):
        paths=[output/'source-preview'/(view+'.png')]+[output/label/(view+'.png') for label in labels]
        canvas=Image.new('RGB',(384*len(paths),414),(40,40,40));draw=ImageDraw.Draw(canvas)
        for col,(label,path) in enumerate(zip(['Source textures / frozen PSP geometry']+labels,paths)):
            canvas.paste(Image.open(path).resize((384,384),Image.Resampling.LANCZOS),(col*384,30));draw.text((col*384+5,8),label,fill='white')
        canvas.save(folder/('model-'+view+'.png'))


def run(source,baseline,output):
    output.mkdir(parents=True,exist_ok=False)
    frozen=FrozenPac(baseline.read_bytes())
    decoded=read_source(source,texture_names=frozen.names)
    original={n:rgba for i,n,r,rgba,d in decoded};candidates=[]
    entries=[]
    for i,name in enumerate(frozen.names):
        p,c=read_gim(frozen.gims[name]);rgba=c[p];bits=4 if len(c)==16 else 8
        entries.append(dict(name=name,index=i,source_dimensions=list(original[name].shape[1::-1]),width=p.shape[1],height=p.shape[0],bits=bits,palette_entries=len(c),encoded_bytes=len(frozen.gims[name]),pixel_palette_bytes=p.size*bits//8+c.size,quantizer='Existing accepted reduction',metrics=compare(original[name],rgba)))
    candidates.append(save_candidate(output,'01-current',frozen,frozen.gims,entries))
    for label in ('02-colors-only','03-moderate','04-original'):
        gims={};entries=[]
        for i,name,raw,rgba,details in decoded:
            w,h=rgba.shape[1],rgba.shape[0]
            p,c=read_gim(frozen.gims[name])
            alpha=np.any(rgba[:,:,3]!=255)
            size=(p.shape[1],p.shape[0]) if label=='02-colors-only' else dimensions(w,h,8,1 if label=='03-moderate' else 0)
            if alpha:size=dimensions(w,h,8)
            gim,_,entry=encode(rgba,size,8)
            entry.update(name=name,index=i,source_dimensions=[w,h],source_format=details,
                         source_aspect_ratio=w/h,aspect_ratio_preserved=size[0]/size[1]==w/h,
                         source_dimension_exception=None if label!='04-original' or size==(w,h) else 'Uniform upsampling required by existing GIM writer minimum pitch; native narrow images use padded storage not implemented in production')
            gims[name]=gim;entries.append(entry)
        candidates.append(save_candidate(output,label,frozen,gims,entries))
    reference=output/'source-preview';reference.mkdir()
    refs=reference_gims(decoded)
    for view in ('front','back','left','front-left'):render(frozen.preview,refs,view,768,1.7).save(reference/(view+'.png'))
    panels(output,decoded,candidates)
    result=dict(source_sha256=digest(source.read_bytes()),baseline_sha256=digest(baseline.read_bytes()),
                scope='Texture-only experiments: all three PSP rigs and geometry frozen, material control words track existing local indexed-depth profile',
                material_control_scope='The local converter contract is retained; native corpus demonstrates the control word is not a universal bit-depth selector',
                baseline_yobj_models=sorted(frozen.models),candidates=candidates)
    (output/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps([{k:r[k] for k in ('label','pac_bytes','texture_section_stored_bytes','encoded_gim_bytes','texture_pixel_palette_bytes','export_eligible','mean_ssim','mean_rgb_rmse_255')} for r in candidates],indent=2),flush=True)
    return frozen,decoded,result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.source,args.baseline,args.output)

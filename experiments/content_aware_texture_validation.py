"""Assemble existing reproducible A/B trials and validate every published payload.

Inputs are directories produced by desktop.texture_optimizer. Raw PS2/native
reference PACs are not copied. CPU comparison renders are labeled as such.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image,ImageDraw

from desktop.core import validate_pac
from desktop.texture_optimizer.__main__ import previews
from desktop.texture_optimizer.candidates import read_gim
from tools.psp_mesh_merge_trial import sections
from tools.psp_mesh_audit import audit_yobj
from tools.pac_inspect import inspect_pac,parse_textures
from model_qa.render import camera
from model_qa.geometry import AXES


def digest(raw):return hashlib.sha256(raw).hexdigest()


def assemble(cases,output):
    output.mkdir(parents=True,exist_ok=False);summary=[]
    for name,folder in cases:
        diagnostics=folder if (folder/'report.json').exists() else folder/'textures'
        report=json.loads((diagnostics/'report.json').read_text())
        candidate=folder/(name+'-adaptive.pac')
        if not candidate.exists():candidate=folder/'adaptive-experimental.pac'
        current=(folder/'current.pac').read_bytes();adaptive=candidate.read_bytes()
        validate_pac(current,gim_reader=read_gim);model,_=validate_pac(adaptive,gim_reader=read_gim)
        a={s['id']:raw for s,raw in sections(current)};b={s['id']:raw for s,raw in sections(adaptive)}
        if a.keys()!=b.keys():raise ValueError('Section set differs')
        for i in a:
            if i!=9 and a[i]!=b[i]:raise ValueError('Unrelated decoded data changed')
        # Refresh allocation arithmetic in older locally captured trial reports,
        # without changing a candidate or its recorded search decisions.
        info=inspect_pac(adaptive);retained={i for i,r in b.items() if i!=9 and len(r)>=16 and
            r[4:16]==bytes.fromhex('000100000000000010000000') and all(t['extension']=='gim' for t in parse_textures(r))}
        fixed=sum(s['size'] for s in info['sections'] if s['id']!=9)+info['payload_start']
        effect=sum(s['size'] for s in info['sections'] if s['id'] in retained)
        report.update(non_texture_stored_bytes_including_header=fixed-effect,
            required_fixed_bytes_before_costume_textures=fixed,retained_texture_stored_bytes=effect,
            nominal_texture_budget=147456-fixed+effect,costume_texture_budget=147456-fixed,
            total_texture_stored_bytes=effect+report['texture_stored_bytes'],
            alignment_padding_bytes=len(adaptive)-fixed-report['texture_stored_bytes'])
        target=output/name;target.mkdir()
        for p in diagnostics.iterdir():
            if p.is_file() and p.suffix in ('.json','.html','.png','.gim'):shutil.copy2(p,target/p.name)
        (target/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        for label,data in [('current',current),('adaptive',adaptive)]:
            p=target/(name+'-'+label+'-experimental.pac');p.write_bytes(data)
            (target/(p.name+'.sha256')).write_text(digest(data)+'  '+p.name+'\n')
            previews(data,target/(label+'-preview'))
        # Matching camera/geometry/lighting; face crop derived from cranial
        # controller support, never a texture filename or wrestler identity.
        points=np.array([v['position'] for m in model['meshes'] for v in m['vertices']])@AXES
        head=set()
        for bone in model['bones']:
            i=bone['index'];seen=set()
            while i!=-1 and i not in seen:
                seen.add(i)
                if model['bones'][i]['name']=='atama':head.add(bone['index']);break
                i=model['bones'][i]['parent']
        head_points=np.array([v['position'] for m in model['meshes'] for v in m['vertices']
            if sum(w for i,w in zip(m['bone_palette'],v['weights']) if i in head)>.5])@AXES
        for view in ('front-left','front','back','left','right'):
            panel=Image.new('RGB',(2048,1054),(30,30,30));draw=ImageDraw.Draw(panel)
            face_panel=Image.new('RGB',(1024,550),(30,30,30));fd=ImageDraw.Draw(face_panel)
            cam=camera(points,view,1024)
            if len(head_points):
                p=head_points-cam.center;xy=np.column_stack((p@cam.right,-p@cam.up))*1024/cam.span+512
                lo=np.maximum(np.floor(xy.min(0)-10).astype(int),0);hi=np.minimum(np.ceil(xy.max(0)+10).astype(int),1024)
            for col,(label,subfolder) in enumerate([('Current Texture Method','current-preview'),('Adaptive Texture Optimization','adaptive-preview')]):
                im=Image.open(target/subfolder/(view+'-full.png'));panel.paste(im,(col*1024,30));draw.text((col*1024+10,8),label,fill='white')
                if len(head_points):
                    crop=im.crop(tuple([*lo,*hi]));scale=min(512/crop.width,512/crop.height)
                    crop=crop.resize((max(1,round(crop.width*scale)),max(1,round(crop.height*scale))),Image.Resampling.NEAREST)
                    face_panel.paste(crop,(col*512+(512-crop.width)//2,30));fd.text((col*512+5,8),label,fill='white')
            panel.save(target/(view+'-comparison.png'))
            if len(head_points):face_panel.save(target/(view+'-face-comparison.png'))
        records=[]
        for t in report['textures']:
            old=t['current_configuration'];new=t['selected_configuration']
            records.append(dict(texture=t['name'],source_dimensions=str(t['source_dimensions']),
                source_used_colors=t['useful_source_colors'],importance=t['importance_score'],detail_coverage_percent=t['detail_coverage_percent'],
                old_dimensions='%dx%d'%(old['width'],old['height']),new_dimensions='%dx%d'%(new['width'],new['height']),
                old_used_colors=old['used_palette_colors'],new_used_colors=new['used_palette_colors'],palette_slots=new['palette_entries'],
                encoded_bytes=new['serialized_bytes'],old_ssim=old['metrics']['luminance_ssim'],new_ssim=new['metrics']['luminance_ssim'],
                old_loss=old['metrics']['perceptual_loss'],new_loss=new['metrics']['perceptual_loss'],
                old_feature_loss=old['metrics']['fine_feature_loss'],new_feature_loss=new['metrics']['fine_feature_loss']))
        with (target/'texture-comparison.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
        before_loss=sum(t['importance_score']*t['current_configuration']['metrics']['perceptual_loss'] for t in report['textures'])
        summary.append(dict(name=name,current_bytes=len(current),adaptive_bytes=len(adaptive),
            current_sha256=digest(current),adaptive_sha256=digest(adaptive),
            current_weighted_loss=before_loss,adaptive_weighted_loss=report['weighted_loss'],
            current_mean_ssim=sum(t['current_configuration']['metrics']['luminance_ssim'] for t in report['textures'])/len(report['textures']),
            adaptive_mean_ssim=sum(t['selected_configuration']['metrics']['luminance_ssim'] for t in report['textures'])/len(report['textures']),
            padded_pixels_and_clut=report['pixel_palette_bytes'],pixel_budget=report['pixel_palette_budget'],
            native_validation='pass',decoded_non_costume_sections_identical=True,
            model_payloads_exact=True,gameplay_validation='pending',measured_combinations=report['measured_combinations']))
        text=(target/'report.html').read_text()
        links='<p>Matching CPU renders: '+ ' | '.join('<a href="%s-comparison.png">%s</a>'%(v,v) for v in ('front-left','front','back','left','right'))+'</p><p><a href="texture-comparison.csv">Per-texture A/B CSV</a></p>'
        (target/'report.html').write_text(text.replace('</body>',links+'</body>'))
        print(name+' packaged and verified',flush=True)
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    body=['<html><meta charset="utf-8"><title>Content-aware A/B trials</title><body><h1>v0.25 experimental adaptive texture trials</h1><p>CPU renders, not PPSSPP captures. All geometry/material payloads exact. Gameplay pending.</p>']
    for r in summary:
        body.append('<h2><a href="%s/report.html">%s</a></h2><p>Current %d bytes; adaptive %d. Weighted loss %.4f → %.4f. Mean SSIM %.4f → %.4f.</p><img style="max-width:100%%" src="%s/front-left-comparison.png">'%(r['name'],r['name'],r['current_bytes'],r['adaptive_bytes'],r['current_weighted_loss'],r['adaptive_weighted_loss'],r['current_mean_ssim'],r['adaptive_mean_ssim'],r['name']))
    (output/'report.html').write_text('\n'.join(body+['</body></html>']))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',nargs=2,action='append',required=True,metavar=('LABEL','FOLDER'));p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();assemble([(n,Path(f)) for n,f in a.case],a.output)

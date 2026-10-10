"""Matching full cameras and source-material detail crops for texture trials."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw

from app.ps2_textures import read_source
from desktop.preview import render
from model_qa.geometry import AXES
from model_qa.render import camera
from .frozen import FrozenPac
from .trial import reference_gims


def run(source,baseline,folders,output,resolution=1536):
    output.mkdir(parents=True,exist_ok=False);frozen=FrozenPac(baseline.read_bytes())
    decoded=read_source(source,texture_names=frozen.names)
    sets=[('00-source-textures',reference_gims(decoded))]
    reports=[]
    for folder in folders:
        report=json.loads((folder/'report.json').read_text());label=report['label'];reports.append(report)
        sets.append((label,{n:(folder/'preview'/(n+'.gim')).read_bytes() for n in frozen.names}))
    points=np.array([v['position'] for m in frozen.preview['meshes'] for v in m['vertices']])@AXES
    # These names select illustration crops only. They do not affect conversion,
    # priorities, optimization, validation or asset generation.
    details={'face':{'rock_face_y','rock_eye_y'},'torso':{'rc_dou'},
             'tattoo':{'rc_kat_l'},'clothing-logos':{'rc_pan1','rc_pan2'}}
    cams={}
    crops={}
    for view in ('front','back','left','right','front-left'):
        cam=camera(points,view,resolution);cams[view]=cam.describe();boxes={}
        offset=0;ids={label:[] for label in details}
        for mesh in frozen.preview['meshes']:
            for mat in mesh['materials']:
                texture=frozen.preview['texture_names'][mat['texture_id']]
                for label,names in details.items():
                    if texture in names:ids[label].extend(offset+i for tri in mat['triangles'] for i in tri)
            offset+=len(mesh['vertices'])
        for label,indices in ids.items():
            p=points[np.unique(indices)]-cam.center
            xy=np.column_stack((p@cam.right,-p@cam.up))*resolution/cam.span+resolution*.5
            lo=np.maximum(np.floor(xy.min(0)-12).astype(int),0);hi=np.minimum(np.ceil(xy.max(0)+12).astype(int),resolution)
            boxes[label]=[int(lo[0]),int(lo[1]),int(hi[0]),int(hi[1])]
        crops[view]=boxes
        images=[]
        for label,gims in sets:
            folder=output/label;folder.mkdir(exist_ok=True)
            image=render(frozen.preview,gims,view,resolution,1.);image.save(folder/(view+'-full.png'));images.append(image)
            for detail,box in boxes.items():
                crop=image.crop(box);crop.thumbnail((512,512),Image.Resampling.LANCZOS)
                crop.save(folder/(view+'-'+detail+'.png'))
        for detail in ('full',*details):
            panel=Image.new('RGB',(384*len(sets),414),(40,40,40));draw=ImageDraw.Draw(panel)
            for col,(label,gims) in enumerate(sets):
                im=Image.open(output/label/(view+'-'+detail+'.png'));im.thumbnail((384,384),Image.Resampling.LANCZOS)
                panel.paste(im,(col*384+(384-im.width)//2,30+(384-im.height)//2));draw.text((col*384+4,8),label,fill='white')
            panel.save(output/(view+'-'+detail+'-comparison.png'))
        print('Matching renders complete: '+view,flush=True)
    (output/'cameras.json').write_text(json.dumps(dict(cameras=cams,crop_boxes=crops,
        source_view_scope='Original decoded HCTP textures applied to exact frozen converted PSP geometry, not original HCTP geometry',
        lighting='Identical fixed camera-relative light and original normals; CPU nearest texture sampling, alpha cutoff .5',
        limitations='Not Noesis captures, PPSSPP screenshots, PSP material-control emulation, mipmaps or hardware texture filtering'),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.baseline,a.candidate,a.output)

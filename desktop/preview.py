"""Offline textured renders from the actual audited PSP output, not the input."""
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from model_qa.render import camera
from model_qa.geometry import AXES
from tools.texture_convert import read_gim

VIEWS=('front-left','front','back','left','right')

def render(model,textures,view='front-left',resolution=768,zoom=1.,*,gim_reader=read_gim,
           rgba_textures=None,highlight_texture=None,yaw=None,capture=None):
    points=np.array([v['position'] for m in model['meshes'] for v in m['vertices']])@AXES
    cam=camera(points,view,resolution)
    if yaw is not None:
        radians=np.deg2rad(float(yaw));cam.direction=np.array([np.sin(radians),0.,np.cos(radians)])
        cam.right=np.cross(cam.up,cam.direction)
        # Orbit uses one fixed, all-angle framing rather than rescaling each view.
        extent=points.max(0)-points.min(0)
        cam.span=max(float(np.hypot(extent[0],extent[2])),float(extent[1]))*1.18
    cam.span/=zoom
    rgba=rgba_textures if rgba_textures is not None else {name:colors[indices] for name,raw in textures.items() for indices,colors in [gim_reader(raw)]}
    pixels=np.full((resolution,resolution,3),72,dtype=np.uint8)
    if capture is not None:
        capture.update(texture=np.full((resolution,resolution),-1,np.int16),
                       address=np.zeros((resolution,resolution),np.int32),
                       vertex_color=np.zeros((resolution,resolution,3)),
                       shade=np.zeros((resolution,resolution)))
    depth=np.full((resolution,resolution),-np.inf)
    light=cam.direction+.45*cam.right+.7*cam.up;light/=np.linalg.norm(light)
    for mesh in model['meshes']:
        vs=np.array([v['position'] for v in mesh['vertices']])@AXES-cam.center
        ns=np.array([v['normal'] for v in mesh['vertices']])@AXES
        uv=np.array([v['uv'] for v in mesh['vertices']])
        colors=np.array([v['color'] for v in mesh['vertices']],dtype=float)/255
        xy=np.column_stack((vs@cam.right,-vs@cam.up))*resolution/cam.span+resolution*.5
        z=vs@cam.direction
        for mat in mesh['materials']:
            texture=rgba[model['texture_names'][mat['texture_id']]];h,w=texture.shape[:2]
            for tri in mat['triangles']:
                face=np.asarray(tri);a,b,c=xy[face]
                denom=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                if abs(denom)<1e-9:continue
                lo=np.maximum(np.floor(xy[face].min(0)).astype(int),0)
                hi=np.minimum(np.ceil(xy[face].max(0)).astype(int),resolution-1)
                if (hi<lo).any():continue
                xx,yy=np.meshgrid(np.arange(lo[0],hi[0]+1)+.5,np.arange(lo[1],hi[1]+1)+.5)
                aa=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/denom
                bb=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/denom;cc=1-aa-bb
                bary=np.stack((aa,bb,cc),axis=-1)
                tc=bary@uv[face];sample=texture[np.floor(tc[:,:,1]*h).astype(int)%h,np.floor(tc[:,:,0]*w).astype(int)%w].astype(float)
                vc=bary@colors[face];alpha=sample[:,:,3]/255*vc[:,:,3]
                zz=bary@z[face];window=depth[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
                take=(aa>=-1e-7)&(bb>=-1e-7)&(cc>=-1e-7)&(zz>window)&(alpha>=.5)
                if not take.any():continue
                normal=bary@ns[face];normal/=np.maximum(np.linalg.norm(normal,axis=-1,keepdims=True),1e-12)
                shade=.4+.6*np.abs(normal@light)
                if capture is not None:
                    sl=np.s_[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
                    capture['texture'][sl][take]=mat['texture_id']
                    address=(np.floor(tc[:,:,1]*h).astype(int)%h)*w+np.floor(tc[:,:,0]*w).astype(int)%w
                    capture['address'][sl][take]=address[take]
                    capture['vertex_color'][sl][take]=vc[:,:,:3][take]
                    capture['shade'][sl][take]=shade[take]
                color=np.clip(sample[:,:,:3]*vc[:,:,:3]*shade[:,:,None],0,255).astype(np.uint8)
                if highlight_texture is not None and model['texture_names'][mat['texture_id']]!=highlight_texture:
                    gray=color.mean(axis=-1,keepdims=True)*.35
                    color=np.repeat(gray,3,axis=-1).astype(np.uint8)
                target=pixels[lo[1]:hi[1]+1,lo[0]:hi[0]+1];target[take]=color[take];window[take]=zz[take]
    image=Image.fromarray(pixels);draw=ImageDraw.Draw(image)
    label=view.replace('-',' ').upper()if yaw is None else 'LIVE ORBIT %.0f DEG'%float(yaw)
    draw.text((14,14),'PSP OUTPUT | '+label,fill='white')
    draw.text((14,resolution-25),'Offline preview | game shading may differ',fill='white')
    return image


def save_views(model,textures,folder,resolution=768,*,gim_reader=read_gim):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    for zoom,label in ((1.,'full'),(1.7,'zoom')):
        for view in VIEWS:render(model,textures,view,resolution,zoom,gim_reader=gim_reader).save(folder/(view+'-'+label+'.png'))

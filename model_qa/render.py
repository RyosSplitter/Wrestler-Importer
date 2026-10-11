"""Deterministic CPU orthographic geometry renders and projected-depth comparisons.

These are QA clay renders, not Noesis or game screenshots. The original fixes
each camera; the candidate is never independently centered, scaled or posed.
"""
from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion, distance_transform_edt


DIRECTIONS = {
    'front': (0,0,1), 'back': (0,0,-1), 'left': (1,0,0), 'right': (-1,0,0),
    'front-left': (1,0,1), 'front-right': (-1,0,1),
    'back-left': (1,0,-1), 'back-right': (-1,0,-1),
}


@dataclass
class Camera:
    name: str
    center: np.ndarray
    right: np.ndarray
    up: np.ndarray
    direction: np.ndarray
    span: float
    resolution: int

    def describe(self):
        return dict(name=self.name,center=self.center.tolist(),right=self.right.tolist(),up=self.up.tolist(),
                    direction=self.direction.tolist(),span=self.span,resolution=self.resolution,projection='orthographic',
                    units_per_pixel=self.span/self.resolution,lighting='fixed camera-relative key + ambient; identical pair',
                    origin='Original aligned geometry only; no independent candidate framing')


def camera(points, view, resolution=320):
    direction=np.array(DIRECTIONS[view],dtype=float);direction/=np.linalg.norm(direction)
    up=np.array([0.,1.,0.]);right=np.cross(up,direction)
    center=(points.max(0)+points.min(0))*.5
    projected=np.column_stack(((points-center)@right,(points-center)@up))
    span=max(float(np.ptp(projected[:,0])),float(np.ptp(projected[:,1])))*1.18
    if not math.isfinite(span) or span<=1e-10:raise ValueError('Invalid reference camera extent')
    return Camera(view,center,right,up,direction,span,resolution)


def raster(g, cam, errors=None, heat_limit=None, *, cull='none'):
    if cull not in ('none','back','front'):
        raise ValueError('Culling must be none, back or front')
    n=cam.resolution;position=g.vertices-cam.center
    xy=np.column_stack((position@cam.right,-position@cam.up))*n/cam.span+n*.5
    z=position@cam.direction
    depth=np.full((n,n),-np.inf);ids=np.full((n,n),-1,dtype=np.int32)
    rgb=np.full((n,n,3),28,dtype=np.uint8)
    light=cam.direction+.45*cam.right+.7*cam.up;light/=np.linalg.norm(light)
    normals=g.mesh.face_normals
    for fi,face in enumerate(g.faces):
        facing=float(np.dot(normals[fi],cam.direction))
        if (cull=='back' and facing<=0) or (cull=='front' and facing>=0):continue
        a,b,c=xy[face]
        denom=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(denom)<1e-9:continue
        lo=np.maximum(np.floor(np.min(xy[face],axis=0)).astype(int),0)
        hi=np.minimum(np.ceil(np.max(xy[face],axis=0)).astype(int),n-1)
        if np.any(hi<lo):continue
        xx,yy=np.meshgrid(np.arange(lo[0],hi[0]+1)+.5,np.arange(lo[1],hi[1]+1)+.5)
        wa=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/denom
        wb=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/denom
        wc=1-wa-wb;inside=(wa>=-1e-8)&(wb>=-1e-8)&(wc>=-1e-8)
        zz=wa*z[face[0]]+wb*z[face[1]]+wc*z[face[2]]
        window=depth[lo[1]:hi[1]+1,lo[0]:hi[0]+1];take=inside&(zz>window)
        if not take.any():continue
        window[take]=zz[take];ids[lo[1]:hi[1]+1,lo[0]:hi[0]+1][take]=fi
        shade=.32+.68*abs(float(np.dot(normals[fi],light)))
        if errors is None:color=np.full((*wa.shape,3),int(shade*220),dtype=np.uint8)
        else:
            amount=(wa*errors[face[0]]+wb*errors[face[1]]+wc*errors[face[2]])/heat_limit
            amount=np.clip(amount,0,1)
            color=np.stack((32+223*amount,130*(1-amount),215*(1-amount)),axis=-1).astype(np.uint8)
        rgb[lo[1]:hi[1]+1,lo[0]:hi[0]+1][take]=color[take]
    return dict(depth=depth,mask=ids>=0,face_ids=ids,rgb=rgb)


def comparison(a,b,cam,height):
    ma,mb=a['mask'],b['mask'];union=ma|mb;common=ma&mb
    edge_a=ma&~binary_erosion(ma);edge_b=mb&~binary_erosion(mb)
    unit=cam.span/cam.resolution
    distances=np.concatenate((distance_transform_edt(~edge_b)[edge_a],distance_transform_edt(~edge_a)[edge_b]))*unit
    difference=b['depth'][common]-a['depth'][common]
    report=dict(silhouette_iou=float(np.sum(common)/max(1,np.sum(union))),silhouette_disagreement_pixels=int(np.sum(ma^mb)),
                edge_distance_p95_height=float(np.percentile(distances,95)/height) if len(distances) else None,
                common_surface_pixels=int(common.sum()),source_pixels=int(ma.sum()),candidate_pixels=int(mb.sum()),
                source_visible_coverage=float(common.sum()/max(1,ma.sum())))
    if len(difference):report.update(depth_signed_mean=float(difference.mean()),depth_absolute_p95_height=float(np.percentile(abs(difference),95)/height),
        inward_depth_p95_height=float(np.percentile(np.maximum(-difference,0),95)/height),outward_depth_p95_height=float(np.percentile(np.maximum(difference,0),95)/height),
        projected_depth_volume_proxy=float(difference.sum()*unit**2),projected_depth_volume_proxy_height3=float(difference.sum()*unit**2/height**3))
    report['volume_caveat']='View-integrated depth difference on common visible pixels, not closed anatomical volume'
    return report


def save_pair(folder,stem,reference,candidate,cam,height,heat=None,save_depth=False,*,cull='none'):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    a=raster(reference,cam,cull=cull);b=raster(candidate,cam,cull=cull)
    difference=np.zeros((cam.resolution,cam.resolution,3),dtype=np.uint8)
    difference[a['mask']]=(80,160,245);difference[b['mask']]=(240,120,65);difference[a['mask']&b['mask']]=(135,135,135)
    tiles=[a['rgb'],b['rgb'],difference];labels=['HCTP geometry reference','PSP candidate','Silhouette: source blue / PSP orange']
    if heat is not None:
        tiles.append(raster(candidate,cam,heat,height*.006,cull=cull)['rgb']);labels.append('Error: blue 0 / red >=0.6% height')
    image=Image.new('RGB',(cam.resolution*len(tiles),cam.resolution+46),(24,24,24));draw=ImageDraw.Draw(image)
    for i,(tile,label) in enumerate(zip(tiles,labels)):
        image.paste(Image.fromarray(tile),(i*cam.resolution,30));draw.text((i*cam.resolution+8,8),label,fill='white')
    draw.text((8,cam.resolution+32),stem+' | Identical cameras | QA clay render | Cull: '+cull,fill='white')
    image.save(folder/(stem+'.png'))
    for suffix,tile in [('reference',tiles[0]),('candidate',tiles[1]),('silhouette',tiles[2])]:
        Image.fromarray(tile).save(folder/(stem+'-'+suffix+'.png'))
    if heat is not None:Image.fromarray(tiles[3]).save(folder/(stem+'-heat.png'))
    # Optional pixel exports use float32; measurements remain float64.
    if save_depth:
        np.savez_compressed(folder/(stem+'-depth.npz'),source=np.where(a['mask'],a['depth'],np.nan).astype(np.float32),candidate=np.where(b['mask'],b['depth'],np.nan).astype(np.float32))
    return comparison(a,b,cam,height),dict(cam.describe(),cull=cull)

"""Read-only, source-relative facial color diagnostics (no skin-tone template).

Thresholds are review heuristics, not calibrated game-compatibility limits.
Compare local colors as well as global means: opposite local biases can cancel.
"""
import copy
import numpy as np
from PIL import Image
from desktop.texture_optimizer.analysis import model_usage


def lab(rgb):
    c=np.asarray(rgb,dtype=float)/255
    linear=np.where(c<=.04045,c/12.92,((c+.055)/1.055)**2.4)
    xyz=linear@np.array([[.4124564,.3575761,.1804375],[.2126729,.7151522,.0721750],[.0193339,.1191920,.9503041]]).T
    xyz/=np.array([.95047,1.,1.08883]);delta=6/29
    f=np.where(xyz>delta**3,np.cbrt(xyz),xyz/(3*delta**2)+4/29)
    return np.stack([116*f[...,1]-16,500*(f[...,0]-f[...,1]),200*(f[...,1]-f[...,2])],axis=-1)


def color_metrics(source,candidate,mask):
    source=np.asarray(source,np.uint8);candidate=np.asarray(candidate,np.uint8);mask=np.asarray(mask,bool)&(source[:,:,3]>0)
    if mask.shape!=source.shape[:2]or not mask.any():raise ValueError('Nonempty source-sized color mask required')
    if candidate.shape!=source.shape:
        candidate=np.array(Image.fromarray(candidate).resize((source.shape[1],source.shape[0]),Image.Resampling.BILINEAR))
    a=source[:,:,:3].astype(float);b=candidate[:,:,:3].astype(float);la,lb=lab(a),lab(b)
    distance=np.linalg.norm(lb-la,axis=2);tiles=[]
    for ys in np.array_split(np.arange(source.shape[0]),8):
        for xs in np.array_split(np.arange(source.shape[1]),8):
            used=mask[np.ix_(ys,xs)]
            if used.sum()<4:continue
            tiles.append(float(np.linalg.norm(lb[np.ix_(ys,xs)][used].mean(0)-la[np.ix_(ys,xs)][used].mean(0))))
    p95=float(np.percentile(distance[mask],95));local=max(tiles,default=0.)
    return dict(occupied_texels=int(mask.sum()),rgb_mean_bias=(b[mask]-a[mask]).mean(0).tolist(),
        rgb_rmse_255=float(np.sqrt(np.square(b[mask]-a[mask]).mean())),
        delta_e76_mean=float(distance[mask].mean()),delta_e76_p95=p95,
        maximum_local_tile_lab_bias=local,lab_mean_bias=(lb[mask]-la[mask]).mean(0).tolist(),
        review=bool(p95>12 or local>8),thresholds=dict(delta_e76_p95=12,maximum_local_tile_lab_bias=8),
        threshold_status='PROVISIONAL review heuristics; not calibrated acceptance thresholds',
        scope='Source-sized bilinear reconstruction in original UV coordinates; source-relative D65 Lab, no prescribed skin tone')


def head_masks(model,images):
    names={b['name']:b['index']for b in model['bones']};head=set()
    for b in model['bones']:
        i=b['index'];seen=set()
        while i>=0 and i not in seen:
            seen.add(i)
            if model['bones'][i]['name']=='atama':head.add(b['index']);break
            i=model['bones'][i]['parent']
    eyes={names[n]for n in ('l_eye','r_eye')if n in names}
    out=copy.deepcopy(model);out['texture_names']=out.get('texture_names',out.get('textures'))
    for mesh in out['meshes']:
        for mat in mesh['materials']:
            selected=[]
            for tri in mat['triangles']:
                vs=[mesh['vertices'][i]for i in tri]
                mass=lambda ids:sum(sum(w for b,w in zip(mesh['bone_palette'],v['weights'])if b in ids)for v in vs)/3
                if mesh.get('role') not in ('Hair','Cutout') and mass(head)>.8 and mass(eyes)<.9 and np.mean([v['normal'][2]for v in vs])<-.1:selected.append(tri)
            mat['triangles']=selected
    usage=model_usage({2:out},images)
    return {name:row['uv_mask']for name,row in usage.items()if row['area']>0 and row['uv_reliable']and row['uv_mask']is not None}


def report(model,source_images,decoded_images):
    masks=head_masks(model,source_images)
    return dict(region='Front-facing cranial skin; excludes pure eyeball surfaces and separate hair',
        textures={name:color_metrics(source_images[name],decoded_images[name],mask)for name,mask in masks.items()},
        coverage_available=bool(masks),limitations='Color representation only; does not validate lighting, material state or actual runtime animation')

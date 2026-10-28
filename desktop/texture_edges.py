"""Source-image evidence for preserving painted clothing edges on limbs.

A wristband/knee pad can share both material and continuous UVs with skin. Its
painted border then has no material/UV seam for the geometric guards to find.
Retain adjacent source triangles on either side of a strong dark/light transition rather
than moving the border or editing its pixels after simplification.
"""
from collections import Counter,defaultdict

import numpy as np

from tools.region_mesh import bone_regions


def clothing_edges(model,images):
    regions=bone_regions(model['bones'])
    names=model.get('texture_names',model.get('textures'))
    # 91 deterministic barycentric samples, including every edge and corner.
    grid=np.array([(i/12,j/12,1-(i+j)/12) for i in range(13) for j in range(13-i)])
    records=[];edges=defaultdict(list);eligible=0
    for mesh in model['meshes']:
        for mat_index,mat in enumerate(mesh['materials']):
            name=names[mat['texture_id']]
            image=np.asarray(images[name])
            if image.ndim!=3 or image.shape[2]!=4 or image.dtype!=np.uint8:
                raise ValueError('Painted edge guards require decoded source RGBA8 images')
            h,w=image.shape[:2]
            for ti,tri in enumerate(mat['triangles']):
                vertices=[mesh['vertices'][i] for i in tri]
                limb=sum(sum(weight for b,weight in zip(mesh['bone_palette'],v['weights'])
                             if regions[b] in ('Arms','Legs')) for v in vertices)/3
                if limb<=.5:continue
                eligible+=1
                uv=np.array([v['uv'] for v in vertices],dtype=float)
                if not np.isfinite(uv).all():raise ValueError('Nonfinite painted edge UV')
                samples=grid@uv
                xy=np.floor(samples*[w,h]).astype(np.int64)
                pixels=image[xy[:,1]%h,xy[:,0]%w]
                # Cutouts already have a separate whole-surface guard. Never
                # mistake their transparent padding for an opaque garment edge.
                if (pixels[:,3]<128).any():continue
                luminance=pixels[:,:3]@np.array([.2126,.7152,.0722])
                record=dict(key=[mesh['index'],mat_index,mat['texture_id'],ti],texture=name,
                            median=float(np.median(luminance)))
                number=len(records);records.append(record)
                points=[tuple(v['position']) for v in vertices]
                for a,b in zip(points,points[1:]+points[:1]):
                    if a!=b:edges[tuple(sorted((a,b)))].append(number)
    selected=set();contrasting_edges=0
    for adjacent in edges.values():
        dark=[i for i in adjacent if records[i]['median']<55]
        light=[i for i in adjacent if records[i]['median']>95]
        if any(records[b]['median']-records[a]['median']>64 for a in dark for b in light):
            contrasting_edges+=1
            selected.update(dark+light)
    faces=[records[i]['key'] for i in sorted(selected)]
    counts=Counter(records[i]['texture'] for i in selected)
    return dict(faces=faces,source_triangles=len(faces),eligible_limb_triangles=eligible,
                per_texture=dict(counts),samples_per_face=len(grid),contrasting_edges=contrasting_edges,
                policy='Preserve both source limb faces adjacent to opaque source-image dark/light clothing borders; no image, UV or weight edits',
                thresholds=dict(dark_below=55,light_above=95,minimum_range=64,opaque_alpha_minimum=128),
                limitations='Fixed source-image samples can also retain dark limb artwork and do not detect every garment color transition.')

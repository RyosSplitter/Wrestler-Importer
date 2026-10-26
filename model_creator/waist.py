"""Display-only waist-plane guide using the same camera as the PSP preview."""
import numpy as np
from PIL import ImageDraw
from model_qa.geometry import AXES
from model_qa.render import camera
from .parts import cut_planes


def draw_guide(image, model, view, waist_y):
    limit=cut_planes(waist_y)['waist'][1]
    points=np.array([v['position'] for m in model['meshes'] for v in m['vertices']]) @ AXES
    cam=camera(points,view,image.width)
    result=image.copy();draw=ImageDraw.Draw(result)
    for mesh in model['meshes']:
        for material in mesh['materials']:
            for triangle in material['triangles']:
                positions=np.array([mesh['vertices'][i]['position'] for i in triangle])
                intersections=[]
                for a,b in zip(positions,np.roll(positions,-1,axis=0)):
                    da,db=a[1]-limit,b[1]-limit
                    if abs(da)<1e-7:intersections.append(a)
                    if da*db<0:intersections.append(a+(b-a)*da/(da-db))
                if len(intersections)<2:continue
                projected=np.asarray(intersections) @ AXES-cam.center
                xy=np.column_stack((projected @ cam.right,-projected @ cam.up))*image.width/cam.span+image.width*.5
                for a,b in zip(xy,xy[1:]):draw.line([tuple(a),tuple(b)],fill=(40,225,245),width=2)
    return result

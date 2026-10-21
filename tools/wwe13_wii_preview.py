"""Display-only unlit texture diagnostics. Never serialize the display copy.

The existing preview shader multiplies texture RGB by .4+.6*abs(N dot L).
A view-only constant normal parallel to L makes that factor one. This reuses the
same rasterizer/UV/alpha path without modifying production preview defaults.
"""
import copy
from pathlib import Path
import numpy as np
from model_qa.geometry import AXES
from model_qa.render import DIRECTIONS
from tools.sym_trial import render_native


def unlit_copy(model,view):
    direction=np.array(DIRECTIONS[view],float);direction/=np.linalg.norm(direction)
    up=np.array([0.,1.,0.]);right=np.cross(up,direction)
    light=direction+.45*right+.7*up;light/=np.linalg.norm(light)
    native_normal=light@AXES.T
    display=copy.deepcopy(model)
    for mesh in display['meshes']:
        for v in mesh['vertices']:v['normal']=native_normal.tolist()
    return display


def render_unlit(model,textures,view,path,*,label='UNLIT DIFFUSE | DISPLAY ONLY',**kwargs):
    render_native(unlit_copy(model,view),textures,view,Path(path),label=label,**kwargs)

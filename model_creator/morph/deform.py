"""Deterministic native-coordinate body fields, shared with Blender workers.

Fields depend on bind-space positions and bone anchors, never vertex ordering or
averaged weights. Coincident UV/palette records receive the same displacement.
Joint centers, the head and extremities are outside these bounded body controls.
"""
import numpy as np

ENGINE='body-fields/1'
CONTROLS={
    'shoulders':('Shoulder width',.06),
    'chest_width':('Chest width',.12),
    'chest_depth':('Chest depth',.12),
    'waist':('Waist width',.12),
    'upper_arms':('Upper-arm thickness',.15),
    'thighs':('Thigh thickness',.12),
    'calves':('Calf thickness',.12),
}


def parameters(values=None):
    values={} if values is None else values
    if not isinstance(values,dict) or set(values)-set(CONTROLS):raise ValueError('Unknown morph controls')
    out={}
    for name in CONTROLS:
        value=values.get(name,0.)
        if type(value) not in (float,int) or not np.isfinite(value) or not -1<=value<=1:
            raise ValueError('Morph control outside -1 to 1: '+name)
        out[name]=float(value)
    return out


def active(values):return any(parameters(values).values())


def bell(x):
    t=np.clip(1-np.abs(x),0,1)
    return t*t*(3-2*t)


def positions(original,anchors,height,values):
    values=parameters(values);p=np.asarray(original,dtype=float);delta=np.zeros_like(p)
    a={n:np.asarray(v,dtype=float) for n,v in anchors.items()}
    center=a['koshi'];chest=a['mune'];neck=a['kubi']
    torso_half=max(abs(a['l_ninoude'][0]-a['r_ninoude'][0])*.5,height*.055)
    lateral=bell((p[:,0]-center[0])/(torso_half*1.2))
    # Native Y points down. Fade to zero before the neck and pelvis joints.
    chest_mask=bell((p[:,1]-chest[1])/(height*.10))*lateral
    waist_center=(center[1]+chest[1])*.5
    waist_mask=bell((p[:,1]-waist_center)/(height*.09))*lateral
    neck_gate=np.clip((p[:,1]-neck[1])/(height*.035),0,1)
    neck_gate=neck_gate*neck_gate*(3-2*neck_gate)
    chest_mask*=neck_gate;waist_mask*=neck_gate
    shoulder_mask=bell((p[:,1]-chest[1])/(height*.085))*bell((p[:,0]-center[0])/(torso_half*1.65))
    shoulder_mask*=np.clip((p[:,1]-neck[1])/(height*.035),0,1)
    delta[:,0]+=(p[:,0]-center[0])*(values['chest_width']*.12*chest_mask+values['waist']*.12*waist_mask+values['shoulders']*.06*shoulder_mask)
    delta[:,2]+=(p[:,2]-chest[2])*values['chest_depth']*.12*chest_mask
    for control,start,end,radius in (('upper_arms','ninoude','kote',.065),('thighs','momo','sune',.10),('calves','sune','ashi',.075)):
        if not values[control]:continue
        for side in ('l_','r_'):
            x,y=a[side+start],a[side+end];axis=y-x;length=float(axis@axis)
            if length<height**2*.0001:raise ValueError('Insufficient limb anchors for '+control)
            t=(p-x)@axis/length;radial=p-(x+t[:,None]*axis)
            envelope=bell((t-.5)/.40)*bell(np.linalg.norm(radial,axis=1)/(height*radius))
            delta+=radial*(values[control]*CONTROLS[control][1]*envelope)[:,None]
    return p+delta


def evaluate(original,normals,anchors,height,values):
    values=parameters(values);p=np.asarray(original,dtype=float);n=np.asarray(normals,dtype=float)
    if not active(values):return p.copy(),n.copy()
    result=positions(p,anchors,height,values)
    step=height*1e-5;columns=[]
    for axis in range(3):
        offset=np.zeros(3);offset[axis]=step
        columns.append((positions(p+offset,anchors,height,values)-positions(p-offset,anchors,height,values))/(2*step))
    jacobian=np.stack(columns,axis=2)
    if np.min(np.linalg.det(jacobian))<.3:raise ValueError('Combined morph folds the body; reduce the controls')
    transformed=np.linalg.solve(jacobian.transpose(0,2,1),n[:,:,None])[:,:,0]
    transformed/=np.maximum(np.linalg.norm(transformed,axis=1,keepdims=True),1e-12)
    unchanged=np.max(np.abs(jacobian-np.eye(3)),axis=(1,2))<1e-7
    transformed[unchanged]=n[unchanged]
    if not np.isfinite(result).all() or not np.isfinite(transformed).all():raise ValueError('Nonfinite morph result')
    return result.astype(np.float32).astype(float),transformed.astype(np.float32).astype(float)

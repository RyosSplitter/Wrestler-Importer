"""Independent local-animation-axis LBS probes for selected native bind branches."""
import numpy as np
import struct

from tools.prepare_model import bone_matrices, local_matrix
from tools.weight_trial_review import rotation


def deform_local(model, positions, weights, controls):
    rest=bone_matrices(model);cache={}
    def world(index):
        if index not in cache:
            bone=model['bones'][index];local=local_matrix(bone);motion=np.eye(4)
            if bone['name'] in controls:motion[:3,:3]=rotation(*controls[bone['name']])
            local=local@motion
            cache[index]=local if bone['parent']==-1 else world(bone['parent'])@local
        return cache[index]
    posed=np.array([world(i) for i in range(len(rest))]);skin=posed@np.linalg.inv(rest)
    homogeneous=np.column_stack((positions,np.ones(len(positions))));out=np.zeros_like(positions)
    for i in range(len(rest)):out+=weights[:,i,None]*(homogeneous@skin[i].T)[:,:3]
    return out


def choose_shared_neck(base,names,records,sources,selections):
    """Minimax shared pivot from measured native endpoints, never vertex offsets.

    Neck translation enters LBS affine-linearly when rotations/hierarchy stay
    fixed. Evaluate both native endpoints under both axis conventions, then
    solve a one-dimensional convex worst-record error problem. Native weights,
    coordinates, rotation records and the established .03 tolerance stay fixed.
    """
    from .core import POSES
    from tools.weight_trial_review import deform
    from scipy.optimize import minimize_scalar
    if selections['Head']==selections['Torso'] or 'kubi' not in names:return dict(applied=False)
    head=sources[selections['Head']]['model'];torso=sources[selections['Torso']]['model']
    hb=next(b for b in head['bones'] if b['name']=='kubi');tb=next(b for b in torso['bones'] if b['name']=='kubi')
    hp=np.array(hb['local_position']);tp=np.array(tb['local_position'])
    if np.max(np.abs(hp-tp))<1e-5 or np.max(np.abs(np.array(hb['rotation'])-tb['rotation']))>1e-5:return dict(applied=False)
    bones=[]
    for i,name in enumerate(names):
        raw=base['bone_raw'];a=i*80
        bones.append(dict(index=i,name=name,parent=struct.unpack_from('<i',raw,a+48)[0],
            local_position=struct.unpack_from('<3f',raw,a+16),rotation=struct.unpack_from('<3f',raw,a+32)))
    p=np.array([r[1] for r in records]);w=np.array([r[2] for r in records]);neck=names.index('kubi')
    a_errors=[];b_errors=[]
    for controls in POSES.values():
        for pose in (deform,deform_local):
            expected=np.zeros_like(p)
            for si,source in enumerate(sources):
                ids=[i for i,r in enumerate(records) if r[0]==si]
                if not ids:continue
                m=source['model'];cols=[names.index(b['name']) for b in m['bones']]
                expected[ids]=pose(dict(bones=m['bones'],bone_count=len(m['bones'])),p[ids],w[ids][:,cols],controls)
            bones[neck]['local_position']=hp
            a=pose(dict(bones=bones,bone_count=len(names)),p,w,controls)-expected
            bones[neck]['local_position']=tp
            b=pose(dict(bones=bones,bone_count=len(names)),p,w,controls)-expected
            a_errors.append(a);b_errors.append(b-a)
    a=np.concatenate(a_errors);b=np.concatenate(b_errors)
    loss=lambda alpha:float(np.linalg.norm(a+alpha*b,axis=1).max(initial=0))
    before=loss(0.)
    if before<=.03:return dict(applied=False,head_endpoint_error=before,reason='Native selected-head pivot already passes both pose conventions')
    optimum=minimize_scalar(loss,bounds=(0.,1.),method='bounded',options={'xatol':1e-10})
    alpha=min((0.,1.,float(optimum.x)),key=lambda x:(loss(x),x))
    after=loss(alpha)
    if alpha<=1e-6 or after>=before-1e-9 or after>.03:return dict(applied=False,head_endpoint_error=before,best_possible_error=after,reason='No accepted shared pivot within the unchanged pose tolerance')
    raw=bytearray(base['bone_raw']);struct.pack_into('<3f',raw,neck*80+16,*(hp+alpha*(tp-hp)));base['bone_raw']=bytes(raw)
    return dict(applied=True,head_native_position=hp.tolist(),torso_native_position=tp.tolist(),
        torso_fraction=alpha,head_endpoint_error=before,predicted_worst_pose_error=after,
        verified_tolerance=.03,method='Minimax native-endpoint neck translation; both model/local-axis poses; vertices and weights unchanged')

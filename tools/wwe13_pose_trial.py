"""Independent finger/hand stress probes for the sample trial; not game clips."""
import numpy as np

from tools.sym_rig import arrays
from tools.weight_trial_review import deform


def hand_probes(model):
    model = dict(model, bone_count=len(model['bones']))
    points, weights = arrays(model)
    # Native float32 coefficients can sum to 1 +/- a few ulps. Compare against
    # the same LBS rest replay, not raw coordinates, to isolate actual motion.
    rest = deform(model, points, weights, {})
    lookup = {b['name']: b['index'] for b in model['bones']}
    results = {}
    for side in ('l','r'):
        for digit in range(5):
            own = [lookup[f'{side}_yubi{digit}{segment}'] for segment in range(3)]
            others = [b['index'] for b in model['bones'] if b['name'].startswith(side+'_yubi') and b['index'] not in own]
            own_mask = weights[:,own].sum(1) > 1e-7
            foreign_mask = (weights[:,others].sum(1) > 1e-7) & ~own_mask
            pose = {f'{side}_yubi{digit}0': ('z', 35 if side=='l' else -35)}
            posed = deform(model, points, weights, pose)
            motion = np.linalg.norm(posed-rest, axis=1)
            own_motion = float(motion[own_mask].max(initial=0))
            foreign_motion = float(motion[foreign_mask].max(initial=0))
            if own_motion < 1e-5 or foreign_motion > 1e-7 or not np.isfinite(posed).all():
                raise ValueError(f'Independent finger motion failure: {side}/{digit}')
            results[f'{side}-digit-{digit}'] = dict(own_motion_max=own_motion, foreign_digit_motion_max=foreign_motion, pose=pose)
    poses = {
        'grip': {b['name']: ('z',-35 if b['name'].startswith('l_') else 35)
                 for b in model['bones'] if '_yubi' in b['name']},
        'finger-extension': {b['name']: ('z',35 if b['name'].startswith('l_') else -35)
                 for b in model['bones'] if '_yubi' in b['name']},
        'wrist-flex': {'l_te':('z',35),'r_te':('z',-35)},
        'forearm-twist': {'l_kote_x':('x',60),'r_kote_x':('x',-60)}}
    faces = np.array([np.asarray(tri)+offset for offset,m in _offsets(model) for mat in m['materials'] for tri in mat['triangles']])
    area = np.linalg.norm(np.cross(rest[faces[:,1]]-rest[faces[:,0]],rest[faces[:,2]]-rest[faces[:,0]]),axis=1)
    valid = area > np.ptp(points[:,1])**2*1e-12
    for name,pose in poses.items():
        q=deform(model,points,weights,pose)
        a=np.linalg.norm(np.cross(q[faces[:,1]]-q[faces[:,0]],q[faces[:,2]]-q[faces[:,0]]),axis=1)
        ratio=a[valid]/area[valid]
        collapsed=int(np.count_nonzero(ratio < 1e-6))
        if collapsed or not np.isfinite(q).all():raise ValueError('Collapsed hand/arm stress geometry: '+name)
        results[name]=dict(minimum_triangle_area_ratio=float(ratio.min()),maximum_triangle_area_ratio=float(ratio.max()),
                           new_collapsed_triangles=collapsed,maximum_motion=float(np.linalg.norm(q-rest,axis=1).max()))
    return dict(tests=results, limitation='PSP analytical LBS; cannot establish actual game grip/twist semantics')


def _offsets(model):
    offset=0
    for mesh in model['meshes']:
        yield offset,mesh
        offset+=len(mesh['vertices'])

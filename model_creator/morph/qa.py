"""Check exported morph geometry and source-authorized contact motion."""
from collections import defaultdict

import numpy as np


def validate(document,model,expected):
    from model_creator.core import dense,POSES
    from model_creator.rigging import deform_local
    from tools.weight_trial_review import deform
    p,w=dense(model);original,weights=dense(document.baseline);height=document.height
    document.check_geometry(p)
    error=float(np.linalg.norm(p-np.asarray(expected),axis=1).max())
    if error>height*2e-6:raise ValueError('Native morph differs from the preview target')
    if not np.array_equal(w,weights):raise ValueError('Morph changed effective skin weights')
    groups=defaultdict(list)
    for i,row in enumerate(original):groups[tuple(row)].append(i)
    shared=[ids for ids in groups.values() if len(ids)>1 and np.max(np.abs(w[ids]-w[ids[0]]))<1e-7]
    poses={}
    for label,fn in (('model',deform),('local',deform_local)):
        for name,controls in POSES.items():
            current=fn(dict(bones=model['bones'],bone_count=len(model['bones'])),p,w,controls)
            if not np.isfinite(current).all():raise ValueError('Nonfinite morph pose: '+name)
            gap=max((float(np.linalg.norm(current[ids]-current[ids[0]],axis=1).max()) for ids in shared),default=0.)
            if gap>height*2e-5:raise ValueError('Morph opens a verified shared contact under '+name)
            poses[label+'-'+name]=dict(finite=True,shared_contact_gap=gap)
    return dict(preview_maximum_error=error,verified_shared_contact_groups=len(shared),poses=poses,
                note='Bone bindings and weights retained. Analytical poses and mesh bounds are not game animation/culling certification.')

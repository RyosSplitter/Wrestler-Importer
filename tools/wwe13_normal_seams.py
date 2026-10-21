"""Preserve opposed authored normal corners during experimental reduction.

Two-sided garment layers must not be welded or averaged merely because their
positions and bone influences coincide. No displacement or weight edit occurs.
"""
from collections import defaultdict
import math
from tools.vertex_identity import annotate,position_key


def mark_opposed(model):
    model=annotate(model);groups=defaultdict(list)
    for mesh in model['meshes']:
        for v in mesh['vertices']:groups[position_key(v)].append(v)
    conflicts=0;marked=0
    for rows in groups.values():
        normals=[v['normal']for v in rows]
        anchor=next((x for x in normals for y in normals if sum(a*b for a,b in zip(x,y))<-.8),None)
        if anchor is None:continue
        conflicts+=1
        for v in rows:
            if not all(math.isfinite(x)for x in v['normal']):raise ValueError('Invalid source normal')
            v['normal_seam']=1 if sum(a*b for a,b in zip(v['normal'],anchor))>=0 else -1;marked+=1
    model['opposed_normal_protection']=dict(conflicting_point_groups=conflicts,marked_corners=marked,
        rule='Same-position authored normal dot < -.8; keep two normal hemispheres distinct without joining topology or influence domains')
    return model

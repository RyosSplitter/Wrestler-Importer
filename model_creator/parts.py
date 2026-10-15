"""Deterministic planar cuts and explicit attachment collars for the first pair.

Only seam vertices move. Interior vertices keep source positions, UVs and weights.
Intersections interpolate attributes; incompatible source records are never welded.
The torso supplies each shared seam's geometry and weights. A union of angular
samples splits both sides at identical positions, avoiding mismatched edge chords.
This is a prepared two-model prototype, not a universal body segmentation rule.
"""
import math
from collections import defaultdict

import numpy as np

PARTS = ('Head', 'Torso', 'Arms', 'Legs')
# Native PSP coordinates: negative Y is up. Cuts lie at neck, upper arms, waist.
JOINTS = {'neck': (1, -6.8), 'waist': (1, -1.3),
          'left_arm': (0, 3.15), 'right_arm': (0, -3.15)}
EPS = 2e-6


def mix(a, b, t):
    return {k: (1-t)*a[k]+t*b[k] for k in a}


def clip(poly, axis, limit, sign):
    result = []
    for a, b in zip(poly, poly[1:]+poly[:1]):
        da, db = sign*(a['p'][axis]-limit), sign*(b['p'][axis]-limit)
        if da >= -1e-9:
            result.append(a)
        if (da < -1e-9 and db > 1e-9) or (da > 1e-9 and db < -1e-9):
            v = mix(a, b, da/(da-db));v['p'][axis] = limit
            result.append(v)
    return result


def extract(model, part, canonical_names):
    remap = [canonical_names.index(b['name']) for b in model['bones']]
    conditions = {
        'Head': [[(1, -6.8, -1)]],
        'Torso': [[(1, -6.8, 1), (1, -1.3, -1), (0, 3.15, -1), (0, -3.15, 1)]],
        'Arms': [[(0, 3.15, 1), (1, -6.8, 1), (1, -1.3, -1)],
                 [(0, -3.15, -1), (1, -6.8, 1), (1, -1.3, -1)]],
        'Legs': [[(1, -1.3, 1)]],
    }[part]
    records = []
    for mesh in model['meshes']:
        vertices = []
        for v in mesh['vertices']:
            w = np.zeros(len(canonical_names))
            for bone, weight in zip(mesh['bone_palette'], v['weights']):
                w[remap[bone]] = weight
            vertices.append(dict(p=np.array(v['position'], float), n=np.array(v['normal'], float),
                                 uv=np.array(v['uv'], float), c=np.array(v['color'], float), w=w,
                                 tag=np.array([len(vertices), len(vertices)**2], float)))
        for mi, mat in enumerate(mesh['materials']):
            texture=model['texture_names'][mat['texture_id']].casefold()
            decoration='blood' in texture or 'hair' in texture
            if decoration:
                used=sorted(set(i for t in mat['triangles'] for i in t))
                center=np.mean([vertices[i]['p'] for i in used],axis=0)
                owner='Head' if 'hair' in texture or center[1]<JOINTS['neck'][1] else 'Torso'
                if owner!=part:continue
            for ti, tri in enumerate(mat['triangles']):
                for planes in ([[]] if decoration else conditions):
                    poly = [vertices[i] for i in tri]
                    for axis, limit, sign in planes:
                        poly = clip(poly, axis, limit, sign)
                        if len(poly) < 3:break
                    if len(poly) >= 3:
                        records.append(dict(mesh=mesh['index'], material=mi, triangle=ti,
                                            poly=poly, part=part, overlay=decoration))
    return records


def edges(records, joint, ordinary_only=False):
    axis, limit = JOINTS[joint]
    result = []
    for row in records:
        if row['overlay']:continue
        poly = row['poly']
        for a, b in zip(poly, poly[1:]+poly[:1]):
            if abs(a['p'][axis]-limit)<EPS and abs(b['p'][axis]-limit)<EPS and np.linalg.norm(a['p']-b['p'])>EPS:
                result.append((a, b))
    return result


def angular(v, axis, center):
    p = np.delete(v['p'], axis)-center
    return math.atan2(p[1], p[0]) % (2*math.pi)


def angle_delta(a, b):
    return (b-a+math.pi) % (2*math.pi)-math.pi


def seam_reference(records, joint):
    edge = edges(records, joint, True)
    if not edge:raise ValueError('Missing ordinary attachment contour: '+joint)
    axis, limit = JOINTS[joint]
    points = np.unique(np.round([v['p'] for e in edge for v in e], 6), axis=0)
    center = np.delete(points, axis, axis=1).mean(0)
    def sample(angle):
        direction = np.array([math.cos(angle), math.sin(angle)])
        options = []
        for a, b in edge:
            p = np.delete(a['p'], axis)-center
            d = np.delete(b['p']-a['p'], axis)
            matrix = np.column_stack((direction, -d))
            if abs(np.linalg.det(matrix)) < 1e-10:continue
            radius, t = np.linalg.solve(matrix, p)
            if radius>0 and -EPS<=t<=1+EPS:
                options.append((radius, a, b, float(np.clip(t, 0, 1))))
        if not options:raise ValueError('Attachment contour is not star shaped: '+joint)
        _, a, b, t = max(options, key=lambda o:o[0])
        return mix(a, b, t)
    return axis, limit, center, sample


def stitch(selected, torso_reference, joints=None):
    changes = []
    for joint in (JOINTS if joints is None else joints):
        axis, limit, center, sample = seam_reference(torso_reference, joint)
        touching = [('Torso', selected['Torso']),
                    ('Head' if joint=='neck' else 'Legs' if joint=='waist' else 'Arms',
                     selected['Head' if joint=='neck' else 'Legs' if joint=='waist' else 'Arms'])]
        angles = sorted(set(round(angular(v, axis, center), 9) for _, rows in touching for a,b in edges(rows, joint) for v in (a,b)))
        before, after, max_displacement = [], [], 0.
        internal_records=0
        for part, rows in touching:
            for row in rows:
                if row['overlay']:continue
                original = row['poly'];poly = []
                for a, b in zip(original, original[1:]+original[:1]):
                    at = abs(a['p'][axis]-limit)<EPS
                    bt = abs(b['p'][axis]-limit)<EPS
                    new_vertices = [a]
                    outer=lambda v:np.linalg.norm(v['p']-sample(angular(v,axis,center))['p'])<.45
                    if at and bt and outer(a) and outer(b) and np.linalg.norm(a['p']-b['p'])>EPS:
                        aa, ab = angular(a, axis, center), angular(b, axis, center)
                        delta = angle_delta(aa, ab)
                        if abs(delta)>1e-8:
                            inserts = []
                            for angle in angles:
                                f = angle_delta(aa, angle)/delta
                                if 2e-6<f<1-2e-6:
                                    # Intersect ray with the original straight edge for UV interpolation.
                                    d = np.delete(b['p']-a['p'], axis)
                                    ray = np.array([math.cos(angle), math.sin(angle)])
                                    mat = np.column_stack((ray, -d))
                                    if abs(np.linalg.det(mat))<1e-10:continue
                                    _, t = np.linalg.solve(mat, np.delete(a['p'], axis)-center)
                                    if EPS<t<1-EPS:inserts.append((float(t), angle))
                            new_vertices += [mix(a, b, t) for t,_ in sorted(inserts)]
                    for vertex in new_vertices:
                        v = {k:x.copy() for k,x in vertex.items()}
                        if abs(v['p'][axis]-limit)<EPS:
                            target = sample(angular(v, axis, center))
                            distance = float(np.linalg.norm(v['p']-target['p']))
                            if distance<.45:
                                max_displacement = max(max_displacement, distance)
                                before.append(v['p'].tolist());v['p']=target['p'];v['w']=target['w']
                                after.append(v['p'].tolist())
                            else:internal_records+=1
                        if not poly or np.linalg.norm(poly[-1]['p']-v['p'])>1e-8:poly.append(v)
                if len(poly)>1 and np.linalg.norm(poly[0]['p']-poly[-1]['p'])<1e-8:poly.pop()
                row['poly']=poly
        changes.append(dict(joint=joint, angular_samples=len(angles), changed_seam_records=len(after),
                            maximum_displacement=max_displacement, unstitched_internal_records=internal_records,
                            before=before, after=after))
    return changes


def triangles(poly):
    # A cut triangle has one boundary chain in the attachment plane. Fan from
    # an off-plane source/intersection vertex, preserving every seam edge split.
    # Fan triangles retain the original polygon order and therefore winding.
    anchor=next((i for i,v in enumerate(poly) if all(abs(v['p'][axis]-limit)>EPS for axis,limit in JOINTS.values())),0)
    order=list(range(anchor,len(poly)))+list(range(anchor))
    result=[]
    for j in range(1,len(order)-1):
        a,b,c=order[0],order[j],order[j+1]
        if np.linalg.norm(np.cross(poly[b]['p']-poly[a]['p'],poly[c]['p']-poly[a]['p']))>1e-10:
            result.append((a,b,c))
    return result

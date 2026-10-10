"""Procedural geometry only: no wrestler meshes or extracted game assets."""
import math
import struct


def model():
    names = [('koshi', -1), ('atama', 0), ('l_sakotsu', 0), ('l_momo', 0),
             ('l_eye', 1), ('r_eye', 1), ('l_mabuta', 1), ('r_mabuta', 1), ('d_kuchi', 1)]
    bones = [dict(index=i, name=n, parent=p, local_position=[0, 0, 0], rotation=[0, 0, 0])
             for i, (n, p) in enumerate(names)]
    meshes = []
    for bone, cx in ((0, 0), (1, 4), (2, 8), (3, 12), (4, 16)):
        vertices = []
        # Periodic torus avoids degenerate pole triangles and has real curvature.
        for j in range(12):
            for k in range(24):
                u, v = 2 * math.pi * k / 24, 2 * math.pi * j / 12
                pos = [cx + (1 + .35 * math.cos(v)) * math.cos(u),
                       (1 + .35 * math.cos(v)) * math.sin(u), .35 * math.sin(v)]
                pos = list(struct.unpack('<3f', struct.pack('<3f', *pos)))
                w = [0.] * len(bones); w[bone] = 1.
                vertices.append(dict(position=pos, normal=[math.cos(v)*math.cos(u),
                    math.cos(v)*math.sin(u), math.sin(v)], uv=[k/24, j/12],
                    color=[180, 120, 80, 255], weights=w))
        faces = []
        for j in range(12):
            for k in range(24):
                a, b = j*24+k, j*24+(k+1)%24
                c, d = ((j+1)%12)*24+k, ((j+1)%12)*24+(k+1)%24
                faces.extend([[a, b, d], [a, d, c]])
        meshes.append(dict(index=len(meshes), bone_palette=list(range(len(bones))),
            vertices=vertices, materials=[dict(texture_id=len(meshes), triangles=faces)]))
    return dict(bones=bones, bone_count=len(bones), textures=['synthetic_%d'%i for i in range(5)],
        meshes=meshes, triangle_count=2880, vertex_count=1440, cutout_texture_ids=[4])


PROFILE = dict(ratios=dict(Head=.8, Torso=.65, Arms=.5, Legs=.5))

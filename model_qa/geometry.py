"""PAC/JSON adapters, uniform alignment and topology-independent measurements."""
from collections import Counter
from dataclasses import dataclass
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import trimesh

from tools.hctp_weights import load_hctp_with_weights
from tools.prepare_model import LANDMARKS, bone_matrices, similarity_fit
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.weight_trial_review import deform, map_source, rotation as axis_rotation


# Proper rotation: x is the wrestler's left, y is up, z is forward.
AXES = np.diag([1., -1., -1.])


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_model(path, source=False):
    path = Path(path)
    if path.suffix.lower() == '.json':
        model = json.loads(path.read_text(encoding='utf-8'))
    elif source:
        model = load_hctp_with_weights(path)
    else:
        raw = path.read_bytes()
        if raw[:4] == b'PAC ':
            candidates = [r for s, r in sections(raw) if s['id'] == 2 and r[:4] == b'YOBJ']
            if len(candidates) != 1:
                raise ValueError('Expected exactly one main PSP YOBJ section')
            raw = candidates[0]
        model = audit_yobj(raw)
    return model


def align_reference(source, target):
    sm, tm = bone_matrices(source), bone_matrices(target)
    sb = {b['name']: b['index'] for b in source['bones']}
    tb = {b['name']: b['index'] for b in target['bones']}
    names = [n for n in LANDMARKS if n in sb and n in tb]
    if len(names) < 6:
        raise ValueError('At least six verified shared bone landmarks are required')
    x = np.array([sm[sb[n]][:3, 3] for n in names])
    y = np.array([tm[tb[n]][:3, 3] for n in names])
    scale, rotation, translation = similarity_fit(x, y)
    if abs(np.linalg.det(rotation) - 1.) > 1e-6:
        raise ValueError('Alignment must be a proper rotation')
    result = copy.deepcopy(source)
    for m in result['meshes']:
        for v in m['vertices']:
            v['position'] = (scale * rotation @ v['position'] + translation).tolist()
            v['normal'] = (rotation @ v['normal']).tolist()
    report = dict(method='Named rest-bone landmarks; one uniform similarity transform',
                  scale=scale, rotation=rotation.tolist(), translation=translation.tolist(),
                  landmarks=names, landmark_errors=np.linalg.norm(scale*x@rotation.T+translation-y, axis=1).tolist(),
                  nonuniform_scaling=False, pose='decoded bind/rest pose',
                  geometry_correspondence='Not assumed; surfaces are queried independently')
    return result, report


@dataclass
class Geometry:
    vertices: np.ndarray
    faces: np.ndarray
    weights: np.ndarray
    bone_names: list
    face_textures: list
    vertex_records: list
    model: dict

    @property
    def mesh(self):
        return trimesh.Trimesh(self.vertices, self.faces, process=False)

    @property
    def height(self):
        return float(np.ptp(self.vertices[:, 1]))


def geometry(model, skeleton=None):
    skeleton = skeleton or model
    count = len(model['bones'])
    vertices, weights, faces, records, textures = [], [], [], [], []
    names = model.get('texture_names', model.get('textures'))
    for m in model['meshes']:
        offset = len(vertices)
        for vi, v in enumerate(m['vertices']):
            vertices.append(v['position']); records.append([m['index'], vi])
            w = np.zeros(count)
            w[m['bone_palette']] = v['weights']
            weights.append(w)
        for a in m['materials']:
            for t in a['triangles']:
                faces.append([i+offset for i in t]); textures.append(names[a['texture_id']])
    vertices = np.asarray(vertices, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if not np.isfinite(vertices).all() or not np.isfinite(weights).all() or (weights < -1e-7).any():
        raise ValueError('Invalid position or weight data')
    sums = weights.sum(1)
    if (np.abs(sums-1.) > 2e-4).any():
        raise ValueError('Weights are not normalized')
    weights /= sums[:, None]
    if skeleton is not model:
        weights, missing, _ = map_source(dict(model,bone_count=count), dict(skeleton,bone_count=len(skeleton['bones'])), weights, True)
        if missing.max() > 1e-7:
            raise ValueError('Original reference weights have no PSP ancestor mapping')
    faces = np.asarray(faces, dtype=np.int64)
    if not len(faces) or faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError('Invalid/empty triangle indices')
    return Geometry(vertices@AXES, faces, weights, [b['name'] for b in skeleton['bones']], textures, records, skeleton)


def posed(g, controls):
    model = dict(bones=g.model['bones'], bone_count=len(g.model['bones']))
    native = g.vertices@AXES
    positions = deform(model, native, g.weights, controls)@AXES
    if not np.isfinite(positions).all():
        raise ValueError('Nonfinite posed geometry')
    return Geometry(positions, g.faces, g.weights, g.bone_names, g.face_textures, g.vertex_records, g.model)


def posed_original(original, alignment, controls):
    """Pose the original HCTP rig, then apply the one fixed uniform alignment."""
    g = geometry(original);rest=bone_matrices(original);cache={}
    rotation=np.asarray(alignment['rotation'])
    def world(i):
        if i not in cache:
            bone=original['bones'][i];parent=bone['parent']
            local=rest[i] if parent==-1 else np.linalg.inv(rest[parent])@rest[i]
            motion=np.eye(4)
            if bone['name'] in controls:
                axis,angle=controls[bone['name']]
                normalized_motion=rotation.T@axis_rotation(axis,angle)@rotation
                basis=rest[i][:3,:3];motion[:3,:3]=basis.T@normalized_motion@basis
            cache[i]=local@motion if parent==-1 else world(parent)@local@motion
        return cache[i]
    matrices=np.array([world(i) for i in range(len(rest))])@np.linalg.inv(rest)
    homogeneous=np.column_stack((g.vertices@AXES,np.ones(len(g.vertices))))
    native=sum(g.weights[:,i,None]*(homogeneous@matrix.T)[:,:3] for i,matrix in enumerate(matrices))
    native=alignment['scale']*native@rotation.T+alignment['translation']
    g.vertices = native@AXES
    return g


def seam_motion(bind, current, height):
    _, groups=np.unique(np.round(bind.vertices/height,7),axis=0,return_inverse=True)
    gaps=[]
    for group in np.unique(groups):
        rows=np.flatnonzero(groups==group)
        if len(rows)>1:gaps.append(float(np.max(np.linalg.norm(current.vertices[rows]-current.vertices[rows[0]],axis=1))))
    return dict(coincident_rest_groups=len(gaps),maximum_gap=max(gaps,default=0.),
                groups_over_0_02_percent_height=sum(v>height*.0002 for v in gaps),
                caveat='Coincident records may include intentional mouth/eyelid contacts; review rather than automatically weld')


class Surface:
    def __init__(self, g, height):
        self.g = g
        self.mesh = g.mesh
        self.valid_ids = np.flatnonzero(self.mesh.area_faces > height**2*1e-12)
        if not len(self.valid_ids):
            raise ValueError('No nondegenerate surface')
        self.surface = trimesh.Trimesh(g.vertices, g.faces[self.valid_ids], process=False)

    def nearest(self, points, chunk=2048):
        results = [trimesh.proximity.closest_point(self.surface, points[i:i+chunk]) for i in range(0, len(points), chunk)]
        return (np.concatenate([r[0] for r in results]), np.concatenate([r[1] for r in results]),
                self.valid_ids[np.concatenate([r[2] for r in results])])

    def sample(self, count=18000, seed=2718):
        # Area-weighted deterministic surface samples, not vertex correspondences.
        rng = np.random.default_rng(seed)
        area = self.surface.area_faces
        chosen = rng.choice(len(area), size=count, p=area/area.sum())
        a, b = np.sqrt(rng.random(count)), rng.random(count)
        bary = np.column_stack((1-a, a*(1-b), a*b))
        points = np.einsum('ni,nij->nj', bary, self.surface.triangles[chosen])
        return points, self.valid_ids[chosen], bary


def distribution(values, height=1.):
    values = np.asarray(values)
    if not len(values):
        return None
    return dict(samples=len(values), mean=float(values.mean()), rms=float(np.sqrt(np.mean(values**2))),
                p50=float(np.percentile(values, 50)), p95=float(np.percentile(values, 95)),
                p99=float(np.percentile(values, 99)), maximum=float(values.max()),
                p95_height=float(np.percentile(values, 95)/height), p99_height=float(np.percentile(values, 99)/height))


def topology(g, height):
    # Weld only the diagnostic graph. Native UV/normal/palette splits are never edited.
    _, inverse = np.unique(np.round(g.vertices/height, 7), axis=0, return_inverse=True)
    welded = inverse[g.faces]
    faces = g.faces
    area = g.mesh.area_faces
    degenerate = area <= height**2*1e-12
    ordered = np.sort(welded[~degenerate], axis=1)
    edges = np.sort(np.concatenate([ordered[:, [0, 1]], ordered[:, [1, 2]], ordered[:, [0, 2]]]), axis=1)
    unique, edge_counts = np.unique(edges, axis=0, return_counts=True)
    boundary = unique[edge_counts == 1]
    graph = coo_matrix((np.ones(len(unique)), (unique[:, 0], unique[:, 1])), shape=(inverse.max()+1,)*2)
    _, labels = connected_components(graph, directed=False)
    used = np.unique(welded[~degenerate])
    components = Counter(labels[used].tolist())
    return dict(vertex_records=len(g.vertices), triangles=len(faces), geometric_vertices=int(inverse.max()+1),
                degenerate_triangles=int(degenerate.sum()), duplicate_geometric_faces=len(ordered)-len(np.unique(ordered, axis=0)),
                boundary_edges=len(boundary), nonmanifold_edges=int(np.sum(edge_counts > 2)),
                geometric_components=len(components), component_vertex_sizes=sorted(components.values(), reverse=True),
                watertight=g.mesh.is_watertight, closed_volume=float(abs(g.mesh.volume)) if g.mesh.is_watertight else None,
                normalization_note='Diagnostic rounding is 1e-7 of reference height; native meshes remain separate',
                caveat='Hair, teeth, eyes, garments and UV/palette splits may legitimately be disconnected/open')


def curvature(g, points, height):
    # Integrated mean curvature on position-welded topology, normalized by radius.
    m = g.mesh.copy()
    m.merge_vertices(digits_vertex=6)
    m.update_faces(m.nondegenerate_faces(height=height*1e-7))
    radius = height*.012
    values = trimesh.curvature.discrete_mean_curvature_measure(m, points, radius)/radius
    return values

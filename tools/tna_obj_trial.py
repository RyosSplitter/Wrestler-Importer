"""Isolated AJ Styles TNA OBJ feasibility trial, never registered in the app.

The OBJ has no rig. All transferred weights and facial binds are newly inferred
PSP binding, not recovered TNA data. Input roles below are sample-scoped and
must not silently be applied to another OBJ.
"""
import argparse
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from desktop.core import base_model, validate_pac
from desktop.native import serialize
from desktop.precision import bounded_precision, validate_native_precision
from desktop.skinning import adapt_yobj
from tools.jericho_hybrid_trial import pack
from tools.prepare_model import bone_matrices
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.pac_inspect import inspect_pac
from tools.sym_rig import arrays
from tools.sym_trial import pose_qa
from tools.weight_trial_review import descendant_names, transfer
from tools.wwe13_adapter_trial import chart_atlas
from tools.wwe13_texture_trial import allocate
from desktop.texture_optimizer.candidates import read_gim

SOURCE_SHA = '6bec7e19d8b06b67be9fa0c91eb9dfb3d7c2f747c14abe5d0a17658daf4f58af'
# Original OBJ position-connected components, inspected with the supplied atlas.
EYE_COMPONENTS = {'l': 149, 'r': 169}
TEETH_COMPONENTS = {0: 'atama', 13: 'd_kuchi'}
AXES = np.diag([1., -1., -1.])


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def read_obj(text):
    """Retain independent OBJ position/UV/normal corner identities and topology."""
    positions, uvs, normals, triangles, materials = [], [], [], [], set()
    def index(token, values):
        n = int(token)
        if n == 0:
            raise ValueError('OBJ indices are one-based')
        n = n - 1 if n > 0 else len(values) + n
        if not 0 <= n < len(values):
            raise ValueError('OBJ index outside its attribute buffer')
        return n
    for line in text.splitlines():
        q = line.split('#', 1)[0].split()
        if not q:
            continue
        kind, values = q[0], q[1:]
        if kind in ('v', 'vt', 'vn'):
            count = 2 if kind == 'vt' else 3
            if len(values) != count:
                raise ValueError('Unsupported OBJ attribute width')
            v = list(map(float, values))
            if not np.isfinite(v).all():
                raise ValueError('Nonfinite OBJ attribute')
            {'v': positions, 'vt': uvs, 'vn': normals}[kind].append(v)
        elif kind == 'usemtl':
            materials.add(' '.join(values))
        elif kind == 'f':
            if len(values) != 3:
                raise ValueError('Trial requires triangulated OBJ')
            face = []
            for token in values:
                fields = token.split('/')
                if len(fields) != 3 or not all(fields):
                    raise ValueError('Explicit OBJ UVs and normals required')
                face.append(tuple(index(t, a) for t, a in zip(fields, (positions, uvs, normals))))
            triangles.append(face)
        elif kind not in ('mtllib', 'o', 'g', 's'):
            raise ValueError('Unsupported OBJ record: ' + kind)
    if not triangles or len(materials) != 1:
        raise ValueError('Trial requires one explicit source material')
    parent = list(range(len(positions)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for tri in triangles:
        for key in tri[1:]:
            a, b = root(tri[0][0]), root(key[0]); parent[max(a,b)] = min(a,b)
    vertices, lookup, faces = [], {}, []
    for tri in triangles:
        face = []
        for key in tri:
            if key not in lookup:
                p, uv, n = key; normal = np.array(normals[n])
                if np.linalg.norm(normal) < 1e-10:
                    raise ValueError('Unusable OBJ normal')
                lookup[key] = len(vertices)
                vertices.append(dict(position=positions[p], normal=(normal/np.linalg.norm(normal)).tolist(),
                    uv=[uvs[uv][0], 1-uvs[uv][1]], color=[255]*4, source_position_index=p,
                    source_corner_indices=list(key), source_component=root(p)))
            face.append(lookup[key])
        faces.append(face)
    ps = np.array([v['position'] for v in vertices]); fs = np.array(faces)
    cross = np.cross(ps[fs[:,1]]-ps[fs[:,0]], ps[fs[:,2]]-ps[fs[:,0]])
    if np.any(np.linalg.norm(cross, axis=1) < 1e-10):
        raise ValueError('Degenerate source triangle')
    model = dict(textures=['aj_diffuse'], texture_names=['aj_diffuse'], texture_count=1,
        vertices_present=True, meshes=[dict(index=0, vertices=vertices,
        materials=[dict(texture_id=0, triangles=faces)])], mesh_count=1,
        vertex_count=len(vertices), triangle_count=len(faces))
    return model, dict(position_records=len(positions), uv_records=len(uvs), normal_records=len(normals),
        corner_records=len(vertices), triangles=len(faces), connected_components=len({root(i) for i in range(len(positions))}),
        material=next(iter(materials)), source_rig_present=False, uv_policy='OBJ bottom origin to PSP top origin; one explicit V flip')


def fit_sphere(points):
    points = np.asarray(points, float)
    a = np.column_stack((2*points, np.ones(len(points))))
    if np.linalg.matrix_rank(a) < 4:
        raise ValueError('Underdetermined source eye sphere')
    fit = np.linalg.lstsq(a, (points**2).sum(1), rcond=None)[0]
    center = fit[:3]; radius2 = fit[3]+center@center
    if radius2 <= 0:
        raise ValueError('Invalid fitted eye radius')
    radius = np.sqrt(radius2)
    residual = np.abs(np.linalg.norm(points-center, axis=1)-radius)
    if residual.max() > .03*radius:
        raise ValueError('Source component not sufficiently spherical')
    return center, float(radius), float(residual.max())


def fit_facial_binds(target, centers):
    """Fit facial-controller positions only; no source geometry deformation.

    A two-eye, axis-preserving uniform fit preserves native local axes. The
    source/body/head anchors stay at their ordinary native locations. This is
    a newly inferred rig, not a claim to reproduce source TNA animation.
    """
    result = copy.deepcopy(target)
    names = {b['name']: b['index'] for b in target['bones']}
    rest = bone_matrices(target)
    original = np.array([rest[names[s+'_eye'], :3, 3] for s in ('l','r')])
    source = np.array([centers[s] for s in ('l','r')])
    scale = float((source[0,0]-source[1,0])/(original[0,0]-original[1,0]))
    if not .8 < scale < 1.2:
        raise ValueError('Facial eye-spacing fit outside reviewed range')
    translation = source.mean(0)-scale*original.mean(0)
    if np.linalg.norm(source-(scale*original+translation),axis=1).max() > .01:
        raise ValueError('Source eyes need an unreviewed facial rotation/asymmetric fit')
    facial = descendant_names(target, 'atama') - {'atama'}
    desired = rest.copy()
    for b in target['bones']:
        if b['name'] in facial:
            desired[b['index'],:3,3] = scale*rest[b['index'],:3,3]+translation
    raw = bytearray(result['bone_raw']); changes = []
    for b in result['bones']:
        if b['name'] not in facial:
            continue
        i, parent = b['index'], b['parent']
        local = np.linalg.inv(desired[parent])@desired[i] if parent >= 0 else desired[i]
        if np.max(np.abs(local[:3,:3]-(np.linalg.inv(rest[parent])@rest[i])[:3,:3])) > 1e-7:
            raise ValueError('Facial fit changed local rotation axes')
        pos = np.asarray(local[:3,3], np.float32)
        struct.pack_into('<3f', raw, 80*i+16, *pos)
        changes.append(dict(bone=b['name'], before=list(b['local_position']), after=pos.tolist()))
        b['local_position'] = pos.tolist()
    result['bone_raw'] = bytes(raw)
    return result, dict(scale=scale, translation=translation.tolist(), changed_local_positions=changes,
        rotations_hierarchy_body_binds_unchanged=True, geometry_changed=False,
        claim='INFERRED new facial rig from source eyeball spheres; source rig unavailable')


def prepare(model, target):
    result = copy.deepcopy(model)
    source = np.array([v['position'] for v in result['meshes'][0]['vertices']])
    ordinary = np.array([m['vertices'][i]['position'] for m in target['meshes']
        for i in {i for a in m['materials'] if a.get('control') not in (0x115,0x117) for t in a['triangles'] for i in t}])
    scale = float(np.ptp(ordinary[:,1])/np.ptp(source[:,1]))
    translation = np.array([-scale*(source[:,0].min()+source[:,0].max())*.5,
        ordinary[:,1].max()+scale*source[:,1].min(), 0.])
    points = np.asarray(source@AXES*scale+translation, np.float32).astype(float)
    vertices = result['meshes'][0]['vertices']; centers, spheres = {}, {}
    for side, component in EYE_COMPONENTS.items():
        ids = [i for i,v in enumerate(vertices) if v['source_component']==component]
        p = np.unique(points[ids],axis=0); center, radius, error = fit_sphere(p)
        centers[side] = center
        spheres[side] = dict(component=component, position_records=len(p), center=center.tolist(), radius=radius, maximum_radial_fit_error=error)
    fitted, facial = fit_facial_binds(target, centers)
    inverse = (points-np.array(facial['translation']))/facial['scale']
    names = {b['name']:b['index'] for b in target['bones']}; binds = bone_matrices(target)
    top, bottom = binds[names['atama'],1,3], binds[names['kubi'],1,3]
    fraction = np.clip((bottom-points[:,1])/(bottom-top),0,1)
    query = points + fraction[:,None]*(inverse-points)
    weights, donor_report = transfer(target, query)
    old_weights, original_report = transfer(target, points)
    changed_eye = []
    for side, component in EYE_COMPONENTS.items():
        eye = names[side+'_eye']; supported = np.array([v['source_component']==component for v in vertices])
        leaked = (~supported)&(weights[:,eye]>0)
        weights[leaked,names['atama']] += weights[leaked,eye]; weights[leaked,eye]=0
        weights[supported] = 0; weights[supported,eye]=1
        changed_eye.append(dict(eye=side, source_component=component, eye_corner_records=int(supported.sum()), non_eye_spill_removed=int(leaked.sum())))
    for component, anchor in TEETH_COMPONENTS.items():
        selected = np.array([v['source_component']==component for v in vertices])
        weights[selected] = 0; weights[selected,names[anchor]]=1
    weights /= weights.sum(1)[:,None]
    for v, point, w in zip(vertices, points, weights):
        v['position'] = point.tolist(); v['normal'] = (np.array(v['normal'])@AXES).tolist(); v['weights'] = w.tolist()
    result['meshes'][0]['bone_palette'] = list(range(fitted['bone_count']))
    result.update(bones=copy.deepcopy(fitted['bones']), bone_count=fitted['bone_count'], model_name=fitted['model_name'],
        uv_v_flipped=False, weight_encoding='float', preparation_report=dict(
        uniform_alignment=dict(scale=scale, translation=translation.tolist(), rotation=AXES.tolist(),
            method='Uniform ordinary-donor height and foot plane/X center; not a bone-landmark registration'),
        facial_binding=facial, eye_spheres=spheres, ocular_roles=changed_eye,
        source_teeth_role_hypothesis=TEETH_COMPONENTS, donor_transfer=donor_report,
        original_donor_transfer=original_report, original_source_weights_available=False,
        newly_bound_record_count=int(np.count_nonzero(np.max(np.abs(weights-old_weights),axis=1)>1e-7)),
        limitation='New PSP weights inferred from geometry; original TNA skinning/animations cannot be compared'))
    return result, fitted


def pad_short_prepared(model):
    out = copy.deepcopy(model)
    for mesh in out['meshes']:
        while len(mesh['bone_palette']) < 3:
            extras = [out['bones'][b]['parent'] for b in mesh['bone_palette']]
            extras += list(range(out['bone_count']))
            new = next(b for b in extras if b>=0 and b not in mesh['bone_palette'])
            mesh['bone_palette'].append(new)
            for v in mesh['vertices']:
                v['weights'].append(0.)
    return out


def quantize_binding(model, units=1024):
    """Bound the precision of NEW inferred weights, never source skin records."""
    from model_qa.geometry import geometry, posed
    from model_qa.pipeline import POSES
    from model_qa.head import controller_probes
    from model_qa.ocular import skin
    if units not in (256,512,1024,4096):
        raise ValueError('Unreviewed new-binding precision')
    out = copy.deepcopy(model); maximum = 0.
    for mesh in out['meshes']:
        for v in mesh['vertices']:
            w = np.array(v['weights']); exact = w/w.sum()*units
            count = np.floor(exact).astype(int)
            order = np.argsort(-(exact-count),kind='stable')
            count[order[:units-int(count.sum())]] += 1
            new = count/units
            maximum = max(maximum,float(np.max(np.abs(new-w))))
            v['weights'] = new.tolist()
    before, after = geometry(model), geometry(out)
    errors = {}
    for name, pose in POSES.items():
        a,b = posed(before,pose), posed(after,pose)
        errors[name] = float(np.linalg.norm(a.vertices-b.vertices,axis=1).max()/before.height)
    for name, probe in controller_probes(model).items():
        a,_ = skin(before,probe);b,_ = skin(after,probe)
        errors['controller-'+name] = float(np.linalg.norm(a.vertices-b.vertices,axis=1).max()/before.height)
    if max(errors.values()) > .00025:
        raise ValueError('Inferred weight precision exceeds .025% height pose bound')
    return out, dict(units=units,maximum_coefficient_delta=maximum,normalized_exactly=True,
        maximum_pose_position_error_height=max(errors.values()),poses=errors,
        position_error_height_limit=.00025,source_skinning_records_changed=False,
        caveat='No original OBJ weights exist; this quantizes the newly synthesized PSP binding only')


def enclose_influences(target, model):
    """Conservative expansion of inferred model-space influence spheres."""
    result=copy.deepcopy(target);raw=bytearray(result['bone_raw']);p,w=arrays(model);changes=[]
    for i,b in enumerate(result['bones']):
        center_radius=struct.unpack_from('<4f',raw,80*i+64)
        active=p[w[:,i]>1e-7]
        maximum=float(np.linalg.norm(active-np.array(center_radius[:3]),axis=1).max()) if len(active) else 0.
        if maximum>center_radius[3]:
            radius=float(np.float32(maximum+.001))
            struct.pack_into('<f',raw,80*i+76,radius)
            changes.append(dict(bone=b['name'],before=center_radius[3],after=radius,
                maximum_influence_distance=maximum))
    result['bone_raw']=bytes(raw)
    return result,changes


def check_bone_changes(original, candidate, report):
    """Explicit experimental exception; production skeleton guard stays intact."""
    old = original['bone_raw']; allowed = bytearray(old)
    names = {b['name']:b['index'] for b in original['bones']}
    facial = descendant_names(original,'atama')-{'atama'}
    rows = report['changed_local_positions']
    if len({r['bone'] for r in rows})!=len(rows) or {r['bone'] for r in rows}!=facial:
        raise ValueError('Facial bind manifest incomplete/duplicated')
    for row in rows:
        struct.pack_into('<3f',allowed,80*names[row['bone']]+16,*row['after'])
    radii=report.get('expanded_influence_radii',[])
    if len({r['bone'] for r in radii})!=len(radii):
        raise ValueError('Duplicate influence radius manifest')
    for row in radii:
        i=names[row['bone']];old_radius=struct.unpack_from('<f',old,80*i+76)[0]
        if row['after']<old_radius or row['after']<row['maximum_influence_distance']:
            raise ValueError('Influence bounds must not shrink or exclude the mesh')
        struct.pack_into('<f',allowed,80*i+76,row['after'])
    if bytes(allowed) != candidate['bone_raw']:
        raise ValueError('Unapproved skeleton/bounds/rotation edit')


def validate_trial_pac(pac, base, facial):
    native,gims = validate_pac(pac,None,148000,accessory_models={},gim_reader=read_gim)
    before,after = inspect_pac(base),inspect_pac(pac)
    if [s['id'] for s in before['sections']] != [s['id'] for s in after['sections']]:
        raise ValueError('Base PAC section order/set changed')
    for a,b in zip(before['sections'],after['sections']):
        if a['id'] not in (2,9) and base[a['offset']:a['offset']+a['size']] != pac[b['offset']:b['offset']+b['size']]:
            raise ValueError('Unrelated PAC data changed')
    original = audit_yobj(next(r for s,r in sections(base) if s['id']==2))
    check_bone_changes(original,native,facial)
    from tools.sym_rig import bounds_probe
    raw=next(r for s,r in sections(pac) if s['id']==2)
    bounds=bounds_probe(raw,dict(native,bone_count=len(native['bones'])))
    if bounds['enclosing_active_bones']!=bounds['active_bones']:
        raise ValueError('Candidate influence sphere fails enclosure check')
    return native,gims


def build(source, mtl, texture, base_path, output, *, chart_cell=0, weight_units=1024, position_divisions=65536):
    source, mtl, texture, base_path, output = map(Path,(source,mtl,texture,base_path,output))
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA:
        raise ValueError('Anatomical roles have only been inspected on supplied AJ OBJ')
    if mtl.read_text().split() != ['newmtl','AJ_STYLESD','Kd','1','1','1','map_Kd','AJ_STYLESD.png']:
        raise ValueError('Unreviewed source material')
    image = np.array(Image.open(texture).convert('RGBA'))
    if image.shape != (512,512,4) or np.any(image[:,:,3]!=255):
        raise ValueError('Unreviewed atlas layout/alpha')
    output.mkdir(parents=True,exist_ok=False)
    model, source_report = read_obj(data.decode('utf-8'))
    base, target = base_model(base_path); prepared, fitted = prepare(model,target)
    quantized, weights = quantize_binding(prepared,weight_units)
    fitted,radii=enclose_influences(fitted,quantized)
    prepared['preparation_report']['facial_binding']['expanded_influence_radii']=radii
    dump(output/'source-report.json',source_report); dump(output/'binding-report.json',prepared['preparation_report'])
    dump(output/'prepared.json',prepared)
    dump(output/'weight-precision.json',weights)
    images = [image]; charted = quantized
    if chart_cell:
        charted, images, charts = chart_atlas(quantized,images,cell=chart_cell)
        charted['textures'] = [f'aj_page_{i:02d}' for i in range(len(images))]
        for row,name in zip(charts['charts'],charted['textures']):row['name']=name
        charted['texture_names'] = charted['textures']; dump(output/'atlas-report.json',charts)
    dump(output/'reference.json',charted)
    (output/'source-images').mkdir()
    for name, im in zip(charted['textures'],images):
        Image.fromarray(im).save(output/'source-images'/(name+'.png'))
    packed = pad_short_prepared(pack(charted,fitted)); contracts = [dict(bits=8,cutout=False) for _ in images]
    before = serialize(packed,fitted,contracts); before,_ = adapt_yobj(before)
    precise, precision = bounded_precision(packed,set(),divisions=position_divisions)
    raw = serialize(precise,fitted,contracts); raw, padding = adapt_yobj(raw)
    native = audit_yobj(raw)
    replay = validate_native_precision(audit_yobj(before),native,set())
    checks = pose_qa(precise,native,target)
    dump(output/'native-checks.json',dict(precision=precision, precision_replay=replay, single_slot=padding,poses=checks))
    (output/'candidate.yobj').write_bytes(raw)
    if any(r['kind'] in ('ocular-envelope-review','analytic-collapse') for r in checks['review_findings']):
        raise ValueError('Native eye/body stress gate failed; see native-checks.json')
    pac, gims, tex_report = allocate(base,raw,precise,images,contracts,output/'textures')
    validate_trial_pac(pac,base,prepared['preparation_report']['facial_binding'])
    (output/'AJ-Styles-TNA-PSP-EXPERIMENTAL.pac').write_bytes(pac)
    dump(output/'result.json',dict(pac='AJ-Styles-TNA-PSP-EXPERIMENTAL.pac', pac_bytes=len(pac),
        sha256=hashlib.sha256(pac).hexdigest(), source_obj_sha256=hashlib.sha256(data).hexdigest(),
        source_texture_sha256=hashlib.sha256(texture.read_bytes()).hexdigest(),source=source_report,
        triangles=native['report']['triangles'],vertices=native['report']['vertices'],meshes=len(native['meshes']),
        textures=len(gims),bones=len(native['bones']),chart_cell=chart_cell,decimation=False,weight_units=weight_units,position_divisions=position_divisions,
        structural_validation_passed=True,analytical_eye_gate_passed=True,
        status='EXPERIMENTAL: newly inferred PSP binding; original TNA skinning unavailable; not game-tested'))
    return output/'AJ-Styles-TNA-PSP-EXPERIMENTAL.pac'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--mtl',type=Path,required=True)
    p.add_argument('--texture',type=Path,required=True);p.add_argument('--base',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--chart-cell',type=int,default=0)
    p.add_argument('--weight-units',type=int,default=1024)
    p.add_argument('--position-divisions',type=int,default=65536)
    a=p.parse_args();print(build(a.source,a.mtl,a.texture,a.base,a.out,chart_cell=a.chart_cell,
        weight_units=a.weight_units,position_divisions=a.position_divisions))

"""Sample-scoped WWE13 source/rig adaptation; never registered in the app."""
import copy
from collections import defaultdict
import io
import re
import struct

import numpy as np
from PIL import Image

from tools.prepare_model import bone_matrices
from tools.wwe13_inspect import read_pach, read_jboy, sha, parse_textures

SOURCE_SHA = '2808111b6c9619cebe015bf8e05ee8cff195bee8f6d4f78bd2269fe00625ba65'
BODY = {'Bip': 'root', 'Bip Pelvis': 'root', 'Bip Spine': 'koshi',
        'Bip Spine1': 'mune', 'Bip Neck': 'kubi', 'Neck_x': 'kubi', 'Bip Head': 'atama'}
PARTS = {'Clavicle': 'sakotsu', 'UpperArm': 'ninoude', 'Forearm': 'kote',
         'Hand': 'te', 'Thigh': 'momo', 'Calf': 'sune', 'Foot': 'ashi', 'Toe0': 'tsumasaki'}
HELPERS = {'Thigh_u': 'momo', 'Thigh_x': 'momo', 'Chest_Dummy': 'mune',
           'Clavicle_m': 'sakotsu', 'Shoulder_m': 'sakotsu', 'UpperArm_x': 'ninoude_x',
           'UpperArm_m': 'ninoude', 'Elbow_m': 'ninoude_x', 'Elbow_j': 'kote',
           'Wrist_x': 'kote_x', 'Wrist_x2': 'kote_x'}


def bone_role(name, available):
    if name in BODY:
        return BODY[name]
    if name in available:
        return name
    m = re.fullmatch(r'Bip ([LR]) (.+)', name)
    if m:
        side, part = m.groups(); prefix = side.lower() + '_'
        if part in PARTS:
            return prefix + PARTS[part]
        digit = re.fullmatch(r'Finger([0-4])([12]?)', part)
        if digit:
            return prefix + 'yubi' + digit[1] + (digit[2] or '0')
    m = re.fullmatch(r'([lLrR])_(.+)', name)
    if m and m[2] in HELPERS:
        role = HELPERS[m[2]]
        return role if role == 'mune' else m[1].lower() + '_' + role
    return None


def source_bundle(data, index=0):
    # The outer directory is not understood yet: restrict discovery to exactly
    # the inspected file, then independently validate the chosen container.
    if sha(data) != SOURCE_SHA or index not in (0, 1):
        raise ValueError('Only the inspected ch104 source and bundles 0/1 are authorized by this trial contract')
    bundle = read_pach(data, (0x4000, 0x471800)[index])
    raw = {s['id']: s['raw'] for s in bundle['sections']}
    models = {sid: read_jboy(raw[sid]) for sid in (0, 10000, 20002)}
    tables = {sid: parse_textures(raw[sid]) for sid in (10, 12)}
    def image(sid, wanted):
        row = next(t for t in tables[sid] if t['name'].lower() == wanted)
        payload = raw[sid][row['offset']:row['offset'] + row['size']]
        return np.array(Image.open(io.BytesIO(payload)).convert('RGBA'))
    diffuse, normal = image(12, 'color'), image(10, 'normal')
    if diffuse.shape != normal.shape:
        raise ValueError('Diffuse/normal atlas dimensions differ')
    bones, bone_ids, origins = [], {}, {}
    for sid, model in models.items():
        for b in model['bones']:
            parent_name = model['bones'][b['parent']]['name'] if b['parent'] >= 0 else None
            if b['name'] in bone_ids:
                other = origins[b['name']]
                # Auxiliary eye hierarchies omit intervening body helpers, so
                # compare global binds below rather than requiring same parent.
                continue
            bone_ids[b['name']] = len(bones)
            bones.append(dict(b, index=len(bones), parent=-1))
            origins[b['name']] = (sid, b['index'], parent_name)
    for b in bones:
        par = origins[b['name']][2]
        b['parent'] = bone_ids[par] if par is not None else -1
    main_matrices = bone_matrices(dict(bones=bones))
    bind_mismatches = []
    for sid, model in models.items():
        local = bone_matrices(model)
        for b in model['bones']:
            delta = float(np.max(np.abs(main_matrices[bone_ids[b['name']]] - local[b['index']])))
            if delta > 1e-3:
                bind_mismatches.append(dict(section=sid, name=b['name'], maximum_matrix_difference=delta))
    if bind_mismatches:
        raise ValueError('Auxiliary source bind mismatch: ' + str(bind_mismatches[:4]))
    meshes, bindings = [], []
    for sid, model in models.items():
        d = raw[sid]
        for mesh in model['meshes']:
            a = 72 + mesh['index'] * 184
            u = lambda o: struct.unpack_from('>I', d, o)[0]
            params = {}
            for k in range(u(a + 148)):
                ptr = u(u(a + 152) + 8 + k * 4) + 8
                label = d[ptr:ptr + 16].split(b'\0', 1)[0].decode('ascii')
                params[label] = dict(type=struct.unpack_from('>H', d, ptr + 16)[0],
                                     bytes=struct.unpack_from('>H', d, ptr + 18)[0],
                                     value=u(ptr + 20))
            sampler = params.get('g_mDiffusePrm')
            if sampler != dict(type=15, bytes=24, value=0) or model['texture_names'][0] != 'color':
                raise ValueError('Unverified source diffuse binding')
            shader = mesh['shader']
            if shader not in {'yCh_skin', 'yCh_skin_flex', 'yCh_gear', 'yCh_Reflect', 'yCh_Aniso_trans', 'yCh_trans'}:
                raise ValueError('Unknown source shader')
            opacity = shader == 'yCh_Aniso_trans'
            palette_names = {model['bones'][b - 1]['name'] for b in mesh['stored_bone_palette']}
            eyeball = palette_names <= {'l_eye', 'r_eye'}
            role = 'Hair' if opacity else 'EyeShell' if sid == 20002 else 'Eyeball' if eyeball else 'Body'
            out = dict(index=len(meshes), bone_palette=list(range(len(bones))), vertices=[],
                       source_section=sid, source_mesh=mesh['index'], source_shader=shader, role=role,
                       materials=[dict(texture_id=int(opacity), triangles=copy.deepcopy(mesh['materials'][0]['triangles']))])
            for vi, v in enumerate(mesh['vertices']):
                weights = np.zeros(len(bones))
                for inf in v['raw_influences']:
                    slot = inf['palette_slot']
                    if slot == 255:
                        continue
                    weight = inf['raw_weight']
                    if weight < 0:
                        raise ValueError('Active negative source influence')
                    b = model['bones'][mesh['stored_bone_palette'][slot] - 1]['name']
                    weights[bone_ids[b]] += weight
                weights /= weights.sum()
                out['vertices'].append(dict(position=v['position'], normal=v['normal'], uv=v['uv'],
                    color=[255] * 4, weights=weights.tolist(), source_record=[sid, mesh['index'], vi]))
            meshes.append(out)
            bindings.append(dict(section=sid, mesh=mesh['index'], shader=shader, diffuse=sampler,
                source_texture=model['texture_names'][sampler['value']], opacity_policy=
                'NormalFx alpha baked only for anisotropic transparent hair/beard; inferred from strand-shaped mask' if opacity else 'Opaque; do not apply utility alpha to skin/eyes'))
    hair = diffuse.copy(); hair[:, :, 3] = normal[:, :, 3]
    result = dict(bones=bones, bone_count=len(bones), meshes=meshes, mesh_count=len(meshes),
        textures=['source_color', 'source_hair'], texture_count=2, geometry_decoded=True,
        triangle_count=sum(len(a['triangles']) for m in meshes for a in m['materials']),
        vertex_count=sum(len(m['vertices']) for m in meshes))
    return result, [diffuse, hair], dict(bindings=bindings, auxiliary_bind_mismatches=bind_mismatches,
        vertex_tint_policy='White PSP vertex tint; source shader utility bytes not multiplied into diffuse',
        material_approximation='Diffuse + inferred hair opacity only; no source normal/specular/muscle/hair shaders',
        source_weight_policy='Discard bounded unused sentinels, retain active influences, normalize float32 sum roundoff',
        source_sha256=sha(data), bundle=index)


def rotation_between(a, b):
    a, b = np.asarray(a) / np.linalg.norm(a), np.asarray(b) / np.linalg.norm(b)
    v = np.cross(a, b); c = np.dot(a, b)
    if c < -.999999:
        raise ValueError('Antiparallel segment frame needs explicit review')
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def adapt_rig(source, target):
    result = copy.deepcopy(source)
    sm, tm = bone_matrices(source), bone_matrices(target)
    sb = {b['name']: b['index'] for b in source['bones']}
    tb = {b['name']: b['index'] for b in target['bones']}
    scale = .1
    translation = tm[tb['root'], :3, 3] - scale * sm[sb['Bip Pelvis'], :3, 3]
    source_origins = scale * sm[:, :3, 3] + translation
    mapping, mapping_report = {}, []
    for b in source['bones']:
        current = b['index']; role = None
        while current != -1:
            role = bone_role(source['bones'][current]['name'], tb)
            if role in tb:
                break
            current = source['bones'][current]['parent']
        if role not in tb:
            if b['name'] in ('vector', 'null'):
                role = 'root'
            else:
                raise ValueError('Unmapped source bone ' + b['name'])
        mapping[b['index']] = tb[role]
        mapping_report.append(dict(source=b['name'], target=role, ancestor=source['bones'][current]['name'] if current >= 0 else None))
    transforms = {}
    frames = {}
    for side in ('l', 'r'):
        prefix = 'Bip ' + side.upper() + ' '
        for label, start, end, target_start, target_end in (
            ('leg', 'Thigh', 'Calf', 'momo', 'sune'),
            ('arm', 'UpperArm', 'Forearm', 'ninoude', 'kote'),
            ('forearm', 'Forearm', 'Hand', 'kote', 'te')):
            a, b = source_origins[[sb[prefix + start], sb[prefix + end]]]
            c, d = tm[[tb[side + '_' + target_start], tb[side + '_' + target_end]], :3, 3]
            r = rotation_between(b - a, d - c)
            frames[side, label] = r, a, c
        # Use physical finger-base landmarks, not incompatible hand local axes.
        a = source_origins[sb[prefix + 'Hand']]; c = tm[tb[side + '_te'], :3, 3]
        src = np.array([source_origins[sb[prefix + 'Finger' + str(i)]] - a for i in range(1, 5)])
        dst = np.array([tm[tb[side + '_yubi' + str(i) + '0'], :3, 3] - c for i in range(1, 5)])
        u, _, vt = np.linalg.svd(src.T @ dst)
        correction = np.eye(3); correction[2, 2] = np.linalg.det(vt.T @ u.T)
        r = vt.T @ correction @ u.T
        frames[side, 'hand'] = r, a, c
    for b in source['bones']:
        names = []; current = b['index']
        while current >= 0:
            names.append(source['bones'][current]['name']); current = source['bones'][current]['parent']
        selected = None
        for side in ('l', 'r'):
            prefix = 'Bip ' + side.upper() + ' '
            if prefix + 'Hand' in names:
                selected = side, 'hand'
            elif prefix + 'Forearm' in names:
                selected = side, 'forearm'
            elif prefix + 'UpperArm' in names or b['name'] in (side.upper() + '_Shoulder_m', side.upper() + '_Clavicle_m'):
                selected = side, 'arm'
            elif prefix + 'Thigh' in names or b['name'] == side.upper() + '_Thigh_u':
                selected = side, 'leg'
        transforms[b['index']] = frames[selected] if selected else (np.eye(3), np.zeros(3), np.zeros(3))
    changed = 0
    for mesh in result['meshes']:
        for v in mesh['vertices']:
            p = scale * np.array(v['position']) + translation
            normal = np.array(v['normal']); q = np.zeros(3); n = np.zeros(3)
            out = np.zeros(target['bone_count'])
            for b, w in enumerate(v['weights']):
                if not w:
                    continue
                r, a, c = transforms[b]
                q += w * (r @ (p - a) + c)
                n += w * (r @ normal)
                out[mapping[b]] += w
            if np.count_nonzero(out > 0) > 4:
                raise ValueError('Retargeting needs more than four influences')
            changed += int(np.linalg.norm(q - p) > 1e-5)
            v['position'] = np.asarray(q, np.float32).astype(float).tolist()
            v['normal'] = (n / np.linalg.norm(n)).tolist()
            v['weights'] = out.tolist()
        mesh['bone_palette'] = list(range(target['bone_count']))
    result.update(bones=copy.deepcopy(target['bones']), bone_count=target['bone_count'], model_name=target['model_name'])
    report = dict(scale=scale, rotation=np.eye(3).tolist(), translation=translation.tolist(),
        changed_bind_records=changed, bone_mapping=mapping_report,
        frame_policy='Minimal segment rotations to PSP rest chains; wrist-anchored rigid hand fit from finger-base landmarks',
        frames={side + '-' + label: dict(rotation=r.tolist(), source_anchor=a.tolist(), target_anchor=c.tolist())
                for (side, label), (r, a, c) in frames.items()},
        cranial_policy='Source facial support mapped by explicit role/name, unmatched controllers collapse to mapped ancestor; no nearest donor spill',
        hair_policy='Unrepresented source spring bones collapse to head ancestor; dynamic hair is not ported',
        animation_semantics='EXPERIMENTAL; actual source/PSP clips not available')
    result['preparation_report'] = report
    return result, report


def ocular_transfer(source, prepared, target):
    """Replace only eye/lid/head mass on source ocular support, preserving jaw.

    Source and PSP facial controllers have different bind axes and pivots. Use
    native donor coefficients for represented ocular roles rather than assuming
    that a same-name source coefficient has compatible animation semantics.
    """
    from tools.weight_trial_review import transfer
    result = copy.deepcopy(prepared)
    sb = {b['name']: b['index'] for b in source['bones']}
    tb = {b['name']: b['index'] for b in target['bones']}
    names = ('l_eye', 'r_eye', 'l_mabuta', 'r_mabuta')
    selected = np.array([sum(v['weights'][sb[n]] for n in names if n in sb) > 1e-7
                         for m in source['meshes'] for v in m['vertices']])
    points = np.array([v['position'] for m in prepared['meshes'] for v in m['vertices']])
    donor, report = transfer(target, points[selected])
    allowed = [tb[n] for n in (*names, 'atama')]
    rows = np.array([v['weights'] for m in prepared['meshes'] for v in m['vertices']])
    before = rows.copy()
    original = [v for m in source['meshes'] for v in m['vertices']]
    unsupported_mass = 0.
    for i, row in enumerate(np.flatnonzero(selected)):
        mass = rows[row, allowed].sum()
        replacement = np.zeros(len(allowed))
        for j, name in enumerate(names):
            # Never introduce eyelid skinning onto an originally rigid eye,
            # or make a left-eye record follow the right controller.
            if name in sb and original[row]['weights'][sb[name]] > 1e-7:
                replacement[j] = donor[i, tb[name]]
        unsupported_mass += float(1 - replacement[:-1].sum())
        replacement[-1] = 1 - replacement[:-1].sum()
        rows[row, allowed] = mass * replacement
    # Four-slot packing may not silently remove the retained jaw/body support.
    if np.max(np.count_nonzero(rows > 0, axis=1)) > 4:
        raise ValueError('Selective ocular transfer exceeds four influences; review required')
    preserved = [i for i in range(target['bone_count']) if i not in allowed]
    if not np.array_equal(rows[:, preserved], before[:, preserved]):
        raise ValueError('Ocular correction changed non-ocular coefficients')
    rigid = np.array([sum(v['weights'][sb[n]] for n in ('l_eye', 'r_eye') if n in sb) > .999999
                      for v in original])
    lid_ids = [tb['l_mabuta'], tb['r_mabuta']]
    rigid_eye_lid_records = int(np.count_nonzero(rows[rigid][:, lid_ids].sum(1) > 1e-7))
    if rigid_eye_lid_records:
        raise ValueError('Native donor introduced eyelid influence on rigid source eyeball')
    for v, weights in zip((v for m in result['meshes'] for v in m['vertices']), rows):
        v['weights'] = weights.tolist()
    return result, dict(selected_records=int(selected.sum()), nonocular_coefficients_exact=True,
        positions_normals_uvs_materials_exact=True, donor_transfer=report,
        maximum_weight_difference=float(np.max(np.abs(rows-before))),
        head_fallback_mass_sum=unsupported_mass,
        rigid_eyeball_eyelid_influences_introduced=rigid_eye_lid_records,
        method='Native donor amplitudes only for original source ocular roles; unsupported donor roles attach to head, never amplify eye coefficients; jaw/body mass untouched')


def chart_atlas(model, images, cell=256, *, power2_context=False, repeat_safe=False):
    """Crop bounded groups of whole triangles, preserving sampled source RGBA.

    Splits oversized islands for atlas detail, without clipping source triangles.
    Source canvases preserve a native-supported aspect with minimal original
    context padding. Only final GIMs must be powers of two. Rounding source
    canvases to POT wasted most face/body pixels in the early rejected trial.
    """
    from tools.sym_atlas import bilinear
    result = copy.deepcopy(model); crops = []; configs = []; cache = {}
    # A page is shared across original mesh boundaries. Computing a different
    # crop per mesh caused 134 redundant images in the first rejected trial.
    bounds = {}
    for mesh in model['meshes']:
        for mat in mesh['materials']:
            image = images[mat['texture_id']]; h, w = image.shape[:2]
            for tri in mat['triangles']:
                uv = np.array([mesh['vertices'][j]['uv'] for j in tri])
                gx, gy = np.floor(uv.mean(0) * [w, h] / cell).astype(int)
                key = mat['texture_id'], gx, gy
                low = np.floor((uv * [w, h] - .5).min(0)).astype(int) - 1
                high = np.ceil((uv * [w, h] - .5).max(0)).astype(int) + 2
                if key in bounds:
                    low = np.minimum(low, bounds[key][0]); high = np.maximum(high, bounds[key][1])
                bounds[key] = low, high
    for mesh in result['meshes']:
        old_vertices = mesh['vertices']; vertices = []; mats = []; vertex_map = {}
        groups = defaultdict(list)
        for mat in mesh['materials']:
            for tri in mat['triangles']:
                uv = np.array([old_vertices[j]['uv'] for j in tri])
                h, w = images[mat['texture_id']].shape[:2]
                mid = np.mean(uv, axis=0) * [w, h]
                groups[mat['texture_id'], *(np.floor(mid / cell).astype(int))].append(tri)
        for (source_tid, gx, gy), faces in sorted(groups.items()):
            image = images[source_tid]; h, w = image.shape[:2]
            uv = np.array([old_vertices[j]['uv'] for tri in faces for j in tri])
            low, high = bounds[source_tid, gx, gy]
            extent = high - low
            if power2_context:
                cw, ch = [1 << max(3, int(x - 1).bit_length()) for x in extent]
                cw = max(cw, ch // 4); ch = max(ch, cw // 4)
            else:
                canvases = []
                for rx, ry in ((1,1),(2,1),(1,2),(4,1),(1,4)):
                    unit = max((int(extent[0])+rx-1)//rx, (int(extent[1])+ry-1)//ry,
                               (32+rx-1)//rx, (32+ry-1)//ry)
                    if rx*unit <= w and ry*unit <= h:
                        canvases.append((rx*unit, ry*unit))
                if not canvases:
                    # A bilinear guard around UVs touching a repeating atlas
                    # edge may extend 1-2 pixels beyond the original canvas.
                    # Reuse that entire canvas exactly; do not upscale or clip
                    # triangles. Opt-in for the multi-model Wii experiment.
                    if (repeat_safe and (w/h in (.25,.5,1.,2.,4.))
                            and np.all(extent<=np.array([w,h])+4)
                            and np.all(uv>=-.01) and np.all(uv<=1.01)):
                        low=np.array([0,0]);cw,ch=w,h
                    else:raise ValueError('Source chart cannot fit a supported aspect without upscaling')
                else:cw, ch = min(canvases, key=lambda s: (s[0]*s[1], max(s), s))
            if cw > w or ch > h:
                raise ValueError('Source chart would exceed atlas ceiling')
            key = source_tid, *low.tolist(), cw, ch
            if key not in cache:
                tid = len(crops); cache[key] = tid
                crop = image[np.ix_((low[1] + np.arange(ch)) % h, (low[0] + np.arange(cw)) % w)].copy()
                crops.append(crop)
                configs.append(dict(name=f'w13_{tid:02d}', source_texture=source_tid, source_origin=low.tolist(),
                    source_dimensions=[cw, ch], source_samples_exact=True, crop_padding='Repeating original atlas context'))
            tid = cache[key]; crop = crops[tid]
            outfaces = []
            for tri in faces:
                face = []
                for j in tri:
                    key = j, tid
                    if key not in vertex_map:
                        v = copy.deepcopy(old_vertices[j]); v['atlas_original_uv'] = list(v['uv'])
                        v['uv'] = ((np.array(v['uv']) * [w, h] - low) / [cw, ch]).tolist()
                        vertex_map[key] = len(vertices); vertices.append(v)
                    face.append(vertex_map[key])
                bary = np.array([[1,0,0],[0,1,0],[0,0,1],[.5,.5,0],[0,.5,.5],[.5,0,.5],[1/3]*3])
                a = bilinear(image, bary @ np.array([old_vertices[j]['uv'] for j in tri]))
                b = bilinear(crop, bary @ np.array([vertices[j]['uv'] for j in face]))
                if np.max(np.abs(a-b)) > 1e-6:
                    raise ValueError('Chart remap changed source RGBA samples')
                outfaces.append(face)
            mats.append(dict(texture_id=tid, triangles=outfaces))
        mesh.update(vertices=vertices, materials=mats)
    result.update(textures=[c['name'] for c in configs], texture_count=len(crops),
                  vertex_count=sum(len(m['vertices']) for m in result['meshes']))
    return result, crops, dict(charts=configs, geometry_moved=False, triangles_clipped=False,
                               maximum_tested_sample_error=1e-6, samples_per_triangle=7)

"""Explicit HCTP/PSP model roles, independent native models and shared textures.

Confirmed on the uploaded Rock pair: HCTP 6/7 contain left/right elbow pads;
PSP 26/27 contain the corresponding independently skinned YOBJs. Generalization
is experimental and gated by direct arm-controller support, not model names.
Unsupported extra models are errors, never silently omitted or merged.
"""
from collections import Counter
import copy
import struct

import numpy as np

from app.ps2_textures import read_source
from desktop.native import serialize
from tools.hctp_weights import read_hctp_with_weights
from tools.pac_inspect import inspect_pac
from tools.pac_repack import rewrite_sections
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.stripify import stripify
from tools.weight_trial_review import POSES, deform
from tools.yukes_bpe import compress, decompress

ROLES = {6: (26, 'l', 'L_elb'), 7: (27, 'r', 'R_elb')}


def source_models(path, main):
    data = path.read_bytes()
    info = inspect_pac(data)
    if len({s['id'] for s in info['sections']}) != len(info['sections']):
        raise ValueError('Duplicate PAC section IDs cannot identify model roles.')
    result = []
    main_bones = {b['name']: b for b in main['bones']}
    main_id = 2 if any(s['id'] == 2 for s in info['sections']) else next(s['id'] for s in info['sections'] if s['kind'] == 'model_section')
    for section, raw in sections(data):
        if section['id'] == main_id:
            continue
        if section['id'] in ROLES and not raw.startswith(b'YOBJ'):
            raise ValueError('Accessory section %d is not a supported YOBJ.' % section['id'])
        if not raw.startswith(b'YOBJ'):
            continue
        if section['id'] not in ROLES:
            raise ValueError('Unrecognized auxiliary YOBJ section %d; output withheld rather than dropping it.' % section['id'])
        model = read_hctp_with_weights(raw)
        destination, side, name = ROLES[section['id']]
        allowed = {side+'_'+n for n in ('ninoude', 'ninoude_x', 'kote', 'kote_x')}
        support = {model['bones'][b]['name'] for m in model['meshes'] for v in m['vertices']
                   for b,w in zip(m['bone_palette'], v['weights']) if w > 0}
        if not support or not support <= allowed or not any(n.endswith('kote') for n in support):
            raise ValueError('Section %d does not match the verified %s elbow-pad controller contract.' % (section['id'], side))
        if not model['triangle_count']:
            raise ValueError('Accessory model contains no supported triangles.')
        # Compare every influencing bone and its ancestors by name, not index.
        # Separate PS2 rigs use different bone numbers and omit unrelated bones.
        for bone in model['bones']:
            if bone['name'] not in support:
                continue
            index = bone['index']
            while index != -1:
                b = model['bones'][index]; other = main_bones.get(b['name'])
                parent = model['bones'][b['parent']]['name'] if b['parent'] != -1 else None
                main_parent = main['bones'][other['parent']]['name'] if other is not None and other['parent'] != -1 else None
                if other is None or parent != main_parent or not np.allclose(
                        [*b['local_position'], *b['rotation']],
                        [*other['local_position'], *other['rotation']], atol=2e-5, rtol=0):
                    raise ValueError('Accessory rest hierarchy differs from the main source at '+b['name'])
                index = b['parent']
        result.append(dict(source_section=section['id'], target_section=destination,
                           side=side, name=name, model=model, support=sorted(support),
                           source_sha256=section['sha256']))
    # Main first, then every accessory's texture dependencies, once by name.
    names = list(main['textures'])
    for item in result:
        for name in item['model']['textures']:
            if name.casefold() not in {n.casefold() for n in names}:
                names.append(name)
    return result, names


def decode_dependencies(path, main_decoded, names):
    if names == [n for i,n,*_ in main_decoded]:
        return main_decoded
    return read_source(path, texture_names=names)


def prepare_accessory(item, target, alignment):
    model = copy.deepcopy(item['model'])
    mapping = {b['index']: next((t['index'] for t in target['bones'] if t['name'] == b['name']), None)
               for b in model['bones']}
    rotation = np.asarray(alignment['rotation']); scale = alignment['scale']
    translation = np.asarray(alignment['translation'])
    for mesh in model['meshes']:
        active = sorted({b for v in mesh['vertices'] for b,w in zip(mesh['bone_palette'],v['weights']) if w > 0})
        if any(mapping[b] is None for b in active):
            raise ValueError('PSP base is missing an influencing accessory controller.')
        palette = [mapping[b] for b in active]
        if not 1 <= len(palette) <= 8:
            raise ValueError('Accessory exceeds the native eight-bone palette.')
        donors = [m for m in target['meshes'] if set(palette) <= set(m['bone_palette'])
                  and not m['rigid'] and m['base_flag'] == 0x17ff]
        if not donors:
            raise ValueError('No compatible PSP arm draw template for this accessory.')
        mesh['target_part'] = donors[0]['index']
        old_palette = mesh['bone_palette']
        for v in mesh['vertices']:
            v['position'] = np.asarray(scale*rotation@v['position']+translation, dtype=np.float32).astype(float).tolist()
            normal = rotation@v['normal']; length = np.linalg.norm(normal)
            if length < 1e-10:
                raise ValueError('Accessory has an unusable zero normal.')
            v['normal'] = (normal/length).tolist()
            values = dict(zip(old_palette, v['weights']))
            # No donor transfer or influence pruning on independently skinned pads.
            v['weights'] = [values.get(b, 0.) for b in active]
        mesh['bone_palette'] = palette
        for material in mesh['materials']:
            material['strips'] = stripify(material['triangles'])
    model.update(bones=copy.deepcopy(target['bones']), bone_count=target['bone_count'],
                 model_name=item['name'])
    return model


def build_accessories(items, target, alignment, texture_entries):
    """All geometry is retained; each pad has its own sparse native palette.

    Native reference accessory tables share local bind transforms with the main
    rig, but store sparse per-model global metadata. Preserve that observed
    pattern using aligned source accessory metadata for influencing bones.
    The runtime interpretation of those three floats remains inferred.
    """
    models = {}; reports = []; prepared_models = {}
    by_name = {e['name'].casefold(): e for e in texture_entries}
    for item in items:
        prepared = prepare_accessory(item, target, alignment)
        donor = copy.deepcopy(target)
        raw = bytearray(donor['bone_raw'])
        for bone in donor['bones']:
            struct.pack_into('<3f',raw,80*bone['index']+64,0,0,0)
            bone['stored_global_position'] = [0.,0.,0.]
        r = np.asarray(alignment['rotation']); t = np.asarray(alignment['translation'])
        target_names = {b['name']:b['index'] for b in target['bones']}
        for bone in item['model']['bones']:
            if bone['name'] not in item['support']:
                continue
            i = target_names[bone['name']]
            point = alignment['scale']*r@bone['stored_global_position']+t
            struct.pack_into('<3f',raw,80*i+64,*point)
            donor['bones'][i]['stored_global_position'] = point.tolist()
        donor['bone_raw'] = bytes(raw)
        name = item['name'].encode('ascii').ljust(16,b'\0')
        donor['model_name_raw'] = name
        donor['model_descriptor_raw'] = name+donor['model_descriptor_raw'][16:]
        prepared['bones'] = copy.deepcopy(donor['bones'])
        entries = [dict(by_name[n.casefold()],index=i) for i,n in enumerate(prepared['textures'])]
        prepared['textures'] = [e['name'] for e in entries]
        yobj = serialize(prepared, donor, entries)
        native = audit_yobj(yobj)
        checked = validate_accessory(prepared, native)
        section = item['target_section']; models[section] = yobj; prepared_models[section] = prepared
        reports.append(dict(source_section=item['source_section'], target_section=section,
                            source_sha256=item['source_sha256'], name=item['name'],
                            source_vertices=item['model']['vertex_count'], source_triangles=item['model']['triangle_count'],
                            **native['report'], analytical_validation=checked,
                            stored_global_metadata='Aligned source values for active bones; zero for inactive bones',
                            local_bind_records_match_main=True, decimation_applied=False,
                            limitation='Actual elbow-pad removal/throw semantics require SVR 2011 testing.'))
    return models, prepared_models, reports


def validate_accessory(expected, native):
    positions = []; weights = []
    for a,b in zip(expected['meshes'],native['meshes']):
        if a['bone_palette'] != b['bone_palette'] or len(a['vertices']) != len(b['vertices']) or len(a['materials']) != len(b['materials']):
            raise ValueError('Accessory serialization changed palette or vertex count.')
        for x,y in zip(a['vertices'],b['vertices']):
            for key in ('position','normal','uv','weights'):
                if struct.pack('<'+'f'*len(x[key]),*x[key]) != struct.pack('<'+'f'*len(y[key]),*y[key]):
                    raise ValueError('Accessory serialization changed '+key)
            if tuple(x['color']) != tuple(y['color']):
                raise ValueError('Accessory serialization changed color/alpha.')
            positions.append(y['position']); dense = np.zeros(len(native['bones']))
            dense[b['bone_palette']] = y['weights']; weights.append(dense)
        def oriented(t):return min(tuple(t[i:]+t[:i]) for i in range(3))
        for x,y in zip(a['materials'],b['materials']):
            if x['texture_id'] != y['texture_id']:
                raise ValueError('Accessory texture assignment changed.')
            if Counter(oriented(list(t)) for t in x['triangles']) != Counter(oriented(list(t)) for t in y['triangles']):
                raise ValueError('Accessory topology/winding changed.')
    if len(expected['meshes']) != len(native['meshes']):
        raise ValueError('Accessory mesh count changed.')
    ps = np.asarray(positions); ws = np.asarray(weights); pose_report = {}
    from model_qa.pipeline import POSES as QA_POSES
    for name,pose in {**POSES,**QA_POSES}.items():
        a = deform(expected, ps, ws, pose)
        b = deform(dict(native,bone_count=len(native['bones'])),ps,ws,pose)
        if not np.isfinite(b).all() or not np.allclose(a,b,atol=1e-7,rtol=0):
            raise ValueError('Accessory analytical pose replay failed in '+name)
        pose_report[name] = dict(maximum_position_delta=float(np.max(np.abs(a-b))),finite=True)
    return dict(status='pass', exact_float32_attributes=True, oriented_triangles_preserved=True,poses=pose_report)


def package_models(base, main, table, accessories, *, max_distinct=200):
    ids = {s['id'] for s in inspect_pac(base)['sections']}
    additions = {}; replacements = {}
    for i,payload in {2:main,9:table,**accessories}.items():
        packed = compress(payload,max_distinct=max_distinct)
        if decompress(packed) != payload:
            raise ValueError('Model-set BPE round trip failed.')
        (replacements if i in ids else additions)[i] = packed
    return rewrite_sections(base,replacements,additions=additions)


def combined_preview(main, accessories):
    """Preview only: remap independent texture arrays to shared names, no rig merge."""
    result = copy.deepcopy(main)
    for model in accessories:
        for name in model['texture_names']:
            if name not in result['texture_names']:
                result['texture_names'].append(name)
        for mesh in model['meshes']:
            mesh = copy.deepcopy(mesh); mesh['index'] = len(result['meshes'])
            for mat in mesh['materials']:
                name = model['texture_names'][mat['texture_id']]
                mat['texture_id'] = result['texture_names'].index(name)
            result['meshes'].append(mesh)
    return result

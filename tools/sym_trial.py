"""Isolated SYM main-model trial, NOT app support or game-verified conversion.

python -m tools.sym_trial ch.pac --base OWN_PSP_BASE.pac --entry 0000 --out NEW_DIR
No decimation; extra SYM objects are reported, not guessed into PSP slots.
"""
from desktop.limits import IN_RING_MAX_PAC_BYTES
import argparse
from collections import Counter, defaultdict
import copy
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageDraw

from desktop.core import base_model, validate_pac
from desktop.native import serialize
from desktop.skinning import adapt_yobj
from desktop.texture_optimizer.analysis import analyze, measure, model_usage, occupied
from desktop.texture_optimizer.allocator import allocate
from desktop.texture_optimizer.candidates import generate, read_gim
from model_qa.geometry import AXES, align_reference, geometry
from model_qa.metrics import measure as surface_measure
from model_qa.ocular import probes, skin
from model_qa.pipeline import POSES
from model_qa.regions import regions
from tools.hctp_weights import read_hctp_with_weights
from tools.jericho_hybrid_trial import pack
from tools.pac_inspect import inspect_pac, parse_textures
from tools.pac_repack import replace_sections, texture_table
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections, write_preview
from tools.sym_atlas import partition
from tools.sym_rig import arrays, bounds_probe, prepare_trial
from tools.sym_source import read_atlas, read_ch_directory, sha
from tools.weight_trial_review import deform
from tools.yukes_bpe import compress, decompress


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def pose_qa(prepared, native, target=None):
    """Verified record correspondence, effective weights and analytic replay.

    Serialization is checked against intended PSP weights, not against invented
    SYM motion for absent helpers/controllers. Source-game motion remains open.
    """
    ps, ws = arrays(prepared)
    native_model = dict(native, bone_count=len(native['bones']))
    np_, nw = arrays(native_model)
    # Packing may duplicate/reorder records. Require an exact float32 attribute
    # and effective-weight match, not a nearest-position-only correspondence.
    def key(vertex, weights):
        return (struct.pack('<3f', *vertex['position']),
                struct.pack('<2f', *vertex['uv']), struct.pack('<3f', *vertex['normal']),
                bytes(vertex['color']), struct.pack('<'+'f'*len(weights), *weights))
    lookup = {}
    for i, (_, v) in enumerate((m, v) for m in prepared['meshes'] for v in m['vertices']):
        lookup.setdefault(key(v, ws[i]), i)
    correspondence = []
    for i, (_, v) in enumerate((m, v) for m in native['meshes'] for v in m['vertices']):
        k = key(v, nw[i])
        if k not in lookup:
            raise ValueError('Native attribute/weight record absent from prepared geometry')
        correspondence.append(lookup[k])
    body = {}
    for name, pose in {'rest': {}, **POSES}.items():
        expected = deform(prepared, ps, ws, pose)[correspondence]
        actual = deform(native_model, np_, nw, pose)
        delta = float(np.abs(expected-actual).max())
        if not np.isfinite(actual).all() or delta > 1e-6:
            raise ValueError('Analytical native body replay failed: '+name)
        body[name] = dict(maximum_position_error=delta, finite=True,
            maximum_motion=float(np.linalg.norm(actual-np_, axis=1).max()))
    gp, gn = geometry(prepared), geometry(native)
    rest_area = np.linalg.norm(np.cross(gn.vertices[gn.faces[:,1]]-gn.vertices[gn.faces[:,0]],
                                        gn.vertices[gn.faces[:,2]]-gn.vertices[gn.faces[:,0]]),axis=1)
    usable = rest_area > gn.height**2*1e-12
    review = []
    for name, pose in {'rest':{},**POSES}.items():
        q = deform(native_model,np_,nw,pose)@AXES
        area = np.linalg.norm(np.cross(q[gn.faces[:,1]]-q[gn.faces[:,0]],q[gn.faces[:,2]]-q[gn.faces[:,0]]),axis=1)
        ratios = area[usable]/rest_area[usable]
        collapsed = int(np.count_nonzero(ratios<1e-6))
        body[name].update(minimum_area_ratio=float(ratios.min()), newly_collapsed_triangles=collapsed)
        if collapsed:review.append(dict(kind='analytic-collapse',pose=name,triangles=collapsed))
    ocular = {}
    for name, probe in probes().items():
        expected, missing_a = skin(gp, probe)
        actual, missing_b = skin(gn, probe)
        delta = float(np.abs(expected.vertices[correspondence]-actual.vertices).max())
        if missing_a or missing_b or delta > 1e-6:
            raise ValueError('Native ocular probe replay failed: '+name)
        ocular[name] = dict(maximum_position_error=delta,
            maximum_motion=float(np.linalg.norm(actual.vertices-gn.vertices, axis=1).max()))
        if target is not None:
            donor = geometry(target)
            posed_donor, missing = skin(donor,probe)
            if missing:raise ValueError('PSP donor lacks requested probe controllers')
            donor_motion=float(np.linalg.norm(posed_donor.vertices-donor.vertices,axis=1).max())
            ocular[name]['native_donor_maximum_motion']=donor_motion
            ocular[name]['exceeds_provisional_donor_envelope']=bool(ocular[name]['maximum_motion']>1.5*donor_motion+.002*gn.height)
            if ocular[name]['exceeds_provisional_donor_envelope']:
                review.append(dict(kind='ocular-envelope-review',probe=name))
    # Every pair of identical source position + effective influences must retain
    # identical motion, even across atlas islands or packing chunks. Distinct
    # source weights at a coincident location are not declared a defect.
    identical = defaultdict(list)
    for i, (p, w) in enumerate(zip(ps, ws)):
        identical[(struct.pack('<3f', *p), struct.pack('<'+'f'*len(w), *w))].append(i)
    seam_max = 0.
    for pose in POSES.values():
        q = deform(prepared, ps, ws, pose)
        seam_max = max(seam_max, max((float(np.ptp(q[rows], axis=0).max())
                       for rows in identical.values() if len(rows) > 1), default=0.))
    if seam_max > 1e-6:
        raise ValueError('Equivalent source skinning records separate in motion')
    from model_qa.head import layout_review
    review.extend(layout_review(native))
    return dict(body=body, ocular=ocular, maximum_equivalent_seam_gap=seam_max,review_findings=review,
        exact_record_correspondence=True,
        limitation='Serialization/LBS consistency only; not original SYM or actual PSP clip equivalence')


def render_native(model, gims, view, path, *, label, pose=None, fingerprint=None,camera_bounds=None):
    from desktop.preview import render
    visible = copy.deepcopy(model)
    visible['texture_names']=visible.get('texture_names',visible.get('textures'))
    if pose is not None:
        visible['bone_count'] = len(visible['bones'])
        p, w = arrays(visible)
        posed = deform(visible, p, w, pose)
        row = 0
        for mesh in visible['meshes']:
            # Diagnostic smooth pose normals; never modify serialized normals.
            normals = np.zeros((len(mesh['vertices']), 3))
            q = posed[row:row+len(mesh['vertices'])]
            for mat in mesh['materials']:
                for tri in mat['triangles']:
                    a, b, c = q[list(tri)]
                    n = np.cross(b-a, c-a)
                    normals[list(tri)] += n
            for i, v in enumerate(mesh['vertices']):
                v['position'] = q[i]
                if np.linalg.norm(normals[i]) > 1e-12:
                    v['normal'] = normals[i]/np.linalg.norm(normals[i])
            row += len(mesh['vertices'])
    if camera_bounds is not None:
        # Shared camera frame only: unreferenced corners constrain the existing
        # bounds-fitted renderer identically. They are never exported or audited
        # as model geometry and produce no rasterized triangles.
        from itertools import product
        low,high=np.asarray(camera_bounds)
        vertices=[dict(position=list(p),normal=[0.,0.,1.],uv=[0.,0.],color=[255]*4)
                  for p in product(*zip(low,high))]
        visible['meshes'].append(dict(vertices=vertices,materials=[]))
    def reader(raw):
        if isinstance(raw,np.ndarray):
            return np.arange(raw.shape[0]*raw.shape[1]).reshape(raw.shape[:2]),raw.reshape(-1,4)
        return read_gim(raw)
    image = render(visible, gims, view, resolution=640, gim_reader=reader)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 640, 32), fill=(72, 72, 72))
    draw.text((10, 9), label+' | '+view, fill='white')
    if fingerprint:draw.text((10,595),'SHA256 '+fingerprint[:20],fill='white')
    image.save(path)


def head_preview(model):
    """View-only crop; source/native PAC geometry is never replaced by this."""
    result=copy.deepcopy(model)
    g=geometry(model)
    from model_qa.head import head_mask
    selected=head_mask(g)
    start=0
    for mesh in result['meshes']:
        mask=selected[start:start+len(mesh['vertices'])];start+=len(mesh['vertices'])
        mats=[dict(mat,triangles=[t for t in mat['triangles'] if mask[list(t)].any()]) for mat in mesh['materials']]
        mats=[m for m in mats if m['triangles']]
        used=sorted({i for mat in mats for tri in mat['triangles'] for i in tri})
        mapping={old:i for i,old in enumerate(used)}
        mesh['vertices']=[mesh['vertices'][i] for i in used]
        for mat in mats:mat['triangles']=[[mapping[i] for i in t] for t in mat['triangles']]
        mesh['materials']=mats
    result['meshes']=[m for m in result['meshes'] if m['materials']]
    return result


def optimize(base, native_bytes, model, sources, folder, max_bytes, *, cancel=lambda:None, progress=None):
    names = model['texture_names']
    usage = model_usage({2: model}, dict(zip(names, sources)))
    choices, reports, importance = [], [], []
    for name, rgba in zip(names, sources):
        cancel()
        u = usage[name]
        features = analyze(rgba, u['uv_mask'], u['surface_fraction'])
        # Minimal donor-support cranial floor; do not infer face identity from
        # source filenames. Square cranial charts retain >=64 (source-bounded),
        # and source color usage. Narrow charts keep their smaller source axis.
        sensitive = u['head_fraction'] > .5
        baseline = rgba
        if sensitive and rgba.shape[0] == rgba.shape[1] and rgba.shape[0] > 64:
            baseline = np.asarray(Image.fromarray(rgba).resize((64, 64), Image.Resampling.NEAREST))
        scoring = dict(features, mask=occupied(rgba, u['uv_mask']))
        controls = {m['control'] for mesh in model['meshes'] for m in mesh['materials']
                    if model['texture_names'][m['texture_id']] == name}
        if len(controls) != 1 or next(iter(controls)) not in (5,7,0x115,0x117):
            raise ValueError('Ambiguous chart rendering bit depth')
        bits = 8 if next(iter(controls)) & 2 else 4
        rows, rejected = generate(rgba, scoring, bits, baseline if sensitive else None, sensitive)
        # True cutouts retain every alpha sample. The existing generator has
        # alpha metrics; make this trial's acceptance rule explicit.
        if np.any(rgba[:, :, 3] < 255):
            rows = [r for r in rows if r['entry']['metrics']['alpha_exact']]
        if not rows:
            raise ValueError(name+': no alpha/quality-safe candidate')
        choices.append(rows)
        importance.append(features['importance_score'])
        reports.append(dict(name=name, analysis=features, required_bits=bits, head_fraction=u['head_fraction'],
            candidates=[r['entry'] for r in rows], rejected=rejected))
    retained_pixels = 0
    base_pixels = 0
    for section, raw in sections(base):
        if len(raw) >= 16 and raw[4:16] == struct.pack('<3I', 0x100, 0, 16):
            records = parse_textures(raw)
            if any(t['extension'] != 'gim' for t in records):
                continue
            memory = sum(len(raw[t['offset']:t['offset']+t['size']])-208 for t in records)
            base_pixels += memory
            if section['id'] != 9:
                retained_pixels += memory
    encoded_model = compress(native_bytes)
    measured = 0
    def build(selected):
        nonlocal measured
        cancel()
        rows = [rs[i] for rs, i in zip(choices, selected)]
        table = texture_table(names, [r['raw'] for r in rows], gim_reader=read_gim)
        stored = compress(table)
        pac = replace_sections(base, {2: encoded_model, 9: stored})
        measured += 1
        if measured % 50 == 0:
            message='Measured actual texture/PAC combinations: '+str(measured)
            if progress is not None:progress(message)
            else:
                import sys
                if sys.stdout is not None:print(message,flush=True)
        return pac, dict(pac_bytes=len(pac), stored_model_bytes=len(encoded_model),
            stored_texture_bytes=len(stored), texture_gim_bytes=sum(len(r['raw']) for r in rows),
            pixel_palette_bytes=retained_pixels+sum(r['entry']['pixel_palette_bytes'] for r in rows))
    pac, selected, report = allocate(choices, importance, build, max_bytes, base_pixels,cancel=cancel)
    rows = [rs[i] for rs, i in zip(choices, selected)]
    gims = {n: r['raw'] for n, r in zip(names, rows)}
    for item, row in zip(reports, rows):
        item['selected'] = row['entry']
    folder.mkdir()
    for name, raw in gims.items():
        (folder/(name+'.gim')).write_bytes(raw)
        p, c = read_gim(raw)
        Image.fromarray(c[p]).save(folder/(name+'.png'))
    report.update(textures=reports, native_base_pixel_palette_envelope=base_pixels,
        retained_base_pixel_palette_bytes=retained_pixels,
        memory_limit_scope='Conservative native-base allocation envelope; actual runtime heap limit UNKNOWN',
        source_atlas_partitioned=True,
        rendering_bits={r['name']:r['required_bits'] for r in reports})
    dump(folder/'report.json', report)
    # Verify this callback reproduces the unchanged canonical packaging path.
    from desktop.accessories import package_models
    canonical = package_models(base, native_bytes,
        texture_table(names, list(gims.values()), gim_reader=read_gim), {})
    if canonical != pac:
        raise ValueError('Trial packaging diverged from existing package_models')
    return pac, gims, report


def run(source, base_path, entry_id, output, max_bytes=IN_RING_MAX_PAC_BYTES):
    original = source.read_bytes()
    directory = read_ch_directory(original)
    entry = next((e for e in directory['entries'] if e['id_hex'] == entry_id), None)
    if entry is None:
        raise ValueError('No such SYM costume ID')
    raw = original[entry['offset']:entry['offset']+entry['stored_bytes']]
    decoded = {s['id']: payload for s, payload in sections(raw)}
    source_model = read_hctp_with_weights(decoded[2])
    p, c, atlas_meta = read_atlas(decoded[1])
    charted, images, atlas_report = partition(source_model, c[p])
    base, target = base_model(base_path)
    if source.resolve() == base_path.resolve():
        raise ValueError('Base and source must differ')
    output.mkdir(parents=True, exist_ok=False)
    dump(output/'atlas.json', atlas_report)
    dump(output/'bone-bounds.json', bounds_probe(decoded[2], source_model))
    dump(output/'source-model.json', source_model)
    prepared, rig = prepare_trial(charted, target)
    control, control_rig = prepare_trial(charted, target, method='ancestor-control')
    dump(output/'rig.json', rig)
    dump(output/'ancestor-control-rig.json', control_rig)
    packed = pack(prepared, target)
    usage = model_usage({2:dict(packed,texture_names=packed['textures'])}, dict(zip(packed['textures'],images)))
    texture_contracts = [dict(bits=8 if usage[n]['head_fraction']>.5 or np.any(i[:,:,3]<255) else 4,
                              cutout=bool(np.any(i[:,:,3]<255))) for n,i in zip(packed['textures'],images)]
    dump(output/'texture-contracts.json',dict(policy='Trial: T8 for majority-cranial/cutout charts; T4 otherwise. Not a production default.',textures=texture_contracts))
    yobj = serialize(packed, target, texture_contracts)
    yobj, compatibility = adapt_yobj(yobj)
    native = audit_yobj(yobj)
    print('Native model built:', len(native['meshes']), 'meshes,', len(yobj), 'bytes', flush=True)
    dump(output/'compatibility.json', compatibility)
    poses = pose_qa(prepared, native, target)
    blocking=[r for r in poses['review_findings'] if r['kind'] in ('analytic-collapse','ocular-envelope-review')]
    if blocking:
        dump(output/'failed-pose-qa.json',poses)
        raise ValueError('Experimental motion QA flagged a regression; PAC export withheld: '+str(blocking))
    unfiltered,_=prepare_trial(charted,target,ocular_support_guard=False)
    unfiltered_yobj=serialize(pack(unfiltered,target),target,texture_contracts)
    unfiltered_yobj,_=adapt_yobj(unfiltered_yobj)
    unfiltered_qa=pose_qa(unfiltered,audit_yobj(unfiltered_yobj),target)
    old_positions,old_weights=arrays(unfiltered)
    new_positions,new_weights=arrays(prepared)
    if not np.array_equal(old_positions,new_positions):raise ValueError('Ocular refinement moved rest geometry')
    jaw=[b['index'] for b in target['bones'] if b['name']=='d_kuchi' or b['name'].startswith('d_kuchi_')]
    jaw_delta=float(np.max(np.abs(old_weights[:,jaw]-new_weights[:,jaw]))) if jaw else 0.
    body_delta=max(float(np.max(np.abs(deform(unfiltered,old_positions,old_weights,p)-deform(prepared,new_positions,new_weights,p)))) for p in POSES.values())
    if jaw_delta or body_delta>1e-7:raise ValueError('Ocular refinement changed jaw/body behavior')
    ocular_refinement=dict(before=unfiltered_qa,after=poses,
        before_control_yobj_sha256=sha(unfiltered_yobj),jaw_coefficient_delta=jaw_delta,
        body_pose_position_delta=body_delta,source_support_guard=rig['ocular_support_guard'])
    dump(output/'ocular-refinement.json',ocular_refinement)
    aligned, _ = align_reference(source_model, target)
    ref, final = geometry(aligned), geometry(native)
    rois = regions(ref, target)
    metrics, heat = surface_measure(ref, final, rois, ref.height, count=4000, with_curvature=True)
    if metrics['maximum_vertex_surface_error']['maximum']/ref.height > 1e-6:
        raise ValueError('Undecimated native source geometry differs unexpectedly')
    pac, gims, texture_report = optimize(base, yobj, native, images, output/'textures', max_bytes)
    restored, restored_gims = validate_pac(pac, base, max_bytes, accessory_models={}, gim_reader=read_gim)
    final_yobj = next(b for s, b in sections(pac) if s['id'] == 2)
    if final_yobj != yobj or restored_gims != gims:
        raise ValueError('Final PAC does not contain the validated model and textures')
    filename = f'SYM-{entry_id}-main-only-EXPERIMENTAL.pac'
    (output/filename).write_bytes(pac)
    (output/'prepared.yobj').write_bytes(final_yobj)
    preview = output/'preview'
    preview.mkdir()
    write_preview(restored, preview/'model.obj')
    lines = []
    for i, name in enumerate(native['texture_names']):
        pixels, palette = read_gim(gims[name])
        Image.fromarray(palette[pixels]).save(preview/(name+'.png'))
        lines += [f'newmtl texture_{i}', 'Kd 1 1 1', f'map_Kd {name}.png']
    (preview/'preview.mtl').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    views = output/'renders'
    views.mkdir()
    all_positions=np.vstack((arrays(aligned)[0],arrays(dict(restored,bone_count=len(restored['bones'])))[0]))
    camera_bounds=[all_positions.min(0).tolist(),all_positions.max(0).tolist()]
    for view in ('front', 'back', 'left', 'right', 'front-left'):
        render_native(restored, gims, view, views/(view+'.png'), label='EXPERIMENTAL PSP | rest',fingerprint=sha(pac),camera_bounds=camera_bounds)
        render_native(aligned,{aligned['textures'][0]:c[p]},view,views/('source-'+view+'.png'),
                      label='Original SYM | uniform alignment',fingerprint=sha(decoded[2]),camera_bounds=camera_bounds)
        pair=Image.new('RGB',(1280,640))
        pair.paste(Image.open(views/('source-'+view+'.png')),(0,0))
        pair.paste(Image.open(views/(view+'.png')),(640,0))
        pair.save(views/('comparison-'+view+'.png'))
    for name in ('standing', 'walk-left', 'bend', 'crouch', 'jaw-18', 'elbow-flex-left'):
        posed_points=[]
        for m in (dict(restored,bone_count=len(restored['bones'])),control):
            points,weights=arrays(m)
            posed_points.append(deform(m,points,weights,POSES[name]))
        pp=np.vstack(posed_points)
        posed_bounds=[pp.min(0).tolist(),pp.max(0).tolist()]
        for model, label in ((restored, 'candidate'), (dict(control, texture_names=control['textures']), 'ancestor-control')):
            render_native(model, gims, 'front-left', views/(label+'-'+name+'.png'),
                label=label+' | synthetic '+name, pose=POSES[name],fingerprint=sha(pac) if label=='candidate' else None,camera_bounds=posed_bounds)
    before_head=head_preview(unfiltered)
    after_head=head_preview(dict(restored,bone_count=len(restored['bones'])))
    for name,pose in [('rest',{}),('eye-x-25',{'l_eye':('x',25),'r_eye':('x',25)}),
                      ('eye-z-25',{'l_eye':('z',25),'r_eye':('z',25)})]:
        points=[]
        for m in (before_head,after_head):
            p0,w0=arrays(m);points.append(deform(m,p0,w0,pose))
        pp=np.vstack(points);bounds=[pp.min(0).tolist(),pp.max(0).tolist()]
        for m,label in ((before_head,'unfiltered'),(after_head,'guarded')):
            render_native(m,gims,'front-left',views/(label+'-'+name+'.png'),
                label=label+' eyes | synthetic '+name,pose=pose,camera_bounds=bounds,
                fingerprint=sha(pac) if label=='guarded' else sha(unfiltered_yobj))
        panel=Image.new('RGB',(1280,640))
        panel.paste(Image.open(views/('unfiltered-'+name+'.png')),(0,0))
        panel.paste(Image.open(views/('guarded-'+name+'.png')),(640,0))
        panel.save(views/('ocular-comparison-'+name+'.png'))
    # No arbitrary per-wrestler patch or reduction. Keep incomplete semantics
    # and omitted source extras prominent instead of presenting a green QA badge.
    extras = [dict(section=sid, sha256=sha(blob), bytes=len(blob)) for sid, blob in decoded.items()
              if blob.startswith(b'YOBJ') and sid != 2]
    report = dict(status='EXPERIMENTAL / HUMAN REVIEW REQUIRED', source_sha256=sha(original),
        entry_id=entry_id, source_model_sha256=sha(decoded[2]), base_sha256=sha(base),
        pac=dict(filename=filename, sha256=sha(pac), bytes=len(pac), budget=max_bytes),
        yobj_sha256=sha(yobj), native_meshes=len(native['meshes']),
        native_vertices=native['report']['vertices'], source_position_records=source_model['source_vertex_count'],
        source_triangles=source_model['triangle_count'], native_triangles=native['report']['triangles'],
        source_meshes=source_model['mesh_count'], texture_count=len(gims),
        decimation=False, geometry_adjustments='One uniform source/base alignment and float32 storage only',
        static_metrics=metrics, analytical_validation=poses,
        ocular_refinement=dict(report='ocular-refinement.json',jaw_coefficient_delta=jaw_delta,body_pose_position_delta=body_delta),
        render_camera=dict(bounds=camera_bounds,resolution=640,shared_reference_candidate=True,
            method='Same view/light/projection with a shared unrendered camera frame; not exported geometry'),
        atlas_sample_equivalence=atlas_report['maximum_sample_rgba_error'],
        omitted_source_model_objects=extras, source_unknown_sections_preserved_in_target=False,
        preserved_target_sections=[s['id'] for s in inspect_pac(base)['sections'] if s['id'] not in (2,9)],
        format_checks='PASS: native offsets/ranges/palettes/weights/relocations, GIMs, base skeleton and unrelated target sections',
        known_limits=['Main-model-only trial; source accessory-state semantics not converted',
            'SYM helper/controller motion unknown; PSP donor mapping hypothesis requires gameplay review',
            'Analytical poses prove serialization consistency, not actual game animation correctness',
            'PSP blood/effect and all costume states not validated',
            'Source atlas/material render semantics not fully reproduced; sampled UV appearance only',
            'Not registered in desktop adapters; production SYM remains disabled'])
    if source.read_bytes() != original or base_path.read_bytes() != base:
        raise RuntimeError('Read-only input changed')
    dump(output/'report.json', report)
    (output/(filename+'.sha256')).write_text(sha(pac)+'  '+filename+'\n', encoding='ascii')
    dump(output/'texture-budget.json', {k: v for k, v in texture_report.items() if k != 'textures'})
    print(json.dumps(dict(pac=report['pac'], triangles=report['native_triangles'],
        omitted_source_objects=extras, status=report['status']), indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--base', required=True, type=Path)
    parser.add_argument('--entry', default='0000')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    run(args.source, args.base, args.entry, args.out)


if __name__ == '__main__':
    main()

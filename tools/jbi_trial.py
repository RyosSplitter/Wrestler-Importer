"""JBI Rock accessory + anatomically constrained arm/hand experiment.

python -m tools.jbi_trial ch.pac --base OWN_PSP_BASE.pac --out NEW_DIRECTORY
Research only: preserves the accepted historical PAC, never enables an adapter.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from desktop.accessories import combined_preview, package_models, validate_accessory
from desktop.core import base_model, validate_pac
from desktop.native import serialize
from desktop.skinning import adapt_yobj
from desktop.texture_optimizer.analysis import model_usage
from desktop.texture_optimizer.candidates import read_gim
from tools.hctp_weights import read_hctp_with_weights
from tools.jbi_rig import arrays, digit_review, finger_chains, refine_arms
from tools.jericho_hybrid_trial import pack
from tools.pac_repack import texture_table
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections, write_preview
from tools.sym_atlas import partition
from tools.sym_rig import prepare_trial
from tools.sym_source import read_atlas, read_ch_directory, sha
from tools.sym_trial import dump, optimize, pose_qa, render_native
from tools.weight_trial_review import deform


def subset(model, section):
    result = copy.deepcopy(model)
    result['meshes'] = [m for m in result['meshes'] if m['source_section'] == section]
    for i, mesh in enumerate(result['meshes']):
        mesh['index'] = i
    result['mesh_count'] = len(result['meshes'])
    result['vertex_count'] = sum(len(m['vertices']) for m in result['meshes'])
    result['triangle_count'] = sum(len(a['triangles']) for m in result['meshes'] for a in m['materials'])
    return result


def geometry_key(model, include_geometry=True):
    return Counter(tuple(min(cs[i:]+cs[:i] for i in range(3)))
        for m in model['meshes'] for a in m['materials'] for tri in a['triangles']
        for cs in [[struct.pack('<3f2f4B3fI', *(m['vertices'][v]['position'] if include_geometry else [0.,0.,0.]),
            *m['vertices'][v]['uv'], *m['vertices'][v]['color'], *(m['vertices'][v]['normal'] if include_geometry else [0.,0.,0.]), a['texture_id']) for v in tri]])


def arm_qa(source, baseline, candidate, donor=None):
    p, before = arrays(baseline); q, after = arrays(candidate); _, sw = arrays(source)
    if geometry_key(baseline,False) != geometry_key(candidate,False):
        raise ValueError('Arm fix changed UV/color/material topology')
    target = candidate
    sb = {b['name']: b['index'] for b in source['bones']}
    tests = {}
    for side in ('l', 'r'):
        sc, tc = finger_chains(source,side), finger_chains(target,side)
        for digit in range(5):
            own = sw[:, sc[digit]].sum(1)>1e-7
            others = np.zeros(len(p), bool)
            for other in range(5):
                if other != digit:
                    others |= sw[:, sc[other]].sum(1)>1e-7
            probe = {target['bones'][tc[digit][0]]['name']: ('z', 35)}
            a = deform(baseline,p,before,probe); b = deform(candidate,q,after,probe)
            leak_before = float(np.linalg.norm(a-p,axis=1)[others].max(initial=0))
            leak_after = float(np.linalg.norm(b-q,axis=1)[others].max(initial=0))
            if leak_after > 1e-7:
                raise ValueError('Independent digit motion moves another source digit')
            own_motion=float(np.linalg.norm(b-q,axis=1)[own].max(initial=0))
            if own_motion<1e-5:raise ValueError('Digit lost all movement under its own controller')
            tests[side+'-digit-'+str(digit)] = dict(probe=probe,
                before_foreign_digit_motion_max=leak_before,
                after_foreign_digit_motion_max=leak_after,
                own_digit_motion_max=own_motion)
    poses = {
        'arms-lowered': {'l_ninoude':('z',65),'r_ninoude':('z',-65)},
        'elbows-bent': {'l_kote':('z',-80),'r_kote':('z',80)},
        'forearm-twist': {'l_kote_x':('x',60),'r_kote_x':('x',-60)},
        'wrist-flex': {'l_te':('z',35),'r_te':('z',-35)},
        'grip': {b['name']:('z',(-1 if b['name'].startswith('l_') else 1)*35)
                 for b in target['bones'] if '_yubi' in b['name']},
        'thumb-only': {'l_yubi00':('z',40),'r_yubi00':('z',-40)}}
    changed = (np.max(np.abs(before-after),axis=1)>1e-7) | (np.linalg.norm(p-q,axis=1)>1e-7)
    rows = []
    offset=0
    for m in baseline['meshes']:
        for a in m['materials']:
            rows += [[offset+i for i in tri] for tri in a['triangles']]
        offset += len(m['vertices'])
    faces=np.asarray(rows)
    rest_areas={label:np.linalg.norm(np.cross(rest[faces[:,1]]-rest[faces[:,0]],rest[faces[:,2]]-rest[faces[:,0]]),axis=1)
                for label,rest in [('before',p),('after',q)]}
    pose_report={}
    for name, probe in poses.items():
        a=deform(baseline,p,before,probe); b=deform(candidate,q,after,probe)
        if not np.isfinite(b).all() or np.max(np.abs(a[~changed]-b[~changed]),initial=0)>1e-7:
            raise ValueError('Arm correction changed an unaffected record')
        stats={}
        for label,points in [('before',a),('after',b)]:
            rest_area=rest_areas[label];usable=rest_area>1e-9
            area=np.linalg.norm(np.cross(points[faces[:,1]]-points[faces[:,0]],points[faces[:,2]]-points[faces[:,0]]),axis=1)
            ratio=area[usable]/rest_area[usable]
            stats[label]=dict(new_collapsed_triangles=int(np.count_nonzero(ratio<1e-6)),
                minimum_area_ratio=float(ratio.min()), maximum_area_ratio=float(ratio.max()))
        if stats['after']['new_collapsed_triangles'] > stats['before']['new_collapsed_triangles']:
            raise ValueError('Arm probe introduced collapsed triangles')
        pose_report[name]=dict(probe=probe, unaffected_position_error=0., **stats)
    # A weights-only correction can pass serialization while stretching the
    # thumb web badly. Compare this stress probe with independent source and
    # native donor references. This envelope is explicit and provisional, not
    # an SVR engine rule or proof of animation equivalence.
    def area_max(model,probe):
        points,weights=arrays(dict(model,bone_count=len(model['bones'])))
        posed=deform(dict(model,bone_count=len(model['bones'])),points,weights,probe)
        triangles=[];offset=0
        for m in model['meshes']:
            for mat in m['materials']:triangles +=[[offset+i for i in tri] for tri in mat['triangles']]
            offset+=len(m['vertices'])
        f=np.asarray(triangles)
        area=lambda a:np.linalg.norm(np.cross(a[f[:,1]]-a[f[:,0]],a[f[:,2]]-a[f[:,0]]),axis=1)
        rest=area(points);usable=rest>1e-9
        return float(np.max(area(posed)[usable]/rest[usable]))
    source_probe={source['bones'][finger_chains(source,side)[0][0]]['name']:('z',40 if side=='l' else -40) for side in ('l','r')}
    source_max=area_max(source,source_probe)
    donor_max=area_max(donor,poses['thumb-only']) if donor is not None else None
    limit=1.5*max(source_max,donor_max or 0)+.25
    observed=pose_report['thumb-only']['after']['maximum_area_ratio']
    if observed>limit:raise ValueError('Thumb-web stress exceeds source/native review envelope')
    stress=dict(source_thumb_area_ratio_max=source_max,native_donor_thumb_area_ratio_max=donor_max,
        candidate_thumb_area_ratio_max=observed,provisional_maximum=limit,
        rule='1.5 * max(original source, native donor) + 0.25; trial review threshold, not a format limit')
    return dict(source_digit_support_before=digit_review(source,target,sw,before),
        source_digit_support_after=digit_review(source,target,sw,after),
        independent_digit_probes=tests, arm_pose_probes=pose_report,thumb_web_reference_stress=stress,
        uv_material_color_topology_exact=True,
        geometry_change='Localized source-to-PSP arm/hand bind conversion; see rig-refinement.json',
        limitation='Controlled synthetic poses, not captured JBI/PSP animation clips'), poses


def crop_region(model, side='l', hand=False):
    """View-only support crop; never changes exported geometry."""
    result=copy.deepcopy(model); p,w=arrays(dict(model,bone_count=len(model['bones'])))
    prefix=side+'_'
    allowed=[b['index'] for b in model['bones'] if b['name'].startswith(prefix) and
        ('_yubi' in b['name'] or b['name'] == prefix+'te' or (not hand and any(s in b['name'] for s in ('kote','ninoude'))))]
    mask=w[:,allowed].sum(1)>1e-7;start=0
    for mesh in result['meshes']:
        local=mask[start:start+len(mesh['vertices'])];start+=len(local)
        for mat in mesh['materials']:
            mat['triangles']=[tri for tri in mat['triangles'] if local[list(tri)].all()]
        mesh['materials']=[m for m in mesh['materials'] if m['triangles']]
        used=sorted({i for a in mesh['materials'] for t in a['triangles'] for i in t})
        mapping={v:i for i,v in enumerate(used)}
        mesh['vertices']=[mesh['vertices'][i] for i in used]
        for a in mesh['materials']:a['triangles']=[[mapping[i] for i in t] for t in a['triangles']]
    result['meshes']=[m for m in result['meshes'] if m['materials']]
    return result


def run(source, base_path, output):
    original=source.read_bytes(); base,target=base_model(base_path)
    directory=read_ch_directory(original); entry=next(e for e in directory['entries'] if e['id_hex']=='0000')
    costume=original[entry['offset']:entry['offset']+entry['stored_bytes']]
    decoded={s['id']:r for s,r in sections(costume)}
    originals={sid:read_hctp_with_weights(decoded[sid]) for sid in (2,6,7)}
    combined=copy.deepcopy(originals[2]);combined['meshes']=[]
    source_roles=[]
    for sid,model in originals.items():
        if model['textures'] != originals[2]['textures']:
            raise ValueError('JBI accessory atlas differs')
        for a,b in zip(model['bones'], originals[2]['bones']):
            if any(a[k]!=b[k] for k in ('name','parent','local_position','rotation')):
                raise ValueError('Source accessory local rig differs')
        p,w=arrays(model)
        support=[b['name'] for b in model['bones'] if np.any(w[:,b['index']]>1e-7)]
        if sid in (6,7):
            side='l' if sid==6 else 'r'
            if any(not n.startswith(side+'_') or not any(t in n for t in ('kote','ninoude')) for n in support):
                raise ValueError('Source extra does not have verified unilateral elbow support')
        source_roles.append(dict(section=sid,vertices=len(p),triangles=model['triangle_count'],
            support=support,bounds=[p.min(0).tolist(),p.max(0).tolist()],sha256=sha(decoded[sid])))
        for mesh in copy.deepcopy(model['meshes']):
            mesh['source_section']=sid;mesh['index']=len(combined['meshes']);combined['meshes'].append(mesh)
    combined['mesh_count']=len(combined['meshes'])
    combined['triangle_count']=sum(m['triangle_count'] for m in originals.values())
    pix,pal,_=read_atlas(decoded[1])
    charted,images,atlas=partition(combined,pal[pix])
    old,rig=prepare_trial(charted,target)
    prepared,refinement=refine_arms(charted,target,old,rig['alignment'])
    qa,probes=arm_qa(charted,old,prepared,target)
    output.mkdir(parents=True,exist_ok=False)
    dump(output/'atlas.json',atlas);dump(output/'rig-refinement.json',refinement);dump(output/'arm-qa.json',qa)
    dump(output/'source-roles.json',source_roles)
    native_bytes={};expected={};pose_reports={}
    usage=model_usage({2:dict(prepared,texture_names=prepared['textures'])},dict(zip(prepared['textures'],images)))
    contracts=[dict(bits=8 if usage[n]['head_fraction']>.5 or np.any(im[:,:,3]<255) else 4,
                    cutout=bool(np.any(im[:,:,3]<255))) for n,im in zip(prepared['textures'],images)]
    for source_sid,target_sid,name in ((2,2,target['model_name']),(6,26,'L_elb'),(7,27,'R_elb')):
        obj=subset(prepared,source_sid); packed=pack(obj,target); donor=copy.deepcopy(target)
        # A two-segment source digit may form a two-slot draw. Use its native
        # third phalanx as an explicitly zero-weight slot to match the observed
        # three-slot native draw convention without inventing an influence.
        # This is an experimental layout choice, not a claimed two-slot ban.
        for mesh in packed['meshes']:
            names=[target['bones'][i]['name'] for i in mesh['bone_palette']]
            if len(names)==2 and all('_yubi' in n for n in names) and len({n[:-1] for n in names})==1:
                third=next(b['index'] for b in target['bones'] if b['name']==names[0][:-1]+'2')
                if third not in mesh['bone_palette']:
                    mesh['bone_palette'].append(third)
                    for v in mesh['vertices']:v['weights'].append(0.)
        if target_sid!=2:
            label=name.encode('ascii').ljust(16,b'\0')
            donor['model_name_raw']=label;donor['model_descriptor_raw']=label+donor['model_descriptor_raw'][16:]
            raw=bytearray(donor['bone_raw'])
            # Preserve all local/bind/radius bytes, using the same sparse
            # per-object sphere-center convention as the existing pad writer.
            points,weights=arrays(obj)
            for b in target['bones']:
                support=points[weights[:,b['index']]>1e-7]
                center=(support.min(0)+support.max(0))/2 if len(support) else np.zeros(3)
                struct.pack_into('<3f',raw,80*b['index']+64,*center)
            donor['bone_raw']=bytes(raw)
        raw=serialize(packed,donor,contracts)
        if target_sid==2:
            raw,compat=adapt_yobj(raw);dump(output/'compatibility.json',compat)
        native=audit_yobj(raw)
        pose_reports[str(target_sid)]=pose_qa(obj,native,target if target_sid==2 else None)
        blocking=[r for r in pose_reports[str(target_sid)]['review_findings']
                  if r['kind'] in ('analytic-collapse','ocular-envelope-review')]
        if blocking:
            dump(output/'failed-native-pose-qa.json',pose_reports)
            raise ValueError('Native body/ocular pose QA needs review: '+str(pose_reports[str(target_sid)]['review_findings']))
        if target_sid!=2:
            validate_accessory(packed,native);expected[target_sid]=packed
        native_bytes[target_sid]=raw
        (output/('main.yobj' if target_sid==2 else name+'.yobj')).write_bytes(raw)
    dump(output/'native-pose-qa.json',pose_reports)
    old_table=next(r for s,r in sections(base) if s['id']==9)
    provisional=package_models(base,native_bytes[2],old_table,{i:r for i,r in native_bytes.items() if i!=2})
    texture_usage_model=combined_preview(audit_yobj(native_bytes[2]),
        [audit_yobj(native_bytes[sid]) for sid in (26,27)])
    pac,gims,texture_report=optimize(provisional,native_bytes[2],texture_usage_model,images,output/'textures',148000)
    table=texture_table(prepared['textures'],[gims[n] for n in prepared['textures']],gim_reader=read_gim)
    if pac!=package_models(base,native_bytes[2],table,{i:r for i,r in native_bytes.items() if i!=2}):
        raise ValueError('Canonical model-set packaging differs')
    native,gims=validate_pac(pac,base,148000,accessory_models=expected,gim_reader=read_gim)
    final_models={s['id']:audit_yobj(r) for s,r in sections(pac) if r.startswith(b'YOBJ')}
    for sid,raw in native_bytes.items():
        if next(r for s,r in sections(pac) if s['id']==sid)!=raw:
            raise ValueError('Final PAC differs from validated YOBJ')
    visual=combined_preview(native,[final_models[26],final_models[27]])
    preview=output/'preview';preview.mkdir();write_preview(visual,preview/'JBI-Rock-with-pads.obj')
    lines=[]
    for i,n in enumerate(visual['texture_names']):
        p,c=read_gim(gims[n]);Image.fromarray(c[p]).save(preview/(n+'.png'))
        lines += [f'newmtl texture_{i}','Kd 1 1 1',f'map_Kd {n}.png']
    (preview/'preview.mtl').write_text('\n'.join(lines)+'\n')
    filename='JBI-Rock-arms-and-elbow-pads-EXPERIMENTAL.pac'
    (output/filename).write_bytes(pac)
    (output/(filename+'.sha256')).write_text(sha(pac)+'  '+filename+'\n')
    views=output/'renders';views.mkdir()
    before_visual=dict(old,texture_names=old['textures'])
    for view in ('front','back','left','right','front-left'):
        points=arrays(dict(visual,bone_count=len(visual['bones'])))[0]
        bounds=[points.min(0).tolist(),points.max(0).tolist()]
        render_native(visual,gims,view,views/(view+'.png'),label='JBI trial | final PAC re-extracted | CPU render',fingerprint=sha(pac),camera_bounds=bounds)
    # Identical textures and camera isolate weights from texture allocation.
    for crop,hand in [('arm',False),('hand',True)]:
        a=crop_region(before_visual,hand=hand);b=crop_region(visual,hand=hand)
        for name,pose in [('rest',{}),*probes.items()]:
            points=[]
            for m in (a,b):
                p,w=arrays(dict(m,bone_count=len(m['bones'])));points.append(deform(dict(m,bone_count=len(m['bones'])),p,w,pose))
            pp=np.vstack(points);bounds=[pp.min(0).tolist(),pp.max(0).tolist()]
            for model,label in [(a,'before'),(b,'after')]:
                render_native(model,gims,'front-left',views/(crop+'-'+name+'-'+label+'.png'),
                    label=label+' | CPU synthetic '+name,pose=pose,camera_bounds=bounds,
                    fingerprint=sha(pac) if label=='after' else None)
            pair=Image.new('RGB',(1280,640))
            for i,label in enumerate(('before','after')):pair.paste(Image.open(views/(crop+'-'+name+'-'+label+'.png')),(i*640,0))
            pair.save(views/(crop+'-'+name+'-comparison.png'))
    if source.read_bytes()!=original or base_path.read_bytes()!=base:
        raise ValueError('Input changed')
    report=dict(status='EXPERIMENTAL; PPSSPP review required',source_game='JBI per owner correction; historical SYM title was erroneous',
        archive_sha256=sha(original),costume_id='0000',source_roles=source_roles,
        pac=dict(filename=filename,bytes=len(pac),sha256=sha(pac),budget=148000),
        models={sid:dict(sha256=sha(native_bytes[sid]),**m['report']) for sid,m in final_models.items()},
        total_triangles=sum(m['report']['triangles'] for m in final_models.values()),
        texture_count=len(gims),texture_pixel_palette_bytes=texture_report['pixel_palette_bytes'],
        source_geometry_changed=True,geometry_change='Localized arm/hand bind-reference conversion; shoulder surface anchors pinned; torso/head/legs unchanged',decimation=False,unrelated_production_code_changed=False,
        native_skeleton_main_exact=True,accessory_local_bind_exact=True,
        packaging='Unchanged desktop.accessories.package_models; byte-exact callback comparison',
        limitations=['JBI helper animation semantics inferred, not captured from the game',
            'Local hand-frame correspondence and JBI helper-controller semantics still require gameplay review',
            'Pad draw/removal/throw semantics need in-game review; no unknown source event data copied',
            'CPU comparison renders and analytical QA are not PPSSPP or Noesis screenshots'])
    dump(output/'report.json',report)
    print(json.dumps(dict(pac=report['pac'],triangles=report['total_triangles'],textures=report['texture_count']),indent=2),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    p.add_argument('--base',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();run(args.source,args.base,args.out)


if __name__=='__main__':main()

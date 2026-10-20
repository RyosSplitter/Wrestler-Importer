"""Export the exact experimental AJ PAC, static Noesis preview and QA evidence."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

import numpy as np
from PIL import Image

from model_qa.pipeline import POSES
from tools.prepare_model import bone_matrices
from tools.psp_mesh_merge_trial import sections, write_preview
from tools.sym_rig import arrays
from tools.sym_trial import render_native
from tools.tna_obj_trial import validate_trial_pac, dump
from tools.weight_trial_review import deform, skin_matrices
from tools.wwe13_export_trial import crop
from tools.wwe13_pose_trial import hand_probes
from desktop.core import base_model
from desktop.texture_optimizer.candidates import read_gim


def posed_model(model, pose):
    """PSP-style blended normal rotations, retaining original smoothing corners."""
    out = copy.deepcopy(model); out['bone_count'] = len(model['bones'])
    p,w = arrays(out); q = deform(out,p,w,pose); matrices = skin_matrices(out,pose)
    normals = np.array([v['normal'] for m in out['meshes'] for v in m['vertices']])
    posed_normals = sum(w[:,i,None]*(normals@matrix[:3,:3].T) for i,matrix in enumerate(matrices))
    posed_normals /= np.maximum(np.linalg.norm(posed_normals,axis=1,keepdims=True),1e-12)
    for i,v in enumerate(v for m in out['meshes'] for v in m['vertices']):
        v['position']=q[i].tolist();v['normal']=posed_normals[i].tolist()
    return out


def export(work, base_path, texture, output):
    work,base_path,texture,output = map(Path,(work,base_path,texture,output))
    result = json.loads((work/'result.json').read_text()); data=(work/result['pac']).read_bytes()
    fingerprint=hashlib.sha256(data).hexdigest()
    if result['sha256'] != fingerprint:
        raise ValueError('PAC changed after build')
    binding=json.loads((work/'binding-report.json').read_text())
    native,gims=validate_trial_pac(data,base_path.read_bytes(),binding['facial_binding'])
    raw=next(r for s,r in sections(data) if s['id']==2)
    if raw!=(work/'candidate.yobj').read_bytes():
        raise ValueError('Final PAC differs from audited model')
    native['bone_count']=len(native['bones'])
    reference=json.loads((work/'prepared.json').read_text());reference['texture_names']=reference['textures']
    source_images={'aj_diffuse':np.array(Image.open(texture).convert('RGBA'))}
    output.mkdir(parents=True,exist_ok=False);preview=output/'preview';preview.mkdir();views=output/'comparisons';views.mkdir()
    (output/result['pac']).write_bytes(data);(preview/'prepared.yobj').write_bytes(raw)
    write_preview(native,preview/'preview.obj');mtl=[]
    for i,name in enumerate(native['texture_names']):
        (preview/(name+'.gim')).write_bytes(gims[name]);ix,palette=read_gim(gims[name]);Image.fromarray(palette[ix]).save(preview/(name+'.png'))
        mtl += ['newmtl texture_'+str(i),'Kd 1 1 1','d 1','map_Kd '+name+'.png','']
    (preview/'preview.mtl').write_text('\n'.join(mtl)+'\n')
    points=np.array([v['position'] for m in reference['meshes'] for v in m['vertices']]);frame=[points.min(0),points.max(0)]
    def pair(a,b,label,view,framing):
        src=views/('source-'+label+'.png');dst=views/('psp-'+label+'.png')
        render_native(a,source_images,view,src,label='SOURCE SHAPE / INFERRED PSP RIG',camera_bounds=framing)
        render_native(b,gims,view,dst,label='FINAL EXPERIMENTAL PSP PAC',fingerprint=fingerprint,camera_bounds=framing)
        sheet=Image.new('RGB',(1280,640));sheet.paste(Image.open(src),(0,0));sheet.paste(Image.open(dst),(640,0));sheet.save(views/('comparison-'+label+'.png'))
    for view in ('front','back','left','right','front-left'):
        pair(reference,native,view,view,frame)
    for kind in ('head','pelvis'):
        a,b=crop(reference,kind),crop(native,kind)
        points=np.array([v['position'] for m in a['meshes'] for v in m['vertices']]);f=[points.min(0),points.max(0)]
        for view in ('front','left') if kind=='head' else ('back','left'):
            pair(a,b,kind+'-'+view,view,f)
    for name in ('standing','walk-left','bend','crouch','elbow-flex-left','jaw-18'):
        a,b=posed_model(reference,POSES[name]),posed_model(native,POSES[name])
        points=np.array([v['position'] for m in a['meshes'] for v in m['vertices']])
        pair(a,b,'pose-'+name,'front-left',[points.min(0),points.max(0)])
    grip={b['name']:('z',-35 if b['name'].startswith('l_') else 35) for b in native['bones'] if '_yubi' in b['name']}
    a,b=posed_model(reference,grip),posed_model(native,grip)
    points=np.array([v['position'] for m in a['meshes'] for v in m['vertices']])
    pair(a,b,'synthetic-finger-flex','front-left',[points.min(0),points.max(0)])
    for name,pose in [('eye-turn',{'l_eye':('y',25),'r_eye':('y',25)}),
                      ('blink',{'l_mabuta':('x',30),'r_mabuta':('x',30)})]:
        a,b=crop(posed_model(reference,pose),'head'),crop(posed_model(native,pose),'head')
        points=np.array([v['position'] for m in a['meshes'] for v in m['vertices']])
        pair(a,b,name,'front',[points.min(0),points.max(0)])
    native_hands=hand_probes(native);reference_hands=hand_probes(reference)
    _,base=base_model(base_path);base_hands=hand_probes(base)
    hand_review=[]
    for name in ('grip','finger-extension','wrist-flex','forearm-twist'):
        donor=base_hands['tests'][name]['maximum_triangle_area_ratio'];observed=native_hands['tests'][name]['maximum_triangle_area_ratio']
        limit=1.5*donor+.25
        if observed>limit:
            hand_review.append(dict(pose=name,maximum_area_ratio=observed,native_base_ratio=donor,provisional_limit=limit,
                inferred_full_precision_binding_ratio=reference_hands['tests'][name]['maximum_triangle_area_ratio'],
                interpretation='Synthetic hand stretch review; source TNA weights unavailable; not a measured original-game regression'))
    dump(output/'hand-stress.json',dict(native=native_hands,inferred_reference=reference_hands,native_base=base_hands,review_findings=hand_review))
    shutil.copytree(work/'qa',output/'qa')
    for name in ('result.json','binding-report.json','native-checks.json','weight-precision.json','source-report.json','atlas-report.json','bounds-check.json'):
        if (work/name).exists():shutil.copy2(work/name,output/name)
    shutil.copy2(work/'textures/report.json',output/'texture-report.json')
    qa=json.loads((work/'qa/report.json').read_text());tex=json.loads((work/'textures/report.json').read_text())
    summary=dict(result,qa_review_findings=len(qa['flags']),hand_stress_review_findings=hand_review,
        all_source_triangles_preserved=True,source_static_shape_p95_height=qa['rest']['overall']['p95_height'],
        pixel_palette_bytes=tex['pixel_palette_bytes'],native_base_texture_envelope=tex['native_base_memory_envelope'],
        raw_yobj_bytes=len(raw),yobj_sha256=hashlib.sha256(raw).hexdigest(),preview_pac_exact=True,
        original_source_motion_validation='UNAVAILABLE: OBJ has no source rig or weights',
        preview_provenance='CPU renders, not Noesis/PPSSPP screenshots',game_tested=False,qa_approved=False)
    dump(output/'summary.json',summary)
    (output/'README.txt').write_text('AJ Styles TNA OBJ -> SVR 2011 PSP EXPERIMENT\n\n'
        'Use AJ-Styles-TNA-PSP-EXPERIMENTAL.pac for the game test.\n'
        'The file is '+str(len(data))+' bytes, below the 148,000-byte configured limit.\n'
        'All 3,565 source triangles are retained. No decimation.\n'
        'A uniform scale/orientation change aligns the OBJ to the PSP donor.\n'
        'Bounded position/normal/UV precision changes are documented in native-checks.json.\n'
        'The OBJ has NO skeleton, weights or animations: this is a newly inferred PSP binding.\n'
        'The PSP donor hierarchy and local rotation axes are retained. Twenty-four facial\n'
        'controller local positions are fitted using the source eye-sphere centers.\n'
        'Inferred influence-sphere radii are conservatively expanded to enclose AJ;\n'
        'their centers and all local rotation axes remain unchanged.\n'
        'This is intentional experimental rigging; production skeleton validation is unchanged.\n'
        'Native structural checks and analytical eye envelopes pass.\n'
        'Synthetic finger-flex/extension stress still flags hand stretching; inspect grips in-game.\n'
        'NOT QA-approved, NOT tested in PPSSPP, NOT added to the production app.\n\n'
        'Back up CH.PAC/ISO, inject using your established workflow, update/rebuild\n'
        'the containing archive/ARC and save the ISO. Restart PPSSPP; use a fresh match.\n'
        'Check entrances, standing, walking, crouching, attacks/grips, eyes, jaw and victory.\n\n'
        'Noesis: open preview/preview.obj beside preview.mtl and PNGs. Apply your usual\n'
        'orientation, face-cull and shading toggles. prepared.yobj is exactly the expanded\n'
        'main model inside this final PAC. OBJ is static and contains no skinning.\n\n'
        'comparisons/ contains identically framed CPU source/final renders. Posed source\n'
        'views use the INFERRED PSP rig, not recovered TNA animation. Smoothed source\n'
        'normals are skinned per vertex for these previews, without changing PAC normals.\n'
        'The reused QA report has legacy HCTP wording; here its source is the original\n'
        'OBJ shape with the shared inferred PSP rig. It cannot verify authentic TNA motion.\n'
        'qa/report.html retains all findings; hand-stress.json adds native-donor comparisons.\n'
        'Stored PAC size and observed texture envelope do not prove total runtime heap safety.\n\n'
        'PAC SHA-256: '+fingerprint+'\n')
    (output/'START-HERE.html').write_text('<!doctype html><meta charset="utf-8"><title>AJ Styles PSP experiment</title>'
        '<h1>AJ Styles — experimental PSP conversion</h1><p>'+str(len(data))+' bytes; all 3,565 triangles retained.</p>'
        '<p>Newly inferred PSP rig. Hand stress findings remain. Not game-tested or QA-approved.</p>'
        '<p><a href="README.txt">Instructions and limitations</a> · <a href="qa/report.html">QA report</a></p>'
        '<p>Original OBJ/texture (left), decoded final PAC (right). CPU renders, not game captures.</p>'
        +''.join('<p><img width="100%" src="comparisons/comparison-'+label+'.png"></p>' for label in ('front','back','left','head-front','head-left','pose-standing','pose-jaw-18','eye-turn')))
    dump(output/'SHA256-MANIFEST.json',[dict(path=f.relative_to(output).as_posix(),bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in sorted(output.rglob('*')) if f.is_file()])
    archive=output.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in sorted(output.rglob('*')):
            if f.is_file():z.write(f,arcname=output.name+'/'+f.relative_to(output).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failure')
        for row in json.loads((output/'SHA256-MANIFEST.json').read_text()):
            b=z.read(output.name+'/'+row['path'])
            if len(b)!=row['bytes'] or hashlib.sha256(b).hexdigest()!=row['sha256']:raise ValueError('ZIP manifest mismatch')
    print(json.dumps(summary,indent=2));print(archive)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('work',type=Path)
    p.add_argument('--base',type=Path,required=True);p.add_argument('--texture',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();export(a.work,a.base,a.texture,a.out)

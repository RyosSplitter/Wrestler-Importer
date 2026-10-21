"""Package actual decoded-PAC evidence and a static Noesis preview for its owner."""
from desktop.limits import IN_RING_MAX_PAC_BYTES
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

import numpy as np
from PIL import Image

from desktop.core import validate_pac
from desktop.texture_optimizer.candidates import read_gim
from model_qa.pipeline import POSES
from tools.psp_mesh_merge_trial import sections, write_preview
from tools.sym_trial import render_native


def crop(model, kind):
    model = copy.deepcopy(model)
    for mesh in model['meshes']:
        ps = np.array([v['position'] for v in mesh['vertices']])
        mask = (ps[:,1] < -7.05) & (np.abs(ps[:,0]) < 1.7) if kind == 'head' else (ps[:,1] > -3) & (ps[:,1] < 2.5) & (np.abs(ps[:,0]) < 3.)
        for mat in mesh['materials']:
            mat['triangles'] = [t for t in mat['triangles'] if mask[list(t)].all()]
        mesh['materials'] = [a for a in mesh['materials'] if a['triangles']]
        used = sorted({i for a in mesh['materials'] for t in a['triangles'] for i in t})
        mapping = {old:new for new,old in enumerate(used)}
        mesh['vertices'] = [mesh['vertices'][i] for i in used]
        for mat in mesh['materials']:
            mat['triangles'] = [[mapping[i] for i in t] for t in mat['triangles']]
    model['meshes'] = [m for m in model['meshes'] if m['materials']]
    return model


def export(work, base, output):
    work, base, output = map(Path, (work, base, output))
    result = json.loads((work/'result.json').read_text())
    data = (work/result['pac']).read_bytes(); fingerprint = hashlib.sha256(data).hexdigest()
    if fingerprint != result['sha256']:
        raise ValueError('PAC no longer matches completed run')
    native, gims = validate_pac(data, base.read_bytes(), IN_RING_MAX_PAC_BYTES, accessory_models={}, gim_reader=read_gim)
    native['bone_count'] = len(native['bones'])
    raw = next(r for s,r in sections(data) if s['id'] == 2)
    if raw != (work/'candidate.yobj').read_bytes():
        raise ValueError('PAC model differs from QA-native model')
    output.mkdir(parents=True, exist_ok=False)
    preview = output/'preview'; preview.mkdir()
    comparisons = output/'comparisons'; comparisons.mkdir()
    (output/result['pac']).write_bytes(data); (preview/'prepared.yobj').write_bytes(raw)
    write_preview(native, preview/'preview.obj'); mtl = []
    for i,name in enumerate(native['texture_names']):
        (preview/(name+'.gim')).write_bytes(gims[name])
        pixels, colors = read_gim(gims[name]); Image.fromarray(colors[pixels]).save(preview/(name+'.png'))
        mtl += ['newmtl texture_'+str(i), 'Kd 1 1 1', 'd 1', 'map_Kd '+name+'.png', '']
    (preview/'preview.mtl').write_text('\n'.join(mtl)+'\n')
    reference = json.loads((work/'charted.json').read_text()); reference['texture_names'] = reference['textures']
    source_images = {n: np.array(Image.open(work/'source-images'/(n+'.png'))) for n in reference['textures']}
    points = np.array([v['position'] for m in reference['meshes'] for v in m['vertices']])
    bounds = [points.min(0), points.max(0)]
    def pair(a, b, view, label, frame):
        src, dst = comparisons/('source-'+label+'.png'), comparisons/('psp-'+label+'.png')
        render_native(a, source_images, view, src, label='FULL-DETAIL SOURCE | PSP REFERENCE POSE', camera_bounds=frame)
        render_native(b, gims, view, dst, label='DECODED EXPERIMENTAL PSP PAC', fingerprint=fingerprint, camera_bounds=frame)
        image = Image.new('RGB', (1280,640)); image.paste(Image.open(src),(0,0)); image.paste(Image.open(dst),(640,0))
        image.save(comparisons/('comparison-'+label+'.png'))
    for view in ('front','back','left','right','front-left'):
        pair(reference, native, view, view, bounds)
    for kind in ('head','pelvis'):
        a,b = crop(reference,kind), crop(native,kind)
        points = np.array([v['position'] for m in a['meshes'] for v in m['vertices']]); frame=[points.min(0),points.max(0)]
        for view in (('front','left') if kind=='head' else ('back','left')):
            pair(a,b,view,kind+'-'+view,frame)
    for name in ('standing','walk-left','crouch','elbow-flex-left','jaw-18'):
        render_native(native,gims,'front-left',comparisons/('pose-'+name+'.png'),label='ANALYTICAL PSP RIG | '+name,
                      pose=POSES[name],fingerprint=fingerprint)
    shutil.copytree(work/'qa',output/'qa')
    for filename in ('result.json','native-checks.json','contracts.json','ocular.json','profile.json','rig.json','atlas.json','source-materials.json'):
        shutil.copy2(work/filename, output/filename)
    shutil.copy2(work/'textures/report.json',output/'texture-report.json')
    qa=json.loads((work/'qa/report.json').read_text())
    original=json.loads((work/'source.json').read_text())
    summary=dict(result, source_stored_vertices=original['vertex_count'],
        source_chart_vertex_records=reference['vertex_count'], source_meshes=original['mesh_count'],
        source_strip_triangles=reference['triangle_count'], final_meshes=len(native['meshes']),
        final_stored_vertices=sum(len(m['vertices']) for m in native['meshes']),
        final_triangles=sum(len(a['triangles']) for m in native['meshes'] for a in m['materials']),
        final_textures=len(gims), final_bones=len(native['bones']), expanded_yobj_bytes=len(raw),
        final_material_draw_records=sum(len(m['materials']) for m in native['meshes']),
        final_yobj_sha256=hashlib.sha256(raw).hexdigest(), reference_comparison='Full-detail source in adapted PSP reference pose',
        geometric_p95_height=qa['rest']['overall']['p95_height'],
        qa_caveat='Provisional source-fidelity review findings remain; not QA-approved or game-tested',
        preview_provenance='CPU renders of exact final decoded PAC; not Noesis or PPSSPP screenshots')
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (output/'README.txt').write_text('WWE 13 Jericho -> SVR 2011 PSP: EXPERIMENTAL COMPATIBILITY TEST\n\n'
        'This is NOT an accepted conversion. Structural/native pose checks pass,\n'
        'but source-fidelity QA retains review findings after heavy reduction.\n'
        'The working app and accepted HCTP/JBI PACs have not changed.\n\n'
        'Use WWE13-Jericho-PSP-EXPERIMENTAL.pac for your game test.\n'
        'Back up CH.PAC and the ISO. Inject using your established PAC Editor\n'
        'workflow, update/rebuild the containing archive/ARC and save the ISO.\n'
        'Restart PPSSPP and start a fresh match; an old save state may retain old data.\n'
        'Inspect entrance, standing/walking, bending, attacks, hand grips, eyes,\n'
        'jaw expressions and victory. The first source costume only is converted.\n\n'
        'For Noesis: open preview/preview.obj with preview.mtl and its PNGs\n'
        'beside it. Use your usual orientation/cull/shading toggles as needed.\n'
        'prepared.yobj is EXACTLY the expanded model inside this PAC.\n'
        'The OBJ is static; it cannot demonstrate game animation compatibility.\n\n'
        'comparisons/ contains identically framed source/final CPU renders and\n'
        'analytical PSP-rig poses, NOT captured source-game/PPSSPP/Noesis frames.\n'
        'qa/report.html and qa/report.json retain all automated findings.\n'
        'See summary.json, native-checks.json and texture-report.json for details.\n'
        'Dynamic source hair/muscle/sweat/specular effects are not ported.\n'
        'Hair opacity is an inferred material bake with resampled binary cutouts.\n'
        'Texture memory is constrained to an observed native-base envelope;\n'
        'total game heap and GPU stability still require PPSSPP testing.\n\n'
        'PAC SHA-256: '+fingerprint+'\n')
    manifest=[]
    for f in sorted(output.rglob('*')):
        if f.is_file():
            content=f.read_bytes();manifest.append(dict(path=f.relative_to(output).as_posix(),bytes=len(content),sha256=hashlib.sha256(content).hexdigest()))
    (output/'SHA256-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    archive=output.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in sorted(output.rglob('*')):
            if f.is_file(): z.write(f,arcname=output.name+'/'+f.relative_to(output).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('Export ZIP checksum failure')
    print(json.dumps(summary,indent=2));print(archive,archive.stat().st_size,hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('work',type=Path);p.add_argument('--base',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();export(a.work,a.base,a.out)

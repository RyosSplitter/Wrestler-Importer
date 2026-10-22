"""Isolated experimental WWE '13 Wii job; existing converters stay independent."""
import contextlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import time
import numpy as np
from PIL import Image

from desktop.core import Cancelled,digest,dump
from desktop.preview import save_views
from desktop.texture_optimizer.candidates import read_gim
from desktop.adapters.wwe13_wii import selected_index
from desktop.wii_textures import allocate
from tools.psp_effect_storage_trial import compact_effect_storage
from tools.psp_mesh_merge_trial import sections,write_preview
from tools.wwe13_wii_corpus import bundles,verified_source_bundle as source_bundle
from tools.wwe13_wii_trial import run as build_wii,validate_trial
from tools.wwe13_budget import budget
from model_qa.pipeline import run as compare
from model_qa.geometry import read_model
from model_qa.surface_attributes import compare as surface_compare
from model_qa.alpha_coverage import report as alpha_report
from model_qa.palette_quality import representation
from desktop.texture_optimizer.analysis import model_usage


def run_job(request,work,progress=lambda p,m:None,cancel=lambda:False,*,qa_samples=None,qa_resolution=None):
    request.validate();work=Path(work);work.mkdir(parents=True,exist_ok=True)
    source,base=Path(request.source),Path(request.base)
    inputs={str(p.resolve()):digest(p) for p in (source,base)}
    def check():
        if cancel():raise Cancelled('Wii conversion cancelled.')
    def step(percent,message):check();progress(percent,message)
    def command(args,logpath,env):
        check()
        with Path(logpath).open('w',encoding='utf-8') as log:
            child=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,env=env,
                creationflags=0x08000000 if os.name=='nt' else 0)
            try:
                while child.poll() is None:check();time.sleep(.1)
                if child.returncode:raise ValueError('Wii geometry processing failed; read '+str(logpath))
            except BaseException:
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=5)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
                raise
    step(2,'Inspecting Wii containers and your PSP base')
    index=selected_index(request.source_entry,len(bundles(source.read_bytes())))
    limits=budget(request.costume_role)
    compact,storage=compact_effect_storage(base.read_bytes())
    reference=work/'storage-reference.pac';reference.write_bytes(compact)
    dump(work/'effect-storage.json',storage)
    # Optional extra locks use the tested clothing-region scope. Face and hand
    # reduction settings and existing shared-joint guards stay independent.
    folder=work/'wii';ratio=.45 if index==0 else .35
    hand_floor=.75 if request.wii_geometry=='Preserve Hands' else .5
    arm_floor=.75 if request.wii_geometry=='Preserve Arms' else None
    step(6,'Adapting Wii rig, then reducing geometry with the tested profile')
    with (work/'wii.log').open('w',encoding='utf-8',buffering=1) as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        built=build_wii(source,reference,folder,index,ratio=ratio,head_floor=.6,hand_floor=hand_floor,arm_floor=arm_floor,mouth_ratio=.6,
            material_only=True,source_reader=source_bundle,atlas_options=dict(repeat_safe=True),export_face_floor=True,
            costume_role=request.costume_role,command_runner=command,texture_allocator=allocate,
            protect_clothing_seams=request.wii_seam_protection,
            progress=lambda message,**kw:step(45,message))
        check()
        candidate=folder/built['pac'];payload=candidate.read_bytes()
        stem=re.sub('[^A-Za-z0-9_.-]','_',source.stem)[:40].strip('.') or 'WWE13'
        final=work/(stem+'-'+f'{index:02d}'+'-'+request.costume_role+'-Wii-PSP-experimental.pac')
        candidate.rename(final);candidate=final
        built['pac']=str(final.resolve());dump(folder/'result.json',built)
        checks=json.loads((folder/'native-checks.json').read_text(encoding='utf-8'))
        ocular=json.loads((folder/'ocular.json').read_text(encoding='utf-8'))
        native,gims,structural=validate_trial(payload,compact,checks['radius_changes'],ocular['source_controller_pivot_fit'],costume_role=request.costume_role)
        step(65,'Comparing source geometry, analytical poses and head controllers')
        qa=compare(folder/'charted.json',candidate,work/'qa',samples=qa_samples or 6000,resolution=qa_resolution or 128,
            max_pac_bytes=limits['max_pac_bytes'],animations=True,renders=True,
            progress=lambda message:step(70,'QA: '+message))
        reference_model=read_model(folder/'charted.json')
        images={n:np.array(Image.open(folder/'source-images'/(n+'.png'))) for n in reference_model['textures']}
        step(84,'Checking UV placement, cutout strands and palette loss')
        attributes=surface_compare(reference_model,read_model(candidate),images,samples=qa_samples or 6000)
        opacity=alpha_report(reference_model,images,{n:read_gim(g)[1][read_gim(g)[0]] for n,g in gims.items()})
        usage=model_usage({2:dict(reference_model,texture_names=reference_model['textures'])},images)
        colors={n:representation(images[n],read_gim(g)[1][read_gim(g)[0]],usage[n]['uv_mask']) for n,g in gims.items() if np.all(images[n][:,:,3]==255)}
        for filename,value in [('surface-attributes',attributes),('opacity-support',opacity),('palette-quality',colors),('native-final',structural)]:dump(work/'qa'/(filename+'.json'),value)
        preview=work/'preview';preview.mkdir();write_preview(native,preview/'output.obj')
        raw=next(r for s,r in sections(payload) if s['id']==2);(preview/'output.yobj').write_bytes(raw)
        lines=[]
        for i,name in enumerate(native['texture_names']):
            ix,pal=read_gim(gims[name]);Image.fromarray(pal[ix]).save(preview/(name+'.png'))
            (preview/(name+'.gim')).write_bytes(gims[name])
            lines+=['newmtl texture_%d'%i,'Kd 1 1 1','map_Kd '+name+'.png']
        (preview/'preview.mtl').write_text('\n'.join(lines)+'\n',encoding='ascii')
        step(90,'Rendering the actual final Wii-to-PSP PAC')
        save_views(native,gims,preview,gim_reader=read_gim)
    check()
    for path,expected in inputs.items():
        if digest(path)!=expected:raise ValueError('An input changed during conversion; output withheld.')
    if final.read_bytes()!=payload:raise ValueError('Review candidate changed during QA; output withheld.')
    flags=len(qa['flags'])+int(attributes['overall']['review'])+int(opacity['review'])
    report=work/'qa/app-report.html'
    report.write_text('\n'.join([
        '<!doctype html><html><meta charset="utf-8"><title>WWE 13 Wii experimental QA</title><body>',
        '<h1>WWE ’13 Wii → SVR 2011 PSP — experimental</h1>',
        '<p>%s, costume %02d, %s. %s / %s bytes. %d review findings.</p>'%(html.escape(source.name),index,request.costume_role,f'{len(payload):,}',f"{limits['max_pac_bytes']:,}",flags),
        '<p>Native structure and analytical pose gates passed. This is not in-game validation. Some Wii hair, hands, clothing, facial color and body shapes still require review; known bad global geometry rules remain disabled. Dynamic Wii blood/hair animation is not reproduced. Unknown layouts are rejected.</p>',
        '<p>Existing material-domain reduction and rig mapping; measured texture allocation with source-nearest alpha and a half-source cutout floor. Opaque 16-color candidates may use lossless T4 storage; only corresponding material depth words change. Section 8 may be BPE-compressed with every decoded effect byte preserved. No UV atlas remapping is enabled.</p>',
        '<p>Protect clothing seams: %s. Extra UV contact locks apply to Arms, Torso and Legs only. Source artwork and UV layout are retained; hand/face reduction settings are independent. Additional geometry can reduce the texture budget. Pose and size gates remain mandatory.</p>'%('enabled'if request.wii_seam_protection else'disabled'),
        '<p><a href="report.html">Complete source/posed comparison and heatmaps</a> · <a href="report.json">Comparison metrics</a> · <a href="surface-attributes.json">UV/source sampling</a> · <a href="opacity-support.json">Thin strands and cutout support</a> · <a href="palette-quality.json">Native-grid palette loss</a> · <a href="native-final.json">Native offsets, palettes and constraints</a> · <a href="../wii/textures/report.json">Every texture and allocation decision</a> · <a href="../effect-storage.json">Lossless effect storage</a> · <a href="app-result.json">Export result</a></p>',
        '<p><a href="../wii/source-materials.json">Original packet Q7/Q8 fields, exact source/IR encoding audit, draw bindings and excluded effects</a>. Transparency indicates a cutout, not anatomical hair; leg decals retain their original leg weights.</p>',
        *['<figure><figcaption>%s — actual final PAC, CPU preview</figcaption><img width="480" src="../preview/%s-full.png"></figure>'%(v,v) for v in ('front','back','left','right','front-left')],
        '</body></html>']),encoding='utf-8')
    result=dict(pac=str(final.resolve()),preview=str(preview.resolve()),report=str(report.resolve()),
        bytes=len(payload),sha256=digest(final),source=str(source.resolve()),base=str(base.resolve()),inputs=inputs,
        source_format='wwe13-wii',source_entry=f'{index:02d}',costume_role=request.costume_role,budget=limits,
        profile='wwe13-wii-experimental-material-domains',wii_geometry=request.wii_geometry,meshes=native['report']['meshes'],
        wii_seam_protection=request.wii_seam_protection,
        vertices=native['report']['vertices'],triangles=native['report']['triangles'],model_count=1,
        native_validation='passed',ocular_validation='passed',review_flags=flags,effect_storage=storage,
        status='Experimental Wii candidate: review QA and test in PPSSPP; geometry issues remain on some sources.')
    dump(work/'qa/app-result.json',result)
    step(100,'Wii PAC and final preview ready for review')
    return result

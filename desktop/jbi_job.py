"""App orchestration around the accepted JBI engine; HCTP stays independent."""
import html
import json
from pathlib import Path
import re

from PIL import Image

from desktop.accessories import combined_preview
from desktop.core import Cancelled,digest,dump,validate_pac
from desktop.preview import save_views
from desktop.texture_optimizer.candidates import read_gim
from tools.jbi_source import read as read_bundle,decoded_textures
from tools.jbi_trial import run as build_jbi
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections,write_preview


def texture_stage(request,baseline,bundle,folder,envelope,check,progress):
    """Texture-only optional comparisons over the validated JBI model set."""
    mode=request.texture_mode or ('ATO' if request.use_adaptive else 'Default')
    decoded=decoded_textures(bundle)
    if mode=='Default' or (mode=='Priority Selection' and not request.priority_textures):
        return baseline,None,None
    if mode in ('ATO','Priority Selection'):
        from desktop.texture_optimizer.pac import optimize_pac
        label='texture-priorities' if mode=='Priority Selection' else 'adaptive-textures'
        payload,report=optimize_pac(baseline,decoded,folder/label,target=148000,
            cancel=check,progress=progress,max_pixel_bytes=envelope,
            priority_textures=request.priority_textures,rebalance_priorities=bool(request.priority_textures),
            strict_source_ceilings=True)
    elif mode=='Downgrade':
        from desktop.texture_modes import downgrade_pac
        label='texture-downgrade'
        payload,report=downgrade_pac(baseline,decoded,folder/label,steps=request.downgrade_steps,cancel=check)
    elif mode=='Maximum Downgrade':
        from desktop.maximum_downgrade import fit_pac
        label='maximum-downgrade'
        payload,report=fit_pac(baseline,folder/label,cancel=check,progress=progress)
    else:raise ValueError('Unsupported JBI texture mode: '+mode)
    # A texture option may not change an arm fix, skeleton, accessory or other
    # non-texture decoded data. Retained effect-table BPE storage may be lossless.
    before={s['id']:raw for s,raw in sections(baseline)}
    after={s['id']:raw for s,raw in sections(payload)}
    if before.keys()!=after.keys():raise ValueError('Texture option changed the JBI model set.')
    for sid,raw in before.items():
        if sid!=9 and raw!=after[sid]:raise ValueError('JBI texture option changed non-texture data.')
    return payload,report,label


def run_job(request,work,progress=lambda p,m:None,cancel=lambda:False):
    request.validate()
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    source,base=Path(request.source),Path(request.base)
    hashes={str(p.resolve()):digest(p) for p in (source,base)}
    def check():
        if cancel():raise Cancelled('JBI conversion cancelled.')
    def step(p,message):check();progress(p,message)
    check()
    folder=work/'jbi'
    report=build_jbi(source,base,folder,entry_id=request.source_entry,progress=progress,cancel=cancel,
                     render_controls=False,skin_palette_compatibility=request.skin_palette_compatibility)
    baseline=(folder/report['pac']['filename']).read_bytes()
    bundle=read_bundle(source.read_bytes(),request.source_entry)
    if bundle['selection']['source_sha256']!=hashes[str(source.resolve())]:
        raise ValueError('JBI input changed during conversion.')
    step(86,'Applying selected texture option to the validated JBI model set')
    payload,texture_report,label=texture_stage(request,baseline,bundle,folder,
        json.loads((folder/'textures/report.json').read_text())['native_base_pixel_palette_envelope'],
        check,lambda message:step(87,message))
    baseline_models={s['id']:audit_yobj(raw) for s,raw in sections(baseline) if raw.startswith(b'YOBJ')}
    for model in baseline_models.values():model['bone_count']=len(model['bones'])
    # The engine checked these against intended source-derived records. All
    # optional texture stages above must retain the exact validated YOBJ bytes.
    lossless={r['section'] for r in (texture_report or {}).get('lossless_retained_texture_storage',[])}
    native,gims=validate_pac(payload,base.read_bytes(),148000,
        accessory_models={sid:m for sid,m in baseline_models.items() if sid!=2},gim_reader=read_gim,
        lossless_texture_sections=lossless)
    final_models={s['id']:audit_yobj(raw) for s,raw in sections(payload) if raw.startswith(b'YOBJ')}
    for sid,model in final_models.items():
        if model['bone_raw']!=baseline_models[sid]['bone_raw']:raise ValueError('JBI texture stage changed the rig.')
    stem=re.sub('[^A-Za-z0-9_.-]','_',source.stem)[:40].strip('.') or 'JBI'
    entry=bundle['selection']['selected_entry']
    filename=stem+('-'+entry if entry else '')+'-JBI-PSP-experimental.pac'
    candidate=work/filename;candidate.write_bytes(payload)
    preview=folder/'preview'
    visual=combined_preview(native,[m for sid,m in final_models.items() if sid!=2])
    write_preview(visual,preview/'output.obj')
    for section,raw in sections(payload):
        if raw.startswith(b'YOBJ'):(preview/('output.yobj' if section['id']==2 else 'section-%d.yobj'%section['id'])).write_bytes(raw)
    lines=[]
    for i,name in enumerate(visual['texture_names']):
        pixels,palette=read_gim(gims[name]);Image.fromarray(palette[pixels]).save(preview/(name+'.png'))
        lines += ['newmtl texture_%d'%i,'Kd 1 1 1','map_Kd '+name+'.png']
    (preview/'preview.mtl').write_text('\n'.join(lines)+'\n',encoding='ascii')
    step(92,'Rendering the actual final JBI PSP model set')
    save_views(visual,gims,preview,gim_reader=read_gim)
    qa=json.loads((folder/'native-pose-qa.json').read_text())
    findings=[dict(section=sid,**row) for sid,item in qa.items() for row in item['review_findings']]
    texture_flags=sum(bool(t.get('quality_review_flags')) for t in (texture_report or {}).get('textures',[]))
    page=work/'qa';page.mkdir()
    document=['<!doctype html><html><meta charset="utf-8"><title>JBI conversion QA</title><body>',
        '<h1>JBI → SVR 2011 PSP</h1>',
        '<p>Entry %s. %d / 148,000 bytes. %d independent models. Texture mode: %s.</p>'%
        (html.escape(entry or 'standalone costume'),len(payload),len(final_models),html.escape(request.texture_mode or 'Default')),
        '<p>Source-derived local arm/hand bind conversion and digit-constrained transfer. No decimation. '
        'Native skeleton, palettes, indices, offsets, alignment, texture contracts and analytical poses checked. '
        'Source helper/controller semantics, all animations and accessory events still require model-specific PPSSPP testing.</p>',
        '<p><a href="report.json">Final PAC and size evidence</a> · '
        '<a href="../jbi/report.json">Validated Default model-set baseline</a> · '
        '<a href="../jbi/arm-qa.json">Source/native thumb stress and independent digit tests</a> · '
        '<a href="../jbi/rig-refinement.json">Bind and weight mapping</a> · '
        '<a href="../jbi/atlas.json">Atlas sampling proof</a> · '
        '<a href="../jbi/native-pose-qa.json">Body/ocular/accessory poses and review findings</a> · '
        '<a href="../jbi/textures/report.json">Default texture allocation</a></p>']
    if label:document.append('<p><a href="../jbi/%s/report.html">Selected texture option, reductions and budgets</a></p>'%html.escape(label))
    document += ['<h2>Review findings</h2><pre>'+html.escape(json.dumps(findings,indent=2))+'</pre>',
        '<p>Analytical pose checks are not captured game animation or a guarantee of runtime safety.</p>']
    for view in ('front','back','left','right','front-left'):
        document.append('<figure><figcaption>%s — actual final PAC, CPU preview</figcaption><img width="360" src="../jbi/preview/%s-full.png"></figure>'%(view,view))
    document.append('</body></html>');(page/'report.html').write_text('\n'.join(document),encoding='utf-8')
    result=dict(pac=str(candidate),preview=str(preview),report=str(page/'report.html'),bytes=len(payload),sha256=digest(candidate),
        source=str(source.resolve()),base=str(base.resolve()),source_format='jbi',source_entry=entry,inputs=hashes,
        profile='jbi-v1-arm-bind',meshes=native['report']['meshes'],triangles=native['report']['triangles'],
        vertices=native['report']['vertices'],model_count=len(final_models),accessory_sections=[sid for sid in final_models if sid!=2],
        total_meshes=sum(m['report']['meshes'] for m in final_models.values()),
        total_vertices=sum(m['report']['vertices'] for m in final_models.values()),
        total_triangles=sum(m['report']['triangles'] for m in final_models.values()),
        native_validation='passed',ocular_validation='passed',review_flags=len(findings)+texture_flags,
        jbi_textures=dict(mode=request.texture_mode or 'Default',report=str(folder/(label or 'textures')/'report.json')),
        status='JBI conversion; review analytical QA and test every new model in PPSSPP.')
    dump(page/'report.json',dict(result,unresolved_review=findings))
    for path,fingerprint in hashes.items():
        if digest(path)!=fingerprint:raise ValueError('An input changed; JBI export withheld.')
    step(100,'JBI PAC and preview ready for review')
    return result

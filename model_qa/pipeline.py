"""Reusable read-only QA stage with explicit inputs and immutable outputs."""
from collections import defaultdict
import copy
import hashlib
import html
import json
from pathlib import Path

import numpy as np

from . import VERSION
from .geometry import align_reference,geometry,posed,posed_original,read_model,seam_motion,sha
from .metrics import DEFAULT_PROFILE,detect,measure,influence_groups
from .regions import regions
from .render import DIRECTIONS,camera,save_pair
from .head import compare_head,controller_probes,layout_review


POSES = {
    'standing':{'l_ninoude':('z',70),'r_ninoude':('z',-70)},
    'walk-left':{'l_momo':('x',22),'r_momo':('x',-22),'r_sune':('x',30)},
    'walk-right':{'l_momo':('x',-22),'r_momo':('x',22),'l_sune':('x',30)},
    'bend':{'koshi':('x',35),'mune':('x',20)},
    'crouch':{'l_momo':('x',-50),'r_momo':('x',-50),'l_sune':('x',95),'r_sune':('x',95),'koshi':('x',20)},
    'shoulders-up':{'l_ninoude':('z',-55),'r_ninoude':('z',55)},
    'neck-turn':{'kubi':('y',25)}, 'head-tilt':{'atama':('z',12)},
    'jaw-06':{'d_kuchi':('x',6)},'jaw-12':{'d_kuchi':('x',12)},
    'jaw-18':{'d_kuchi':('x',18)},'jaw-25':{'d_kuchi':('x',25)},
    'elbow-flex-left':{'l_ninoude':('z',70),'r_ninoude':('z',-70),'l_kote':('y',-90)},
    'elbow-flex-right':{'l_ninoude':('z',70),'r_ninoude':('z',-70),'r_kote':('y',90)},
}


def dump(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def export_obj(g,path):
    lines=['# QA-only uniformly aligned geometry; canonical x=left, y=up, z=front']
    lines+=['v %.12g %.12g %.12g'%tuple(p) for p in g.vertices]
    lines+=['f %d %d %d'%tuple(t+1) for t in g.faces]
    Path(path).write_text('\n'.join(lines)+'\n',encoding='ascii')


def normalized_profile(profile):
    p=copy.deepcopy(DEFAULT_PROFILE)
    if profile:p.update(profile)
    for key in ('distance_p95_height','distance_p99_height','depth_absolute_p95_height','inward_depth_p95_height','edge_distance_p95_height','animation_extra_p95_height'):
        if not isinstance(p[key],(int,float)) or not np.isfinite(p[key]) or p[key]<=0:raise ValueError('Invalid tolerance: '+key)
        for regional in p.get('regional',{}).values():
            if key in regional and (not np.isfinite(regional[key]) or regional[key]<=0):raise ValueError('Invalid regional tolerance: '+key)
    from .material_boundaries import DEFAULT_LIMITS
    boundary=dict(DEFAULT_LIMITS,**p.get('material_boundaries',{}))
    for key in ('maximum_height','p95_height','animation_extra_maximum_height','seam_extra_height'):
        for limits in (boundary,*boundary.get('per_texture',{}).values()):
            if key in limits and (not isinstance(limits[key],(int,float)) or not np.isfinite(limits[key]) or limits[key]<=0):
                raise ValueError('Invalid material boundary tolerance: '+key)
    p['material_boundaries']=boundary
    return p


def render_views(reference,candidate,bind,rois,height,heat,folder,pose='rest',resolution=320,selected=None,save_depth=False):
    entries=[];views={}
    selected=selected or list(rois)
    if pose=='rest':
        for view in DIRECTIONS:
            cam=camera(reference.vertices,view,resolution)
            stem=pose+'-whole-'+view
            metrics,configuration=save_pair(folder,stem,reference,candidate,cam,height,heat,save_depth=save_depth)
            entries.append(dict(region='whole',pose=pose,view=view,file='renders/'+stem+'.png',camera=configuration,metrics=metrics))
    for name in selected:
        roi=rois[name];mask=roi.mask(bind.vertices)
        if mask.sum()<6:
            views[name]={};continue
        points=reference.vertices[mask];views[name]={}
        for view in roi.views:
            cam=camera(points,view,resolution)
            stem=pose+'-'+name+'-'+view
            metrics,configuration=save_pair(folder,stem,reference,candidate,cam,height,heat,save_depth=save_depth)
            views[name][view]=metrics
            entries.append(dict(region=name,pose=pose,view=view,file='renders/'+stem+'.png',camera=configuration,metrics=metrics))
    return entries,views


def stage_diagnosis(flags,trace):
    """Match the specific finding; sharing a region is not stage causation."""
    first=[]
    for flag in flags:
        if flag['severity']=='insufficient-evidence' or flag['region']=='whole-model':continue
        matches=[s for s in trace if any(f['region']==flag['region'] and f['pose']==flag['pose'] and
                    f['kind']==flag['kind'] and f['severity']!='insufficient-evidence' for f in s['flags'])]
        first.append(dict(region=flag['region'],pose=flag['pose'],first_flagged_supplied_stage=matches[0]['label'] if matches else None,
                          kind=flag['kind'],
                          caveat='First among supplied ordered stages, not proof that earlier unsaved stages were correct'))
    diagnosis=[]
    for region in sorted({f['region'] for f in flags if f['severity']!='insufficient-evidence' and f['region']!='whole-model'}):
        events=[x for x in first if x['region']==region]
        static=[x for x in events if x['pose']=='rest']
        dynamic=[x for x in events if x['pose']!='rest']
        diagnosis.append(dict(region=region,rest_deviation_flagged=bool(static),pose_deviation_flagged=bool(dynamic),
            first_supplied_stages=sorted({x['first_flagged_supplied_stage'] for x in events if x['first_flagged_supplied_stage']}),
            suspected_origin=('Unvalidated native rendering layout; runtime cause unresolved' if
                any(f['region']==region and f['kind']=='unvalidated-small-skinned-palette' for f in flags) else
                'Geometry processing before animation' if static else 'Rig/weight adaptation; geometry is within rest tolerances'),
            evidence_policy='Stage measurements and identical-PSP-rig source-weight control; cause is provisional, not an automatic correction instruction'))
    return first,diagnosis


def run(source_path,candidate_path,output,*,profile=None,stages=(),samples=16000,resolution=320,
        animations=True,renders=True,poses=None,save_depth=False,progress=lambda message:None):
    source_path,candidate_path,output=map(Path,(source_path,candidate_path,output))
    if output.exists():raise FileExistsError('QA refuses to overwrite an existing result: '+str(output))
    if samples<2000 or resolution<96:raise ValueError('At least 2,000 samples and 96-pixel renders are required')
    paths=[source_path,candidate_path]+[Path(s['path']) for s in stages]
    hashes={str(p.resolve()):sha(p) for p in paths}
    source=read_model(source_path,source=True);target=read_model(candidate_path)
    aligned,alignment=align_reference(source,target)
    reference,candidate=geometry(aligned),geometry(target)
    mapped_reference=geometry(aligned,skeleton=target)
    height=reference.height;rois=regions(reference,target);thresholds=normalized_profile(profile)
    output.mkdir(parents=True);(output/'renders').mkdir();(output/'geometry').mkdir()
    export_obj(reference,output/'geometry/reference.obj');export_obj(candidate,output/'geometry/candidate.obj')
    np.savez_compressed(output/'geometry/reference.npz',vertices=reference.vertices,faces=reference.faces,weights=reference.weights)
    np.savez_compressed(output/'geometry/candidate.npz',vertices=candidate.vertices,faces=candidate.faces,weights=candidate.weights)
    dump(output/'geometry/source-rig.json',dict(bones=source['bones'],alignment=alignment,weight_bones=reference.bone_names))
    dump(output/'geometry/candidate-rig.json',dict(bones=target['bones'],weight_bones=candidate.bone_names))
    np.savez_compressed(output/'geometry/mapped-reference.npz',vertices=mapped_reference.vertices,faces=mapped_reference.faces,weights=mapped_reference.weights)
    progress('Measuring bidirectional rest surfaces and curvature')
    rest,heat=measure(reference,candidate,rois,height,count=samples,with_curvature=True)
    np.savez_compressed(output/'geometry/vertex-errors.npz',**heat)
    gallery=[]
    if renders:
        progress('Rendering fixed front/back/side/three-quarter and anatomical close-up pairs')
        entries,views=render_views(reference,candidate,reference,rois,height,heat['vertex_error'],output/'renders',resolution=resolution,save_depth=save_depth)
        gallery+=entries
        for name,metrics in views.items():rest['regions'][name]['views']=metrics
    flags=detect(rest,thresholds);motion={};pose_controls=poses or POSES
    head_resolution=min(resolution,160)
    head_rest=compare_head(reference,candidate,resolution=head_resolution,
        render_folder=output/'renders' if renders else None)
    native_head_flags=[dict(f,region='head',pose='rest') for f in layout_review(target)]
    flags+=head_rest['flags']+native_head_flags;gallery+=head_rest['gallery']
    head_poses={}
    if renders:
        gallery+=render_material_flags(reference,candidate,rest,flags,output/'renders',height,resolution)
    if animations:
        source_names=set(reference.bone_names);target_names=set(candidate.bone_names)
        for name,controls in pose_controls.items():
            if not set(controls)<=source_names&target_names:raise ValueError('Pose requires bones absent from either rig: '+name)
            progress('Comparing source-derived and converted weights on the same PSP rig in '+name)
            rp=posed(mapped_reference,controls);cp=posed(candidate,controls)
            comparison,pose_heat=measure(rp,cp,rois,height,reference,candidate,count=samples)
            comparison['source_seams']=seam_motion(reference,rp,height);comparison['candidate_seams']=seam_motion(candidate,cp,height)
            comparison['reference_height']=height
            np.savez_compressed(output/'geometry'/(name+'-reference.npz'),vertices=rp.vertices)
            np.savez_compressed(output/'geometry'/(name+'-candidate.npz'),vertices=cp.vertices)
            pose_flags=detect(comparison,thresholds,name,rest)
            if renders:
                gallery+=render_material_flags(rp,cp,comparison,pose_flags,output/'renders',height,resolution,name)
            if renders and name in ('standing','bend','crouch','neck-turn','jaw-18','jaw-25'):
                selections=['jaw','chin','neck'] if name.startswith('jaw') or name=='neck-turn' else ['shoulders','pelvis','buttocks']
                entries,views=render_views(rp,cp,reference,rois,height,pose_heat['vertex_error'],output/'renders',pose=name,resolution=resolution,selected=selections,save_depth=save_depth)
                gallery+=entries
                for region,metrics in views.items():comparison['regions'][region]['views']=metrics
            motion[name]=comparison;flags+=pose_flags
        from .ocular import skin
        progress('Checking complete cranial support under facial and head-controller stress probes')
        for name,probe in controller_probes(target).items():
            rp,unsupported=skin(mapped_reference,probe);cp,unsupported_candidate=skin(candidate,probe)
            h=compare_head(rp,cp,mapped_reference,candidate,resolution=head_resolution,
                pose='head-probe-'+name,render_folder=output/'renders' if renders and name in
                ('head-turn','neck-turn','jaw-open','psp-brow-local','eye-lid-neck-jaw') else None)
            h['probe']=probe;h['unsupported_controllers']=sorted(set(unsupported+unsupported_candidate))
            head_poses[name]=h;flags+=h['flags'];gallery+=h['gallery']
    progress('Tracing optional stages in the single fixed reference frame')
    trace=[]
    for stage in stages:
        sm=read_model(stage['path']);space=stage.get('space','target')
        if space=='source':
            sm=copy.deepcopy(sm);r=np.asarray(alignment['rotation']);tr=np.asarray(alignment['translation'])
            for mesh in sm['meshes']:
                for v in mesh['vertices']:v['position']=(alignment['scale']*r@v['position']+tr).tolist()
        elif space!='target':raise ValueError('Stage space must explicitly be source or target')
        sg=geometry(sm);metrics,_=measure(reference,sg,rois,height,count=samples)
        stage_flags=detect(metrics,thresholds)
        stage_head=compare_head(reference,sg,resolution=head_resolution)
        stage_flags+=stage_head['flags']
        skeleton_matches=len(sm['bones'])==len(target['bones']) and all(a['name']==b['name'] and np.allclose(a['local_position'],b['local_position'],atol=1e-6) and np.allclose(a['rotation'],b['rotation'],atol=1e-6) for a,b in zip(sm['bones'],target['bones']))
        stage_motion={}
        if animations and skeleton_matches:
            for pose_name in ('neck-turn','jaw-18'):
                controls=pose_controls.get(pose_name)
                if controls:
                    m,_=measure(posed(mapped_reference,controls),posed(sg,controls),rois,height,reference,sg,count=samples)
                    stage_motion[pose_name]=m;stage_flags+=detect(m,thresholds,pose_name,metrics)
        trace.append(dict(label=stage['label'],path=str(Path(stage['path']).resolve()),sha256=sha(stage['path']),space=space,
                          skeleton_matches_final=skeleton_matches,rest=metrics,poses=stage_motion,flags=stage_flags,
                          head_diagnostics=stage_head))
    # A source-weight control isolates rig remapping from transferred hybrid weights.
    bridge=None
    if animations:
        mapped=mapped_reference
        bridge_rest,_=measure(reference,mapped,rois,height,count=samples)
        bridge_poses={}
        for name in ('neck-turn','jaw-18'):
            if name not in pose_controls:continue
            controls=pose_controls[name]
            m,_=measure(posed_original(source,alignment,controls),posed(mapped,controls),rois,height,reference,mapped,count=samples)
            hybrid_deviation=motion[name]
            original_rig_comparison,_=measure(posed_original(source,alignment,controls),posed(candidate,controls),rois,height,reference,candidate,count=samples)
            bridge_poses[name]=dict(original_rig_vs_mapped_original_weights=m, mapped_original_weights_vs_final=hybrid_deviation,original_hctp_rig_vs_final=original_rig_comparison)
        bridge=dict(description='Analytical control only: original geometry and source ancestor-mapped weights on final PSP rig; no model is written',rest=bridge_rest,poses=bridge_poses)
    first,diagnosis=stage_diagnosis(flags,trace)
    native=isinstance(target.get('report'),dict) and 'allocations' in target['report']
    fmt=dict(native_psp_audit_passed=native,within_148000_byte_budget=candidate_path.stat().st_size<=148000 if candidate_path.suffix.lower()=='.pac' else None,
             pac_bytes=candidate_path.stat().st_size if candidate_path.suffix.lower()=='.pac' else None)
    if native:fmt.update(bone_table_sha256=hashlib.sha256(target['bone_raw']).hexdigest(),mesh_count=target['report']['meshes'],
                          textures=target['texture_names'],material_controls=sorted({a['control'] for m in target['meshes'] for a in m['materials']}),
                          checks=['internal pointers/allocations/alignment','relocations','vertex/index ranges','bone palettes','finite normalized weights'])
    for path,old in hashes.items():
        if sha(path)!=old:raise RuntimeError('QA input unexpectedly changed: '+path)
    report=dict(qa_version=VERSION,mode='comparison-and-report-only',inputs=dict(source=str(source_path.resolve()),candidate=str(candidate_path.resolve()),sha256=hashes),
        reference_height=height,alignment=alignment,canonical_axes='Proper rotation (x,-y,-z): x=wrestler left, y=up, z=forward',
        thresholds=thresholds,rest=rest,poses=motion,pose_controls=pose_controls if animations else {},
        head_diagnostics=dict(rest=head_rest,poses=head_poses,native_layout_review=native_head_flags,
            limitation='Provisional full-head/outlier/winding/controller review. CPU cull conventions are diagnostic; actual SVR loader, GPU state and clips are not emulated.'),
        animation_method='Primary: original HCTP geometry and ancestor-mapped source weights vs final geometry/weights, both on the identical PSP rig and poses. Additional original-HCTP-rig controls isolate rig adaptation.',
        animation_limitations=['Analytical LBS poses, not real game clips or a PPSSPP test','Original facial controller semantics and absent source bones may differ intentionally'],
        stage_trace=trace,defect_first_appearance=first,rig_mapping_control=bridge,format=fmt,flags=flags,gallery=gallery,numeric_pixel_depth_saved=save_depth,
        regional_diagnosis=diagnosis,influence_diagnostics=dict(source=influence_groups(reference,rois,height,samples),candidate=influence_groups(candidate,rois,height,samples)),
        corrections_attempted=[],automatic_correction_enabled=False,can_replace_best_model=False,inputs_unchanged=True,
        preserved_previous_candidate_sha256=hashes[str(candidate_path.resolve())],
        unresolved_review=[f for f in flags if f['severity']!='insufficient-evidence'],
        limitations=['Open body/material surfaces: local depth integration is a volume proxy, not a watertight volume',
                     'CPU geometry renders use identical clay shading; they do not simulate textures, alpha, PSP rendering flags or Noesis',
                     'Finite surface sampling can miss extremely small defects; sample count and coverage are reported',
                     'Curvature and disconnected components are diagnostics, not proof of defects',
                     'No verified anatomical vertex-index correspondence is assumed'])
    dump(output/'report.json',report);write_html(report,output/'report.html')
    manifest={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
    dump(output/'manifest.json',dict(inputs_unchanged=True,sha256=manifest))
    return report


def render_material_flags(reference,candidate,metrics,flags,folder,height,resolution,pose='rest'):
    """Matching close-ups for flagged materials, using only reference framing."""
    from hashlib import sha256
    result=[]
    for flag in flags:
        texture=flag.get('texture')
        if texture is None:continue
        points=metrics['material_boundaries']['materials'][texture].get('reference_camera_points')
        if points is None or len(points)<3:continue
        safe=sha256(texture.encode()).hexdigest()[:12]
        for view in ('front','back','left','right'):
            cam=camera(np.asarray(points),view,resolution);cam.span*=1.3
            stem=pose+'-material-'+safe+'-'+view
            values,configuration=save_pair(folder,stem,reference,candidate,cam,height)
            result.append(dict(region='material:'+texture,pose=pose,view=view,file='renders/'+stem+'.png',camera=configuration,metrics=values))
    return result


def write_html(report,path):
    e=html.escape
    rows=[]
    for name,r in report['rest']['regions'].items():
        d=r['distance']
        values=[name,str(d['samples']) if d else '0',('%.5f'%d['mean']) if d else 'n/a',('%.4f%%'%(100*d['p95_height'])) if d else 'n/a',
                ', '.join(sorted({f['severity'] for f in report['flags'] if f['region']==name and f['severity']!='insufficient-evidence'})) or 'Within provisional tolerances']
        rows.append('<tr>'+''.join('<td>'+e(v)+'</td>' for v in values)+'</tr>')
    findings=''.join('<li><b>'+e(f['region'])+' / '+e(f['pose'])+'</b>: '+e(f['severity'])+' — '+e(f['kind'])+'</li>' for f in report['flags'] if f['severity']!='insufficient-evidence')
    views=[]
    for entry in report['gallery']:
        stem=entry['file'][:-4]
        views.append('<details><summary>'+e(entry['pose']+' / '+entry['region']+' / '+entry['view'])+'</summary>'
                     '<div class="pair"><img src="'+e(stem+'-reference.png')+'"><img class="candidate" src="'+e(stem+'-candidate.png')+'"></div>'
                     '<label>Wipe HCTP / PSP <input type="range" min="0" max="100" value="50" oninput="this.parentNode.previousElementSibling.lastElementChild.style.clipPath=\'inset(0 0 0 \'+this.value+\'%)\'"></label>'
                     '<a href="'+e(entry['file'])+'"><img class="atlas" loading="lazy" src="'+e(entry['file'])+'"></a></details>')
    body='''<!doctype html><html><head><meta charset="utf-8"><title>Model geometric QA</title><style>
body{font:16px system-ui,sans-serif;color:#ddd;background:#202329;max-width:1300px;margin:28px auto;padding:18px}
a{color:#8ecaff}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #50555c;text-align:left}
details{padding:12px;border:1px solid #50555c;margin:10px 0}summary{cursor:pointer}.atlas{width:100%;margin-top:12px}
.pair{position:relative;width:320px;height:320px;max-width:100%;margin:10px 0}.pair img{position:absolute;inset:0;width:100%;height:100%}
.candidate{clip-path:inset(0 0 0 50%)}.notice{padding:14px;background:#333b48}pre{white-space:pre-wrap}
</style></head><body><h1>Model geometric QA</h1>'''
    body+='<p class="notice">Read-only comparison. No PAC or correction was generated. Review flags are not proof of an error. Animation views are analytical skinning, not game footage.</p>'
    body+='<p>Source: '+e(Path(report['inputs']['source']).name)+' | Candidate: '+e(Path(report['inputs']['candidate']).name)+'</p>'
    d=report['rest']['overall'];body+='<p>Bidirectional mean surface distance '+str(round(d['mean'],6))+' model units; p95 '+str(round(d['p95_height']*100,4))+'% of original height. Uniform scale only.</p>'
    body+='<p><a href="report.json">Full machine-readable report</a> · <a href="manifest.json">SHA-256 manifest</a> · <a href="geometry/reference.obj">Aligned reference OBJ</a> · <a href="geometry/candidate.obj">Candidate OBJ</a></p>'
    body+='<table><tr><th>Region</th><th>Samples</th><th>Mean distance</th><th>P95 / height</th><th>Review</th></tr>'+''.join(rows)+'</table>'
    material_rows=[]
    for name,r in report['rest'].get('material_boundaries',{}).get('materials',{}).items():
        status=', '.join(sorted({f['severity'] for f in report['flags'] if f.get('texture')==name})) or r['status']
        values=[name,str(r['source_edges']),str(r['candidate_edges']),('%.4f%%'%(r['maximum_height']*100)) if r['distance'] else 'n/a',status]
        material_rows.append('<tr>'+''.join('<td>'+e(v)+'</td>' for v in values)+'</tr>')
    body+='<h2>Material and accessory boundaries</h2><p>Every boundary endpoint and midpoint is checked against the corresponding material boundary. Peak drift catches small corners that area percentiles can miss. Shared skin seams are also checked under poses; intentional material/LOD differences remain review findings.</p><table><tr><th>Texture/material</th><th>Source edges</th><th>Candidate edges</th><th>Maximum / height</th><th>Review</th></tr>'+''.join(material_rows)+'</table>'
    body+='<h2>Detected deviations</h2><ul>'+findings+'</ul><h2>Saved-stage evidence</h2><pre>'+e(json.dumps(report['defect_first_appearance'],indent=2))+'</pre>'
    body+='<h2>Matching renders and heatmaps</h2><p>Source-only camera framing, identical orthographic projection and lights. Blue is low surface error; red is at least 0.6% of height. Open details to use the comparison wipe.</p>'+''.join(views)
    body+='<h2>Tolerances and limitations</h2><pre>'+e(json.dumps(report['thresholds'],indent=2))+'</pre><ul>'+''.join('<li>'+e(v)+'</li>' for v in report['limitations']+report['animation_limitations'])+'</ul></body></html>'
    Path(path).write_text(body,encoding='utf-8')

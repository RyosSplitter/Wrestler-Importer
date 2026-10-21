"""Export private, exact-PAC Wii trial evidence; never publish game assets."""
import argparse,hashlib,html,json,shutil,zipfile
from pathlib import Path
import numpy as np
from PIL import Image
from desktop.texture_optimizer.candidates import read_gim
from model_qa.pipeline import POSES
from model_qa.geometry import geometry,Surface
from model_qa.render import camera,save_pair
from tools.psp_mesh_merge_trial import sections,write_preview
from tools.sym_trial import render_native
from tools.tna_obj_export import posed_model
from tools.wwe13_wii_trial import validate_trial,dump


def crop(model,kind):
    """Display-only triangle clipping; never edit the exported PAC/OBJ.

    Dropping any triangle that crosses the ROI cuts artificial holes in a
    coarse model. Clip its UV/normal/color corners instead, without capping.
    """
    import copy
    out=copy.deepcopy(model);out['meshes']=[]
    planes=[(1,-1.,7.05),(0,1.,1.7),(0,-1.,1.7)]if kind=='head'else[(1,1.,2.5),(1,-1.,3.),(0,1.,3.),(0,-1.,3.)]
    # Each halfspace is sign*position[axis] <= limit. Head y <= -7.05.
    if kind=='head':planes[0]=(1,1.,-7.05)
    for mesh in model['meshes']:
        vertices=[];mats=[]
        for mat in mesh['materials']:
            faces=[]
            for tri in mat['triangles']:
                polygon=[copy.deepcopy(mesh['vertices'][i])for i in tri]
                for axis,sign,limit in planes:
                    clipped=[]
                    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
                        da=sign*a['position'][axis]-limit;db=sign*b['position'][axis]-limit
                        if da<=0:clipped.append(a)
                        if (da<=0)!=(db<=0):
                            t=da/(da-db);v=copy.deepcopy(a)
                            for key in ('position','uv','normal','color','weights'):
                                if key in a:v[key]=((1-t)*np.array(a[key])+t*np.array(b[key])).tolist()
                            v['color']=np.rint(v['color']).astype(int).tolist();clipped.append(v)
                    polygon=clipped
                    if not polygon:break
                if len(polygon)<3:continue
                offset=len(vertices);vertices.extend(polygon)
                faces.extend([[offset,offset+i,offset+i+1]for i in range(1,len(polygon)-1)])
            if faces:mats.append(dict(mat,triangles=faces))
        if mats:out['meshes'].append(dict(mesh,vertices=vertices,materials=mats))
    return out


def preview(model,images,path):
    path.mkdir();write_preview(model,path/'preview.obj');mtl=[]
    for i,name in enumerate(model.get('texture_names',model.get('textures'))):
        im=images[name]
        if isinstance(im,bytes):
            (path/(name+'.gim')).write_bytes(im);ix,pal=read_gim(im);im=pal[ix]
        Image.fromarray(im).save(path/(name+'.png'))
        mtl+=['newmtl texture_'+str(i),'Kd 1 1 1','d 1','map_Kd '+name+'.png','']
    (path/'preview.mtl').write_text('\n'.join(mtl)+'\n')


def export(work,base,output,*,unlit=False):
    work,base,output=map(Path,(work,base,output));result=json.loads((work/'result.json').read_text())
    title=result.get('source_filename','HBK Wii')+' / variant '+str(result.get('variant',0))+' PSP experiment'
    renderer=render_native
    if unlit:
        from tools.wwe13_wii_preview import render_unlit
        renderer=render_unlit
    data=(work/result['pac']).read_bytes();fingerprint=hashlib.sha256(data).hexdigest()
    if fingerprint!=result['sha256']:raise ValueError('PAC changed after build')
    checks=json.loads((work/'native-checks.json').read_text());ocular=json.loads((work/'ocular.json').read_text())
    native,gims,structural=validate_trial(data,base.read_bytes(),checks['radius_changes'],ocular['source_controller_pivot_fit'])
    if checks['poses']['review_findings']or not all(r['passes']for r in checks['hand_reference_envelope'].values()):raise ValueError('Analytical gate failed')
    raw=next(r for s,r in sections(data)if s['id']==2)
    if raw!=(work/'candidate.yobj').read_bytes():raise ValueError('PAC differs from checked YOBJ')
    qa=json.loads((work/'qa/report.json').read_text())
    if fingerprint not in qa['inputs']['sha256'].values():raise ValueError('QA does not reference final PAC hash')
    native['bone_count']=len(native['bones']);reference=json.loads((work/'charted.json').read_text());reference['texture_names']=reference['textures']
    images={n:np.array(Image.open(work/'source-images'/(n+'.png')))for n in reference['textures']}
    output.mkdir(parents=True,exist_ok=False);(output/result['pac']).write_bytes(data)
    preview(native,gims,output/'preview');(output/'preview'/'prepared.yobj').write_bytes(raw)
    preview(reference,images,output/'source-preview')
    views=output/'comparisons';views.mkdir()
    def pair(a,b,label,view='front'):
        ps=np.array([v['position']for m in a['meshes']for v in m['vertices']]);frame=[ps.min(0),ps.max(0)]
        left=views/('source-'+label+'.png');right=views/('psp-'+label+'.png')
        suffix=' | UNLIT DIFFUSE'if unlit else ''
        renderer(a,images,view,left,label='WII SOURCE | ADAPTED PSP REFERENCE POSE'+suffix,camera_bounds=frame)
        renderer(b,gims,view,right,label='EXACT DECODED EXPERIMENTAL PSP PAC'+suffix,fingerprint=fingerprint,camera_bounds=frame)
        sheet=Image.new('RGB',(1280,640));sheet.paste(Image.open(left),(0,0));sheet.paste(Image.open(right),(640,0));sheet.save(views/('comparison-'+label+'.png'))
    for view in ('front','back','left','right','front-left'):pair(reference,native,view,view)
    for kind in ('head','pelvis'):
        for view in (('front','left')if kind=='head'else('back','left')):pair(crop(reference,kind),crop(native,kind),kind+'-'+view,view)
    for name in ('standing','walk-left','bend','crouch','elbow-flex-left','jaw-18'):
        pair(posed_model(reference,POSES[name]),posed_model(native,POSES[name]),'pose-'+name,'front-left')
    for name,pose in [('eye-turn',{'l_eye':('y',25),'r_eye':('y',25)}),('blink',{'l_mabuta':('x',30),'r_mabuta':('x',30)})]:
        pair(crop(posed_model(reference,pose),'head'),crop(posed_model(native,pose),'head'),name)
    a,b=geometry(reference),geometry(native);_,errors,_=Surface(a,a.height).nearest(b.vertices)
    for view in ('front','back','left'):
        save_pair(views,'clay-heatmap-'+view,a,b,camera(a.vertices,view,256),a.height,errors)
    shutil.copytree(work/'qa',output/'qa')
    for n in ('native-checks','source-materials','rig','ocular','atlas','profile','contracts','structural'):
        shutil.copy2(work/(n+'.json'),output/(n+'.json'))
    shutil.copy2(work/'textures/report.json',output/'texture-report.json')
    source=json.loads((work/'source.json').read_text());tex=json.loads((work/'textures/report.json').read_text())
    summary=dict(result,status='EXPERIMENTAL; structure/analytical replay passed, source-fidelity review findings remain; NOT game-tested',
        expanded_yobj_bytes=len(raw),native_pose_gate_passed=True,source_vertices=source['vertex_count'],
        p95_surface_error_height=qa['rest']['overall']['p95_height'],review_findings=len(qa['flags']),
        texture_pixel_palette_bytes=tex['pixel_palette_bytes'],observed_native_texture_envelope=tex['native_base_memory_envelope'],
        preview_provenance='CPU renders of exact decoded final PAC, not Noesis or PPSSPP screenshots',
        preview_lighting='Unlit diffuse, display-only normals; native model normals unchanged'if unlit else 'Existing neutral CPU preview lighting',
        qa_source_label_note='Shared QA text mentions HCTP generically. Actual reference is decoded Wii geometry in adapted PSP rest pose, shown by input paths/hashes. No HCTP model was used.')
    dump(output/'summary.json',summary)
    (output/'README.txt').write_text(title+'\nWWE 13 Wii -> SVR 2011 PSP: EXPERIMENTAL TEST\n\n'
        'Use '+result['pac']+'. Source variant indices are not proof of ring/entrance slot semantics.\n'
        'Back up your ISO/CH.PAC and accepted wrestler PAC. Inject this file using\n'
        'your established PAC Editor workflow, rebuild/update its containing\n'
        'archive/ARC and save the ISO. Use the appropriate ring/entrance slot.\n'
        'Restart PPSSPP and start a fresh match; old states can retain old assets.\n\n'
        'Inspect entrance, standing/walking, bends/crouches, jaw/eye expressions,\n'
        'hand grips and victory; also watch unrelated ring geometry and crashes.\n'
        'Stored-size compliance and structural checks do not prove game stability.\n\n'
        'Open preview/preview.obj in Noesis, with preview.mtl and PNGs beside it.\n'
        'Apply your usual orientation, face-cull and shading toggles as needed.\n'
        'prepared.yobj is byte-exact to the expanded model in this PAC.\n'
        'source-preview is FULL-DETAIL Wii geometry in the adapted PSP pose.\n'
        'OBJ previews are static and do not prove animation compatibility.\n\n'
        'Comparisons show source left / exact final PAC right. They are CPU\n'
        'renders and analytical poses, not Noesis or actual game screenshots.\n'
        'QA is comparison-only; all remaining findings are retained, including\n'
        'shape loss and head-fold/winding review after reduction. Not QA-approved.\n'
        'Open START-HERE.html and qa/report.html. Some generic QA labels say HCTP;\n'
        'the actual reference here is decoded Wii source on the same PSP rig.\n\n'
        'Limitations: the source three-bone blend formula is strongly supported\n'
        'by binary/shared-vertex evidence, not independent Wii runtime emulation.\n'
        'Source spring-bone hair motion is collapsed to the PSP head ancestor.\n'
        'Source shaders/normal/specular/muscle effects are not ported.\n'
        'Source dynamic blood overlays ('+str(sum(e['triangles']for e in result.get('source_blood_draws_excluded',[])))+' triangles) are excluded\n'
        'from ordinary static rendering rather than made permanently visible.\n'
        'Hair source alpha levels are retained at nearest-resampled positions,\n'
        'with RGB quantized separately; source RGBA/color ceilings are enforced.\n'
        'Total game runtime heap and real facial animation remain unverified.\n'
        'Production converter and accepted HCTP/JBI outputs are unchanged.\n\n'
        'Preview lighting: '+summary['preview_lighting']+'\n'
        'PAC bytes: '+str(len(data))+'\nSHA-256: '+fingerprint+'\n')
    labels=('front','back','left','head-front','head-left','pelvis-back','pose-standing','pose-crouch','pose-jaw-18','eye-turn','blink')
    (output/'START-HERE.html').write_text('<!doctype html><meta charset="utf-8"><title>'+html.escape(title)+'</title><h1>'+html.escape(title)+'</h1><p>Experimental, not game-tested or QA-approved. '+str(len(data))+' bytes. '+str(len(qa['flags']))+' source-fidelity review findings retained.</p><p><a href="README.txt">Instructions</a> | <a href="qa/report.html">QA report</a></p><p>Full-detail source in adapted pose (left), exact final PAC (right). CPU previews. '+html.escape(summary['preview_lighting'])+'</p>'+''.join('<p><img style="max-width:100%" src="comparisons/comparison-'+n+'.png"></p>'for n in labels))
    dump(output/'SHA256-MANIFEST.json',[dict(path=f.relative_to(output).as_posix(),bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest())for f in sorted(output.rglob('*'))if f.is_file()])
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('work');p.add_argument('--base',required=True);p.add_argument('--out',required=True);p.add_argument('--unlit',action='store_true');a=p.parse_args();print(json.dumps(export(a.work,a.base,a.out,unlit=a.unlit),indent=2))

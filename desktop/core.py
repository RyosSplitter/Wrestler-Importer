"""Offline job orchestration. Established readers/reducer/writer/QA stay separate.

No character hashes or file names select conversion behavior. User files are
read-only; every candidate is built in its own disposable job directory.
"""
from dataclasses import dataclass
from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import numpy as np
from PIL import Image
from desktop.adapters import adapter
from desktop.native import serialize
from desktop.budget import SizeFitReport
from desktop.precision import bounded_precision,ocular_positions,validate_native_precision
from desktop.accessories import source_models,decode_dependencies,build_accessories,package_models,combined_preview,validate_accessory
from tools.pac_inspect import inspect_pac,parse_textures
from tools.pac_repack import replace_sections,texture_table
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections,write_preview
from tools.texture_convert import write_gim4,write_gim8,read_gim,budget_texture
from tools.yukes_bpe import compress,decompress
from tools.weight_trial_review import map_source,transfer,descendant_names
from tools.jericho_hybrid_trial import pack
from model_qa.geometry import align_reference,geometry
from model_qa.ocular import OCULAR_NAMES,probes,skin

ROOT=Path(__file__).resolve().parents[1]
PROFILE=ROOT/'desktop/profiles/hctp-v1.json'

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')

class Cancelled(Exception):pass

@dataclass(frozen=True)
class Request:
    source:str
    base:str
    source_format:str='hctp'
    adaptive_textures:bool=False

    def validate(self):
        if not isinstance(self.adaptive_textures,bool):raise ValueError('Adaptive texture option must be a boolean.')
        adapter(self.source_format)
        for raw in (self.source,self.base):
            p=Path(raw)
            if not p.is_file() or p.suffix.lower()!='.pac':raise ValueError('Choose an existing .pac file.')
            if p.stat().st_size>32*1024*1024:raise ValueError('The supported input budget is 32 MiB.')
        if Path(self.source).resolve()==Path(self.base).resolve():raise ValueError('Source and PSP base must be different files.')

def base_model(path):
    data=Path(path).read_bytes();report=inspect_pac(data)
    models=[r for s,r in sections(data) if s['id']==2 and r.startswith(b'YOBJ')]
    if len(models)!=1 or 9 not in {s['id'] for s in report['sections']}:raise ValueError('The PSP base needs supported model and texture sections (2 and 9).')
    model=audit_yobj(models[0])
    if any(m['base_flag']!=0x17ff or m['rigid'] for m in model['meshes']):raise ValueError('This base uses an unimplemented vertex format; choose a float-weight PSP SVR base.')
    controls={m['control'] for mesh in model['meshes'] for m in mesh['materials']}
    if not {5,7}<=controls:raise ValueError('The PSP base needs ordinary indexed4 and indexed8 rendering templates.')
    model.update(bone_count=len(model['bones']),textures=model['texture_names'],model_name=model['report']['model_name'])
    return data,model

def prepare(source,target):
    """Same-name/ancestor body and jaw mapping; donor eyes selected by support."""
    aligned,fit=align_reference(source,target)
    ps=np.array([v['position'] for m in aligned['meshes'] for v in m['vertices']])
    sw=np.zeros((len(ps),source['bone_count']));row=0
    for m in source['meshes']:
        for v in m['vertices']:
            for b,w in zip(m['bone_palette'],v['weights']):sw[row,b]=w
            row+=1
    sw/=sw.sum(1)[:,None];mapped,missing,redirects=map_source(source,target,sw,True)
    if missing.max()>1e-7:raise ValueError('Source weights have no compatible PSP ancestor.')
    ocular=[b['index'] for b in source['bones'] if b['name'] in OCULAR_NAMES]
    jaw=[b['index'] for b in source['bones'] if b['name']=='d_kuchi' or b['name'].startswith('d_kuchi_')]
    selected=sw[:,ocular].sum(1)>1e-7
    if jaw and np.any(sw[selected][:,jaw].sum(1)>1e-7):raise ValueError('Eye/eyelid support overlaps jaw weights; requires review before automatic transfer.')
    if selected.any() and not set(OCULAR_NAMES)<={b['name'] for b in target['bones']}:raise ValueError('PSP base is missing eye/eyelid controllers.')
    names=descendant_names(source,'atama')
    cranial=sw[:,[b['index'] for b in source['bones'] if b['name'] in names]].sum(1)
    donor,transfer_report=transfer(target,ps)
    legacy=mapped*(1-cranial[:,None])+donor*cranial[:,None]
    def prune(w):
        w=w.copy();np.put_along_axis(w,np.argsort(w,axis=1)[:,:-4],0,axis=1);w/=w.sum(1)[:,None];return w
    jaw_weights=prune(mapped);legacy=prune(legacy);weights=jaw_weights.copy();weights[selected]=legacy[selected]
    absent=[b['index'] for b in source['bones'] if b['name'] not in {b['name'] for b in target['bones']}]
    attachments=sw[:,absent].sum(1)>1e-7
    def stage(ws):
        out=copy.deepcopy(aligned);row=0
        for m in out['meshes']:
            m['bone_palette']=list(range(target['bone_count']))
            for v in m['vertices']:
                v['position']=np.asarray(v['position'],dtype=np.float32).astype(float).tolist()
                n=np.array(v['normal']);length=np.linalg.norm(n)
                if length<1e-10:raise ValueError('Source contains an unusable zero normal.')
                v['normal']=(n/length).tolist();v['color']=[*v['color'][:3],255]
                v['weights']=ws[row].tolist();row+=1
        out.update(bones=copy.deepcopy(target['bones']),bone_count=target['bone_count'],uv_v_flipped=False,weight_encoding='float',
                   preserved_attachment_positions=np.asarray(ps[attachments],dtype=np.float32).astype(float).tolist(),
                   preparation_report=dict(alignment=fit,hybrid_weights=dict(ancestor_redirects=redirects,donor_transfer=transfer_report,
                   ocular_selected_records=int(selected.sum()),jaw_source_mapping_preserved=True,
                   policy='Source-derived body/jaw; legacy PSP donor transfer only on source eye/eyelid support')))
        return out
    return stage(weights),stage(legacy),stage(jaw_weights)

def palette_rgba(rgba):
    colors,inverse=np.unique(rgba.reshape(-1,4),axis=0,return_inverse=True)
    if len(colors)>256:raise ValueError('Exact cutout preservation needs at most 256 RGBA colors; no lossy alpha fallback is permitted.')
    pal=np.zeros((256,4),dtype=np.uint8);pal[:len(colors)]=colors
    return inverse.reshape(rgba.shape[:2]).astype(np.uint8),pal

def textures(decoded,prepared,folder,cap):
    folder=Path(folder);folder.mkdir()
    # Pick a main cranial material from controller support, not a texture name.
    head={b['index'] for b in prepared['bones'] if b['name'] in descendant_names(prepared,'atama')}
    scores=Counter()
    for mesh in prepared['meshes']:
        for mat in mesh['materials']:
            scores[mat['texture_id']]+=sum(sum(v['weights'][b] for b in head) for t in mat['triangles'] for v in [mesh['vertices'][t[0]]])/3
    cutouts={i for i,n,r,rgba,d in decoded if np.any(rgba[:,:,3]<128)}
    face=max((i for i in scores if i not in cutouts),key=scores.get,default=None)
    entries=[];gims=[]
    for i,name,raw,rgba,details in decoded:
        cutout=i in cutouts;bits=8 if cutout or i==face else 4
        if cutout:
            pixels,palette=palette_rgba(rgba)
        else:
            limit=128 if i==face else cap
            # Expanded source decoding handles indexed4/8 and direct PS2 colors.
            quant=Image.fromarray(rgba).quantize(colors=256,method=Image.Quantize.FASTOCTREE,dither=Image.Dither.NONE)
            pixels=np.asarray(quant,dtype=np.uint8);palette=np.zeros((256,4),dtype=np.uint8)
            p=np.asarray(quant.getpalette('RGBA'),dtype=np.uint8).reshape(-1,4);palette[:len(p)]=p;palette[:,3]=255
            pixels,palette=budget_texture(pixels,palette,limit,bits)
            # Reuse the successful one-axis resolution reduction. Palette,
            # normalized UVs and source cutout pixels are left unchanged.
            from tools.reduce_psp_textures import smaller
            size=smaller(pixels.shape[1],pixels.shape[0],bits)
            if size:pixels=np.asarray(Image.fromarray(pixels).resize(size,Image.Resampling.NEAREST),dtype=np.uint8)
        gim=(write_gim8 if bits==8 else write_gim4)(pixels,palette)
        p,c=read_gim(gim)
        if not np.array_equal(p,pixels) or not np.array_equal(c,palette):raise ValueError('GIM round trip changed a texture.')
        if cutout and not np.array_equal(c[p],rgba):raise ValueError('Cutout RGBA changed.')
        filename='texture_%02d'%i
        (folder/(filename+'.gim')).write_bytes(gim);Image.fromarray(c[p]).save(folder/(filename+'.png'))
        entries.append(dict(index=i,name=name,bits=bits,cutout=cutout,exact_source_rgba=cutout,gim=filename+'.gim',png=filename+'.png',
                            width=p.shape[1],height=p.shape[0],source_format=details,bytes=len(gim)));gims.append(gim)
    dump(folder/'textures.json',dict(textures=entries))
    return entries,gims

def validate_pac(data,base=None,max_bytes=148000,*,accessory_models=None,gim_reader=read_gim):
    report=inspect_pac(data)
    if len(data)>max_bytes or len(data)%2048 or any(s['offset']%16 for s in report['sections']):raise ValueError('PSP PAC size/alignment check failed.')
    if len({s['id'] for s in report['sections']})!=len(report['sections']):raise ValueError('Duplicate final PAC section IDs.')
    unpacked={s['id']:r for s,r in sections(data)}
    models={i:audit_yobj(raw) for i,raw in unpacked.items() if raw.startswith(b'YOBJ')}
    native=models[2];texture_records=parse_textures(unpacked[9])
    gims={r['name']:unpacked[9][r['offset']:r['offset']+r['size']] for r in texture_records}
    if len(gims)!=len(texture_records) or set(gims)!={n for m in models.values() for n in m['texture_names']}:raise ValueError('Native texture table does not match the YOBJ model set.')
    for raw in gims.values():gim_reader(raw)
    for section,model in models.items():
        for mesh in model['meshes']:
            if (model['report']['mesh_reports'][mesh['index']]['vertex_buffer_start']-8)%16:raise ValueError('Native vertex alignment failed.')
            for row in model['report']['mesh_reports'][mesh['index']]['submeshes']:
                if any((r['start']-8)%16 for r in row['index_ranges']):raise ValueError('Native index alignment failed.')
            for mat in mesh['materials']:
                raw=gims[model['texture_names'][mat['texture_id']]]
                import struct
                bits=struct.unpack_from('<H',raw,76)[0];expected=5 if bits==4 else 7 if bits==8 else None
                if mat['control'] not in (expected,(expected|0x110) if expected else None):raise ValueError('Native GIM/material bit depth mismatch.')
        if section!=2:
            if section not in (26,27):raise ValueError('Unrecognized final auxiliary YOBJ role.')
            if model['texture_names']!=native['texture_names']:raise ValueError('Shared-section accessory texture array differs from the main model.')
            if len(model['bone_raw'])!=len(native['bone_raw']) or any(
                    model['bone_raw'][i:i+64]!=native['bone_raw'][i:i+64] or
                    model['bone_raw'][i+76:i+80]!=native['bone_raw'][i+76:i+80]
                    for i in range(0,len(native['bone_raw']),80)):
                raise ValueError('Accessory local bind records differ from the main PSP rig.')
    if accessory_models is not None:
        if set(models)!={2,*accessory_models}:raise ValueError('Expected accessory model set differs from final PAC.')
        for section,expected in accessory_models.items():validate_accessory(expected,models[section])
    if base is not None:
        before=inspect_pac(base)
        before_ids=[s['id'] for s in before['sections']];after_ids=[s['id'] for s in report['sections']]
        additions=sorted(set(accessory_models or {})-set(before_ids))
        if after_ids!=before_ids+additions:raise ValueError('Base section order or explicit accessory additions changed.')
        after_by_id={s['id']:s for s in report['sections']}
        for a in before['sections']:
            if a['id'] not in {2,9,*(accessory_models or {})} and a['sha256']!=after_by_id[a['id']]['sha256']:raise ValueError('Unrelated base section changed.')
        original=next(r for s,r in sections(base) if s['id']==2)
        if audit_yobj(original)['bone_raw']!=native['bone_raw']:raise ValueError('Base skeleton changed.')
    return native,gims

def ocular_checks(prepared,legacy,jaw,native):
    """Exact selected record replay and local/world probes, not game semantics."""
    src,old,bad,final=map(geometry,(prepared,legacy,jaw,native))
    ids=[i for i,n in enumerate(src.bone_names) if n in OCULAR_NAMES]
    selected=bad.weights[:,ids].sum(1)>1e-7
    by_position={tuple(p):i for i,p in enumerate(src.vertices)}
    final_ids=[];source_ids=[]
    for i,p in enumerate(final.vertices):
        j=by_position.get(tuple(p))
        if j is not None and selected[j]:final_ids.append(i);source_ids.append(j)
    if selected.any() and not final_ids:raise ValueError('Protected ocular records disappeared.')
    if final_ids and not np.allclose(final.weights[final_ids],old.weights[source_ids],atol=2e-7,rtol=0):raise ValueError('PSP packing altered protected ocular weights.')
    rows={}
    for name,probe in probes().items():
        a,unsupported=skin(src,probe);b,_=skin(old,probe);c,_=skin(final,probe)
        delta=float(np.max(np.abs(c.vertices[final_ids]-b.vertices[source_ids]))) if final_ids else 0.
        if delta>src.height*1e-7:raise ValueError('Ocular compatibility replay failed in '+name)
        rows[name]=dict(maximum_legacy_eye_motion_delta=delta,unsupported_controllers=unsupported,finite_positions=bool(np.isfinite(c.vertices).all()))
    return dict(status='pass',selected_source_records=int(selected.sum()),serialized_ocular_records=len(final_ids),poses=rows,
                limitation='Compatibility with the selected donor transfer, not proof of actual SVR eye animation semantics; PPSSPP validation required.')

def blender_path():
    frozen=getattr(sys,'frozen',False)
    path=Path(sys.executable).parent/'runtime/blender/blender.exe' if frozen else Path(os.environ.get('PS2PSP_DEV_BLENDER','/usr/bin/blender'))
    if not path.is_file():raise ValueError('Bundled Blender runtime is missing. Extract the entire portable ZIP again.')
    return path

def run_job(request,work,progress=lambda p,m:None,cancel=lambda:False,*,qa_samples=None,qa_resolution=None):
    request.validate();work=Path(work);work.mkdir(parents=True,exist_ok=True)
    profile=json.loads(PROFILE.read_text());source=Path(request.source);base=Path(request.base)
    hashes={str(p.resolve()):digest(p) for p in (source,base)}
    def check():
        if cancel():raise Cancelled('Conversion cancelled.')
    def step(p,m):check();progress(p,m)
    def command(args,logname):
        check()
        last_qa_line=None
        env=os.environ.copy();env['BLENDER_USER_CONFIG']=str(work/'blender-config');env['BLENDER_USER_EXTENSIONS']=str(work/'blender-extensions')
        with (work/logname).open('w',encoding='utf-8') as log:
            process=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,env=env,
                                     creationflags=0x08000000 if os.name=='nt' else 0)
            try:
                while process.poll() is None:
                    check()
                    if logname=='qa.log':
                        lines=(work/logname).read_text(encoding='utf-8',errors='replace').splitlines()
                        if lines and lines[-1]!=last_qa_line:
                            last_qa_line=lines[-1]
                            poses=sum(line.startswith('Comparing source-derived') for line in lines)
                            if poses:progress(min(90,76+poses),'QA: checking '+last_qa_line.rsplit(' in ',1)[-1].replace('-',' '))
                    time.sleep(.2)
            except BaseException:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
                raise
            if process.returncode:raise ValueError('Processing failed. Read '+logname+' in this job’s logs.')
    step(5,'Reading HCTP source and your PSP base')
    original,decoded=adapter(request.source_format).read(source);base_bytes,target=base_model(base)
    accessories,texture_names=source_models(source,original)
    decoded=decode_dependencies(source,decoded,texture_names)
    source_roles={a['target_section'] for a in accessories}
    base_roles={s['id'] for s,r in sections(base_bytes) if s['id']!=2 and r.startswith(b'YOBJ')}
    if not base_roles<=source_roles:raise ValueError('The PSP base contains unmatched accessory models; choose a base without them or a source with matching supported accessories.')
    dump(work/'model-set-input.json',dict(source_models=[dict(section=2,role='main',vertices=original['vertex_count'],triangles=original['triangle_count'])]+
         [dict(section=a['source_section'],psp_section=a['target_section'],role=a['name'],support=a['support'],vertices=a['model']['vertex_count'],triangles=a['model']['triangle_count']) for a in accessories],texture_dependencies=texture_names))
    step(15,'Uniform alignment and selective facial weighting')
    prepared,legacy,jaw=prepare(original,target)
    prepared['textures']=texture_names;prepared['texture_count']=len(texture_names)
    prepared['cutout_texture_ids']=[i for i,n,r,rgba,d in decoded if np.any(rgba[:,:,3]<128)]
    for name,model in (('source',original),('prepared',prepared),('legacy-eye-control',legacy),('source-jaw-control',jaw)):dump(work/(name+'.json'),model)
    step(25,'Protecting source anatomy and material boundaries before decimation')
    attempts=[];candidate=None
    size_report=SizeFitReport(work/'size-fit.json',profile['max_pac_bytes'],hashes,
                              dict(bytes=source.stat().st_size,meshes=original['mesh_count'],
                                   triangles=original['triangle_count'],textures=len(original['textures'])))
    # Texture fitting precedes lower free-limb retention. Held source surfaces,
    # head floor and facial policy never change between budget attempts.
    for trial,limb_ratio in enumerate((None,.5,.35)):
        trial_profile=copy.deepcopy(profile)
        if limb_ratio is not None:trial_profile['ratios'].update(Arms=limb_ratio,Legs=limb_ratio)
        pp=work/('profile-%d.json'%trial);rp=work/('reduced-%d.json'%trial);dump(pp,trial_profile)
        command([str(blender_path()),'--background','--factory-startup','--python-exit-code','1','--python',str(ROOT/'desktop/geometry_worker.py'),'--',str(work/'prepared.json'),str(rp),str(pp)],'geometry-%d.log'%trial)
        reduced=json.loads(rp.read_text());step(45,'Packing sparse PSP bone palettes and native draw buffers')
        packed=pack(reduced,target)
        for cap in (64,32):
            step(55,'Converting PS2 textures; preserving cutout RGBA')
            tf=work/('textures-'+str(cap))
            if tf.exists():
                entries=json.loads((tf/'textures.json').read_text())['textures'];gims=[(tf/e['gim']).read_bytes() for e in entries]
            else:entries,gims=textures(decoded,prepared,tf,cap)
            accessory_yobjs,accessory_prepared,accessory_reports=build_accessories(accessories,target,prepared['preparation_report']['alignment'],entries)
            yobj=serialize(packed,target,entries)
            table=texture_table(texture_names,gims)
            candidate=package_models(base_bytes,yobj,table,accessory_yobjs);symbols=200
            # Lossless dictionary packing is tried before more geometry loss.
            # The established compressor/grammar and 4000-byte block cap stay
            # unchanged; every candidate is independently decoded and compared.
            if len(candidate)>profile['max_pac_bytes']:
                check()
                smaller_pac=package_models(base_bytes,yobj,table,accessory_yobjs,max_distinct=220)
                if len(smaller_pac)<len(candidate):candidate=smaller_pac;symbols=220
            attempts.append(size_report.record(candidate,accessory_sections=accessory_yobjs,texture_cap=cap,
                free_region_ratios=reduced['reduction_report']['region_ratios'],
                complete_head_minimum_ratio=trial_profile['ratios']['Head'],
                bpe_max_distinct=symbols,bpe_block_cap=4000,
                vertices=packed['vertex_count'],triangles=packed['triangle_count'],
                meshes=packed['mesh_count'],
                protected_triangles=reduced['reduction_report']['protected_triangles']))
            if len(candidate)<=profile['max_pac_bytes']:break
        if len(candidate)<=profile['max_pac_bytes']:break
    precision_validation=None
    # Isolated preview fallback: retain the last guarded topology and all weight
    # bits, then test explicitly bounded float attribute precision. This never
    # runs for a candidate that already fits the established size budget.
    if len(candidate)>profile['max_pac_bytes']:
        step(60,'Testing bounded attribute precision; keeping weights, textures and ocular records')
        original_packed=packed;original_yobj=yobj;held_positions=ocular_positions(jaw)
        precision_rejections=[]
        for divisions in (65536,32768):
            check()
            try:limited,precision_report=bounded_precision(original_packed,held_positions,divisions)
            except ValueError as exc:
                precision_rejections.append(dict(position_divisions=divisions,error=str(exc)))
                dump(work/'precision-rejections.json',precision_rejections);continue
            limited_yobj=serialize(limited,target,entries)
            for symbols in (200,220):
                check()
                limited_pac=package_models(base_bytes,limited_yobj,table,accessory_yobjs,max_distinct=symbols)
                row=size_report.record(limited_pac,accessory_sections=accessory_yobjs,texture_cap=cap,
                    free_region_ratios=reduced['reduction_report']['region_ratios'],
                    complete_head_minimum_ratio=trial_profile['ratios']['Head'],
                    bpe_max_distinct=symbols,bpe_block_cap=4000,
                    vertices=limited['vertex_count'],triangles=limited['triangle_count'],
                    meshes=limited['mesh_count'],
                    protected_triangles=reduced['reduction_report']['protected_triangles'],
                    attribute_precision=precision_report)
                attempts.append(row)
                if len(limited_pac)>profile['max_pac_bytes']:continue
                precision_validation=validate_native_precision(audit_yobj(original_yobj),
                                                               audit_yobj(limited_yobj),held_positions)
                dump(work/'precision-validation.json',precision_validation)
                dump(work/'precision.json',precision_report)
                candidate=limited_pac;packed=limited;yobj=limited_yobj;break
            if len(candidate)<=profile['max_pac_bytes']:break
    size_report.finish(len(candidate)<=profile['max_pac_bytes'])
    if len(candidate)>profile['max_pac_bytes']:raise size_report.error()
    dump(work/'reduced.json',reduced);dump(work/'packed.json',packed)
    texture_reader=read_gim
    adaptive_report=None
    if request.adaptive_textures:
        # The established conversion (including geometry selection) runs exactly
        # as before. The opt-in stage is allowed to replace only texture table 9.
        from desktop.texture_optimizer import optimize_pac
        from desktop.texture_optimizer.candidates import read_gim as adaptive_reader
        step(63,'Analyzing source texture detail and measured PAC upgrade costs')
        (work/'current-texture-method.pac').write_bytes(candidate)
        candidate,adaptive_report=optimize_pac(candidate,decoded,work/'adaptive-textures',
            target=profile['max_pac_bytes'],cancel=check,progress=lambda message:progress(63,message))
        texture_reader=adaptive_reader
    step(65,'Validating final PAC pointers, buffers, weights, rendering records and size')
    native,gim_map=validate_pac(candidate,base_bytes,profile['max_pac_bytes'],accessory_models=accessory_prepared,gim_reader=texture_reader)
    dump(work/'accessory-qa.json',dict(status='pass',models=accessory_reports,
         limitation='Exact source-derived geometry and direct weights, native structure and analytical poses; removal/throw behavior requires in-game validation.'))
    unpacked=next(r for s,r in sections(candidate) if s['id']==2)
    if unpacked!=yobj:raise ValueError('Preview model differs from final PAC.')
    stem=re.sub(r'[^A-Za-z0-9_.-]','_',source.stem)[:48].strip('.') or 'wrestler'
    pac=work/(stem+('-PSP-adaptive-experimental.pac' if request.adaptive_textures else '-PSP-experimental.pac'));pac.write_bytes(candidate)
    preview=work/'preview';preview.mkdir();(preview/'output.yobj').write_bytes(yobj)
    accessory_native=[audit_yobj(raw) for raw in accessory_yobjs.values()]
    visual=combined_preview(native,accessory_native);write_preview(visual,preview/'output.obj')
    for section,raw in accessory_yobjs.items():
        (preview/('section-%d.yobj'%section)).write_bytes(raw)
        independent=combined_preview(native,[])  # Shared preview texture indexing, independent accessory geometry.
        independent['meshes']=[]
        write_preview(combined_preview(independent,[audit_yobj(raw)]),preview/('section-%d.obj'%section))
    mtl=[]
    for i,name in enumerate(visual['texture_names']):
        filename='texture_%02d.png'%i;pixels,palette=texture_reader(gim_map[name]);Image.fromarray(palette[pixels]).save(preview/filename)
        mtl.extend(['newmtl texture_%d'%i,'Kd 1 1 1','map_Kd '+filename])
    (preview/'preview.mtl').write_text('\n'.join(mtl)+'\n',encoding='ascii')
    step(70,'Checking eye/eyelid compatibility and facial regression poses')
    ocular=ocular_checks(prepared,legacy,jaw,native);dump(work/'ocular-qa.json',ocular)
    step(74,'Running static, anatomical, material-boundary and analytical-pose QA')
    args=['--qa',str(source),str(pac),str(work/'qa'),str(work/'prepared.json'),str(work/'reduced.json'),
          str(qa_samples or profile['qa_samples']),str(qa_resolution or profile['qa_resolution'])]
    entry=[sys.executable] if getattr(sys,'frozen',False) else [sys.executable,str(ROOT/'ps2psp_converter.py')]
    command(entry+args,'qa.log')
    qa=json.loads((work/'qa/report.json').read_text())
    # Body QA stays a separate reusable stage. Link the independent model-set
    # evidence so the displayed report does not imply it audited only section 2.
    qa['model_set_validation']=dict(status='pass',model_count=1+len(accessory_yobjs),
        accessory_sections=sorted(accessory_yobjs),report='../accessory-qa.json',
        scope='Every native YOBJ audited; independent accessories compared against prepared source attributes and analytical poses.')
    dump(work/'qa/report.json',qa)
    html=work/'qa/report.html'
    text=html.read_text(encoding='utf-8')
    note='<p>Native model set: %d models. <a href="../accessory-qa.json">Independent accessory structure, attributes and pose validation</a>. <a href="../preview/output.obj">Combined OBJ preview</a>. Actual in-game pad removal/throw behavior remains unverified.</p>'%(1+len(accessory_yobjs))
    if adaptive_report is not None:
        note+='<p>Adaptive textures enabled. <a href="../adaptive-textures/report.html">Source/current/adaptive textures and allocation report</a>. Every non-texture section payload is byte-identical to the current-method baseline.</p>'
    text=text.replace('</body>',note+'</body>')
    html.write_text(text,encoding='utf-8')
    step(92,'Rendering textured views of the actual final PSP output')
    from desktop.preview import save_views
    save_views(visual,gim_map,preview,gim_reader=texture_reader)
    for p,h in hashes.items():
        if digest(p)!=h:raise ValueError('An input changed during conversion; output withheld.')
    result=dict(pac=str(pac),preview=str(preview),report=str(work/'qa/report.html'),bytes=len(candidate),sha256=digest(pac),
                source=str(source.resolve()),base=str(base.resolve()),inputs=hashes,profile=profile['id'],size_attempts=attempts,
                meshes=native['report']['meshes'],triangles=packed['triangle_count'],vertices=packed['vertex_count'],
                model_count=1+len(accessory_yobjs),accessory_sections=sorted(accessory_yobjs),
                total_meshes=native['report']['meshes']+sum(a['meshes'] for a in accessory_reports),
                total_triangles=packed['triangle_count']+sum(a['triangles'] for a in accessory_reports),
                total_vertices=packed['vertex_count']+sum(a['vertices'] for a in accessory_reports),
                native_validation='passed',review_flags=len(qa['unresolved_review']),ocular_validation=ocular['status'],
                attribute_precision=packed.get('attribute_precision_report'),
                precision_validation=precision_validation,
                status='Experimental conversion; review QA and test in PPSSPP. File checks do not certify game compatibility.')
    if adaptive_report is not None:
        result['adaptive_textures']=dict(report=str(work/'adaptive-textures/report.html'),
            baseline_pac=str(work/'current-texture-method.pac'),baseline_bytes=adaptive_report['baseline_bytes'],
            pixel_palette_bytes=adaptive_report['pixel_palette_bytes'],unchanged_non_texture_payloads=True)
    dump(work/'result.json',result);step(100,'Ready for review and Save As')
    return result

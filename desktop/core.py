"""Offline job orchestration. Established readers/reducer/writer/QA stay separate.

No character hashes or file names select conversion behavior. User files are
read-only; every candidate is built in its own disposable job directory.
"""
from desktop.limits import IN_RING_MAX_PAC_BYTES
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
from tools.vertex_identity import annotate, protected_face_positions
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
    skin_palette_compatibility:bool=True
    priority_textures:tuple=()
    texture_review_sha256:str=''
    texture_mode:str=''
    downgrade_steps:int=0
    source_entry:str=''
    texture_review_entry:str=''
    costume_role:str='ring'
    wii_geometry:str='Standard'

    @property
    def use_adaptive(self):
        return self.texture_mode=='ATO' if self.texture_mode else self.adaptive_textures

    @property
    def maximum_downgrade(self):
        return self.texture_mode=='Maximum Downgrade'

    @property
    def default_texture_quality(self):
        if self.use_adaptive or self.maximum_downgrade or self.priority_textures:
            return False
        return self.texture_mode in ('','Default','Downgrade','Priority Selection')

    def validate(self):
        from desktop.texture_review import validate_selection
        selected=validate_selection(self.priority_textures)
        from desktop.texture_modes import MODES
        if self.texture_mode and self.texture_mode not in MODES:raise ValueError('Unknown texture mode.')
        if type(self.downgrade_steps) is not int or self.downgrade_steps not in (0,1,2,3):raise ValueError('Downgrade must be one, two or three sizes.')
        if self.texture_mode and self.texture_mode!='ATO' and self.adaptive_textures:raise ValueError('Choose one texture mode; ATO cannot be combined with this mode.')
        if self.texture_mode and self.texture_mode!='Priority Selection' and selected:raise ValueError('Selected textures require Priority Selection mode.')
        if self.texture_mode=='Downgrade' and not self.downgrade_steps:raise ValueError('Choose one, two or three downgrade steps.')
        if self.downgrade_steps and (self.texture_mode not in ('','Downgrade') or self.use_adaptive or selected):raise ValueError('Downgrade cannot be combined with ATO or priorities.')
        if selected and (not isinstance(self.texture_review_sha256,str) or not re.fullmatch('[0-9a-f]{64}',self.texture_review_sha256)):
            raise ValueError('Selected textures require the source preview SHA-256; review textures again.')
        if not isinstance(self.adaptive_textures,bool):raise ValueError('Adaptive texture option must be a boolean.')
        if not isinstance(self.skin_palette_compatibility,bool):raise ValueError('Skin palette compatibility option must be a boolean.')
        adapter(self.source_format)
        if self.costume_role not in ('ring','entrance'):raise ValueError('Choose ring or entrance output.')
        if self.source_format!='wwe13-wii' and self.costume_role!='ring':raise ValueError('Entrance budget is available only for WWE 13 Wii.')
        if self.wii_geometry not in ('Standard','Preserve Hands','Preserve Arms'):raise ValueError('Unknown Wii geometry profile.')
        if self.source_format!='wwe13-wii' and self.wii_geometry!='Standard':raise ValueError('Wii geometry profiles require a Wii source.')
        if not isinstance(self.source_entry,str) or not isinstance(self.texture_review_entry,str):raise ValueError('Source entry must be a string.')
        if self.source_format=='jbi':
            if self.source_entry and not re.fullmatch('[0-9a-f]{4}',self.source_entry):raise ValueError('Choose a four-digit JBI archive entry.')
            if self.texture_mode=='Legacy':raise ValueError('Legacy textures are HCTP-only. Select Default for the validated JBI texture path.')
            if selected and self.texture_review_entry!=self.source_entry:raise ValueError('JBI costume changed since texture review; review its textures again.')
        elif self.source_format=='wwe13-wii':
            if self.source_entry and not re.fullmatch('[0-9]{2}',self.source_entry):raise ValueError('Choose a two-digit Wii costume index.')
            if self.texture_mode not in ('','Default') or selected or self.use_adaptive or self.downgrade_steps:
                raise ValueError('This experimental Wii preview supports Default textures only; HCTP/JBI texture modes are unchanged.')
            if self.texture_review_entry:raise ValueError('Wii texture priority review is not available in this preview.')
        elif self.source_entry or self.texture_review_entry:raise ValueError('Only JBI archives or Wii containers have a costume selector.')
        for raw in (self.source,self.base):
            p=Path(raw)
            if not p.is_file() or p.suffix.lower()!='.pac':raise ValueError('Choose an existing .pac file.')
            limit=64*1024*1024 if self.source_format=='wwe13-wii' and raw==self.source else 32*1024*1024
            if p.stat().st_size>limit:raise ValueError('The supported input budget is %d MiB.'%(limit//1024//1024))
        if Path(self.source).resolve()==Path(self.base).resolve():raise ValueError('Source and PSP base must be different files.')
        if selected and digest(self.source)!=self.texture_review_sha256:
            raise ValueError('Source PAC changed since texture review; select the source and review textures again.')

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
        annotate(out)
        from model_qa.skinning_records import contact_shape_guards
        out['source_contact_shape_guards']=contact_shape_guards(out)
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

def validate_pac(data,base=None,max_bytes=IN_RING_MAX_PAC_BYTES,*,accessory_models=None,gim_reader=read_gim,lossless_texture_sections=()):
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
            if a['id'] not in {2,9,*(accessory_models or {})} and a['sha256']!=after_by_id[a['id']]['sha256']:
                if a['id'] not in lossless_texture_sections:raise ValueError('Unrelated base section changed.')
                old_raw=next(r for s,r in sections(base) if s['id']==a['id'])
                if old_raw!=unpacked[a['id']]:raise ValueError('Lossless retained texture section changed decoded data.')
                for t in parse_textures(old_raw):
                    if t['extension']!='gim':raise ValueError('Lossless storage exception requires a named GIM table.')
                    gim_reader(old_raw[t['offset']:t['offset']+t['size']])
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
    if request.source_format=='wwe13-wii':
        from desktop.wii_job import run_job as run_wii
        return run_wii(request,work,progress,cancel,qa_samples=qa_samples,qa_resolution=qa_resolution)
    if request.source_format=='jbi':
        from desktop.jbi_job import run_job as run_jbi
        return run_jbi(request,work,progress,cancel)
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
    from desktop.texture_review import validate_selection
    validate_selection(request.priority_textures,[n for i,n,raw,rgba,details in decoded])
    if request.priority_textures and digest(source)!=request.texture_review_sha256:
        raise ValueError('Source PAC changed since texture review; review textures again.')
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
        original_packed=packed;original_yobj=yobj;held_positions=ocular_positions(jaw)|protected_face_positions(packed)
        precision_rejections=[]
        # Intentional skinning contacts must not be collapsed by position
        # rounding. Keep every position exact for these source models; only
        # bounded shading/UV precision is considered outside protected faces.
        preserve_contacts=prepared['source_skinning_identity']['conflicting_positions']>0
        precision_trials=[(65536,('normal',)),(65536,('normal','uv'))] if preserve_contacts else [(n,('position','uv','normal')) for n in (65536,32768)]
        for divisions,attributes in precision_trials:
            check()
            try:limited,precision_report=bounded_precision(original_packed,held_positions,divisions,attributes=attributes)
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
                if len(limited_pac)>profile['max_pac_bytes'] and not (request.maximum_downgrade and len(limited_pac)<len(candidate)):continue
                precision_validation=validate_native_precision(audit_yobj(original_yobj),
                                                               audit_yobj(limited_yobj),held_positions)
                dump(work/'precision-validation.json',precision_validation)
                dump(work/'precision.json',precision_report)
                candidate=limited_pac;packed=limited;yobj=limited_yobj
                if len(candidate)<=profile['max_pac_bytes']:break
            if len(candidate)<=profile['max_pac_bytes']:break
    if not request.maximum_downgrade:
        size_report.finish(len(candidate)<=profile['max_pac_bytes'])
        if len(candidate)>profile['max_pac_bytes']:raise size_report.error()
    dump(work/'reduced.json',reduced);dump(work/'packed.json',packed)
    texture_reader=read_gim
    adaptive_report=None
    if request.use_adaptive:
        # The established conversion (including geometry selection) runs exactly
        # as before. The opt-in stage is allowed to replace only texture table 9.
        from desktop.texture_optimizer import optimize_pac
        from desktop.texture_optimizer.candidates import read_gim as adaptive_reader
        step(63,'Analyzing source texture detail and measured PAC upgrade costs')
        (work/'current-texture-method.pac').write_bytes(candidate)
        candidate,adaptive_report=optimize_pac(candidate,decoded,work/'adaptive-textures',
            target=profile['max_pac_bytes'],cancel=check,progress=lambda message:progress(63,message))
        texture_reader=adaptive_reader
    compatibility_report=None
    if request.skin_palette_compatibility:
        from desktop.skinning import apply_single_slot_compatibility
        step(64,'Checking single-slot skinning layouts; preserving effective weights')
        (work/'before-skin-compatibility.pac').write_bytes(candidate)
        candidate,compatibility_report=apply_single_slot_compatibility(candidate,
            max_bytes=max(profile['max_pac_bytes'],len(candidate)+8*len(yobj)) if request.maximum_downgrade else profile['max_pac_bytes'],cancel=check)
        dump(work/'skin-compatibility.json',compatibility_report)
        yobj=next(raw for s,raw in sections(candidate) if s['id']==2)
        accessory_yobjs={s['id']:raw for s,raw in sections(candidate) if s['id'] in accessory_yobjs}
        # Keep the source-derived accessory validator exact in the expanded
        # representation. Only append the zero slots already proven by the
        # native before/after verifier; never substitute final geometry for the
        # independent expected source attributes.
        for model_report in compatibility_report['changed_models']:
            section=model_report['section']
            if section not in accessory_prepared:continue
            expected=copy.deepcopy(accessory_prepared[section])
            for change in model_report['changed_meshes']:
                mesh=expected['meshes'][change['mesh']]
                if mesh['bone_palette']!=change['old_palette']:raise ValueError('Accessory compatibility provenance differs.')
                mesh['bone_palette']=change['new_palette']
                count=len(change['new_palette'])-len(change['old_palette'])
                for vertex in mesh['vertices']:vertex['weights']=vertex['weights']+[0.]*count
            accessory_prepared[section]=expected
    default_report=None
    if request.default_texture_quality:
        from desktop.default_textures import upgrade
        from desktop.texture_optimizer.candidates import read_gim as default_reader
        step(64,'Preserving source texture detail within the final model and native-reference budget')
        (work/'legacy-texture-method.pac').write_bytes(candidate)
        candidate,default_report=upgrade(candidate,decoded,work/'default-textures',
            target=profile['max_pac_bytes'],cancel=check,progress=lambda message:progress(64,message))
        texture_reader=default_reader
    priority_report=None
    if request.priority_textures:
        from desktop.default_textures import upgrade
        from desktop.texture_optimizer.candidates import read_gim as priority_reader
        step(64,'Allocating the selected texture fidelity priorities within the final model budget')
        (work/'before-texture-priorities.pac').write_bytes(candidate)
        candidate,priority_report=upgrade(candidate,decoded,work/'texture-priorities',
            target=profile['max_pac_bytes'],cancel=check,progress=lambda message:progress(64,message),
            priority_textures=request.priority_textures)
        texture_reader=priority_reader
    downgrade_report=None
    if request.downgrade_steps:
        from desktop.texture_modes import downgrade_pac
        from desktop.texture_optimizer.candidates import read_gim as downgrade_reader
        step(64,'Applying the selected Default-texture downgrade; checking actual PAC and texture allocation')
        (work/'before-texture-downgrade.pac').write_bytes(candidate)
        candidate,downgrade_report=downgrade_pac(candidate,decoded,work/'texture-downgrade',
            steps=request.downgrade_steps,target=profile['max_pac_bytes'],cancel=check)
        texture_reader=downgrade_reader
    maximum_report=None
    if request.maximum_downgrade:
        from desktop.maximum_downgrade import fit_pac
        from desktop.texture_optimizer.candidates import read_gim as maximum_reader
        step(64,'Fitting textures only; keeping the validated Default geometry candidate unchanged')
        (work/'before-maximum-downgrade.pac').write_bytes(candidate)
        try:
            candidate,maximum_report=fit_pac(candidate,work/'maximum-downgrade',target=profile['max_pac_bytes'],
                cancel=check,progress=lambda message:progress(64,message))
        except ValueError:
            size_report.finish(False)
            raise
        texture_reader=maximum_reader
        attempts.append(size_report.record(candidate,accessory_sections=accessory_yobjs,texture_mode='Maximum Downgrade',
            vertices=packed['vertex_count'],triangles=packed['triangle_count'],meshes=packed['mesh_count']))
        size_report.finish(True)
    step(65,'Validating final PAC pointers, buffers, weights, rendering records and size')
    native,gim_map=validate_pac(candidate,base_bytes,profile['max_pac_bytes'],accessory_models=accessory_prepared,gim_reader=texture_reader,
        lossless_texture_sections={r['section'] for report in (default_report,adaptive_report,priority_report) if report for r in report['lossless_retained_texture_storage']})
    from model_qa.skinning_records import compare as compare_skinning_records
    skinning_identity=compare_skinning_records(prepared,native,strict=False)
    dump(work/'skinning-identity-qa.json',skinning_identity)
    if skinning_identity['status']!='pass':
        raise ValueError('Source skinning validation failed; read skinning-identity-qa.json. '+skinning_identity['issues'][0]['kind'])
    dump(work/'accessory-qa.json',dict(status='pass',models=accessory_reports,
         limitation='Exact source-derived geometry and direct weights, native structure and analytical poses; removal/throw behavior requires in-game validation.'))
    unpacked=next(r for s,r in sections(candidate) if s['id']==2)
    if unpacked!=yobj:raise ValueError('Preview model differs from final PAC.')
    stem=re.sub(r'[^A-Za-z0-9_.-]','_',source.stem)[:48].strip('.') or 'wrestler'
    suffix='-PSP-maximum-downgrade-experimental.pac' if request.maximum_downgrade else '-PSP-adaptive-experimental.pac' if request.use_adaptive else ('-PSP-downgrade-%d-experimental.pac'%request.downgrade_steps if request.downgrade_steps else '-PSP-experimental.pac')
    pac=work/(stem+suffix);pac.write_bytes(candidate)
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
    qa['source_skinning_identity']=dict(status=skinning_identity['status'],report='../skinning-identity-qa.json',
        conflicting_source_locations=skinning_identity['source_conflicting_locations'],
        maximum_motion_error=skinning_identity['maximum_motion_error'])
    if default_report is not None:
        qa['default_texture_quality']=dict(report='../default-textures/report.html',
            automatic_priorities=default_report['default_policy']['chosen_priorities'],
            pixel_palette_bytes=default_report['pixel_palette_bytes'],pixel_palette_budget=default_report['pixel_palette_budget'],
            unchanged_model_payloads=True,detail_review_textures=default_report['default_policy']['detail_review_textures'])
    if compatibility_report is not None:
        qa['skin_palette_compatibility']=dict(report='../skin-compatibility.json',
            changed_meshes=compatibility_report['changed_meshes'],
            added_vertex_buffer_bytes=compatibility_report['added_vertex_buffer_bytes'],
            effective_geometry_weights_exact=True,analytical_pose_replay='exact')
    dump(work/'qa/report.json',qa)
    html=work/'qa/report.html'
    text=html.read_text(encoding='utf-8')
    note='<p>Native model set: %d models. <a href="../accessory-qa.json">Independent accessory structure, attributes and pose validation</a>. <a href="../preview/output.obj">Combined OBJ preview</a>. Actual in-game pad removal/throw behavior remains unverified.</p>'%(1+len(accessory_yobjs))
    note+='<p>Source-authorized coincident skinning: %d locations. <a href="../skinning-identity-qa.json">Protected face correspondence, effective weights and analytical motion/gap checks</a>. Distinct source branches are retained; newly introduced inconsistencies stop export.</p>'%skinning_identity['source_conflicting_locations']
    if default_report is not None:
        note+='<p>Default textures: <a href="../default-textures/report.html">Automatic detail priorities, source/final images and independent texture budget</a>. The final model data is unchanged by this texture stage. <a href="../legacy-texture-method.pac">Legacy comparison PAC</a>.</p>'
    if adaptive_report is not None:
        texture_flags=sum(bool(t['quality_review_flags']) for t in adaptive_report['textures'])
        note+='<p>Adaptive textures enabled: %d textures have tradeoffs requiring review. <a href="../adaptive-textures/report.html">Source/current/adaptive textures and allocation report</a>. The texture stage preserves every non-texture payload; any subsequent skin-layout adaptation is reported separately.</p>'%texture_flags
    if compatibility_report is not None:
        note+='<p>Single-slot skinning compatibility: %d meshes adapted, %d additional decoded vertex-buffer bytes. <a href="../skin-compatibility.json">Exact geometry, effective weights and analytical pose preservation checks</a>. Other small palettes remain review findings; no universal minimum is claimed.</p>'%(compatibility_report['changed_meshes'],compatibility_report['added_vertex_buffer_bytes'])
    if priority_report is not None:
        note+='<p>Manual texture priorities: <a href="../texture-priorities/report.html">Source/current/final previews, selected settings, reductions and budget decisions</a>. Up to three selections; size limits and source ceilings remain enforced.</p>'
    if downgrade_report is not None:
        note+='<p>Texture downgrade: <a href="../texture-downgrade/report.html">Requested source reductions, actual dimensions, palette/alpha checks and serialized budget</a>. No additional texture reduction or geometry changes were used to force this setting to fit.</p>'
    if maximum_report is not None:
        note+='<p>Maximum Downgrade: <a href="../maximum-downgrade/report.html">Texture quality losses, candidates and measured size decisions</a>. Default geometry fitting is unchanged; every non-texture payload is identical to the compatibility-adjusted baseline. Any existing bounded attribute-precision fallback is reported separately.</p>'
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
                skinning_identity_validation=skinning_identity['status'],
                attribute_precision=packed.get('attribute_precision_report'),
                precision_validation=precision_validation,
                status='Experimental conversion; review QA and test in PPSSPP. File checks do not certify game compatibility.')
    if adaptive_report is not None:
        result['adaptive_textures']=dict(report=str(work/'adaptive-textures/report.html'),
            baseline_pac=str(work/'current-texture-method.pac'),baseline_bytes=adaptive_report['baseline_bytes'],
            pixel_palette_bytes=adaptive_report['pixel_palette_bytes'],unchanged_non_texture_payloads=True,
            preservation_scope='Texture stage; subsequent skin-layout changes validated separately.',
            review_flags=texture_flags)
        result['review_flags']+=texture_flags
    if default_report is not None:
        policy=default_report['default_policy']
        result['default_textures']=dict(report=str(work/'default-textures/report.html'),
            baseline_pac=str(work/'legacy-texture-method.pac'),
            automatic_priorities=policy['chosen_priorities'],detail_review_textures=policy['detail_review_textures'],
            pixel_palette_bytes=default_report['pixel_palette_bytes'],pixel_palette_budget=default_report['pixel_palette_budget'],
            unchanged_model_payloads=True,policy=policy['id'])
        result['review_flags']+=sum(bool(t['quality_review_flags']) for t in default_report['textures'])
    if priority_report is not None:
        selected=[t for t in priority_report['textures'] if t['manual_priority']]
        reductions=sum(not t['priority_reduction_report']['full_source_preserved'] for t in selected)
        result['texture_priorities']=dict(names=list(request.priority_textures),
            report=str(work/'texture-priorities/report.html'),reductions=reductions,
            baseline_pac=str(work/'before-texture-priorities.pac'),
            donor_textures=[t['name'] for t in priority_report['textures'] if 'donor_change' in t],
            unimproved_textures=[t['name'] for t in selected if t['priority_quality_improvement']<=1e-10],
            selected_settings=[dict(name=t['name'],**t['priority_reduction_report']) for t in selected])
        result['review_flags']+=sum(bool(t['quality_review_flags']) for t in priority_report['textures'])
    if downgrade_report is not None:
        result['texture_downgrade']=dict(report=str(work/'texture-downgrade/report.html'),
            steps=request.downgrade_steps,baseline_pac=str(work/'before-texture-downgrade.pac'),
            pixel_palette_bytes=downgrade_report['pixel_palette_bytes'],
            pixel_palette_budget=downgrade_report['pixel_palette_budget'])
    result['texture_mode']=request.texture_mode or ('Downgrade' if request.downgrade_steps else 'ATO' if request.use_adaptive else 'Priority Selection' if request.priority_textures else 'Default')
    if maximum_report is not None:
        result['maximum_downgrade']=dict(report=str(work/'maximum-downgrade/report.html'),
            baseline_pac=str(work/'before-maximum-downgrade.pac'),baseline_bytes=maximum_report['baseline_bytes'],
            changed_textures=maximum_report['changed_textures'],unchanged_non_texture_payloads=True,
            pixel_palette_bytes=maximum_report['final_texture_pixel_palette_bytes'])
    if compatibility_report is not None:
        result['skin_palette_compatibility']=dict(report=str(work/'skin-compatibility.json'),
            baseline_pac=str(work/'before-skin-compatibility.pac'),
            changed_meshes=compatibility_report['changed_meshes'],
            added_vertex_buffer_bytes=compatibility_report['added_vertex_buffer_bytes'],
            effective_geometry_weights_exact=True)
    dump(work/'result.json',result);step(100,'Ready for review and Save As')
    return result

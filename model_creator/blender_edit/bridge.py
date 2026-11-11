"""Private Blender sessions and validated, reversible native edit builds."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace

import numpy as np
from PIL import Image

from desktop.blender_runtime import resolve,version
from desktop.texture_optimizer.candidates import encode,read_gim
from model_creator.core import load_source,dump,MAX_BYTES,qa,preview
from model_creator.morph.document import Document
from model_creator.morph.native_patch import patch as patch_shape
from model_creator.morph.qa import validate as validate_shape
from model_creator.uv.native_patch import patch as patch_uv
from tools.prepare_model import bone_matrices
from tools.pac_repack import replace_sections,texture_table
from tools.yukes_bpe import compress,decompress
from tools.psp_mesh_merge_trial import sections

SCHEMA='psp-model-creator.blender-edit/1'
def sha(raw):return hashlib.sha256(raw).hexdigest()

def run_worker(mode,job,output,*,runtime=None,extra=(),cancel=lambda:False):
    executable=resolve(runtime);version(executable)
    env=os.environ.copy();env['BLENDER_USER_CONFIG']=str(output.parent/'config');env['BLENDER_USER_EXTENSIONS']=str(output.parent/'extensions')
    with output.with_suffix('.log').open('w',encoding='utf-8') as log:
        child=subprocess.Popen([str(executable),'--background','--factory-startup','--disable-autoexec','--python-exit-code','1',
            '--python',str(Path(__file__).with_name('worker.py')),'--',mode,str(job),str(output),*[str(p) for p in extra]],
            stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=0x08000000 if os.name=='nt' else 0)
        start=time.monotonic()
        try:
            while child.poll() is None:
                if cancel():raise ValueError('Blender edit operation cancelled')
                if time.monotonic()-start>180:raise ValueError('Blender edit operation timed out')
                time.sleep(.05)
            if child.returncode:raise ValueError('Blender edit validation failed: '+output.with_suffix('.log').read_text(encoding='utf-8')[-2500:])
        finally:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait()
    return json.loads(output.read_text(encoding='utf-8'))

def make_job(source):
    model=source['model'];points=np.array([v['position']for m in model['meshes']for v in m['vertices']]);height=float(np.ptp(points[:,1]));matrices=bone_matrices(model)
    if height<=0:raise ValueError('Model has no usable height')
    if any(m['rigid'] or m['base_flag']!=0x17ff for m in model['meshes']):raise ValueError('Blender editing currently requires native float-weight skinned meshes')
    meshes=[]
    for m in model['meshes']:
        meshes.append(dict(vertices=[{k:v[k] for k in ('position','normal','uv','weights')}for v in m['vertices']],palette=m['bone_palette'],
            faces=[list(t) for a in m['materials']for t in a['triangles']],texture_ids=[a['texture_id']for a in m['materials']for _ in a['triangles']]))
    result=dict(schema=SCHEMA,baseline_sha256=source['sha256'],height=height,meshes=meshes,
        bones=[dict(name=b['name'],parent=b['parent'],position=matrices[b['index'],:3,3].tolist())for b in model['bones']],
        textures=[dict(name=n,file=f'texture_{i:03d}.png',size=list(read_gim(source['textures'][n.casefold()])[0].shape[::-1]))for i,n in enumerate(model['texture_names'])])
    return json.loads(json.dumps(result,allow_nan=False))

def create_session(pac,folder,*,runtime=None,library=False,cancel=lambda:False):
    source=load_source(pac,library=library);job=make_job(source);folder=Path(folder)
    # Never overwrite a previous Blender work session.
    folder.mkdir(parents=True,exist_ok=False);(folder/'baseline.pac').write_bytes(source['data'])
    for row in job['textures']:
        ix,pal=read_gim(source['textures'][row['name'].casefold()]);Image.fromarray(pal[ix]).save(folder/row['file'])
    dump(folder/'job.json',job);contract=run_worker('create',folder/'job.json',folder/'contract.json',runtime=runtime,cancel=cancel)
    metadata=dict(schema=SCHEMA,baseline_sha256=source['sha256'],job_sha256=sha((folder/'job.json').read_bytes()),contract_sha256=sha((folder/'contract.json').read_bytes()),library=library,runtime=version(resolve(runtime)))
    dump(folder/'session.json',metadata)
    (folder/'README.txt').write_text('Edit model.blend in Blender 4.3.2. Edit Mode/sculpt positions, PSP UVs and existing textures are supported. Keep vertex order/count, faces, rig, weights and material assignments unchanged. Keep each native vertex UV together; split UV corners cannot return without new vertex records. Apply object transforms and shape keys; remove extra modifiers before import. Save the .blend and save/pack painted images. The rig is a bind-position display, not a reproduction of PSP animation axes. Use Creator Import saved Blender file to validate a new build. Your baseline and previous builds remain unchanged. Reassembling Creator choices does not reapply Blender edits.\n',encoding='utf-8')
    return folder/'model.blend'

def launch(blend,*,runtime=None):
    executable=resolve(runtime);version(executable)
    return subprocess.Popen([str(executable),'--disable-autoexec',str(Path(blend).resolve())],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000 if os.name=='nt' else 0)

def session_source(folder,current_pac):
    folder=Path(folder);meta=json.loads((folder/'session.json').read_text(encoding='utf-8'))
    if meta.get('schema')!=SCHEMA:raise ValueError('Unsupported Blender session')
    if sha(Path(current_pac).read_bytes())!=meta['baseline_sha256'] or sha((folder/'baseline.pac').read_bytes())!=meta['baseline_sha256']:raise ValueError('Blender session baseline differs from the current Creator build; restore the matching build first')
    for name,key in [('job.json','job_sha256'),('contract.json','contract_sha256')]:
        if sha((folder/name).read_bytes())!=meta[key]:raise ValueError('Blender session contract changed')
    source=load_source(folder/'baseline.pac',library=meta['library'])
    if json.loads((folder/'job.json').read_text())!=make_job(source):raise ValueError('Blender session records differ from the native baseline')
    return meta,source

def apply_result(source,result,texture_paths,report,*,library=False):
    """Worker-independent native validation; output remains private until all checks pass."""
    if result.get('baseline_sha256')!=source['sha256'] or len(result['meshes'])!=len(source['model']['meshes']):raise ValueError('Blender result identity differs')
    raw=source['sections'][2];model=source['model'];job=make_job(source);points=[];normals=[];uv=[]
    for row,baseline in zip(result['meshes'],job['meshes']):
        for key,width,output in [('positions',3,points),('normals',3,normals),('uv',2,uv)]:
            a=np.asarray(row[key],float)
            if a.shape!=(len(baseline['vertices']),width) or not np.isfinite(a).all():raise ValueError('Invalid Blender '+key)
            old=np.array([v[{'positions':'position','normals':'normal','uv':'uv'}[key]]for v in baseline['vertices']])
            tolerance=job['height']*1e-7 if key=='positions' else 1e-6
            a[np.max(np.abs(a-old),axis=1)<tolerance]=old[np.max(np.abs(a-old),axis=1)<tolerance]
            output.extend(a.tolist())
    p=np.array([v['position']for m in model['meshes']for v in m['vertices']]);faces=[];offset=0
    for m in model['meshes']:
        faces.extend([[offset+i for i in t]for mat in m['materials']for t in mat['triangles']]);offset+=len(m['vertices'])
    reference=SimpleNamespace(points=p,height=job['height'],faces=np.asarray(faces,int),baseline=model)
    reference.check_geometry=lambda value:Document.check_geometry(reference,value)
    reference.check_geometry(np.array(points))
    old_normals=np.array([v['normal']for m in model['meshes']for v in m['vertices']])
    changed_normals=np.max(np.abs(np.asarray(normals)-old_normals),axis=1)>1e-6
    if np.any(np.abs(np.linalg.norm(np.asarray(normals)[changed_normals],axis=1)-1)>.05):raise ValueError('Blender returned non-unit normals')
    if np.array_equal(np.asarray(points,np.float32),p.astype(np.float32)) and np.array_equal(np.asarray(normals,np.float32),old_normals.astype(np.float32)):
        shape=dict(native_readback=True,topology_uv_weights_materials_bones_exact=True,changed_bytes=0,mesh_bounds_expanded=[])
    else:raw,shape=patch_shape(raw,points,normals)
    raw,uvproof=patch_uv(raw,uv)
    from model_creator.native import audit_yobj
    native=audit_yobj(raw);checks=validate_shape(reference,native,np.array(points));checks['creator']=qa(raw,report,library=library)
    maps={};changed=[]
    if len(texture_paths)!=len(job['textures']):raise ValueError('Blender texture bindings differ')
    for row,path in zip(job['textures'],texture_paths):
        name=row['name'];original=source['textures'][name.casefold()];ix,pal=read_gim(original)
        with Image.open(path)as image:
            if list(image.size)!=row['size']:raise ValueError('Blender texture dimensions changed: '+name)
            rgba=np.array(image.convert('RGBA'))
        decoded=pal[ix];visible=decoded[:,:,3]>0
        if np.array_equal(rgba[:,:,3],decoded[:,:,3]) and np.array_equal(rgba[:,:,:3][visible],decoded[:,:,:3][visible]):maps[name]=original;continue
        bits=4 if len(pal)==16 else 8;encoded=encode(rgba,image.size,bits,1<<bits)['raw'];ei,ep=read_gim(encoded)
        if not np.array_equal(ep[ei][:,:,3],rgba[:,:,3]):raise ValueError('Texture palette cannot preserve edited alpha: '+name)
        maps[name]=encoded;changed.append(name)
    replacements={}
    if raw!=source['sections'][2]:replacements[2]=compress(raw,max_distinct=220)
    if changed:replacements[9]=compress(texture_table(model['texture_names'],[maps[n]for n in model['texture_names']],gim_reader=read_gim),max_distinct=220)
    pac=replace_sections(source['data'],replacements) if replacements else source['data']
    if len(pac)>MAX_BYTES:raise ValueError(f'Blender edits exceed the PSP PAC budget ({len(pac):,} / {MAX_BYTES:,} bytes); simplify the edit or fit textures before export')
    decoded={s['id']:r for s,r in sections(pac)}
    if decoded[2]!=raw or any(decoded[k]!=v for k,v in source['sections'].items()if k not in replacements):raise ValueError('Blender PAC roundtrip changed unrelated data')
    return pac,dict(shape=shape,uv=uvproof,poses=checks,changed_textures=changed,baseline_sha256=source['sha256'],runtime_status='Analytical checks only; not game-tested')

def import_session(folder,blend,current_pac,output,*,runtime=None,report=None,cancel=lambda:False):
    folder=Path(folder).resolve();blend=Path(blend).resolve();meta,source=session_source(folder,current_pac);report=copy.deepcopy(report or dict(seams=[],selections={}))
    blend_sha=sha(blend.read_bytes());original_sha=sha(Path(current_pac).read_bytes());output=Path(output)
    if output.exists():raise ValueError('Choose a new Blender import build folder')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.creator-blender-readback-',dir=output.parent) as temp:
        temp=Path(temp);result=run_worker('extract',folder/'job.json',temp/'result.json',runtime=runtime,extra=(folder/'contract.json',blend),cancel=cancel)
        paths=[temp/f'texture_{i:03d}.png'for i in range(len(source['model']['texture_names']))]
        pac,proof=apply_result(source,result,paths,report,library=meta['library'])
        if sha(blend.read_bytes())!=blend_sha or sha(Path(current_pac).read_bytes())!=original_sha:raise ValueError('Blender file or Creator build changed during import')
        if cancel():raise ValueError('Blender import cancelled')
        stage=temp/'validated-build';stage.mkdir();(stage/'created-model.pac').write_bytes(pac)
        final=load_source(stage/'created-model.pac',library=meta['library']);maps={n:final['textures'][n.casefold()]for n in final['model']['texture_names']}
        report.update(pac_bytes=len(pac),pac_sha256=sha(pac),yobj_sha256=sha(final['sections'][2]),within_budget=True,qa=proof['poses']['creator'],textures_byte_exact=not bool(proof['changed_textures']),blender_edit=dict(proof,blend_sha256=blend_sha,session=str(folder),previous_build=str(Path(current_pac).parent)),geometry_decimation=False)
        report.pop('budget_warning',None);dump(stage/'qa.json',report)
        view=stage/'preview';view.mkdir();(view/'model.yobj').write_bytes(final['sections'][2])
        from tools.psp_mesh_merge_trial import write_preview
        ordinary=copy.deepcopy(final['model'])
        for mesh in ordinary['meshes']:mesh['materials']=[m for m in mesh['materials']if 'blood'not in ordinary['texture_names'][m['texture_id']].casefold()]
        write_preview(ordinary,view/'model.obj');mtl=[]
        for i,name in enumerate(final['model']['texture_names']):
            ix,pal=read_gim(maps[name]);filename=f'texture_{i:03d}.png';Image.fromarray(pal[ix]).save(view/filename);mtl.extend(['newmtl texture_'+str(i),'Kd 1 1 1','map_Kd '+filename])
        (view/'preview.mtl').write_text('\n'.join(mtl)+'\n',encoding='utf-8')
        for direction in ('front','back','left','right','front-left'):
            if cancel():raise ValueError('Blender import cancelled')
            preview(final['model'],maps,direction,384).save(view/(direction+'.png'))
        (stage/'SHA256SUMS.txt').write_text(sha(pac)+'  created-model.pac\n',encoding='ascii')
        (stage/'README.txt').write_text('Validated Blender edit of a separate Creator build. Previous build and Blender session are preserved. No topology, bone, skin-weight or material-assignment editing is supported. Test the exported PAC in-game. Reassembling Creator choices starts a new build and does not replay this Blender edit.\n',encoding='utf-8')
        if sha(blend.read_bytes())!=blend_sha or sha(Path(current_pac).read_bytes())!=original_sha:raise ValueError('Inputs changed before publishing Blender build')
        if output.exists():raise ValueError('Blender build destination already exists')
        output.parent.mkdir(parents=True,exist_ok=True);stage.rename(output);final['path']=str((output/'created-model.pac').resolve())
    return output,report,final

"""Prepared native PSP library and opt-in multi-donor creator policy.

Library PACs are immutable snapshots, not converter templates. No resampling,
retargeting, decimation or texture optimization is performed by this module.
"""
import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import uuid

import numpy as np

from .core import PARTS, VERSION, digest, dump, load_source
from tools.weight_trial_review import descendant_names

SCHEMA='psp-model-creator.library-project/1'
BODY_BONES={'root','koshi','mune','kubi'} | {
    side+'_'+name for side in ('l','r') for name in
    ('ashi','kote','kote_x','momo','ninoude','ninoude_x','sakotsu','sune','te','tsumasaki')
} | {side+'_yubi'+str(finger)+str(joint) for side in ('l','r') for finger in range(5) for joint in range(3)}


def bundled_root():
    root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    return root/'creator_library'


class Library:
    def __init__(self, root=None):
        self.root=Path(root or bundled_root()).resolve()
        self.catalog=json.loads((self.root/'catalog.json').read_text(encoding='utf-8'))
        if self.catalog.get('schema')!='psp-model-creator.library/1':raise ValueError('Unsupported prepared library')
        self.entries=self.catalog['models'];self.cache={}
        if not self.entries:raise ValueError('The prepared library is empty')
        for entry in self.entries:
            path=self.root/entry['file']
            if path.is_symlink() or not path.resolve().is_relative_to(self.root):raise ValueError('Invalid library asset path')

    def source(self, index):
        if type(index)!=int or not 0<=index<len(self.entries):raise ValueError('Invalid library selection')
        entry=self.entries[index];path=self.root/entry['file']
        data=path.read_bytes()
        if digest(data)!=entry['sha256']:raise ValueError('Prepared library asset changed: '+entry['label'])
        if index not in self.cache:self.cache[index]=load_source(path,library=True)
        return self.cache[index]

    def selection(self, choices):
        ids=sorted(set(choices.values()))
        return [self.source(i) for i in ids],{p:ids.index(choices[p]) for p in PARTS}


@contextmanager
def catalog_lock(root):
    """OS-owned lock: another importer cannot lose an existing catalog update.

    The OS releases the lock on process exit, including an interrupted import.
    Readers continue to see a complete old or new catalog via atomic replace.
    """
    with (Path(root)/'.donor-import.lock').open('a+b') as stream:
        if stream.seek(0,2)==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        if sys.platform=='win32':
            import msvcrt
            try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:raise ValueError('Another donor import is running. Try again when it finishes.') from exc
        else:
            import fcntl
            try:fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as exc:raise ValueError('Another donor import is running. Try again when it finishes.') from exc
        try:yield
        finally:
            stream.seek(0)
            if sys.platform=='win32':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def add_donors(paths, root=None, *, progress=lambda _:None):
    """Register validated native PSP snapshots; never edit or replace a donor.

    Each valid input gets its own report entry. Invalid inputs do not prevent
    other valid files in the batch from being added. Existing entries keep their
    order/identity so saved UI selections remain meaningful after a refresh.
    """
    from .core import preview
    from desktop.edit_folder import publish_new
    root=Path(root or bundled_root()).resolve()
    report=dict(added=[],duplicates=[],rejected=[],catalog_backup=None)
    with catalog_lock(root):
        library=Library(root);catalog=copy.deepcopy(library.catalog)
        known={entry['sha256']:entry for entry in catalog['models']}
        new_files=[]
        try:
            for filename in paths:
                path=Path(filename)
                progress('Checking donor: '+path.name)
                created=[]
                try:
                    if path.suffix.casefold()!='.pac' or path.is_symlink():raise ValueError('Select an ordinary native PSP .pac file')
                    source=load_source(path,library=True)
                    sha=source['sha256']
                    if sha in known:
                        report['duplicates'].append(dict(file=str(path),label=known[sha]['label'],sha256=sha));continue
                    model=source['model'];stats=model['report'];textures={n:source['textures'][n.casefold()] for n in model['texture_names']}
                    previews={};images={}
                    import io
                    for view in ('front','back'):
                        name=f'previews/user-{sha}-{view}.png';buffer=io.BytesIO()
                        preview(model,textures,view,256).save(buffer,format='PNG');images[name]=buffer.getvalue();previews[view]=name
                    if path.read_bytes()!=source['data']:raise ValueError('Input changed during import; finish saving it and retry')
                    relative=f'pacs/user-{sha}.pac';payloads={relative:source['data'],**images}
                    for name,data in payloads.items():
                        target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
                        if target.exists():
                            if target.is_symlink() or target.read_bytes()!=data:raise ValueError('Existing library object differs: '+name)
                        else:publish_new(target,data);created.append(target)
                    entry=dict(label=path.stem,file=relative,sha256=sha,pac_bytes=len(source['data']),
                        preview_only_over_budget=len(source['data'])>148000,previews=previews,origin='user-added',
                        **{k:stats[k] for k in ('meshes','bones','vertices','triangles','textures','descriptor_count','descriptor_mesh_counts')})
                    catalog['models'].append(entry);known[sha]=entry;new_files.extend(created)
                    report['added'].append(dict(file=str(path),label=entry['label'],sha256=sha,pac_bytes=entry['pac_bytes']))
                except (OSError,ValueError,IndexError,KeyError,UnicodeError,struct.error) as exc:
                    for target in created:target.unlink(missing_ok=True)
                    report['rejected'].append(dict(file=str(path),reason=str(exc)))
            if report['added']:
                backup=root/'backups'/('catalog-'+uuid.uuid4().hex+'.json');backup.parent.mkdir(exist_ok=True)
                publish_new(backup,(root/'catalog.json').read_bytes());report['catalog_backup']=str(backup)
                # Write and fsync before atomic replace; a failed write leaves
                # the old catalog authoritative and all existing models intact.
                fd,name=tempfile.mkstemp(prefix='.catalog-',suffix='.tmp',dir=root)
                try:
                    with os.fdopen(fd,'w',encoding='utf-8') as stream:
                        stream.write(json.dumps(catalog,indent=2,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())
                    os.replace(name,root/'catalog.json')
                finally:Path(name).unlink(missing_ok=True)
        except Exception:
            for target in new_files:target.unlink(missing_ok=True)
            raise
    return report


def compatible(sources,selections):
    if len(set(selections.values()))==1:return {'mode':'unchanged native source'}
    base=sources[selections['Torso']]['model'];body=BODY_BONES
    ref={b['name']:b for b in base['bones']}
    differences=[]
    for source in sources:
        m=source['model']
        for b in m['bones']:
            if b['name'] not in body:continue
            if b['name'] not in ref:raise ValueError('Missing compatible native body bone in torso donor: '+b['name'])
            a=ref[b['name']]
            parent=lambda model,v:None if v['parent']==-1 else model['bones'][v['parent']]['name']
            if parent(base,a)!=parent(m,b):raise ValueError('Incompatible body hierarchy: '+b['name'])
            delta={k:float(np.max(np.abs(np.array(a[k])-b[k]))) for k in ('local_position','rotation')}
            if max(delta.values())>1e-5:differences.append(dict(source=source['label'],bone=b['name'],**delta))
    return {'mode':'Selected anatomical branch binds; native-source pose comparison is mandatory',
            'body_bind_differences':differences,'pose_tolerance':.03,
            'geometry_or_weights_retargeted':False}



def skeleton(sources,selections):
    base=copy.deepcopy(sources[selections['Torso']]['model'])
    names=list(dict.fromkeys(b['name'] for s in sources for b in s['model']['bones']))
    head=sources[selections['Head']]['model'];facial=descendant_names(head,'atama')
    # Extra controllers belong to the geometry they actually influence. Names
    # such as "kami" are not sufficient evidence that a controller is for hair.
    from .parts import extract, JOINTS
    active={name:set() for name in names}
    preserved={}
    for part in PARTS:
        si=selections[part]
        source_bones=sources[si]['model']['bones']
        by_name={b['name']:b for b in source_bones}
        used=set()
        for row in extract(sources[si]['model'],part,names):
            for vertex in row['poly']:
                used.update(names[b] for b in np.flatnonzero(vertex['w']>0))
                tag=vertex['tag']
                if abs(tag[1]-tag[0]**2)<1e-8 and all(abs(vertex['p'][axis]-limit)>2e-6 for axis,limit in JOINTS.values()):
                    preserved[(si,row['mesh'],int(round(tag[0])))]=(si,vertex['p'],vertex['w'])
        for name in used:
            b=by_name[name]
            while True:
                active[b['name']].add(si)
                if b['parent']==-1:break
                b=source_bones[b['parent']]
    records=bytearray()
    for name in names:
        preferred=selections['Head'] if name in facial or name=='kubi' else selections['Arms'] if any(k in name for k in ('sakotsu','ninoude','kote','yubi')) or name in ('l_te','r_te') else selections['Legs'] if any(k in name for k in ('momo','sune','ashi','tsumasaki')) else selections['Torso']
        donors=[s['model'] for s in sources if any(b['name']==name for b in s['model']['bones'])]
        donor=sources[preferred]['model']
        if name not in BODY_BONES and name not in facial and active[name]:
            needed=[sources[i]['model'] for i in sorted(active[name])]
            donor=needed[0]
            def signature(model):
                b=next(b for b in model['bones'] if b['name']==name)
                return (None if b['parent']==-1 else model['bones'][b['parent']]['name'],tuple(b['local_position']),tuple(b['rotation']))
            if any(signature(m)!=signature(donor) for m in needed[1:]):
                raise ValueError('Selected parts require incompatible native controller binds: '+name)
        if not any(b['name']==name for b in donor['bones']):donor=donors[0]
        b=next(b for b in donor['bones'] if b['name']==name)
        r=bytearray(donor['bone_raw'][80*b['index']:80*(b['index']+1)])
        struct.pack_into('<i',r,48,-1 if b['parent']==-1 else names.index(donor['bones'][b['parent']]['name']))
        # Enclose the native spheres without shrinking a donor's culling bounds.
        import math
        spheres=[struct.unpack_from('<4f',m['bone_raw'],80*next(b['index'] for b in m['bones'] if b['name']==name)+64) for m in donors]
        center=struct.unpack_from('<3f',r,64)
        radius=max(math.dist(center,s[:3])+s[3] for s in spheres)+1e-5
        struct.pack_into('<4f',r,64,*center,radius)
        records.extend(r)
    base['bone_raw']=bytes(records)
    h=bytearray(base['header']);struct.pack_into('<I',h,28,len(names));base['header']=bytes(h)
    from .rigging import choose_shared_neck
    base['branch_bind_fit']=choose_shared_neck(base,names,list(preserved.values()),sources,selections)
    return base,names


def create_project(sources,selections,output):
    output=Path(output)
    if output.exists():raise FileExistsError('Choose a new project folder')
    output.mkdir(parents=True)
    rows=[]
    for i,s in enumerate(sources):
        filename=f'source-{i}.pac';(output/filename).write_bytes(s['data'])
        rows.append(dict(file=filename,label=s['label'],sha256=s['sha256']))
    dump(output/'project.json',dict(schema=SCHEMA,version=VERSION,sources=rows,selections=selections))
    return output/'project.json'


def read_project(path):
    path=Path(path);project=json.loads(path.read_text(encoding='utf-8'))
    rows=project.get('sources',[]);choices=project.get('selections',{})
    if project.get('schema')!=SCHEMA or not 1<=len(rows)<=4:raise ValueError('Unsupported library project')
    if set(choices)!=set(PARTS) or any(type(v)!=int or not 0<=v<len(rows) for v in choices.values()):raise ValueError('Invalid part selections')
    sources=[]
    for i,row in enumerate(rows):
        if row['file']!=f'source-{i}.pac':raise ValueError('Invalid snapshot path')
        s=load_source(path.parent/row['file'],library=True)
        if s['sha256']!=row['sha256']:raise ValueError('Source snapshot changed')
        s['label']=row['label'];sources.append(s)
    return project,sources


def prepare(folder,output):
    """Explicit build-time asset preparation; the app never scans inputs on boot."""
    from .core import preview
    output=Path(output)
    if output.exists():raise FileExistsError('Prepared library already exists')
    output.mkdir(parents=True);(output/'pacs').mkdir();(output/'previews').mkdir()
    entries=[]
    for i,path in enumerate(sorted(Path(folder).glob('*'),key=lambda p:p.name.casefold())):
        if path.suffix.casefold()!='.pac':continue
        s=load_source(path,library=True);m=s['model'];r=m['report'];filename=f'pacs/{path.name}'
        (output/filename).write_bytes(s['data'])
        textures={n:s['textures'][n.casefold()] for n in m['texture_names']}
        views={}
        for view in ('front','back'):
            name=f'previews/{len(entries):03d}-{view}.png';preview(m,textures,view,256).save(output/name);views[view]=name
        entries.append(dict(label=s['label'],file=filename,sha256=s['sha256'],pac_bytes=len(s['data']),
            preview_only_over_budget=len(s['data'])>148000,previews=views,
            **{k:r[k] for k in ('meshes','bones','vertices','triangles','textures','descriptor_count','descriptor_mesh_counts')}))
    dump(output/'catalog.json',dict(schema='psp-model-creator.library/1',models=entries,
        assets='User-supplied native PSP PAC snapshots. Rights remain with their owners.',
        constraints='Original preview is independent of the 148000-byte mixed export budget. Mixed builds require compatible body binds and passing native/pose/seam checks.'))
    return entries

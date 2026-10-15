"""Private-project native PSP assembly, strict readback, pose QA and export."""
import copy
import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from desktop.preview import render
from desktop.texture_optimizer.candidates import read_gim
from tools.pac_inspect import inspect_pac, parse_textures
from tools.pac_repack import replace_sections, texture_table
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge import write_model
from tools.psp_mesh_merge_trial import sections, write_preview
from tools.stripify import stripify, join_strips
from tools.weight_trial_review import descendant_names, deform
from tools.prepare_model import bone_matrices
from model_creator.parts import PARTS, JOINTS, extract, stitch, triangles

VERSION = '0.2.0'
SCHEMA = 'psp-model-creator/1'
MAX_BYTES = 148000
POSES = {'rest': {}, 'standing': {'l_ninoude': ('z',70), 'r_ninoude': ('z',-70)},
         'walk': {'l_momo': ('x',22),'r_momo': ('x',-22),'r_sune': ('x',30)},
         'bend': {'koshi': ('x',35),'mune': ('x',20)},
         'crouch': {'l_momo': ('x',-50),'r_momo': ('x',-50),'l_sune': ('x',95),'r_sune': ('x',95)},
         'shoulders': {'l_ninoude': ('z',-55),'r_ninoude': ('z',55)},
         'neck': {'kubi': ('y',25)}, 'jaw': {'d_kuchi': ('x',18)},
         'eyes': {'l_eye': ('y',12),'r_eye': ('y',-12)},
         'eyelids': {'l_mabuta': ('x',10),'r_mabuta': ('x',10)}}


def digest(data):return hashlib.sha256(data).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def load_source(path, *, library=False):
    data = Path(path).read_bytes()
    items=list(sections(data));decoded = dict((s['id'],r) for s,r in items)
    if len(items)!=len(decoded):raise ValueError('Duplicate PAC section IDs are unsupported.')
    if 2 not in decoded or 9 not in decoded:raise ValueError('A native PSP main-model PAC with section 9 textures is required.')
    if library:
        from .native import audit_yobj as reader, allocation_fill
        model=reader(decoded[2]);padding=allocation_fill(decoded[2],model)
    else:model=audit_yobj(decoded[2])
    cursor=0;padding=[] if not library else padding
    pointer_targets={8+struct.unpack_from('<I',decoded[2],a)[0] for a in model['report']['relocation_locations']}
    for allocation in ([] if library else sorted(model['report']['allocations'],key=lambda a:a['start'])):
        if allocation['start']>cursor and any(decoded[2][cursor:allocation['start']]):
            gap=decoded[2][cursor:allocation['start']]
            # The actual pair uses short 0xffffffff fill runs between native
            # palettes/materials. No relocated pointer may target such a run.
            if len(gap)>16 or len(gap)%4 or gap!=b'\xff'*len(gap) or any(cursor<=p<allocation['start'] for p in pointer_targets):
                raise ValueError('Unclassified nonzero YOBJ data cannot be discarded safely.')
            padding.append(dict(start=cursor,bytes=len(gap),value='ff',classification='INFERRED native allocation fill; rewritten layout uses zero padding'))
        cursor=max(cursor,allocation['end'])
    if not library and any(decoded[2][cursor:model['report']['declared_yobj_end']]):raise ValueError('Unclassified trailing YOBJ data cannot be discarded safely.')
    if any(m['rigid'] or m['base_flag']!=0x17ff for m in model['meshes']):
        raise ValueError('This prototype accepts the verified float32-skinned PSP layout only.')
    names = [b['name'] for b in model['bones']]
    if len(set(names))!=len(names):raise ValueError('Ambiguous duplicate bone names.')
    textures = {}
    for e in parse_textures(decoded[9]):
        key=e['name'].casefold()
        if key in textures:raise ValueError('Ambiguous texture names.')
        raw=decoded[9][e['offset']:e['offset']+e['size']];read_gim(raw);textures[key]=raw
    if any(n.casefold() not in textures for n in model['texture_names']):raise ValueError('Missing main texture references.')
    return dict(path=str(Path(path).resolve()), data=data, model=model, sections=decoded,
                textures=textures, sha256=digest(data), label=Path(path).stem,allocation_fill=padding)


def compatible(a,b):
    am,bm=a['model'],b['model'];names=[x['name'] for x in am['bones']]
    if set(names)!={x['name'] for x in bm['bones']}:raise ValueError('Bone-name sets differ; automatic retargeting is unsupported.')
    face=descendant_names(am,'atama')
    for name in names:
        x=next(x for x in am['bones'] if x['name']==name);y=next(y for y in bm['bones'] if y['name']==name)
        parent=lambda m,v: None if v['parent']==-1 else m['bones'][v['parent']]['name']
        if parent(am,x)!=parent(bm,y):raise ValueError('Bone hierarchy differs: '+name)
        if name not in face and max(np.max(np.abs(np.array(x[k])-y[k])) for k in ('local_position','rotation'))>1e-5:
            raise ValueError('Body bind transforms differ: '+name)
    return dict(shared_body_bind=True, facial_bones=len(face), bone_order_identical=names==[x['name'] for x in bm['bones']],
                policy='Map by verified name; selected head supplies its own complete facial bind subtree.')


def create_project(first, second, output):
    a,b=load_source(first),load_source(second);review=compatible(a,b)
    output=Path(output)
    if output.exists():raise FileExistsError('Choose a new project folder.')
    output.mkdir(parents=True)
    for i,source in enumerate((a,b)):(output/f'source-{i}.pac').write_bytes(source['data'])
    project=dict(schema=SCHEMA, version=VERSION, sources=[dict(file=f'source-{i}.pac',sha256=s['sha256'],label=s['label']) for i,s in enumerate((a,b))],
                 selections={p:0 for p in PARTS}, compatibility=review)
    dump(output/'project.json',project)
    return str(output/'project.json')


def read_project(path):
    path=Path(path);project=json.loads(path.read_text(encoding='utf-8'))
    if project.get('schema')!=SCHEMA or len(project.get('sources',[]))!=2:raise ValueError('Unsupported creator project.')
    choices=project.get('selections',{})
    if set(choices)!=set(PARTS) or any(type(v)!=int or v not in (0,1) for v in choices.values()):raise ValueError('Invalid saved part selections.')
    sources=[]
    for i,row in enumerate(project['sources']):
        if row['file']!=f'source-{i}.pac':raise ValueError('Invalid snapshot filename.')
        source=load_source(path.parent/row['file'])
        if source['sha256']!=row['sha256']:raise ValueError('Source snapshot was modified; assembly withheld.')
        source['label']=row['label'];sources.append(source)
    compatible(*sources)
    return project,sources


def skeleton(sources, selections):
    base=copy.deepcopy(sources[selections['Torso']]['model']);names=[x['name'] for x in base['bones']]
    facial=descendant_names(base,'atama');raw=bytearray()
    for name in names:
        donor=sources[selections['Head'] if name in facial else selections['Arms'] if ('ninoude' in name or 'kote' in name or '_te'==name[1:] or 'yubi' in name) else selections['Legs'] if any(x in name for x in ('momo','sune','ashi','tsumasaki')) else selections['Torso']]['model']
        b=next(b for b in donor['bones'] if b['name']==name);record=bytearray(donor['bone_raw'][b['index']*80:(b['index']+1)*80])
        parent=-1 if b['parent']==-1 else names.index(donor['bones'][b['parent']]['name'])
        struct.pack_into('<i',record,48,parent)
        # Observed center/radius records are conservatively enclosed; semantics
        # beyond their native culling use remain inferred, so never shrink them.
        spheres=[struct.unpack_from('<4f',s['model']['bone_raw'],next(x['index'] for x in s['model']['bones'] if x['name']==name)*80+64) for s in sources]
        center=spheres[0][:3];radius=max(math.dist(center,s[:3])+s[3] for s in spheres)+1e-5
        struct.pack_into('<4f',record,64,*center,radius);raw.extend(record)
    base['bone_raw']=bytes(raw)
    return base,names


def assemble(sources, selections, *, library=False):
    reader=audit_yobj
    if library:
        from .native import audit_yobj as reader
        from .library import compatible as library_compatible, skeleton as library_skeleton
    if set(selections)!=set(PARTS) or any(type(v)!=int or not 0<=v<len(sources) for v in selections.values()) or (not library and len(sources)!=2):raise ValueError('Choose a source for each of the four parts.')
    if library:library_compatible(sources,selections)
    else:compatible(*sources)
    if len(set(selections.values()))==1:
        s=sources[selections['Head']]
        return s['sections'][2],{n:s['textures'][n.casefold()] for n in s['model']['texture_names']},dict(mode='Original native model',seams=[],sources=[s['sha256']],geometry_unchanged=True)
    base,names=(library_skeleton(sources,selections) if library else skeleton(sources,selections))
    selected={part:extract(sources[selections[part]]['model'],part,names) for part in PARTS}
    reference=extract(sources[selections['Torso']]['model'],'Torso',names)
    joints=[]
    if selections['Head']!=selections['Torso']:joints.append('neck')
    if selections['Legs']!=selections['Torso']:joints.append('waist')
    if selections['Arms']!=selections['Torso']:joints+=['left_arm','right_arm']
    seams=stitch(selected,reference,joints)
    if max(s['maximum_displacement'] for s in seams)>1.0:raise ValueError('Attachment mismatch exceeds the prepared-pair tolerance; export withheld.')
    meshes=[];texture_names=[];textures={};provenance=[];interior_checks=[]
    # Stable source-part/material draw order; no merging across source boundaries.
    for source_id in range(len(sources)):
        source=sources[source_id];model=source['model']
        rows=[r for p in PARTS if selections[p]==source_id for r in selected[p]]
        rows.sort(key=lambda r:(r['mesh'],r['material'],r['triangle'],PARTS.index(r['part'])))
        buckets=[]
        for row in rows:
            for tri in triangles(row['poly']):
                vs=[row['poly'][i] for i in tri]
                bones=set(int(i) for v in vs for i in np.flatnonzero(v['w']>0))
                if len(bones)>8:raise ValueError('Attachment requires more than eight bone slots.')
                key=(row['mesh'],row['material'])
                if not buckets or buckets[-1]['key']!=key or len(buckets[-1]['bones']|bones)>8:
                    buckets.append(dict(key=key,bones=set(),triangles=[],parts=set()))
                bucket=buckets[-1];bucket['bones']|=bones;bucket['triangles'].append(vs);bucket['parts'].add(row['part'])
        for bucket in buckets:
            mesh_id,mat_id=bucket['key'];donor=model['meshes'][mesh_id];mat=copy.deepcopy(donor['materials'][mat_id])
            oldname=model['texture_names'][mat['texture_id']];gim=source['textures'][oldname.casefold()]
            # Names are generated ASCII identifiers, never source-controlled paths.
            texname=oldname
            if texname in textures and textures[texname]!=gim:
                texname=f's{source_id}_{model["texture_names"].index(oldname):02d}_{oldname}'[:15]
            if texname not in textures:texture_names.append(texname);textures[texname]=gim
            texid=texture_names.index(texname);record=bytearray(mat['raw']);struct.pack_into('<H',record,22,texid)
            mat['raw']=bytes(record);mat['texture_id']=texid
            palette=sorted(bucket['bones'])
            original_palette=[names.index(model['bones'][b]['name']) for b in donor['bone_palette']]
            for bone in original_palette:
                if bone not in palette and len(palette)<8:palette.append(bone)
            vertices=[];lookup={};indices=[]
            for tri in bucket['triangles']:
                face=[]
                for v in tri:
                    # Relevant attributes AND original-record signature form identity.
                    key=b''.join(np.asarray(v[k],'<f8').tobytes() for k in ('p','n','uv','c','w','tag'))
                    if key not in lookup:
                        lookup[key]=len(vertices)
                        original_record=abs(v['tag'][1]-v['tag'][0]**2)<1e-8
                        n=v['n'] if original_record else v['n']/max(np.linalg.norm(v['n']),1e-12)
                        w=v['w'][palette]
                        vertices.append(dict(position=v['p'].tolist(),normal=n.tolist(),uv=v['uv'].tolist(),
                                             color=np.clip(np.rint(v['c']),0,255).astype(int).tolist(),weights=w.tolist()))
                        if original_record and all(abs(v['p'][axis]-limit)>2e-6 for axis,limit in JOINTS.values()):
                            interior_checks.append((len(meshes),len(vertices)-1,source_id,mesh_id,int(round(v['tag'][0]))))
                    face.append(lookup[key])
                indices.append(face)
            strips=join_strips(stripify(indices));mat.update(strips=strips,triangles=indices,
                strip_headers=[mat['strip_headers'][0]]*len(strips))
            mesh=copy.deepcopy(donor);mesh.update(index=len(meshes),bone_palette=palette,weight_slots=len(palette),
                stride=36+4*len(palette),vertices=vertices,materials=[mat])
            mesh['raw_vertices']=b''.join(struct.pack('<'+'f'*len(palette)+'2f4B6f',*v['weights'],*v['uv'],*v['color'],*v['normal'],*v['position']) for v in vertices)
            points=np.array([v['position'] for v in vertices]);center=(points.min(0)+points.max(0))/2;radius=np.linalg.norm(points-center,axis=1).max()+.001
            header=bytearray(mesh['raw_header']);struct.pack_into('<4f',header,48,*center,float(radius));mesh['raw_header']=bytes(header)
            provenance.append(dict(descriptor=donor.get('descriptor_owner',model.get('descriptor_owners',[0]*len(model['meshes']))[mesh_id]),output_mesh=mesh['index'],source=source_id,source_mesh=mesh_id,source_material=mat_id,parts=sorted(bucket['parts']),texture=oldname,output_texture=texname))
            meshes.append(mesh)
    descriptor_records=None;descriptor_sizes=None
    if library:
        # Body draw groups precede the selected head's native hair groups.
        # Keep stable ordering inside each group; never merge across them.
        order=sorted(range(len(meshes)),key=lambda i:provenance[i]['descriptor'])
        reverse={old:new for new,old in enumerate(order)}
        meshes=[meshes[i] for i in order];provenance=[provenance[i] for i in order]
        for i,(mesh,row) in enumerate(zip(meshes,provenance)):mesh['index']=i;row['output_mesh']=i
        interior_checks=[(reverse[om],ov,si,sm,sv) for om,ov,si,sm,sv in interior_checks]
        head=sources[selections['Head']]['model'];torso=sources[selections['Torso']]['model']
        descriptor_records=[torso['descriptors'][0]]
        descriptor_sizes=[sum(r['descriptor']==0 for r in provenance)]
        for d in sorted({r['descriptor'] for r in provenance}-{0}):
            descriptor_records.append(head['descriptors'][d]);descriptor_sizes.append(sum(r['descriptor']==d for r in provenance))
        h=bytearray(base['header']);struct.pack_into('<I',h,52,1);base['header']=bytes(h)
        base['model_descriptor_raw']=descriptor_records[0]
    base['meshes']=meshes;base['texture_names']=texture_names
    base['texture_raw']=b''.join(n.encode('ascii').ljust(16,b'\0') for n in texture_names)
    h=bytearray(base['header']);struct.pack_into('<I',h,32,len(texture_names));base['header']=bytes(h)
    # Both supplied native main models relocate header word 60 with value zero
    # (the relative alias to byte 8). Preserve that relocation explicitly without
    # broadening the converter's deliberately conservative writer policy.
    reserved_alias=60 in base['report']['relocation_locations']
    if reserved_alias:
        if struct.unpack_from('<I',base['header'],60)[0]!=0:raise ValueError('Unknown nonzero header-60 pointer.')
        base['report']['relocation_locations']=[a for a in base['report']['relocation_locations'] if a!=60]
    raw=write_model(base,[[i] for i in range(len(meshes))])
    unmerged=audit_yobj(raw)
    comparisons=[]
    for outmesh,outvertex,source_id,sourcemesh,sourcevertex in interior_checks:
        donor=sources[source_id]['model'];oldmesh=donor['meshes'][sourcemesh];old=oldmesh['vertices'][sourcevertex]
        newmesh=unmerged['meshes'][outmesh];new=newmesh['vertices'][outvertex]
        for attribute in ('position','normal','uv','color'):
            if old[attribute]!=new[attribute]:raise ValueError('Interior source attribute changed: '+attribute)
        expected={donor['bones'][b]['name']:float(w) for b,w in zip(oldmesh['bone_palette'],old['weights']) if w}
        actual={names[b]:float(w) for b,w in zip(newmesh['bone_palette'],new['weights']) if w}
        if expected!=actual:raise ValueError('Interior source weights changed.')
        comparisons.append((outmesh,outvertex,source_id,sourcemesh,sourcevertex))
    # Independently compare each untouched source record under every pose. Body
    # transforms match by compatibility check; selected head retains its rig.
    pose_regressions={}
    native_p,native_w=dense(unmerged)
    offsets=np.cumsum([0]+[len(m['vertices']) for m in unmerged['meshes']])
    source_dense=[dense(s['model']) for s in sources]
    source_offsets=[np.cumsum([0]+[len(m['vertices']) for m in s['model']['meshes']]) for s in sources]
    for label,controls in POSES.items():
        output_pose=deform(dict(bones=unmerged['bones'],bone_count=len(names)),native_p,native_w,controls)
        expected_poses=[deform(dict(bones=s['model']['bones'],bone_count=len(s['model']['bones'])),p,w,controls) for s,(p,w) in zip(sources,source_dense)]
        errors=[float(np.linalg.norm(output_pose[offsets[om]+ov]-expected_poses[si][source_offsets[si][sm]+sv])) for om,ov,si,sm,sv in comparisons]
        maximum=max(errors,default=0.)
        # Mixed neck-influenced torso records can use the selected head pivot.
        # Record that small differential explicitly rather than calling it exact.
        pose_regressions[label]=dict(maximum_source_position_difference=maximum,records=len(errors),tolerance=.03,passed=maximum<=.03)
        if maximum>.03:raise ValueError('Untouched source pose regressed: '+label+' '+str(maximum))
    from collections import Counter
    oriented=lambda t:min(tuple(t[i:]+t[:i]) for i in range(3))
    for before,after in zip(meshes,unmerged['meshes']):
        if before['raw_vertices']!=after['raw_vertices'] or before['bone_palette']!=after['bone_palette']:raise ValueError('Native vertex/palette readback differs.')
        if Counter(map(oriented,before['materials'][0]['triangles']))!=Counter(map(oriented,after['materials'][0]['triangles'])):raise ValueError('Native triangle winding readback differs.')
    # Rejoin only adjacent splits from the SAME original source buffer. The
    # existing lossless merge verifier checks weights, UVs, materials and winding.
    from tools.psp_mesh_merge import plan, rebuild, verify
    origin=[(r['source'],r['source_mesh'],r['descriptor']) for r in provenance]
    groups=plan(unmerged,origin)
    combined=rebuild(raw,groups,origin);merge_validation=verify(raw,combined,groups);raw=combined
    from desktop.skinning import adapt_yobj
    raw,slot_compatibility=adapt_yobj(raw)
    if reserved_alias:
        from tools.psp_mesh_audit import encode_relocations
        from tools.yobj_alignment import align_yobj_pof0
        reloc=encode_relocations(sorted(audit_yobj(raw)['report']['relocation_locations']+[60]))
        end=8+struct.unpack_from('<I',raw,4)[0]
        raw=align_yobj_pof0(raw[:end]+b'POF0'+struct.pack('<I',len(reloc))+reloc)
    if library:
        # Merge groups cannot cross descriptor owners. Recount after merging.
        owners=[provenance[g[0]]['descriptor'] for g in groups]
        ds=sorted(set(owners));descriptor_sizes=[owners.count(d) for d in ds]
        from .native import restore_descriptors
        raw=restore_descriptors(raw,descriptor_records,descriptor_sizes)
    native=reader(raw)
    return raw,textures,dict(mode='Prepared-pair stitched assembly',seams=seams,provenance=provenance,
        lossless_buffer_groups=groups,lossless_buffer_validation=merge_validation,
        single_slot_compatibility=slot_compatibility,
        interior_source_records_verified=len(interior_checks),interior_pose_comparison=pose_regressions,
        rig_policy='Native body bind; selected head facial subtree, remapped by name.',
        changed_geometry='Planar cut intersections, shared torso-surface attachment vertices and edge splits only. No decimation.',
        source_sha256=[s['sha256'] for s in sources],readback_attributes_and_topology=True)


def dense(model):
    positions=[];weights=[]
    for mesh in model['meshes']:
        for v in mesh['vertices']:
            positions.append(v['position']);w=np.zeros(len(model['bones']));w[mesh['bone_palette']]=v['weights'];weights.append(w)
    return np.array(positions),np.array(weights)


def posed_model(model, pose):
    result=copy.deepcopy(model);p,w=dense(model)
    rig=dict(bones=model['bones'],bone_count=len(model['bones']))
    output=deform(rig,p,w,POSES[pose])
    normals=np.array([v['normal'] for m in model['meshes'] for v in m['vertices']])
    normal_output=deform(rig,p+normals,w,POSES[pose])-output
    normal_output/=np.maximum(np.linalg.norm(normal_output,axis=1,keepdims=True),1e-12);i=0
    for mesh in result['meshes']:
        for v in mesh['vertices']:v['position']=output[i].tolist();v['normal']=normal_output[i].tolist();i+=1
    return result


def qa(raw, report, *, library=False):
    reader=audit_yobj
    if library:
        from .native import audit_yobj as reader
    model=reader(raw);p,w=dense(model);height=float(np.ptp(p[:,1]));results={}
    if not np.isfinite(p).all() or not np.isfinite(w).all():raise ValueError('Nonfinite model attributes.')
    # Test only the deliberately shared joins. Other coincident native records
    # can legitimately have different source weights and are not welded.
    seam_groups={}
    for joint in report['seams']:
        axis,limit=JOINTS[joint['joint']]
        for i in np.flatnonzero(np.abs(p[:,axis]-limit)<2e-6):
            seam_groups.setdefault(tuple(np.round(p[i],5)),[]).append(int(i))
    for name,controls in POSES.items():
        posed=deform(dict(bones=model['bones'],bone_count=len(model['bones'])),p,w,controls)
        if not np.isfinite(posed).all():raise ValueError('Nonfinite analytical pose '+name)
        maximum=max((float(np.linalg.norm(posed[ids]-posed[ids[0]],axis=1).max()) for ids in seam_groups.values()),default=0.)
        if report['seams'] and maximum>height*2e-5:raise ValueError('Attachment opens under '+name+': '+str(maximum))
        results[name]=dict(shared_seam_maximum_gap=maximum,finite=True,analytical_not_game_animation=True)
    return dict(native_structural_audit=model['report'],poses=results,
                seam_position_and_weight_equality=bool(report['seams']),
                runtime_status='Experimental: PPSSPP import and animation testing still required.')


def preview(model,textures,view='front-left',resolution=640,pose='rest',green=False):
    shown=posed_model(model,pose)
    for mesh in shown['meshes']:
        mesh['materials']=[m for m in mesh['materials'] if 'blood' not in model['texture_names'][m['texture_id']].casefold()]
    if green:
        from desktop.texture_optimizer.candidates import write_gim
        c=np.zeros((16,4),np.uint8);c[:,3]=255;c[0,:3]=(80,180,115)
        raw=write_gim(np.zeros((8,32),np.uint8),c,4);textures={name:raw for name in model['texture_names']}
    return render(shown,textures,view,resolution,gim_reader=read_gim)


def build(project_path, selections, output, *, resolution=640, progress=lambda _:None, library=False):
    from tools.yukes_bpe import compress,decompress
    reader=audit_yobj;project_reader=read_project
    if library:
        from .native import audit_yobj as reader
        from .library import read_project as project_reader
    project,sources=project_reader(project_path);output=Path(output)
    if output.exists():raise FileExistsError('Output directory already exists; previous versions are preserved.')
    progress('Assembling native parts and attachment seams')
    raw,textures,report=assemble(sources,selections,library=library)
    progress('Checking native buffers, bone palettes and analytical poses')
    report['qa']=qa(raw,report,library=library);model=reader(raw)
    # Source 0 is the explicit output-container template for mixed assemblies.
    # This prototype assembles the main model, not optional source-1 auxiliary
    # nested PACs. Both complete originals remain in the private project.
    template=selections['Torso'] if library else 0
    donor=sources[template]
    if len(set(selections.values()))==1:
        donor=sources[selections['Head']]
        pac=donor['data'];report['packaging']='Original PAC byte-exact (single-source assembly).'
    else:
        from desktop.source_reference_qa import safe_repack
        safe_repack(donor['data'])
        packed=compress(raw,max_distinct=220)
        if decompress(packed)!=raw:raise ValueError('Model compression roundtrip failed.')
        table=texture_table(model['texture_names'],[textures[n] for n in model['texture_names']],gim_reader=read_gim)
        pac=replace_sections(donor['data'],{2:packed,9:compress(table,max_distinct=220)})
        # Section 100 in Brian is a nested PAC. It is retained byte-for-byte
        # as unrelated donor data, not silently stripped to meet the budget.
        original=inspect_pac(donor['data']);final=inspect_pac(pac);unchanged=[]
        for a,b in zip(original['sections'],final['sections']):
            if a['id']!=b['id']:raise ValueError('PAC section identity changed.')
            if a['id'] not in (2,9):
                if donor['data'][a['offset']:a['offset']+a['size']]!=pac[b['offset']:b['offset']+b['size']]:raise ValueError('Unrelated PAC payload changed.')
                unchanged.append(a['id'])
        report['unrelated_stored_sections_identical']=unchanged
        report['container_template_source']=template
        report['source_1_auxiliary_sections_not_assembled']=[i for i in sources[1]['sections'] if i not in (2,8,9)]
        if library:
            report['non_template_auxiliary_sections_not_assembled']=[dict(source=index,sections=[i for i in s['sections'] if i not in (2,8,9)])
                for index,s in enumerate(sources) if index!=template]
    report.update(selections=selections,labels=[s['label'] for s in sources],pac_bytes=len(pac),max_pac_bytes=MAX_BYTES,
                  pac_sha256=digest(pac),yobj_sha256=digest(raw),textures_byte_exact=True,
                  geometry_decimation=False,within_budget=len(pac)<=MAX_BYTES)
    report['source_allocation_fill']=[s['allocation_fill'] for s in sources]
    report['review_findings']=[dict(joint=s['joint'],unstitched_ambiguous_records=s['unstitched_internal_records'],
        explanation='Some cut records lie inside the chosen outer radial contour. They are retained, not assumed invalid. Visual and in-game seam review is required.')
        for s in report['seams'] if s['unstitched_internal_records']]
    report['texture_allocation']=dict(output_gim_bytes=sum(len(v) for v in textures.values()),
        output_pixel_clut_bytes=sum(len(v)-208 for v in textures.values()),
        source_pixel_clut_bytes=[sum(len(v)-208 for v in s['textures'].values()) for s in sources],
        runtime_limit='UNKNOWN: file-size compliance is not proof of a safe game heap allocation.')
    if len(pac)>MAX_BYTES:
        raise ValueError(f'Assembly is {len(pac):,} bytes, exceeding {MAX_BYTES:,}. Export withheld; no geometry or textures were reduced. Try fewer mixed parts or a different torso donor.')
    container=inspect_pac(pac)
    if len(pac)%2048:raise ValueError('PAC final alignment failed.')
    aligned=all(s['offset']%16==0 for s in container['sections'])
    if len(set(selections.values()))!=1 and not aligned:raise ValueError('Rebuilt PAC section alignment failed.')
    report['section_alignment']=dict(rebuilt_sections_16_aligned=aligned,
        native_single_source_layout_retained=len(set(selections.values()))==1)
    finalraw=next(r for s,r in sections(pac) if s['id']==2)
    if finalraw!=raw:raise ValueError('Exported PAC and preview model differ.')
    # Output directory is created only after all mandatory checks pass.
    output.mkdir(parents=True);folder=output/'preview';folder.mkdir()
    (output/'created-model.pac').write_bytes(pac);(folder/'model.yobj').write_bytes(finalraw)
    ordinary=copy.deepcopy(model)
    for mesh in ordinary['meshes']:
        mesh['materials']=[m for m in mesh['materials'] if 'blood' not in model['texture_names'][m['texture_id']].casefold()]
    write_preview(ordinary,folder/'model.obj');mtl=[]
    for i,name in enumerate(model['texture_names']):
        indices,colors=read_gim(textures[name]);filename=f'texture_{i:03d}.png';Image.fromarray(colors[indices]).save(folder/filename)
        mtl+=['newmtl texture_%d'%i,'Kd 1 1 1','Ks 0 0 0','map_Kd '+filename]
    (folder/'preview.mtl').write_text('\n'.join(mtl)+'\n',encoding='ascii')
    for view in ('front','back','left','right','front-left'):
        progress('Rendering '+view);preview(model,textures,view,resolution).save(folder/(view+'.png'))
    (output/'SHA256SUMS.txt').write_text(report['pac_sha256']+'  created-model.pac\n',encoding='ascii')
    dump(output/'qa.json',report);dump(output/'recipe.json',dict(schema=SCHEMA,selections=selections,sources=project['sources']))
    (output/'README.txt').write_text('Experimental native PSP assembly. Import created-model.pac into a COPY of the wrestler slot using your established PAC/ARC workflow. Rebuild the enclosing archive and update its ARC metadata before testing a copied ISO in PPSSPP. Do not overwrite accepted PACs. Analytical poses are not captured game animations. OBJ is preview-only; native YOBJ and PAC retain rigging. Blood overlay meshes are retained in PAC and OBJ, but hidden in normal preview PNGs. Review qa.json, standing/walking/crouching, facial motion and blood in-game.\n',encoding='utf-8')
    return report

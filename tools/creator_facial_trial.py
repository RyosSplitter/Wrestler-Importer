"""Isolated native facial geometry proof, never imported by the creator UI.

python -m tools.creator_facial_trial --shell creator_library/pacs/Batista.PAC \
  --insert creator_library/pacs/Chris-Masters.PAC --shell-depth -1 \
  --insert-depth -0.9 --regularize-boundary --output NEW
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw

from model_creator.core import load_source,dump,posed_model,POSES,MAX_BYTES
from model_creator.native import audit_yobj
from model_creator.experiments.facial import (partition,inventory,records,serialize,
    stitch_contours,graft_rig,pose_review,topology_review,source_signature,winding_review,Contour,regularized_partition,triangles)
from tools.prepare_model import bone_matrices,Surface
from tools.psp_mesh_merge_trial import sections,write_preview
from desktop.texture_optimizer.candidates import read_gim,write_gim


def export_preview(raw,textures,folder):
    folder=Path(folder);folder.mkdir(parents=True)
    model=audit_yobj(raw);ordinary=copy.deepcopy(model)
    for mesh in ordinary['meshes']:
        mesh['materials']=[m for m in mesh['materials'] if 'blood' not in model['texture_names'][m['texture_id']].casefold()]
    (folder/'model.yobj').write_bytes(raw);write_preview(ordinary,folder/'model.obj');mtl=[]
    for i,name in enumerate(model['texture_names']):
        indices,colors=read_gim(textures[name]);png=f'texture_{i:03d}.png'
        Image.fromarray(colors[indices]).save(folder/png)
        mtl+=['newmtl texture_%d'%i,'Kd 1 1 1','Ks 0 0 0','map_Kd '+png]
    (folder/'preview.mtl').write_text('\n'.join(mtl)+'\n',encoding='ascii')


def package(source,raw,textures,path):
    from tools.yukes_bpe import compress,decompress
    from tools.pac_repack import replace_sections,texture_table
    from tools.pac_inspect import inspect_pac
    from desktop.source_reference_qa import safe_repack
    safe_repack(source['data']);m=audit_yobj(raw);packed=compress(raw,max_distinct=220)
    if decompress(packed)!=raw:raise ValueError('BPE roundtrip failed.')
    table=texture_table(m['texture_names'],[textures[n] for n in m['texture_names']],gim_reader=read_gim)
    pac=replace_sections(source['data'],{2:packed,9:compress(table,max_distinct=220)})
    if len(pac)>MAX_BYTES:raise ValueError(f'Facial prototype is {len(pac)} bytes; exceeds {MAX_BYTES}. No texture/geometry reduction attempted.')
    old,new=[list(sections(d)) for d in (source['data'],pac)]
    if len(old)!=len(new):raise ValueError('PAC section count changed.')
    unchanged=[]
    for (a,ar),(b,br) in zip(old,new):
        if a['id']!=b['id']:raise ValueError('PAC section ID changed.')
        if b['id'] not in (2,9):
            if source['data'][a['offset']:a['offset']+a['size']]!=pac[b['offset']:b['offset']+b['size']]:raise ValueError('Unrelated stored section changed.')
            unchanged.append(b['id'])
    if next(r for s,r in new if s['id']==2)!=raw:raise ValueError('PAC preview YOBJ mismatch.')
    parsed=load_source_bytes(pac,path.parent/'readback.pac')
    if parsed['model']['texture_names']!=m['texture_names']:raise ValueError('Texture reference readback changed.')
    if {n:parsed['textures'][n.casefold()] for n in m['texture_names']}!=textures:raise ValueError('PAC texture bytes changed.')
    info=inspect_pac(pac)
    if len(pac)%2048 or any(s['offset']%16 for s in info['sections']):raise ValueError('PAC alignment failed.')
    path.write_bytes(pac)
    return dict(bytes=len(pac),sha256=hashlib.sha256(pac).hexdigest(),within_budget=True,
        unrelated_stored_sections_identical=unchanged,preview_yobj_identical=True,
        texture_bytes_identical=True,sections_16_aligned=True,file_2048_aligned=True,
        native_structural_checks=True,in_game_tested=False)


def load_source_bytes(raw,path):
    # The existing loader accepts paths; keep the diagnostic within the new run.
    try:path.write_bytes(raw);return load_source(path,library=True)
    finally:path.unlink(missing_ok=True)


def crop_head(model):
    result=copy.deepcopy(model);meshes=[]
    for mesh in result['meshes']:
        for mat in mesh['materials']:
            mat['triangles']=[t for t in mat['triangles'] if max(mesh['vertices'][i]['position'][1] for i in t)<-6.8]
        mesh['materials']=[m for m in mesh['materials'] if m['triangles'] and 'blood' not in result['texture_names'][m['texture_id']].casefold()]
        used=sorted({i for m in mesh['materials'] for t in m['triangles'] for i in t})
        if not used:continue
        remap={i:j for j,i in enumerate(used)};mesh['vertices']=[mesh['vertices'][i] for i in used]
        for mat in mesh['materials']:mat['triangles']=[[remap[i] for i in t] for t in mat['triangles']]
        meshes.append(mesh)
    result['meshes']=meshes
    return result


def render_comparisons(models,texture_sets,labels,folder,resolution=448):
    from desktop.preview import render
    crops=[crop_head(m) for m in models]
    p=np.array([v['position'] for m in crops for mesh in m['meshes'] for v in mesh['vertices']])
    bounds=[p.min(0),p.max(0)]
    for m in crops:
        # Unreferenced renderer-only bounding anchors force IDENTICAL cameras;
        # never serialized or used for geometric QA.
        mesh=copy.deepcopy(m['meshes'][0]);mesh['materials']=[]
        mesh['vertices']=[dict(position=b.tolist(),normal=[0,0,1],uv=[0,0],color=[255]*4) for b in bounds]
        m['meshes'].append(mesh)
    cams={}
    from model_qa.render import camera
    from model_qa.geometry import AXES
    folder.mkdir(parents=True,exist_ok=True)
    for view in ('front','back','left','right','front-left'):
        sheet=Image.new('RGB',(resolution*len(crops),resolution+30),(235,235,235));draw=ImageDraw.Draw(sheet)
        for i,(m,t,label) in enumerate(zip(crops,texture_sets,labels)):
            image=render(m,t,view,resolution,gim_reader=read_gim)
            sheet.paste(image,(i*resolution,30));draw.text((i*resolution+8,9),label,fill='black')
        sheet.save(folder/(view+'.png'));cams[view]=camera(p@AXES,view,resolution).describe()
    dump(folder/'cameras.json',cams)


def library_inventory(folder):
    catalog=json.loads((folder/'catalog.json').read_text(encoding='utf-8'));rows=[]
    for entry in catalog['models']:
        source=load_source(folder/entry['file'],library=True);model=source['model']
        if source['sha256']!=entry['sha256']:raise ValueError('Library donor hash changed: '+entry['label'])
        row=dict(label=entry['label'],sha256=source['sha256'],bone_names=[b['name'] for b in model['bones']],
            descriptor_count=entry['descriptor_count'],facial_material_buffers=inventory(model))
        try:
            part=partition(model);row['partition']=part.report
            try:
                Contour(part,records(model,0,[b['name'] for b in model['bones']],lambda k:k in part.face));row['automatic_fit_chart']=True
            except ValueError as exc:row.update(automatic_fit_chart=False,fit_review=str(exc))
        except ValueError as exc:row['partition_rejected']=str(exc)
        rows.append(row)
    return dict(models=rows,partition_ok=sum('partition' in r for r in rows),
        automatic_fit_chart_ok=sum(r.get('automatic_fit_chart',False) for r in rows),
        note='Inventory and boundary feasibility only; not library-wide transplants or game validation.')


def texture_inventory(source):
    result=[]
    for name in source['model']['texture_names']:
        if 'face' not in name.casefold():continue
        raw=source['textures'][name.casefold()];indices,colors=read_gim(raw)
        result.append(dict(name=name,width=indices.shape[1],height=indices.shape[0],
            declared_palette_entries=len(colors),used_palette_entries=len(np.unique(indices)),
            encoded_gim_bytes=len(raw),source_sha256=hashlib.sha256(raw).hexdigest()))
    return result


def inserted_feature_distances(shell,donor,part,output,origins):
    reference=copy.deepcopy(shell)
    for mesh in reference['meshes']:
        mesh['materials']=[m for m in mesh['materials'] if 'face' in reference['texture_names'][m['texture_id']].casefold()]
    surface=Surface(reference)
    actual_skin={(mi,i) for (mi,ai,ti),mesh,mat,ids,name in triangles(donor) if (mi,ai,ti) in part.face for i in ids}
    seen=set();distances=[]
    for mi,vi,origin,changed in origins:
        if origin is None or changed or origin[0]!=1 or origin in seen or origin[1:] not in actual_skin:continue
        seen.add(origin);distances.append(surface.nearest(output['meshes'][mi]['vertices'][vi]['position'])[2])
    return dict(samples=len(distances),mean=float(np.mean(distances)),p95=float(np.percentile(distances,95)),maximum=max(distances),
        method='Exact nearest triangle on original shell facial skin; no cross-donor vertex-index correspondence',
        caveat='Proves nonzero geometry change, not identity recognition or a likeness score.')


def run(args):
    output=args.output
    if output.exists():raise FileExistsError('Use a new output folder; existing baselines are never overwritten.')
    sources=[load_source(p,library=True) for p in (args.shell,args.insert)]
    a,b=[s['model'] for s in sources];names=[b['name'] for b in a['bones']]
    cut=regularized_partition if args.regularize_boundary else partition
    pa,pb=cut(a,args.shell_depth),cut(b,args.insert_depth)
    # Verify parameterization before creating any exports.
    for m,part in ((a,pa),(b,pb)):Contour(part,records(m,0,[b['name'] for b in m['bones']],lambda k:k in part.face))
    if set(names)!={bone['name'] for bone in b['bones']}:raise ValueError('First facial prototype requires the same named bone set; no missing controller collapse.')
    output.mkdir(parents=True);report=dict(schema='creator-facial-research/1',
        sources=[dict(file=Path(s['path']).name,sha256=s['sha256'],native_counts={k:s['model']['report'][k] for k in ('meshes','vertices','triangles')}) for s in sources],
        partitions=[pa.report,pb.report],inventories=[inventory(a),inventory(b)],face_textures=[texture_inventory(s) for s in sources],
        production_code_changed=False,blender_dependency=False,
        implementation_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).relative_to(Path.cwd()),Path('model_creator/experiments/facial.py'))})
    if args.inventory_library:dump(output/'library-inventory.json',library_inventory(args.inventory_library))
    ta={n:sources[0]['textures'][n.casefold()] for n in a['texture_names']}
    tb={n:sources[1]['textures'][n.casefold()] for n in b['texture_names']}
    shell_rows=records(a,0,names,lambda k:k not in pa.face|pa.attachments)
    original_insert=records(a,0,names,lambda k:k in pa.face|pa.attachments)
    shell_raw,shell_tex,_,_=serialize(a,[sources[0]],shell_rows)
    face_raw,face_tex,_,_=serialize(a,[sources[0]],original_insert)
    export_preview(shell_raw,shell_tex,output/'extraction/head-shell')
    export_preview(face_raw,face_tex,output/'extraction/facial-insert')
    # Rebuild from both actual extracted polygon sets, not a shortcut returning
    # the original binary. Every native attribute/material/weight is compared.
    reconstruction_rows=sorted(shell_rows+original_insert,key=lambda r:(r['mesh'],r['material'],r['triangle']))
    reconstruction,rt,ro,rs=serialize(a,[sources[0]],reconstruction_rows);rm=audit_yobj(reconstruction)
    exact=source_signature(a,sources[0]['textures'])==source_signature(rm,{n.casefold():v for n,v in rt.items()})
    if not exact or rm['bone_raw']!=a['bone_raw']:raise ValueError('Same-face reconstruction failed source identity.')
    rqa=pose_review(rm,[sources[0],sources[0]],ro,np.zeros(3),pa.contour)
    if not rqa['passed']:raise ValueError('Reconstructed source pose regression.')
    export_preview(reconstruction,rt,output/'reconstruction/preview')
    report['reconstruction']=dict(oriented_attribute_triangles_materials_and_textures_exact=exact,
        skeleton_records_byte_exact=True,qa=rqa,serialization=rs,
        native_counts={k:rm['report'][k] for k in ('meshes','vertices','triangles')},
        packaging=package(sources[0],reconstruction,rt,output/'reconstruction/reconstructed-original-EXPERIMENTAL.pac'))
    eyes=lambda m:np.mean([bone_matrices(m)[b['index'],:3,3] for b in m['bones'] if b['name'] in ('l_eye','r_eye')],axis=0)
    translation=eyes(a)-eyes(b)
    shell_rows=records(a,0,names,lambda k:k not in pa.face|pa.attachments)
    donor_rows=records(b,1,names,lambda k:k in pb.face|pb.attachments,translation)
    seam=stitch_contours(shell_rows,donor_rows,pa,pb,translation)
    base,rig=graft_rig(a,b,shell_rows,donor_rows,translation,0.)
    raw,tex,origins,serial=serialize(base,sources,shell_rows+donor_rows);model=audit_yobj(raw)
    poses=pose_review(model,sources,origins,translation,seam['seam_points'])
    topology=topology_review(model,seam['seam_points'])
    winding=winding_review(shell_rows+donor_rows,sources)
    export_preview(raw,tex,output/'transplant/preview')
    report['transplant']=dict(alignment=dict(method='Eye midpoint rigid translation ONLY',translation=translation.tolist(),scale=1.,rotation=np.eye(3).tolist()),
        seam=seam,rig=rig,qa=poses,topology=topology,winding=winding,serialization=serial,
        geometric_change_from_shell=inserted_feature_distances(a,b,pb,model,origins),
        native_counts={k:model['report'][k] for k in ('meshes','vertices','triangles')},
        textures_preserved=True,geometry_decimation=False,
        recognizable_likeness_status='Human visual review required; exact interior donor geometry verified, not a recognition score.')
    if poses['passed'] and topology['passed'] and winding['passed']:
        report['transplant']['packaging']=package(sources[0],raw,tex,output/'transplant/shell-with-donor-face-EXPERIMENTAL.pac')
    else:report['transplant']['export_withheld']='Native preview only: attachment topology, winding or analytical pose QA failed.'
    aligned=copy.deepcopy(b)
    for mesh in aligned['meshes']:
        for v in mesh['vertices']:v['position']=(np.array(v['position'])+translation).tolist()
    render_comparisons([a,rm,model,aligned],[ta,rt,tex,tb],
        ['Original shell donor','Same-face reconstruction','Transplanted face','Aligned face donor'],output/'comparisons',args.resolution)
    render_comparisons([audit_yobj(shell_raw),audit_yobj(face_raw)],[shell_tex,face_tex],
        ['Extracted head shell','Extracted original facial insert'],output/'extraction',args.resolution)
    for pose in ('standing','neck','jaw','eyes','eyelids'):
        render_comparisons([posed_model(a,pose),posed_model(model,pose)],[ta,tex],
            ['Native shell donor: '+pose,'Experimental transplant: '+pose],output/'poses'/pose,max(256,args.resolution//2))
    # Same texture makes the actual change of geometry visible, independently of
    # facial skin image/color differences. These resources exist for renders only.
    c=np.zeros((16,4),np.uint8);c[:,3]=255;c[0,:3]=(190,190,190)
    clay=write_gim(np.zeros((8,32),np.uint8),c,4)
    render_comparisons([a,model,aligned],[{n:clay for n in m['texture_names']} for m in (a,model,aligned)],
        ['Original shell geometry','Transplant geometry','Original donor geometry (aligned)'],output/'clay',args.resolution)
    dump(output/'report.json',report)
    (output/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(output).as_posix()+'\n' for p in sorted(output.rglob('*.pac'))),encoding='ascii')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--shell',required=True,type=Path);p.add_argument('--insert',required=True,type=Path)
    p.add_argument('--shell-depth',type=float);p.add_argument('--insert-depth',type=float);p.add_argument('--output',required=True,type=Path);p.add_argument('--resolution',type=int,default=448)
    p.add_argument('--inventory-library',type=Path)
    p.add_argument('--regularize-boundary',action='store_true')
    report=run(p.parse_args());print(json.dumps(dict(reconstruction=report['reconstruction']['packaging'],transplant=report['transplant'].get('packaging',report['transplant'].get('export_withheld'))),indent=2))

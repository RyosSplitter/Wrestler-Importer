"""Pinned HCTP Jericho -> PSP trial using Lance's hybrid float-weight workflow.

Preserves complete torso/hip surfaces before reduction, and keeps ponytail
attachment source-derived. This is an asset trial; it does not update the beta.
"""
import argparse
from collections import Counter,defaultdict
import copy
import json
import math
import os
from pathlib import Path
import struct
import subprocess

import numpy as np
from PIL import Image

from app.ps2_textures import read_source
from .convert_hctp import verify_serialized
from .editor_bridge import export
from .hctp_weights import load_hctp_with_weights
from .lance_abs_fix import reference_model
from .lance_rear_waist_fix import dense,posed_view
from .lance_anatomy_restore import oriented_face_key
from .pac_inspect import inspect_pac,parse_textures
from .pac_repack import texture_table,replace_sections
from .prepare_model import Surface
from .psp_materials import REGULAR_CONTROLS
from .psp_mesh_audit import audit_yobj,digest
from .psp_mesh_merge_trial import sections,write_preview,write_json,dump_audit
from .stripify import stripify
from .texture_convert import read_rtx3,read_gim,write_gim4,write_gim8,budget_texture
from .weight_trial_review import map_source,transfer,descendant_names,deform,POSES
from .yobj_read import read_yobj
from .yukes_bpe import compress,decompress

SOURCE_SHA='052da6cb97e1adcf865a89fd8d7d8544de8298025b36344f38de74ec600e9b1e'
BASE_SHA='bf935a51fe30bfd2df929f8eb9e50be5d793426ea05125ca9411ce21b19ead80'
PROTECTED=('y2j_body','y2j_mata','y2j_eye','y2j_ha','y2j_kuti','y2j_hair','y2j_tail','y2j_top')
PROFILE=dict(ratios={'Head':.8,'Torso':.65,'Arms':.8,'Legs':.65},protected_textures=PROTECTED,smooth_protected_textures=('y2j_body','y2j_mata'))
EXTRA_HALF_RESOLUTION={'y2j_arm','y2j_body','y2j_eye','y2j_head','y2j_hige','y2j_sune','y2j_top'}


def prepare_hybrid(source,target):
    aligned,alignment=reference_model(source,target)
    ps=np.array([v['position'] for m in aligned['meshes'] for v in m['vertices']]);sw=np.zeros((len(ps),source['bone_count']));row=0
    for m in source['meshes']:
        for v in m['vertices']:
            for b,w in zip(m['bone_palette'],v['weights']):sw[row,b]=w
            row+=1
    sw/=sw.sum(1)[:,None];mapped,missing,redirects=map_source(source,target,sw,True)
    if missing.max()>1e-7:raise ValueError('Source weights cannot map to the PSP skeleton')
    transferred,transfer_report=transfer(target,ps)
    head_names=descendant_names(source,'atama');fraction=sw[:,[b['index'] for b in source['bones'] if b['name'] in head_names]].sum(1)
    weights=mapped*(1-fraction[:,None])+transferred*fraction[:,None]
    # The source ponytail bones are absent from Kurt. Ancestor mapping attaches
    # them to the head; nearest-body transfer would attach the low tail to skin.
    held_positions={tuple(m['vertices'][i]['position']) for m in aligned['meshes'] for a in m['materials'] if aligned['textures'][a['texture_id']] in ('y2j_hair','y2j_tail','y2j_top') for i in {j for t in a['triangles'] for j in t}}
    held=np.array([tuple(p) in held_positions for p in ps]);weights[held]=mapped[held]
    order=np.argsort(weights,axis=1);np.put_along_axis(weights,order[:,:-4],0,axis=1);weights/=weights.sum(1)[:,None]
    row=0
    for m in aligned['meshes']:
        m['bone_palette']=list(range(target['bone_count']))
        for v in m['vertices']:
            v['weights']=weights[row].tolist();v['color']=[*v['color'][:3],255]
            v['normal']=(np.array(v['normal'])/np.linalg.norm(v['normal'])).tolist()
            v['position']=np.asarray(v['position'],dtype=np.float32).astype(float).tolist();row+=1
    aligned.update(bones=copy.deepcopy(target['bones']),bone_count=target['bone_count'],uv_v_flipped=False,weight_encoding='float')
    aligned['preparation_report']=dict(vertex_alpha={'policy':'opaque_psp_base'},alignment=alignment,
        hybrid_weights=dict(method=3,head_blended_vertices=int(np.count_nonzero(fraction>1e-7)),source_attachment_records=int(held.sum()),bone_redirects=redirects,transfer=transfer_report,
        body_weight_difference_max=float(np.max(np.abs(weights[fraction==0]-mapped[fraction==0])))))
    return aligned


def textures(source,output):
    output.mkdir();records=[];gims=[]
    for i,name,raw,rgba,details in read_source(source):
        cutout=int(rgba[:,:,3].min())<128
        if cutout:
            # This source is PSMT8/CSM1. Keep its cutout indices and all original
            # RGBA palette entries, with no resize, quantization or alpha snap.
            pixels,palette=read_rtx3(raw);bits=8;alpha_exact=True
        else:
            indices,palette=read_rtx3(raw)
            limit,bits=(128,8) if name=='y2j_face' else (64,4)
            pixels,palette=budget_texture(indices,palette,limit,bits)
            from .reduce_psp_textures import smaller
            size=smaller(pixels.shape[1],pixels.shape[0],bits)
            if size:pixels=np.array(Image.fromarray(pixels).resize(size,Image.Resampling.NEAREST),dtype=np.uint8)
            if name in EXTRA_HALF_RESOLUTION:
                if pixels.shape!=(32,64):raise ValueError('Unexpected budget texture dimensions')
                pixels=np.array(Image.fromarray(pixels).resize((32,32),Image.Resampling.NEAREST),dtype=np.uint8)
            alpha_exact=False
        gim=(write_gim8 if bits==8 else write_gim4)(pixels,palette);back,colors=read_gim(gim)
        if not np.array_equal(back,pixels) or not np.array_equal(colors,palette):raise ValueError('GIM texture round trip changed')
        (output/(name+'.gim')).write_bytes(gim);Image.fromarray(palette[pixels]).save(output/(name+'.png'));gims.append(gim)
        records.append(dict(index=i,name=name,bits=bits,bytes=len(gim),source_dimensions=list(rgba.shape[1::-1]),dimensions=list(pixels.shape[1::-1]),source_format=details,
            cutout_palette_and_pixels_exact=alpha_exact,source_rgba_sha256=digest(rgba.tobytes()),converted_rgba_sha256=digest(palette[pixels].tobytes())))
    return records,gims


def pack(model,target):
    donor=copy.deepcopy(target)
    for m in donor['meshes']:m['materials']=[a for a in m['materials'] if a['control'] not in (0x115,0x117)]
    surface=Surface(donor);corners={};buckets=defaultdict(list);removed=[]
    # Cache weight pruning by position so UV/material/region seam copies stay
    # identical after interpolation. Keep float weights and at most four slots.
    cache={}
    for m in model['meshes']:
        for vi,v in enumerate(m['vertices']):
            p=tuple(v['position']);w=np.array(v['weights'])
            if p not in cache:
                old=w.sum();w[np.argsort(w)[:-4]]=0;removed.append(float(old-w.sum()));w/=w.sum();cache[p]=w
            elif np.max(np.abs(cache[p]-w/w.sum()))>2e-6 and np.count_nonzero(w>1e-7)<=4:raise ValueError('Conflicting seam weights')
            corners[m['index'],vi]=(v,cache[p])
    for m in model['meshes']:
        for mat in m['materials']:
            for tri in mat['triangles']:
                ids=[(m['index'],i) for i in tri];center=np.mean([corners[i][0]['position'] for i in ids],axis=0)
                nearest,_,_=surface.nearest(center);part=int(surface.owners[nearest]);support=set(np.flatnonzero(np.any([corners[i][1]>0 for i in ids],axis=0)).tolist())
                if len(support)>8:raise ValueError('Triangle exceeds eight-bone PSP palette')
                candidates=[b for b in buckets[part] if len(b['palette']|support)<=8]
                def cost(b):
                    n=len(b['palette']|support)
                    return len(set(ids)-b['vertices'])*(36+4*n)+len(b['vertices'])*4*(n-len(b['palette']))+(160 if mat['texture_id'] not in b['textures'] else 0)
                if candidates and min(map(cost,candidates))<=320+len(ids)*(36+4*len(support)):bucket=min(candidates,key=cost)
                else:bucket={'palette':set(),'vertices':set(),'textures':set(),'faces':[]};buckets[part].append(bucket)
                bucket['palette'].update(support);bucket['vertices'].update(ids);bucket['textures'].add(mat['texture_id']);bucket['faces'].append((mat['texture_id'],ids))
    meshes=[];duplicates_removed=0
    for part,groups in sorted(buckets.items()):
        for ci,bucket in enumerate(groups):
            palette=sorted(bucket['palette']);vertices=[];vmap={};attribute_map={};materials=defaultdict(list)
            def attributes(idx):
                v,w=corners[idx]
                return struct.pack('<'+'f'*len(palette)+'2f4B3f3f',*w[palette],*v['uv'],*v['color'],*v['normal'],*v['position'])
            # Some original faces contain coincident corner records. Keep their
            # distinct indices rather than collapsing or discarding those faces.
            independent={idx for _,ids in bucket['faces'] if len({attributes(i) for i in ids})<3 for idx in ids}
            for tid,ids in bucket['faces']:
                face=[]
                for idx in ids:
                    if idx not in vmap:
                        v,w=corners[idx];v=copy.deepcopy(v);v['weights']=w[palette].tolist()
                        # Only identical serialized attributes may share an index.
                        # Materials and draw records remain separate and ordered.
                        key=(attributes(idx),idx if idx in independent else None)
                        if key in attribute_map:
                            vmap[idx]=attribute_map[key];duplicates_removed+=1
                        else:
                            vmap[idx]=len(vertices);attribute_map[key]=len(vertices);vertices.append(v)
                    face.append(vmap[idx])
                materials[tid].append(face)
            meshes.append(dict(index=len(meshes),target_part=part,part_chunk=ci,bone_palette=palette,vertices=vertices,materials=[dict(texture_id=tid,triangles=ts,strips=stripify(ts)) for tid,ts in sorted(materials.items())]))
    result=copy.deepcopy(model);result.update(meshes=meshes,mesh_count=len(meshes),model_name=target['model_name'],regional=True,
        vertex_count=sum(len(m['vertices']) for m in meshes),triangle_count=sum(len(a['triangles']) for m in meshes for a in m['materials']))
    result['preparation_report']['maximum_pruned_weight_mass']=max(removed,default=0.)
    result['preparation_report']['byte_identical_vertex_duplicates_removed']=duplicates_removed
    return result


def check_protected(reference,model):
    comparisons={}
    for name in PROTECTED:
        tid=reference['textures'].index(name)
        def keys(m):return Counter(oriented_face_key(x,t) for x in m['meshes'] for a in x['materials'] if a['texture_id']==tid for t in a['triangles'])
        aa,bb=keys(reference),keys(model)
        if aa!=bb:raise ValueError('Protected source surface changed: '+name)
        def uv_keys(m):
            return Counter(min(tuple(cs[i:]+cs[:i]) for i in range(3))
                for x in m['meshes'] for a in x['materials'] if a['texture_id']==tid for t in a['triangles']
                for cs in [[struct.pack('<3f2f',*x['vertices'][i]['position'],*x['vertices'][i]['uv']) for i in t]])
        ua,ub=uv_keys(reference),uv_keys(model)
        if ua!=ub:raise ValueError('Protected source UVs changed: '+name)
        lookup=defaultdict(list)
        for m in reference['meshes']:
            for a in m['materials']:
                if a['texture_id']!=tid:continue
                for i in {i for t in a['triangles'] for i in t}:
                    v=m['vertices'][i];w=np.zeros(reference['bone_count'])
                    w[m['bone_palette']]=v['weights'];lookup[struct.pack('<3f2f',*v['position'],*v['uv'])].append(w)
        delta=0.
        for m in model['meshes']:
            for a in m['materials']:
                if a['texture_id']!=tid:continue
                for i in {i for t in a['triangles'] for i in t}:
                    v=m['vertices'][i];w=np.zeros(reference['bone_count']);w[m['bone_palette']]=v['weights']
                    delta=max(delta,min(float(np.max(np.abs(w-r))) for r in lookup[struct.pack('<3f2f',*v['position'],*v['uv'])]))
        if delta>2e-6:raise ValueError('Protected hybrid weights changed: '+name)
        comparisons[name]=dict(triangles=sum(aa.values()),oriented_source_surface_sha256=digest(b''.join(b''.join(t) for t in sorted(aa.elements()))),
            oriented_position_uv_sha256=digest(b''.join(b''.join(t) for t in sorted(ua.elements()))),maximum_hybrid_weight_difference=delta,exact_float32_geometry_winding_and_uvs=True)
    return comparisons


def pose_checks(model,poses):
    ps,ws=dense(model);groups=defaultdict(list)
    for i,p in enumerate(ps):groups[struct.pack('<3f',*p)].append(i)
    triangles=[];offset=0
    for m in model['meshes']:
        for a in m['materials']:
            if model['texture_names'][a['texture_id']] in ('y2j_body','y2j_mata'):
                triangles.extend([np.asarray(t)+offset for t in a['triangles']])
        offset+=len(m['vertices'])
    report={}
    for name,pose in poses.items():
        q=deform(dict(bones=model['bones'],bone_count=len(model['bones'])),ps,ws,pose)
        if not np.isfinite(q).all():raise ValueError('Nonfinite pose: '+name)
        gap=max((float(np.max(np.abs(q[rows]-q[rows[0]]))) for rows in groups.values() if len(rows)>1),default=0.)
        if gap>2e-6:raise ValueError('Coincident seam separates in pose: '+name)
        ratios=[];original_zero=0
        for t in triangles:
            original=np.linalg.norm(np.cross(ps[t[1]]-ps[t[0]],ps[t[2]]-ps[t[0]]))
            if original<1e-10:original_zero+=1;continue
            area=np.linalg.norm(np.cross(q[t[1]]-q[t[0]],q[t[2]]-q[t[0]]));ratios.append(float(area/original))
        if min(ratios)<1e-6:raise ValueError('Protected body face collapses in pose: '+name)
        report[name]=dict(maximum_coincident_position_gap=gap,minimum_protected_body_face_area_ratio=min(ratios),original_zero_area_body_faces=original_zero,finite_positions=True)
    return report


def cutout_materials(native,texture_info):
    """Keep the observed PSP hair alpha flags, plus matching GIM bit depth.

    Native supplied Jericho hair uses 0x115 (indexed4 + alpha flags 0x110).
    The source's unchanged indexed8 cutout requires the same flags with 0x7.
    Every other byte and every ordinary skin material remains unchanged.
    """
    model=audit_yobj(native);data=bytearray(native);changes=[]
    start=struct.unpack_from('<I',native,36)[0]+8
    for mesh in model['meshes']:
        material_start=struct.unpack_from('<I',native,start+64*mesh['index']+12)[0]+8
        for mi,mat in enumerate(mesh['materials']):
            info=texture_info[mat['texture_id']]
            if not info['cutout_palette_and_pixels_exact']:continue
            value=REGULAR_CONTROLS[info['bits']]|0x110
            struct.pack_into('<I',data,material_start+144*mi+24,value)
            changes.append(dict(mesh=mesh['index'],material=mi,texture=info['name'],before_control=mat['control'],after_control=value))
    result=bytes(data);check=audit_yobj(result)
    for mesh in check['meshes']:
        for mat in mesh['materials']:
            info=texture_info[mat['texture_id']];expected=REGULAR_CONTROLS[info['bits']]|(0x110 if info['cutout_palette_and_pixels_exact'] else 0)
            if mat['control']!=expected:raise ValueError('Material alpha/depth profile mismatch')
    for a,b in zip(model['meshes'],check['meshes']):
        if a['raw_vertices']!=b['raw_vertices']:raise ValueError('Hair control edit changed geometry')
        for aa,bb in zip(a['materials'],b['materials']):
            if aa['raw'][:24]+aa['raw'][28:]!=bb['raw'][:24]+bb['raw'][28:]:raise ValueError('Hair control edit changed unrelated material bytes')
    return result,changes


def build(source_path,base_path,editor_path,output,blender='blender',reduced=True):
    if output.exists():raise FileExistsError(output)
    source=source_path.read_bytes();base=base_path.read_bytes()
    if digest(source)!=SOURCE_SHA:raise ValueError('Source is not the supplied HCTP Jericho PAC')
    if digest(base)!=BASE_SHA:raise ValueError('Base is not the accepted Kurt PSP PAC')
    s=load_hctp_with_weights(source_path);base_yobj=next(raw for sec,raw in sections(base) if sec['id']==2)
    t=read_yobj(base_yobj,psp_geometry=True);a=prepare_hybrid(s,t)
    output.mkdir(parents=True);write_json(output/'aligned-hybrid.json',a);write_json(output/'profile.json',PROFILE);(output/'base.yobj').write_bytes(base_yobj)
    tex_info,gims=textures(source_path,output/'textures');bits=[r['bits'] for r in tex_info]
    if reduced:
        env=os.environ.copy()
        for var,folder in [('BLENDER_USER_CONFIG','blender-config'),('BLENDER_USER_EXTENSIONS','blender-extensions'),('MESA_SHADER_CACHE_DIR','mesa-cache')]:env[var]=str((output/folder).resolve())
        with (output/'reduction.log').open('w') as log:
            subprocess.run([blender,'--background','--python-exit-code','1','--python',str(Path(__file__).with_name('blender_hybrid_reduce.py').resolve()),'--',str((output/'aligned-hybrid.json').resolve()),str((output/'reduced.json').resolve()),str((output/'profile.json').resolve())],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        model=json.loads((output/'reduced.json').read_text())
    else:model=a
    protected=check_protected(a,model);prepared=pack(model,t);prepared['texture_bits']=bits
    write_json(output/'prepared.json',prepared);export(editor_path,output/'base.yobj',output/'prepared.json',output/'native-export')
    ver=verify_serialized(prepared,base_yobj,output/'native-export/prepared.yobj');native=(output/'native-export/prepared.yobj').read_bytes()
    native,hair_controls=cutout_materials(native,tex_info);(output/'native-export/prepared.yobj').write_bytes(native);audited=audit_yobj(native)
    ver['regular_material_controls_match_texture_depth']=True;ver['cutout_controls']=hair_controls
    protected=check_protected(a,dict(meshes=audited['meshes']))
    table=texture_table(s['textures'],gims);packed_model=compress(native);packed_tex=compress(table)
    if decompress(packed_model)!=native or decompress(packed_tex)!=table:raise ValueError('BPE round trip changed')
    pac=replace_sections(base,{2:packed_model,9:packed_tex})
    if len(pac)>148000:raise ValueError('Candidate exceeds the 148,000-byte PAC budget')
    (output/'0600-PSP-hybrid-Jericho.pac').write_bytes(pac)
    old=inspect_pac(base)['sections'];new=inspect_pac(pac)['sections'];unchanged=[]
    for sec in new:
        if sec['offset']%16:raise ValueError('PAC section alignment failed')
        if sec['id'] not in (2,9):
            old_sec=next(x for x in old if x['id']==sec['id'])
            if pac[sec['offset']:sec['offset']+sec['size']]!=base[old_sec['offset']:old_sec['offset']+old_sec['size']]:raise ValueError('Unrelated base data changed')
            unchanged.append(sec['id'])
    if next(raw for sec,raw in sections(pac) if sec['id']==2)!=native:raise ValueError('Preview YOBJ differs from final PAC')
    final_table=next(raw for sec,raw in sections(pac) if sec['id']==9)
    entries={e['name']:e for e in parse_textures(final_table)}
    if set(entries)!=set(s['textures']):raise ValueError('Final PAC texture names changed')
    for name,gim in zip(s['textures'],gims):
        e=entries[name]
        if final_table[e['offset']:e['offset']+e['size']]!=gim:raise ValueError('Final PAC texture differs from preview: '+name)
    preview=output/'preview';preview.mkdir();(preview/'prepared.yobj').write_bytes(native)
    for r in tex_info:
        for ext in ('png','gim'):(preview/(r['name']+'.'+ext)).write_bytes((output/'textures'/(r['name']+'.'+ext)).read_bytes())
    mtl=[]
    for i,name in enumerate(s['textures']):mtl+=['newmtl texture_%d'%i,'Kd 0.984 0.984 1.000','Ks 0.502 0.502 0.502','map_Kd '+name+'.png']
    (preview/'preview.mtl').write_text('\n'.join(mtl)+'\n');write_preview(audited,preview/'prepared.obj')
    for view,angle in [('front',0),('rear',180),('side',90)]:write_preview(posed_view(audited,{},angle),preview/('jericho-'+view+'.obj'));write_preview(posed_view(a,{},angle),preview/('source-'+view+'.obj'))
    pose_definitions={**POSES,'standing':{'l_ninoude':('z',70),'r_ninoude':('z',-70)},'forward-bend':{'koshi':('x',35),'mune':('x',20)},'crouch':{'l_momo':('x',-50),'r_momo':('x',-50),'l_sune':('x',95),'r_sune':('x',95),'koshi':('x',20),'mune':('x',10)}}
    for i in range(16):
        swing=math.sin(2*math.pi*i/16)
        pose_definitions['walk-%02d'%i]={'l_momo':('x',25*swing),'r_momo':('x',-25*swing),'l_sune':('x',40*max(0,-swing)),'r_sune':('x',40*max(0,swing))}
    pose_validation=pose_checks(audited,pose_definitions)
    for name,pose in pose_definitions.items():write_preview(posed_view(audited,pose,135),preview/('jericho-'+name+'.obj'))
    audit=output/'audit';audit.mkdir();dump_audit(audited,audit,'jericho',len(pac))
    report=dict(status='Experimental candidate; PPSSPP validation pending',source_sha256=digest(source),base_sha256=digest(base),pac_sha256=digest(pac),base_filename=base_path.name,
        source=dict(pac_bytes=len(source),vertices=s['vertex_count'],triangles=s['triangle_count'],meshes=s['mesh_count'],textures=s['texture_count'],bones=s['bone_count']),
        output=dict(pac_bytes=len(pac),model_expanded_bytes=len(native),model_stored_bytes=len(packed_model),texture_stored_bytes=len(packed_tex),**{k:audited['report'][k] for k in ('meshes','vertices','triangles','indices','strips','textures','material_records','bones')}),
        budget_bytes=148000,within_budget=len(pac)<=148000,preparation=prepared['preparation_report'],reduction=model.get('reduction_report'),
        protected_source_surfaces=protected,textures=tex_info,serialized_verification=ver,unchanged_base_sections=unchanged,preview_yobj_equals_final_pac=True,
        pose_definitions=pose_definitions,pose_validation=pose_validation,limitations=['Synthetic pose checks are not game animation playback','Kurt PSP lacks original ponytail bones; the source chain maps to its head ancestor and has no independent hair physics'])
    write_json(output/'report.json',report)
    print(json.dumps(dict(output=report['output'],within_budget=report['within_budget'],protected=protected),indent=2));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--editor',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--blender',default='blender');p.add_argument('--no-reduction',action='store_true')
    x=p.parse_args();build(x.source,x.base,x.editor,x.output,x.blender,not x.no_reduction)

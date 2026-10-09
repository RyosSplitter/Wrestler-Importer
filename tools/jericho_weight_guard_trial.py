"""Correct source-supported cranial transfer and replay weights on frozen topology.

The new transfer stage keeps original facial controller weights. Its output is
interpolated onto the saved reduced surface by verified position or same-material
nearest-triangle coordinates. Geometry/UVs/index buffers stay exactly fixed.
Only model buffers/palettes are serialized; no PAC is constructed or repacked.
"""
import argparse
from collections import defaultdict
import copy
from pathlib import Path
import struct

import numpy as np
import trimesh

from model_qa.geometry import AXES,Surface,geometry
from tools.hctp_weights import load_hctp_with_weights
from tools.jericho_hybrid_trial import prepare_hybrid
from tools.psp_mesh_audit import audit_yobj,digest
from tools.psp_mesh_merge import write_model
from tools.psp_mesh_merge_trial import sections,write_json
from tools.weight_trial_review import descendant_names,map_source,transfer
from tools.yobj_read import read_yobj


def key(position):return struct.pack('<3f',*position)


def replay(raw,corrected):
    before=audit_yobj(raw);after=copy.deepcopy(before);g=geometry(corrected)
    heads=[i for i,n in enumerate(g.bone_names) if n in descendant_names(corrected,'atama')]
    by_position=defaultdict(list)
    for m in corrected['meshes']:
        for v in m['vertices']:by_position[key(v['position'])].append(np.array(v['weights']))
    surfaces={}
    for tid in {a['texture_id'] for m in before['meshes'] for a in m['materials']}:
        subset=copy.deepcopy(corrected)
        for m in subset['meshes']:m['materials']=[a for a in m['materials'] if a['texture_id']==tid]
        surfaces[tid]=Surface(geometry(subset),g.height)
    cache={};changes=[];palettes=[];pruned=[];exact=interpolated=0
    for m in after['meshes']:
        uses=defaultdict(set)
        for a in m['materials']:
            for i in {j for t in a['triangles'] for j in t}:uses[i].add(a['texture_id'])
        new_weights=[]
        for vi,v in enumerate(m['vertices']):
            p=key(v['position']);old=np.zeros(len(g.bone_names));old[m['bone_palette']]=v['weights']
            if p not in cache:
                candidates=by_position.get(p)
                if candidates:
                    if any(np.max(abs(w-candidates[0]))>2e-6 for w in candidates):raise ValueError('Ambiguous original coincident source weights')
                    w=candidates[0].copy();method='verified original float32 position';distance=0.;exact+=1
                else:
                    options=[]
                    for tid in uses[vi]:
                        s=surfaces[tid];closest,d,ids=s.nearest(np.array([v['position']])@AXES)
                        bary=trimesh.triangles.points_to_barycentric(s.g.vertices[s.g.faces[ids]],closest)[0]
                        w=bary@s.g.weights[s.g.faces[ids[0]]];options.append((float(d[0]),tid,w))
                    if not options:raise ValueError('Unreferenced native record has no weight provenance')
                    distance,_,w=min(options,key=lambda x:(x[0],x[1]));method='same-material source triangle barycentric replay';interpolated+=1
                active=np.flatnonzero(w>1e-7);mass=float(w[active].sum());w[np.argsort(w)[:-4]]=0
                pruned.append(float(mass-w.sum()));w/=w.sum()
                cache[p]=(w,method,distance)
            w,method,distance=cache[p]
            if w[heads].sum()<=1e-7 and old[heads].sum()<=1e-7:w=old
            if np.max(abs(w-old))>1e-7:
                changes.append(dict(mesh=m['index'],vertex=vi,position=v['position'],method=method,reference_surface_distance=distance,
                    before={g.bone_names[i]:float(x) for i,x in enumerate(old) if x>1e-7},after={g.bone_names[i]:float(x) for i,x in enumerate(w) if x>1e-7}))
            new_weights.append(w)
        needed=set(np.flatnonzero(np.any(np.array(new_weights)>1e-7,axis=0)).tolist())
        if not needed<=set(m['bone_palette']):
            palette=[b for b in m['bone_palette'] if b in needed]+sorted(needed-set(m['bone_palette']))
        else:palette=m['bone_palette']
        if len(palette)>8:raise ValueError('Corrected facial weights exceed PSP palette; separate experiment required')
        old_palette=list(m['bone_palette']);old_stride=m['stride'];old_slots=m['weight_slots'];data=bytearray()
        for i,(v,w) in enumerate(zip(m['vertices'],new_weights)):
            weights=w[palette].tolist();v['weights']=weights
            data+=struct.pack('<'+'f'*len(palette),*weights)+m['raw_vertices'][i*old_stride+4*old_slots:(i+1)*old_stride]
        m['raw_vertices']=bytes(data);m['bone_palette']=palette;m['weight_slots']=len(palette);m['stride']=36+4*len(palette)
        if palette!=old_palette:palettes.append(dict(mesh=m['index'],before=old_palette,after=palette,before_names=[g.bone_names[i] for i in old_palette],after_names=[g.bone_names[i] for i in palette]))
    result=write_model(after,[[i] for i in range(len(after['meshes']))]);checked=audit_yobj(result)
    for a,b in zip(before['meshes'],checked['meshes']):
        if len(a['vertices'])!=len(b['vertices']):raise ValueError('Vertex layout changed')
        for i in range(len(a['vertices'])):
            x=a['raw_vertices'][i*a['stride']+4*a['weight_slots']:(i+1)*a['stride']]
            y=b['raw_vertices'][i*b['stride']+4*b['weight_slots']:(i+1)*b['stride']]
            if x!=y:raise ValueError('Geometry/UV/color/normal bytes changed')
        for x,y in zip(a['materials'],b['materials']):
            if x['strips']!=y['strips'] or x['raw'][:132]!=y['raw'][:132]:raise ValueError('Topology or material state changed')
    for field in ('bone_raw','texture_raw','model_descriptor_raw'):
        if before[field]!=checked[field]:raise ValueError(field+' changed')
    return result,dict(policy='Preserve verified source cranial controller weights before decimation; replay corrected weights on fixed topology',
        geometry_uv_normals_colors_indices_materials_skeleton_unchanged=True,weight_changes=changes,palette_changes=palettes,
        exact_source_position_matches=exact,barycentric_replay_positions=interpolated,maximum_replay_pruned_mass=max(pruned,default=0.),
        baseline_yobj_sha256=digest(raw),candidate_yobj_sha256=digest(result),pac_written=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','base','baseline','output'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    source=load_hctp_with_weights(a.source);base=next(r for s,r in sections(a.base.read_bytes()) if s['id']==2)
    target=read_yobj(base,psp_geometry=True);legacy=prepare_hybrid(source,target);corrected=prepare_hybrid(source,target,preserve_source_cranial=True)
    raw=next(r for s,r in sections(a.baseline.read_bytes()) if s['id']==2);result,report=replay(raw,corrected)
    a.output.mkdir(parents=True);(a.output/'candidate.yobj').write_bytes(result)
    write_json(a.output/'input-source-weighted.json',source);write_json(a.output/'input-psp-donor.json',target)
    write_json(a.output/'corrected-weight-transfer.json',corrected);write_json(a.output/'legacy-weight-transfer.json',legacy)
    lg,cg=geometry(legacy),geometry(corrected)
    original=geometry(source);mapped,missing,redirects=map_source(source,target,original.weights,True)
    donor,donor_report=transfer(target,lg.vertices@AXES)
    np.savez_compressed(a.output/'weight-comparison.npz',source_weights=original.weights,mapped_source_weights=mapped,
        nearest_donor_weights=donor,legacy_hybrid_weights=lg.weights,corrected_weights=cg.weights,aligned_positions=lg.vertices)
    if not np.array_equal(lg.vertices,cg.vertices) or not np.array_equal(lg.faces,cg.faces):raise ValueError('Transfer-stage geometry changed')
    report.update(source_sha256=digest(a.source.read_bytes()),psp_base_sha256=digest(a.base.read_bytes()),bone_redirects=redirects,donor_transfer_diagnostics=donor_report,
        transfer_stage_vertices=len(lg.vertices),transfer_stage_geometry_unchanged=True)
    write_json(a.output/'experiment.json',report)


if __name__=='__main__':main()

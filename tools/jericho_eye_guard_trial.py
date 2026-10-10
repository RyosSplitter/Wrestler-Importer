"""Isolated ocular compatibility trial on verified, frozen Jericho topology.

Restore the previously serialized PSP hybrid weights only on records supported
by source eye/eyelid controllers. All other records retain the reviewed jaw fix.
This tool writes no PAC; packaging remains a separate unchanged stage.
"""
import argparse
import copy
from pathlib import Path
import struct

import numpy as np

from model_qa.geometry import geometry,align_reference
from tools.psp_mesh_audit import audit_yobj,digest
from tools.psp_mesh_merge import write_model
from tools.psp_mesh_merge_trial import sections,write_json
from tools.prepare_model import bone_matrices

OCULAR={'l_eye','r_eye','l_mabuta','r_mabuta'}

def frozen_attributes(a,b):
    if len(a['meshes'])!=len(b['meshes']):raise ValueError('Mesh layout differs')
    for x,y in zip(a['meshes'],b['meshes']):
        if len(x['vertices'])!=len(y['vertices']) or x['opaque']!=y['opaque']:
            raise ValueError('Vertex layout or mesh state differs')
        for i in range(len(x['vertices'])):
            xx=x['raw_vertices'][i*x['stride']+4*x['weight_slots']:(i+1)*x['stride']]
            yy=y['raw_vertices'][i*y['stride']+4*y['weight_slots']:(i+1)*y['stride']]
            if xx!=yy:raise ValueError('Non-weight vertex bytes differ')
        if len(x['materials'])!=len(y['materials']):raise ValueError('Material layout differs')
        for xx,yy in zip(x['materials'],y['materials']):
            if xx['strips']!=yy['strips'] or xx['raw'][:132]!=yy['raw'][:132]:
                raise ValueError('Indices or rendering state differ')
    for field in ('bone_raw','texture_raw','model_descriptor_raw'):
        if a[field]!=b[field]:raise ValueError(field+' differs')

def repair(previous_raw,jaw_raw):
    previous,jaw=map(audit_yobj,(previous_raw,jaw_raw));frozen_attributes(previous,jaw)
    a,b=geometry(previous),geometry(jaw)
    controllers=[i for i,n in enumerate(b.bone_names) if n in OCULAR]
    if len(controllers)!=4:raise ValueError('Missing eye/eyelid controllers')
    selected=b.weights[:,controllers].sum(1)>1e-7
    # Selection comes from source-supported controller weights in the reviewed
    # jaw experiment, not an arbitrary face box, texture name or vertex index.
    lower=[i for i,n in enumerate(b.bone_names) if n=='d_kuchi' or n.startswith('d_kuchi_')]
    if np.any(b.weights[selected][:,lower].sum(1)>1e-7):
        raise ValueError('Ocular selection overlaps jaw controllers; needs human review')
    output=copy.deepcopy(jaw);weights=b.weights.copy();weights[selected]=a.weights[selected]
    offset=0;changes=[];palettes=[]
    for m,old in zip(output['meshes'],previous['meshes']):
        n=len(m['vertices']);block=weights[offset:offset+n]
        needed=set(np.flatnonzero(np.any(block>0,axis=0)).tolist())
        palette=list(m['bone_palette'])
        additions=needed-set(palette)
        if additions:
            palette=[i for i in palette if i in needed]+sorted(additions)
        if len(palette)>8:raise ValueError('Ocular trial exceeds native palette limit')
        raw=bytearray();before_palette=list(m['bone_palette'])
        for vi,w in enumerate(block):
            global_i=offset+vi
            src=old if selected[global_i] else m
            # Copy exact float32 weight bytes by bone identity; unselected jaw
            # records never pass through interpolation, pruning or normalization.
            record=src['raw_vertices'][vi*src['stride']:(vi+1)*src['stride']]
            lookup={bone:record[4*j:4*j+4] for j,bone in enumerate(src['bone_palette'])}
            raw+=b''.join(lookup.get(bone,bytes(4)) for bone in palette)
            raw+=m['raw_vertices'][vi*m['stride']+4*m['weight_slots']:(vi+1)*m['stride']]
            if np.max(abs(a.weights[global_i]-b.weights[global_i]))>1e-7 and selected[global_i]:
                uses=[jaw['texture_names'][mat['texture_id']] for mat in m['materials']
                      if any(vi in tri for tri in mat['triangles'])]
                changes.append(dict(mesh=m['index'],vertex=vi,position=m['vertices'][vi]['position'],textures=uses,
                    role='eye' if 'y2j_eye' in uses else 'eyelid/surrounding facial seam',
                    previous_psp={name:float(v) for name,v in zip(a.bone_names,a.weights[global_i]) if v>0},
                    jaw_experiment={name:float(v) for name,v in zip(b.bone_names,b.weights[global_i]) if v>0}))
        if palette!=before_palette:palettes.append(dict(mesh=m['index'],before=before_palette,after=palette))
        m.update(raw_vertices=bytes(raw),bone_palette=palette,weight_slots=len(palette),stride=36+4*len(palette))
        offset+=n
    result=write_model(output,[[i] for i in range(len(output['meshes']))]);fixed=audit_yobj(result)
    frozen_attributes(jaw,fixed);c=geometry(fixed)
    if not np.array_equal(c.weights[selected],a.weights[selected]):raise ValueError('Ocular weights not exact PSP baseline')
    if not np.array_equal(c.weights[~selected],b.weights[~selected]):raise ValueError('Unselected weights changed')
    return result,dict(policy='Selective original-eye/eyelid-supported PSP hybrid preservation; jaw weights untouched',
        selected_records=int(selected.sum()),changed_records=len(changes),weight_changes=changes,palette_changes=palettes,
        selected_vertex_records=[b.vertex_records[i] for i in np.flatnonzero(selected)],
        geometry_uv_normals_colors_indices_materials_skeleton_unchanged=True,
        selected_weights_equal_previous_psp=True,unselected_weights_equal_jaw_experiment=True,
        previous_yobj_sha256=digest(previous_raw),jaw_yobj_sha256=digest(jaw_raw),candidate_yobj_sha256=digest(result),pac_written=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('previous','jaw','source-stage','donor-stage','output'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    import json
    source=json.loads(args.source_stage.read_text());donor=json.loads(args.donor_stage.read_text())
    previous=next(raw for s,raw in sections(args.previous.read_bytes()) if s['id']==2)
    jaw=args.jaw.read_bytes();result,report=repair(previous,jaw)
    aligned,fit=align_reference(source,audit_yobj(jaw));sm,tm=bone_matrices(source),bone_matrices(donor)
    target={b['name']:b for b in donor['bones']};binding=[]
    for bone in source['bones']:
        if not any(x in bone['name'] for x in ('eye','mabuta','mayu','meziri')):continue
        name=bone['name'];pivot=fit['scale']*np.array(fit['rotation'])@sm[bone['index']][:3,3]+fit['translation']
        record=dict(name=name,source=bone,aligned_source_world_pivot=pivot.tolist(),same_name_target_present=name in target)
        if name in target:
            b=target[name];record.update(target=b,target_world_pivot=tm[b['index']][:3,3].tolist(),
                aligned_pivot_difference=float(np.linalg.norm(pivot-tm[b['index']][:3,3])))
        else:record['mapping']='Nearest shared ancestor atama; no same-name PSP eyebrow controller'
        binding.append(record)
    report.update(controller_bind_comparison=binding,
        stage_policy='After weight transfer/reduction: preserve source-derived jaw weights, replay known-working serialized PSP ocular weights on verified frozen geometry',
        source_stage_sha256=digest(args.source_stage.read_bytes()),donor_stage_sha256=digest(args.donor_stage.read_bytes()))
    args.output.mkdir(parents=True);(args.output/'candidate.yobj').write_bytes(result)
    write_json(args.output/'experiment.json',report)
    print(json.dumps(dict(selected_records=report['selected_records'],changed_records=report['changed_records'],
        palette_changes=len(report['palette_changes']),candidate_yobj_sha256=report['candidate_yobj_sha256']),indent=2))

if __name__=='__main__':main()

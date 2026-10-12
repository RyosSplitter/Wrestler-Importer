"""Reproduce per-contact reports/renders from reference, old reduction and PAC.

Usage: python -m tools.source_skinning_report reference.json before.json
       candidate.pac output-folder
The reference must contain source-derived weights on the verified target rig.
"""
import argparse
import copy
import json
from pathlib import Path
import struct
import numpy as np
from PIL import Image,ImageDraw
from model_qa.geometry import AXES,geometry,posed,read_model,sha
from model_qa.render import camera,raster
from model_qa.skinning_records import POSES,compare,records


def build(reference_path,before_path,candidate_path,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    reference=read_model(reference_path);before=read_model(before_path);candidate=read_model(candidate_path)
    a=compare(reference,before,strict=False);b=compare(reference,candidate,strict=False)
    (output/'before.json').write_text(json.dumps(a,indent=2)+'\n')
    (output/'after.json').write_text(json.dumps(b,indent=2)+'\n')
    models=[reference,before,candidate];gs=[geometry(m) for m in models]
    poses={name:[posed(g,p) for g in gs] for name,p in POSES.items()}
    rp,rw,rids,rf,rg=records(reference)
    locations=[];gallery=[]
    for after,old in zip(b['locations'],a['locations']):
        number=after['location'];p=struct.pack('<3f',*after['position']);ids=rg[p]
        source_faces=np.flatnonzero(np.any(np.isin(gs[0].faces,ids),axis=1))
        patch=gs[0].vertices[np.unique(gs[0].faces[source_faces])]
        center=(patch.max(0)+patch.min(0))*.5;radius=max(np.linalg.norm(patch-center,axis=1).max(),.03)*1.3
        face_sets=[np.flatnonzero(np.linalg.norm(g.vertices[g.faces].mean(1)-center,axis=1)<radius) for g in gs]
        # All three panels share each reference camera and pose. Selection uses
        # a spatial neighborhood; no old/native vertex index match is assumed.
        for pose in ('standing','crouch','toe-flex','mouth-open'):
            source_patch=poses[pose][0].vertices[np.unique(gs[0].faces[source_faces])]
            for view in ('front','left'):
                cam=camera(source_patch,view,200);cam.span*=1.25
                sheet=Image.new('RGB',(600,226),(28,28,28));draw=ImageDraw.Draw(sheet)
                for column,(g,selection,label) in enumerate(zip(poses[pose],face_sets,('Source-derived reference','Old reducer (no PAC)','Corrected native PAC'))):
                    g=copy.copy(g);g.faces=g.faces[selection]
                    render=Image.fromarray(raster(g,cam)['rgb'])
                    sheet.paste(render,(column*200,26));draw.text((column*200+5,6),label,fill='white')
                name='location-%02d-%s-%s.png'%(number,pose,view);sheet.save(output/name);gallery.append(name)
        locations.append(dict(location=number,position=after['position'],before_preserved_records=old['preserved_records'],
            after_preserved_records=after['preserved_records'],required_records=after['required_records'],
            before_maximum_motion_error=max((x['maximum_corresponding_motion_error'] or 0 for x in old['poses'].values()),default=0) if old['preserved_records']==old['required_records'] else None,
            before_observed_weight_branches=len(old['observed_weight_branches']),after_observed_weight_branches=len(after['observed_weight_branches']),
            expected_weight_branches=after['source_weight_branch_count'],
            before_maximum_observed_gap_error=max(x['observed_gap_error'] for x in old['poses'].values()) if all(x['observed_gap_error'] is not None for x in old['poses'].values()) else None,
            after_maximum_motion_error=max((x['maximum_corresponding_motion_error'] or 0 for x in after['poses'].values()),default=0),
            original_record_ids=[[r['mesh'],r['vertex']] for r in after['source_records']]))
    report=dict(inputs={str(p):sha(p) for p in (reference_path,before_path,candidate_path)},before_status=a['status'],after_status=b['status'],
                source_conflicting_locations=b['source_conflicting_locations'],locations=locations,gallery=gallery,
                limitation='CPU clay renders and target-rig analytical poses; not Noesis screenshots or captured game animation')
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    rows=''.join('<tr><td>%d</td><td>%s</td><td>%d / %d</td><td>%d / %d</td><td>%s</td><td>%.9g</td></tr>'%
        (l['location'],l['original_record_ids'],l['before_preserved_records'],l['required_records'],l['after_preserved_records'],l['required_records'],str(l['before_maximum_motion_error']) if l['before_maximum_motion_error'] is not None else 'Incomplete correspondence',l['after_maximum_motion_error']) for l in locations)
    images=''.join('<p>%s</p><img width="600" src="%s">'%(f,f) for f in gallery)
    (output/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Source skinning contacts</title><h1>Source skinning contact comparison</h1><p>'+report['limitation']+'</p><p>Face correspondence uses verified material, float32 position/UV and cyclic topology. Missing faces are failures, not zero-error observations. No source/native vertex-index correspondence is assumed.</p><table border="1"><tr><th>Location</th><th>Original mesh/vertex IDs</th><th>Before matched records</th><th>After matched records</th><th>Before motion error</th><th>After motion error</th></tr>'+rows+'</table>'+images,encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','before','candidate','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();build(args.reference,args.before,args.candidate,args.output)

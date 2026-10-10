"""Review isolated YOBJ experiments without writing or modifying any PAC."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

from model_qa.geometry import geometry,posed

from model_qa.metrics import detect,tolerances
from tools.pac_inspect import inspect_pac
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress,decompress


def structural_budget(baseline, yobj, *, allow_palette_changes=False):
    pac=Path(baseline).read_bytes();raw=Path(yobj).read_bytes()
    source=next(r for s,r in sections(pac) if s['id']==2);a,b=map(audit_yobj,(source,raw))
    for key in ('bone_raw','texture_raw','model_descriptor_raw'):
        if a[key]!=b[key]:raise ValueError('Experiment changed '+key)
    if len(a['meshes'])!=len(b['meshes']):raise ValueError('Experiment changed mesh layout')
    for old,new in zip(a['meshes'],b['meshes']):
        if (old['bone_palette']!=new['bone_palette'] and not allow_palette_changes) or old['opaque']!=new['opaque']:
            raise ValueError('Experiment changed palette or opaque mesh metadata')
        if len(old['materials'])!=len(new['materials']):raise ValueError('Material layout changed')
        for x,y in zip(old['materials'],new['materials']):
            if x['raw'][:132]!=y['raw'][:132]:raise ValueError('Texture/material/rendering state changed')
    packed=compress(raw)
    if decompress(packed)!=raw:raise ValueError('Model compression round trip failed')
    layout=inspect_pac(pac);cursor=8+8*len(layout['sections'])
    for section in layout['sections']:
        cursor+=(-cursor)%16
        cursor+=len(packed) if section['id']==2 else section['size']
    projected=cursor+(-cursor)%2048
    return dict(native_audit_passed=True,skeleton_texture_material_metadata_preserved=True,
                palettes_preserved=all(x['bone_palette']==y['bone_palette'] for x,y in zip(a['meshes'],b['meshes'])),palette_changes_authorized=allow_palette_changes,
                baseline_pac_sha256=hashlib.sha256(pac).hexdigest(),baseline_pac_bytes=len(pac),
                expanded_yobj_bytes=len(raw),model_bpe_bytes=len(packed),
                projected_existing_layout_pac_bytes=projected,budget_bytes=148000,
                within_budget=projected<=148000,pac_written=False,
                budget_note='Arithmetic projection using unchanged PAC layout/other payload sizes. No container is constructed or repacked.',
                meshes=b['report']['meshes'],vertices=b['report']['vertices'],triangles=b['report']['triangles'])


def unchanged_region_proofs(before,after,baseline,yobj):
    """Explain sampling threshold crossings only after exact local proof.

    Adding distant faces changes global area-weighted candidate sample draws.
    Never suppress the raw QA flag or change its threshold. Verify unchanged
    local triangle positions/weights, identical analytical pose, and unchanged
    forward reference-sample error before classifying that crossing as noise.
    """
    a=geometry(audit_yobj(next(r for s,r in sections(Path(baseline).read_bytes()) if s['id']==2)))
    b=geometry(audit_yobj(Path(yobj).read_bytes()));proofs=[]
    old_flags={(f['region'],f['pose']) for f in before['flags'] if f['severity']!='insufficient-evidence'}
    for flag in after['flags']:
        region,pose=flag['region'],flag['pose']
        if region not in after['rest']['regions']:continue
        if (region,pose) in old_flags or region=='whole-model' or flag['severity']=='insufficient-evidence':continue
        roi=after['rest']['regions'][region]['roi'];lo,hi=np.array(roi['lower']),np.array(roi['upper'])
        def signatures(g):
            triangles=g.vertices[g.faces];selected=np.all(triangles.max(1)>=lo,axis=1)&np.all(triangles.min(1)<=hi,axis=1)
            controls={} if pose=='rest' else after['pose_controls'][pose]
            p=posed(g,controls).vertices if controls else g.vertices
            values=[]
            for t in g.faces[selected]:
                corners=[p[i].astype('<f8').tobytes()+g.weights[i].astype('<f8').tobytes() for i in t]
                values.append(min(tuple(corners[k:]+corners[:k]) for k in range(3)))
            return sorted(values)
        aa,bb=signatures(a),signatures(b)
        old=before['rest'] if pose=='rest' else before['poses'][pose]
        new=after['rest'] if pose=='rest' else after['poses'][pose]
        forward_old=old['regions'][region]['source_to_candidate'];forward_new=new['regions'][region]['source_to_candidate']
        same_forward=forward_old and forward_new and forward_old['samples']==forward_new['samples'] and all(abs(forward_old[k]-forward_new[k])<1e-12 for k in ('mean','p95','p99','maximum'))
        if aa and aa==bb and same_forward:
            proofs.append(dict(region=region,pose=pose,local_triangles=len(aa),identical_posed_position_and_bone_weight_signatures=True,
                identical_fixed_reference_sample_errors=True,source_to_candidate_p95=forward_new['p95'],
                local_signature_sha256=hashlib.sha256(b''.join(b''.join(t) for t in aa)).hexdigest(),
                candidate_samples_before=old['regions'][region]['candidate_to_source']['samples'],candidate_samples_after=new['regions'][region]['candidate_to_source']['samples'],
                interpretation='Raw QA threshold crossing retained: distant area changes alter candidate sample draws; exact local geometry/weights/poses and fixed source queries are unchanged. No tolerance was relaxed.'))
    return proofs


def compare(before,after,structure,known,unchanged_proofs=()):
    profile=before['thresholds']
    if profile!=after['thresholds']:raise ValueError('Tolerance profile changed between trials')
    before_flags={(f['region'],f['pose']) for f in before['flags'] if f['severity']!='insufficient-evidence'}
    # Shape/concavity labels may change as a defect improves. A previously
    # failing region is not a newly failing region merely because its label did.
    raw_new_flags=[f for f in after['flags'] if f['severity']!='insufficient-evidence' and (f['region'],f['pose']) not in before_flags]
    proven={(p['region'],p['pose']) for p in unchanged_proofs}
    new_flags=[f for f in raw_new_flags if (f['region'],f['pose']) not in proven]
    regressions=[];improvements=[]
    for region,pose in known:
        old=before['rest'] if pose=='rest' else before['poses'][pose]
        new=after['rest'] if pose=='rest' else after['poses'][pose]
        a,b=old['regions'][region]['distance'],new['regions'][region]['distance']
        improvements.append(dict(region=region,pose=pose,before_p95_height=a['p95_height'],after_p95_height=b['p95_height'],improved=b['p95_height']<a['p95_height']))
    for pose in ['rest',*before['poses']]:
        old=before['rest'] if pose=='rest' else before['poses'][pose]
        new=after['rest'] if pose=='rest' else after['poses'][pose]
        for region,a in old['regions'].items():
            b=new['regions'][region];limit=tolerances(profile,region)
            if a['distance'] and b['distance']:
                if b['distance']['p95_height']>a['distance']['p95_height']+limit['distance_p95_height']:
                    regressions.append(dict(region=region,pose=pose,reason='Surface error worsened by more than the established regional tolerance',before=a['distance']['p95_height'],after=b['distance']['p95_height']))
                # Preserve established absolute/static and added-motion review limits.
                previous_review=any(f['region']==region and f['pose']==pose for f in before['flags'] if f['severity']!='insufficient-evidence')
                if not previous_review and any(f['region']==region and f['pose']==pose for f in new_flags):
                    regressions.append(dict(region=region,pose=pose,reason='Previously passing region gained a review flag'))
    if not structure['within_budget']:regressions.append(dict(region='format',pose='all',reason='Projected unchanged-layout PSP budget exceeded'))
    for f in new_flags:
        if f['region']=='whole-model':regressions.append(dict(region='whole-model',pose=f['pose'],reason=f['kind']))
    return dict(status='eligible-for-human-review' if all(x['improved'] for x in improvements) and not regressions and not new_flags else 'rejected',
                improvements=improvements,new_flags=new_flags,raw_new_flags=raw_new_flags,unchanged_region_sampling_reviews=list(unchanged_proofs),regressions=regressions,structure=structure,
                automatic_baseline_replacement=False,pac_packaging_changed=False,
                limitations=['Human comparison-render review is still required','Analytical poses are not actual game animations','Existing unrelated review flags are not hidden or certified as passes'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','baseline','yobj','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--known',action='append',required=True,metavar='REGION:POSE')
    p.add_argument('--allow-palette-changes',action='store_true',help='Permit audited weight-only palette changes in the facial-weight experiment')
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    before,after=json.loads(a.before.read_text()),json.loads(a.after.read_text())
    proofs=unchanged_region_proofs(before,after,a.baseline,a.yobj)
    r=compare(before,after,structural_budget(a.baseline,a.yobj,allow_palette_changes=a.allow_palette_changes),[tuple(x.split(':')) for x in a.known],proofs)
    a.output.write_text(json.dumps(r,indent=2,allow_nan=False)+'\n');print(json.dumps(r,indent=2))


if __name__=='__main__':main()

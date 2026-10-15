"""Standalone, conservative PAC QA. Never writes to the input or converter.

Repairs are allowlisted layout transformations with exact preservation checks.
Unknown anatomy/controller semantics require reference review, not guessed edits.
"""
import html
import copy
import json
from pathlib import Path
import struct

import numpy as np

from desktop.edit_folder import publish_new
from desktop.workspace import digest, dump, inspect_workspace
from model_qa.geometry import geometry, posed, seam_motion
from model_qa.head import controller_probes, layout_review
from model_qa.ocular import skin
from model_qa.pipeline import POSES
from tools.pac_inspect import inspect_pac
from tools.pac_repack import replace_sections
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections


def safe_repack(data):
    """Refuse to discard unknown data between declared sections."""
    info = inspect_pac(data)
    cursor = info['payload_start']
    for s in sorted(info['sections'], key=lambda s:s['offset']):
        if any(data[cursor:s['offset']]):
            raise ValueError('Nonzero unclassified PAC gap data: repacking is unsafe.')
        cursor = s['offset']+s['size']
    if any(data[cursor:]):
        raise ValueError('Nonzero unclassified PAC trailing data: repacking is unsafe.')


def pose_checks(model):
    # Native rigid vertices carry no explicit weight values; their sole palette
    # entry is an implicit unit influence. Expand only the analytical copy.
    model=copy.deepcopy(model)
    for mesh in model['meshes']:
        if mesh.get('rigid'):
            if len(mesh['bone_palette'])!=1:raise ValueError('Unsupported rigid palette.')
            for vertex in mesh['vertices']:vertex['weights']=[1.]
    g = geometry(model)
    result = {}
    for name, controls in POSES.items():
        missing = sorted(set(controls)-set(g.bone_names))
        if missing:
            result[name] = dict(status='unsupported', missing_bones=missing)
            continue
        p = posed(g, controls)
        result[name] = dict(status='finite', bounds=[p.vertices.min(0).tolist(),p.vertices.max(0).tolist()],
                            seam_motion=seam_motion(g,p,max(g.height,1e-12)))
    for name, probe in controller_probes(model).items():
        missing = sorted(set(probe['controls'])-set(g.bone_names))
        if missing:
            result['controller:'+name] = dict(status='unsupported', missing_bones=missing)
            continue
        p, _ = skin(g,probe)
        result['controller:'+name] = dict(status='finite', maximum_displacement=float(np.linalg.norm(p.vertices-g.vertices,axis=1).max()))
    return dict(poses=result, limitation='Analytical LBS finite-motion/seam diagnostics only. Without a source reference, finite poses do not establish anatomical or animation correctness.')


def inspect(source, output, max_bytes, resolution):
    """Run native reader, all models/textures, rest previews and pose diagnostics."""
    m = inspect_workspace(source, output, resolution=resolution)
    data = Path(source).read_bytes(); info = inspect_pac(data)
    errors = []
    if len({s['id'] for s in info['sections']})!=len(info['sections']):
        errors.append('Duplicate PAC section IDs are ambiguous.')
    for row in m['models']:
        if row['error']:errors.append(row['error'])
    errors += [t['error'] for t in m['textures'] if t['error']]
    # Unsupported preview/mapping/decoded streams must not produce a repair.
    errors += [f for f in m['findings'] if not f.startswith('Converter export-profile check:')]
    if len(data)>max_bytes:errors.append(f'PAC is {len(data)} bytes; configured budget is {max_bytes}.')
    models=[]
    for row in m['models']:
        if row['error']:continue
        try:
            native=audit_yobj((output/row['yobj']).read_bytes())
            for name_index,name in enumerate(native['texture_names']):
                choices=[t for t in m['textures'] if t['name'].casefold()==name.casefold()]
                main=[t for t in choices if t['section']==9]
                choices=main or choices
                if len(choices)!=1 or not choices[0].get('png'):continue
                capacity=choices[0]['palette_entries']
                expected={16:5,256:7}.get(capacity)
                for mesh in native['meshes']:
                    for mat in mesh['materials']:
                        if mat['texture_id']==name_index and mat['control'] not in (expected,expected|0x110):
                            errors.append(f'Section {row["section"]}, texture {name}: unsupported GIM/material depth controls.')
            models.append(dict(section=row['section'], audit=native['report'],
                               layout_review=layout_review(native), analytical=pose_checks(native)))
        except (ValueError,IndexError,struct.error,np.linalg.LinAlgError) as exc:
            errors.append(f"Section {row['section']} pose checks: {exc}")
    return dict(blocking_findings=errors, models=models, findings=m['findings'],
                aligned_sections=all(s['offset']%16==0 for s in info['sections']),
                aligned_file=len(data)%2048==0, bytes=len(data), sha256=digest(data),
                textures=len(m['textures']), manifest=str((output/'manifest.json').resolve()),
                converter_profile=m['converter_export_profile'])


def validate_pac(source, output, *, reference=None, repair=True, max_bytes=148000,
                 resolution=256, samples=4000, progress=lambda message:None):
    """Return QA report; emit repaired.pac ONLY after all supported checks pass.

    Optional HCTP reference invokes the existing full geometric/posed QA stage.
    Without it shape correctness is explicitly unknown. No anatomy is displaced.
    """
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():raise FileExistsError('Choose a new validation results folder.')
    if not isinstance(max_bytes,int) or max_bytes<=0:raise ValueError('Invalid PAC size budget.')
    if not 96<=resolution<=1024 or samples<2000:raise ValueError('QA requires resolution >=96 and samples >=2000.')
    data=source.read_bytes(); ref=Path(reference).resolve() if reference else None
    ref_data=ref.read_bytes() if ref else None
    output.mkdir(parents=True)
    publish_new(output/'original.pac',data)
    if ref:publish_new(output/'reference-hctp.pac',ref_data)
    report=dict(schema='psp-model-suite.pac-validation/1',source=str(source),
                original_sha256=digest(data),max_pac_bytes=max_bytes,repair_requested=bool(repair),
                repairs=[],repair_failures=[],repaired_pac=None,geometry_reference='provided' if ref else 'not provided',
                anatomy_status='unknown without original reference',game_compatibility='Requires PPSSPP testing.',
                report_path=str(output/'report.html'),input_unchanged=False)
    candidate=data
    try:
        progress('Validating native structures, textures and analytical poses')
        before=inspect(output/'original.pac',output/'before',max_bytes,resolution)
        report['before']=before
        if repair and not before['blocking_findings']:
            # Layout policy is a compatibility experiment, not a hardware limit.
            if not before['aligned_sections'] or not before['aligned_file']:
                try:
                    safe_repack(candidate)
                    aligned=replace_sections(candidate,{})
                    a,b=inspect_pac(candidate),inspect_pac(aligned)
                    if [(s['id'],s['sha256']) for s in a['sections']]!=[(s['id'],s['sha256']) for s in b['sections']]:
                        raise ValueError('Stored section payload changed during alignment.')
                    if len(aligned)>max_bytes:raise ValueError('Alignment repair exceeds configured budget.')
                    candidate=aligned
                    report['repairs'].append(dict(kind='PAC alignment',stored_sections_exact=True,
                        evidence='CONFIRMED payload preservation; conservative converter alignment convention, not a universal native restriction.'))
                except ValueError as exc:report['repair_failures'].append(str(exc))
            from desktop.skinning import apply_single_slot_compatibility
            one_slot=any(x['kind']=='unvalidated-small-skinned-palette' and x['weight_slots']==1 for m in before['models'] for x in m['layout_review'])
            if one_slot:
                try:
                    safe_repack(candidate)
                    adapted, evidence=apply_single_slot_compatibility(candidate,max_bytes=max_bytes)
                    if adapted!=candidate:
                        report['repairs'].append(dict(kind='single-slot rendering compatibility',evidence=evidence))
                        candidate=adapted
                except ValueError as exc:report['repair_failures'].append(str(exc))
        changed=candidate!=data
        # Candidate is private until validation and optional reference regression pass.
        private=output/'candidate-for-qa.pac'
        if changed:publish_new(private,candidate)
        after=inspect(private,output/'after',max_bytes,resolution) if changed else before
        report['after']=after
        reference_ok=True
        if ref and not before['blocking_findings']:
            from model_qa.pipeline import run
            progress('Running source-reference surface, silhouette, anatomy and posed QA')
            original_qa=run(output/'reference-hctp.pac',output/'original.pac',output/'reference-before',
                            samples=samples,resolution=resolution,progress=progress)
            final_qa=run(output/'reference-hctp.pac',private,output/'reference-after',samples=samples,
                         resolution=resolution,progress=progress) if changed else original_qa
            def flags(qa):
                return {(f['region'],f['pose'],f['kind'],f['severity']) for f in qa['flags'] if f['severity']!='insufficient-evidence'}
            added=flags(final_qa)-flags(original_qa)
            reference_ok=not added
            report['reference_qa']=dict(before='reference-before/report.html',
                after='reference-after/report.html' if changed else 'reference-before/report.html',
                before_findings=len(flags(original_qa)),after_findings=len(flags(final_qa)),
                new_findings=[list(v) for v in sorted(added)], regression_check_passed=reference_ok)
            report['anatomy_status']='review required' if flags(final_qa) else 'within provisional reference tolerances'
        if source.read_bytes()!=data or (ref and ref.read_bytes()!=ref_data):
            raise ValueError('Input changed during validation; repair withheld.')
        if changed and not after['blocking_findings'] and not report['repair_failures'] and reference_ok:
            publish_new(output/'repaired.pac',candidate)
            report['repaired_pac']=str(output/'repaired.pac')
            report['status']='repaired; game test required'
        elif before['blocking_findings'] or after['blocking_findings'] or report['repair_failures'] or not reference_ok:
            report['status']='review required; repair withheld'
        else:report['status']='no verified repair needed; game compatibility unverified'
        if private.exists():private.unlink()
    except Exception as exc:
        report['status']='review required; repair withheld'
        report['repair_failures'].append(str(exc))
        private=output/'candidate-for-qa.pac'
        if private.exists():private.unlink()
    report['input_unchanged']=source.read_bytes()==data and (ref is None or ref.read_bytes()==ref_data)
    report['limitations']=['No arbitrary geometry, UV, texture, material or weight edits.',
        'One-slot compatibility adds exact zero-weight slots; effective weights and all analytical poses must remain identical.',
        'Coincident vertices with distinct source weights are preserved; no averaging or welding.',
        'Unknown layouts, unsafe offsets, missing texture mappings and excessive budgets require human review.',
        'Reference QA is diagnostic. Existing PACs lack saved intermediate stages; root cause tracing and automatic anatomical corrections are unavailable.',
        'Analytical poses are not game animation clips. Full runtime memory and loader behavior remain unknown.']
    dump(output/'report.json',report)
    links=['<a href="before/manifest.json">Native audit and preview inventory</a>']
    if report.get('reference_qa'):
        links += [f'<a href="{report["reference_qa"][v]}">Reference {v} QA and renders</a>' for v in ('before','after')]
    if report['repaired_pac']:links.append('<a href="repaired.pac">Repaired PAC</a>')
    body='<html><head><meta charset="utf-8"><title>PAC validation</title></head><body><h1>PAC validation</h1>'
    body+='<p>'+html.escape(report['status'])+'</p><p>'+' · '.join(links)+'</p>'
    body+='<p>Original preserved as original.pac. Geometry correctness without a reference and in-game compatibility remain unverified.</p>'
    body+='<p><a href="report.json">Machine-readable report</a></p><pre>'+html.escape(json.dumps(report,indent=2))+'</pre></body></html>'
    (output/'report.html').write_text(body,encoding='utf-8')
    return report

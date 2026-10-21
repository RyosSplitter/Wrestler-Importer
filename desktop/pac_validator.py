"""Texture / Model / Full compatibility validation against a user's PSP base.

This is independent of HCTP anatomical comparison (source_reference_qa) and of
conversion. Donor shape, rigging, textures and opaque PAC sections are never copied.
"""
from desktop.limits import IN_RING_MAX_PAC_BYTES
from collections import defaultdict
import html
import json
from pathlib import Path
import struct

import numpy as np

from desktop import compatibility_validation as cv
from desktop.edit_folder import publish_new
from desktop.source_reference_qa import safe_repack, pose_checks
from desktop.workspace import digest, dump, inspect_workspace
from tools.pac_repack import replace_sections
from tools.psp_mesh_audit import audit_yobj

MODES={'Textures':'textures','Model':'model','Full':'full'}


def scope_report(inv,base_profile,mode,max_bytes,*,analytical=True):
    issues=dict(container=list(inv['errors']),textures=list(inv['table_errors']),model=[])
    if inv['info']['size']%2048 or any(s['offset']%16 for s in inv['info']['sections']):
        issues['container'].append('PAC wrapper differs from the established 16-byte/2048-byte export alignment convention.')
    if not inv['models'] and not inv['model_errors']:issues['model'].append('No PSP YOBJ model found.')
    issues['model'] += [f'Section {s}: {e}' for s,e in inv['model_errors'].items()]
    rows=[]
    for t in inv['textures']:
        record=dict(section=t['section'],name=t['name'],bytes=len(t['raw']),error=t['error'])
        if t['error']:issues['textures'].append(f"Texture {t['name']}: {t['error']}")
        else:
            p,c=t['pixels'],t['colors']
            record.update(width=p.shape[1],height=p.shape[0],palette_entries=len(c),
                          used_rgba_colors=len(np.unique(c[p].reshape(-1,4),axis=0)),alpha=bool((c[p][:,:,3]!=255).any()))
        rows.append(record)
    models=[]
    for section,m in inv['models'].items():
        record=dict(section=section,name=m['report']['model_name'],meshes=m['report']['meshes'],
            vertices=m['report']['vertices'],triangles=m['report']['triangles'],bones=len(m['bones']),
            skeleton_sha256=digest(m['bone_raw']),
            shared_base_bones=sorted(set(b['name'] for b in m['bones'])&set(base_profile['bone_names'])),
            policy='Counts/proportions and different valid bones are observations, not a donor-shape target.')
        for name in m['texture_names']:
            if cv.resolve(inv,name) is None:issues['textures'].append(f'Model section {section}: missing/ambiguous texture {name}.')
        for mesh in m['meshes']:
            for mat in mesh['materials']:
                t=cv.resolve(inv,m['texture_names'][mat['texture_id']]);bits=cv.texture_bits(t) if t else None
                if bits is None:continue
                expected=5 if bits==4 else 7
                if mat['control'] not in (expected,expected|0x110):
                    category='textures' if mode=='textures' and mat['control'] in (5,7,0x115,0x117) else 'model'
                    issues[category].append(f"Section {section} mesh {mesh['index']}: material {hex(mat['control'])} / {bits}-bit texture mismatch or unsupported rendering state.")
            if (not mesh['rigid'] and mesh['base_flag']==0x17ff and len(mesh['bone_palette'])==1
                    and any(n>1 for n in base_profile['float_weight_slots'])):
                issues['model'].append(f"Section {section} mesh {mesh['index']}: one-slot skinning differs from base-compatible layout convention.")
        if analytical and mode in ('model','full'):
            try:record['analytical']=pose_checks(m)
            except Exception as exc:issues['model'].append(f'Section {section}: analytical pose check failed: {exc}')
        models.append(record)
    return dict(issues=issues,models=models,textures=rows,
                checked=dict(container=True,textures=mode in ('textures','full'),model=mode in ('model','full')))


def app_check(path,output,resolution):
    """Exercise the actual app reader/exporter/renderer, not only a format probe."""
    try:
        manifest=inspect_workspace(path,output,resolution=resolution)
        ready=bool(manifest['models']) and all(not m['error'] and not m['preview_error'] and len(m['views'])==5 for m in manifest['models'])
        ready=ready and all(not t['error'] for t in manifest['textures'])
        # A completely alpha-hidden main model can generate five empty images.
        # Detect that provable case without guessing whether alpha was intended.
        inv=cv.inventory(Path(path).read_bytes());visibility={}
        for section,model in inv['models'].items():
            possible=False
            for mesh in model['meshes']:
                va=max((v['color'][3] for v in mesh['vertices']),default=0)
                for mat in mesh['materials']:
                    t=cv.resolve(inv,model['texture_names'][mat['texture_id']])
                    if t and t['pixels'] is not None and va*int(t['colors'][t['pixels']][:,:,3].max())>=255*255*.5:
                        possible=True
            visibility[str(section)]=possible
        main='2' if '2' in visibility else next(iter(visibility),None)
        if main is not None and not visibility[main]:
            ready=False
            manifest['findings'].append('Main model is fully hidden by the app alpha test; opacity intent cannot be inferred from a different wrestler base.')
        return dict(viewable=ready,manifest=str(output/'manifest.json'),models=manifest['models'],
                    visible_alpha_possible=visibility,
                    findings=manifest['findings'],
                    limitation='Actual app offline previews, not a PPSSPP/gameplay certification.')
    except Exception as exc:return dict(viewable=False,error=str(exc),models=[],findings=[str(exc)])


def checks_pass(report):
    return all(not report['issues'][name] for name,checked in report['checked'].items() if checked)


def materials_requirements(inv):
    required=defaultdict(set)
    for m in inv['models'].values():
        for mesh in m['meshes']:
            for mat in mesh['materials']:
                if mat['control'] not in (5,7,0x115,0x117):continue
                row=cv.resolve(inv,m['texture_names'][mat['texture_id']])
                if row:required[(row['section'],row['index'])].add(4 if (mat['control']&15)==5 else 8)
    return required


def preservation(before,after,original,final,mode):
    """Global payload and shape/rigging invariants, independent of issue counts."""
    if [s['id'] for s in before['info']['sections']]!=[s['id'] for s in after['info']['sections']]:raise ValueError('PAC section identity/order changed.')
    texture_sections={t['section'] for t in before['textures']}
    model_sections={s for s,r in before['decoded'].items() if r.startswith(b'YOBJ')}
    a={s['id']:original[s['offset']:s['offset']+s['size']] for s in before['info']['sections']}
    b={s['id']:final[s['offset']:s['offset']+s['size']] for s in after['info']['sections']}
    allowed=(texture_sections if mode=='textures' else model_sections if mode=='model' else texture_sections|model_sections)
    for s in a:
        if s not in allowed and a[s]!=b[s]:raise ValueError(f'Unselected or unrelated stored section {s} changed.')
    for s,m in before['models'].items():
        n=after['models'].get(s)
        if n is None:raise ValueError('Previously readable model became unreadable.')
        if m['bone_raw']!=n['bone_raw'] or m['texture_raw']!=n['texture_raw']:raise ValueError('Skeleton or material texture bindings changed.')
        if len(m['meshes'])!=len(n['meshes']):raise ValueError('Mesh structure changed.')
        for x,y in zip(m['meshes'],n['meshes']):
            if len(x['vertices'])!=len(y['vertices']):raise ValueError('Vertex count changed.')
            for p,q in zip(x['vertices'],y['vertices']):
                for name in ('position','normal','uv','color'):
                    if tuple(p[name])!=tuple(q[name]):raise ValueError('Geometry or vertex attributes changed: '+name)
                wa={bone:w for bone,w in zip(x['bone_palette'],p['weights']) if w}
                wb={bone:w for bone,w in zip(y['bone_palette'],q['weights']) if w}
                if wa!=wb:raise ValueError('Effective bone weights changed.')
            if [mat['triangles'] for mat in x['materials']]!=[mat['triangles'] for mat in y['materials']]:raise ValueError('Topology/winding changed.')
    return dict(unselected_stored_sections_exact=True,readable_input_geometry_attributes_topology_exact=True,
                skeleton_and_effective_weights_exact=True,donor_assets_copied=False,
                metadata_recovered_models='Only individually reported redundant metadata bytes may differ before the first successful strict audit.')


def validate_pac(source,output,*,base,mode='full',repair=True,max_bytes=IN_RING_MAX_PAC_BYTES,
                 resolution=256,samples=4000,progress=lambda message:None):
    """Repair selected compatibility domains, compare with a usable PSP base.

    Full: retain valid texture pixels/depth and adapt model rendering metadata.
    Textures: retain every model byte; convert texture layout/depth as required.
    Model: retain every stored texture section; repair model layout/metadata.
    """
    if mode not in MODES.values():raise ValueError('Choose textures, model or full validation.')
    if not isinstance(repair,bool):raise ValueError('repair must be a boolean.')
    if not isinstance(max_bytes,int) or isinstance(max_bytes,bool) or max_bytes<=0:raise ValueError('Invalid PAC byte budget.')
    if not 96<=resolution<=1024:raise ValueError('Preview resolution must be 96–1024.')
    source,base,output=Path(source).resolve(),Path(base).resolve(),Path(output).resolve()
    if output.exists():raise FileExistsError('Choose a new validation results folder.')
    data,base_data=source.read_bytes(),base.read_bytes()
    output.mkdir(parents=True);publish_new(output/'original.pac',data);publish_new(output/'base-psp.pac',base_data)
    report=dict(schema='psp-model-suite.pac-validation/2',source=str(source),base=str(base),mode=mode,
        original_sha256=digest(data),base_sha256=digest(base_data),max_pac_bytes=max_bytes,
        repair_requested=repair,repairs=[],repair_failures=[],repaired_pac=None,
        report_path=str(output/'report.html'),input_unchanged=False,base_unchanged=False,
        game_compatibility='Unverified; test repaired PACs in PPSSPP.',
        comparison_goal='Compatibility with app and PSP format conventions; do not match a different wrestler’s anatomy.')
    private=output/'candidate-for-qa.pac';candidate=data
    try:
        progress('Checking the PSP base and its actual app previews')
        base_inv,bp=cv.profile(base_data);report['base_profile']=bp
        report['base_app']=app_check(output/'base-psp.pac',output/'base-preview',resolution)
        if not report['base_app']['viewable']:raise ValueError('The selected PSP base cannot be previewed in the app; select a working PSP base PAC.')
        progress('Inspecting the input PAC and selected compatibility domains')
        before=cv.inventory(data)
        report['before']=scope_report(before,bp,mode,max_bytes)
        report['before']['bytes']=len(data)
        if len(data)>max_bytes:report['before']['issues']['container'].append(f'{len(data)} bytes exceeds configured {max_bytes}-byte target.')
        report['before']['app']=app_check(output/'original.pac',output/'before',resolution)
        changed_raw={};working=dict(before['decoded'])
        if repair:progress('Repairing recoverable '+mode+' compatibility issues')
        if repair and mode in ('model','full'):
            for s,raw in list(working.items()):
                if not raw.startswith(b'YOBJ'):continue
                try:
                    fixed,m,patches=cv.repair_model_metadata(raw)
                    if patches:report['repairs'].append(dict(kind='model metadata aliases',section=s,patches=patches,
                        scope='model',vertices_and_weights_untouched=True))
                    if fixed!=raw:working[s]=fixed;changed_raw[s]=fixed
                except Exception as exc:
                    report['repair_failures'].append(dict(scope='model',section=s,reason=str(exc)))
        # A fresh in-memory inventory lets valid recovered models define texture
        # bindings before packing; no intermediate file is exposed as output.
        models={}
        for s,r in working.items():
            if r.startswith(b'YOBJ'):
                try:models[s]=audit_yobj(r)
                except (ValueError,IndexError,struct.error):pass
        current=dict(before,models=models,decoded=working)
        if repair and mode in ('textures','full'):
            requirements=materials_requirements(current);tables=defaultdict(dict)
            for t in before['textures']:
                raw=t['raw'];fixed=raw;p,c=t['pixels'],t['colors'];evidence=[]
                try:
                    if t['error']:
                        fixed,p,c,proof=cv.recover_gim(raw);evidence.append(proof)
                    required=requirements[(t['section'],t['index'])]
                    if mode=='textures' and required:
                        if len(required)!=1:raise ValueError('One texture has incompatible material depth requirements; model validation is needed.')
                        desired=next(iter(required))
                        if len(c)!=(1<<desired):
                            fixed,proof=cv.convert_depth(fixed,p,c,desired);evidence.append(proof)
                    if fixed!=raw:
                        tables[t['section']][t['index']]=fixed
                        report['repairs'].append(dict(scope='textures',kind='texture compatibility',section=t['section'],name=t['name'],
                            old_bytes=len(raw),bytes=len(fixed),evidence=evidence))
                except Exception as exc:report['repair_failures'].append(dict(scope='textures',section=t['section'],texture=t['name'],reason=str(exc)))
            for s,images in tables.items():working[s]=cv.rebuild_table(working[s],images);changed_raw[s]=working[s]
            # Model mode/full reads actual final texture depth without altering
            # texture names or material IDs. Rebuild a decoded inventory view.
            current['textures']=[]
            for t in before['textures']:
                row=dict(t);image=tables.get(t['section'],{}).get(t['index'],t['raw']);row['raw']=image
                try:row['pixels'],row['colors']=cv.read_gim(image);row['error']=None
                except (ValueError,IndexError,struct.error):pass
                current['textures'].append(row)
        if repair and mode in ('model','full'):
            for s,m in models.items():
                raw=working[s]
                try:
                    fixed,edits=cv.patch_materials(raw,m,current,bp['material_controls'])
                    if edits:report['repairs'].append(dict(scope='model',kind='material/texture depth match',section=s,edits=edits))
                    fixed,m=audit_and_pair(fixed)
                    adapted,proof=cv.adapt_layout(fixed,m,bp['float_weight_slots'])
                    if proof:report['repairs'].append(dict(scope='model',kind='base-compatible skinning layout',section=s,evidence=proof))
                    aligned=cv.align_yobj_pof0(adapted)
                    if aligned!=adapted:report['repairs'].append(dict(scope='model',kind='POF0 padding',section=s,relocations_unchanged=True))
                    if aligned!=raw:working[s]=aligned;changed_raw[s]=aligned
                except Exception as exc:report['repair_failures'].append(dict(scope='model',section=s,reason=str(exc)))
        stored={s['id']:data[s['offset']:s['offset']+s['size']] for s in before['info']['sections']}
        donor_stored={s['id']:base_data[s['offset']:s['offset']+s['size']] for s in base_inv['info']['sections']}
        replacements={s:cv.encode_section(r,stored[s],donor_stored.get(s,b'')) for s,r in changed_raw.items()}
        # Oversized files can try lossless storage changes in selected domains,
        # but only where the base demonstrates BPE for the same payload role.
        if repair and len(data)>max_bytes:
            eligible=set(models) if mode=='model' else {t['section'] for t in before['textures']} if mode=='textures' else set(models)|{t['section'] for t in before['textures']}
            for s in eligible:
                if s not in replacements and donor_stored.get(s,b'').startswith(b'BPE ') and not stored[s].startswith(b'BPE '):
                    replacements[s]=cv.encode_section(working[s],stored[s],donor_stored[s])
                    report['repairs'].append(dict(scope='storage',kind='base-compatible lossless BPE storage',section=s,decoded_payload_exact=True))
        aligned=all(s['offset']%16==0 for s in before['info']['sections']) and len(data)%2048==0
        if replacements or (repair and not aligned):
            if aligned and all(len(r)==len(stored[s]) for s,r in replacements.items()):
                buf=bytearray(data)
                for s in before['info']['sections']:
                    if s['id'] in replacements:buf[s['offset']:s['offset']+s['size']]=replacements[s['id']]
                candidate=bytes(buf)
            else:
                safe_repack(data);candidate=replace_sections(data,replacements)
                if not aligned:report['repairs'].append(dict(scope='container',kind='PAC wrapper alignment',payloads_not_selected_for_repair_exact=True))
        changed=candidate!=data
        if changed:publish_new(private,candidate)
        progress('Rechecking preservation, size, allocation and app previews')
        final=cv.inventory(candidate);report['after']=scope_report(final,bp,mode,max_bytes)
        if final['decoded']!=working:raise ValueError('Serialized PAC differs from the checked replacement payloads.')
        def allocation(inv):
            total=0
            for t in inv['textures']:
                if t['error']:
                    try:cv.recover_gim(t['raw'])
                    except ValueError:continue
                total+=len(t['raw'])-208
            return total
        envelope=max(allocation(before),bp['pixel_clut_bytes'])
        report['texture_allocation']=dict(before=allocation(before),after=allocation(final),
            base=bp['pixel_clut_bytes'],repair_envelope=envelope,
            policy='Do not grow pixel/CLUT allocations beyond both input and usable PSP base. Observed reference envelope, not a hardware/engine heap limit.')
        if mode in ('textures','full') and allocation(final)>envelope:
            report['after']['issues']['textures'].append('Texture repair exceeds the input/base pixel and CLUT allocation envelope; try Model validation to correct material depth without expanding textures.')
        report['after']['bytes']=len(candidate)
        if len(candidate)>max_bytes:report['after']['issues']['container'].append(f'{len(candidate)} bytes exceeds configured {max_bytes}-byte target. No geometry or texture quality was reduced to fit.')
        report['preservation']=preservation(before,final,data,candidate,mode)
        report['after']['app']=app_check(private,output/'after',resolution) if changed else report['before']['app']
        selected=checks_pass(report['after'])
        # Full success requires the real app to render all model views too.
        if mode=='full' and not report['after']['app']['viewable']:
            report['after']['issues']['container'].append('Final PAC cannot produce all required app previews. See app findings.')
            selected=False
        if source.read_bytes()!=data or base.read_bytes()!=base_data:raise ValueError('Input or PSP base changed during validation; export withheld.')
        if selected and not report['repair_failures']:
            if changed:
                publish_new(output/'repaired.pac',candidate);report['repaired_pac']=str(output/'repaired.pac')
                report['status']='Selected validation passed; repaired copy saved.'
            else:report['status']='Selected validation passed; no changes needed.'
        else:report['status']='Selected validation incomplete; repair export withheld.'
        report['app_viewable']=report['after']['app']['viewable']
        report['selected_validation_passed']=selected and not report['repair_failures']
    except Exception as exc:
        report['status']='Validation incomplete; repair export withheld.'
        report['repair_failures'].append(dict(scope='validation',reason=str(exc)))
        report['selected_validation_passed']=False;report['app_viewable']=False
    finally:private.unlink(missing_ok=True)
    report['input_unchanged']=source.exists() and source.read_bytes()==data
    report['base_unchanged']=base.exists() and base.read_bytes()==base_data
    report['limitations']=['The base supplies compatibility conventions, never another wrestler’s shape, weights, textures or missing data.',
        'Texture-only validation preserves all stored YOBJ payloads; model-only preserves all stored texture payloads.',
        'Missing pixels, ambiguous texture names, invalid indices, corrupt weights and unsupported vertex formats require recovery/reconversion; they are not replaced or erased.',
        'Finite analytical poses do not establish game animation semantics. Anatomical source comparison remains a separate HCTP QA stage.',
        'An app preview is not proof of SVR 2011 loader/runtime-memory compatibility. Test edited PACs in PPSSPP.']
    dump(output/'report.json',report);write_html(report,output/'report.html',output)
    return report


def audit_and_pair(raw):
    return raw,audit_yobj(raw)


def write_html(report,path,root):
    e=html.escape
    body='<html><head><meta charset="utf-8"><title>PAC compatibility validation</title><style>body{font:15px Segoe UI,sans-serif;max-width:1100px;margin:24px auto;padding:15px} td,th{padding:8px;border:1px solid #ccc}table{border-collapse:collapse}pre{white-space:pre-wrap}img{max-width:240px}</style></head><body>'
    body+='<h1>'+e(report['mode'].title())+' validation</h1><p>'+e(report['status'])+'</p>'
    body+='<p>Input: '+e(Path(report['source']).name)+' · PSP base: '+e(Path(report['base']).name)+'</p>'
    body+='<p>App preview: '+('viewable' if report['app_viewable'] else 'incomplete / unavailable')+'. In-game compatibility still requires PPSSPP testing.</p>'
    if report['repaired_pac']:body+='<p><a href="repaired.pac">Repaired PAC</a></p>'
    body+='<table><tr><th>Check</th><th>Before</th><th>After</th></tr>'
    for name in ('container','textures','model'):
        body+='<tr><td>'+e(name.title())+'</td>'
        for stage in ('before','after'):
            r=report.get(stage,{})
            status=('Skipped' if not r.get('checked',{}).get(name) else ('Pass' if not r.get('issues',{}).get(name) else '; '.join(r['issues'][name])))
            body+='<td>'+e(status)+'</td>'
        body+='</tr>'
    body+='</table><h2>Changes</h2><ul>'+''.join('<li>'+e(r['kind'])+'</li>' for r in report['repairs'])+'</ul>'
    body+='<h2>App previews</h2>'
    for stage in ('before','after'):
        body+='<h3>'+stage.title()+'</h3>'
        for m in report.get(stage,{}).get('app',{}).get('models',[]):
            for view,image in m.get('views',{}).items():
                folder='after' if stage=='after' and (root/'after').exists() else 'before'
                body+='<a href="'+e(folder+'/'+image)+'"><img src="'+e(folder+'/'+image)+'" alt="'+e(view)+'"></a>'
    body+='<h2>Details and unresolved checks</h2><a href="report.json">JSON report</a><pre>'+e(json.dumps(report,indent=2))+'</pre></body></html>'
    Path(path).write_text(body,encoding='utf-8')

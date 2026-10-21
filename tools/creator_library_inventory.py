"""Read-only creator library study. Does not enable new app formats or write PACs.

python -m tools.creator_library_inventory --folder USER_FOLDER --reference Kenny.PAC --output NEW_FOLDER --previews
Multi-descriptor previews are explicitly diagnostic; the production auditor and
creator importer retain their existing policies. No repaired model is exported.
"""
from desktop.limits import IN_RING_MAX_PAC_BYTES
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

from desktop.texture_optimizer.candidates import read_gim
from model_creator.core import compatible, load_source, preview
from tools.pac_inspect import parse_textures
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.weight_trial_review import descendant_names


def sha(data):return hashlib.sha256(data).hexdigest()


def read_for_study(raw):
    """Return ordinary audit, or clearly labeled geometry-only diagnostics.

    Six supplied files have two named descriptor records whose mesh counts sum
    to the global count. To inspect their other buffers using the unchanged
    single-descriptor auditor, modify only an IN-MEMORY copy of that one count.
    This is not an audit of the unmodified descriptor array or a writer adapter.
    """
    try:model=audit_yobj(raw);ordinary_error=None
    except ValueError as exc:model=None;ordinary_error=str(exc)
    count=struct.unpack_from('<I',raw,52)[0];start=8+struct.unpack_from('<I',raw,48)[0]
    end=8+struct.unpack_from('<I',raw,4)[0];meshes=struct.unpack_from('<I',raw,24)[0]
    # Original generated conformance vectors leave word 52 zero, while the
    # ordinary reader still establishes one complete descriptor. Do not turn an
    # observed native convention into a new hard validity rule.
    effective=1 if count==0 and model is not None else count
    if not 1<=effective<=16 or start<72 or start+32*effective>end:raise ValueError('Unsupported descriptor array bounds.')
    records=[]
    for i in range(effective):
        a=start+i*32
        records.append(dict(name=raw[a:a+16].split(b'\0')[0].decode('ascii'),
                            words_16_20_24_28=list(struct.unpack_from('<4I',raw,a+16))))
    details=dict(count_at_header_52=count,records=records,global_mesh_count=meshes,
                 mesh_count_sum=sum(r['words_16_20_24_28'][2] for r in records))
    if model is not None:details['ordinary_audit_passed']=True
    else:
        details.update(ordinary_audit_passed=False,ordinary_audit_error=ordinary_error)
        if ordinary_error!='Secondary descriptor mesh count disagrees' or count<2 or details['mesh_count_sum']!=meshes:
            raise ValueError(ordinary_error)
        if any(r['words_16_20_24_28'][:2]!=[1,0] or r['words_16_20_24_28'][3]!=0 or not 1<=r['words_16_20_24_28'][2]<=meshes for r in records):
            raise ValueError('Descriptor pattern differs from the studied six-file pattern.')
        adjusted=bytearray(raw);struct.pack_into('<I',adjusted,start+24,meshes)
        model=audit_yobj(bytes(adjusted))
        details['diagnostic_only']='First descriptor count overridden IN MEMORY to reuse the existing auditor. Other buffers checked; source descriptors remain unsupported for rewriting. No PAC or YOBJ exported.'
        offset=0
        for record in records:
            length=record['words_16_20_24_28'][2]
            record['inferred_contiguous_group_textures']=sorted({model['texture_names'][mat['texture_id']]
                for mesh in model['meshes'][offset:offset+length] for mat in mesh['materials']})
            offset+=length
    return model,details


def body_comparison(reference,model):
    ref={b['name']:b for b in reference['bones']};bones={b['name']:b for b in model['bones']}
    refbody=set(ref)-descendant_names(reference,'atama');body=set(bones)-descendant_names(model,'atama')
    differences=[]
    for name in sorted(refbody&set(bones)):
        a,b=ref[name],bones[name]
        parent=lambda m,b:None if b['parent']==-1 else m['bones'][b['parent']]['name']
        position=float(np.max(np.abs(np.array(a['local_position'])-b['local_position'])))
        rotation=float(np.max(np.abs(np.array(a['rotation'])-b['rotation'])))
        if position>1e-5 or rotation>1e-5 or parent(reference,a)!=parent(model,b):
            differences.append(dict(bone=name,position_delta=position,rotation_delta=rotation,
                                    parent_matches=parent(reference,a)==parent(model,b)))
    active=Counter()
    for mesh in model['meshes']:
        for v in mesh['vertices']:
            for bone,weight in zip(mesh['bone_palette'],v['weights']):
                if weight>0:active[model['bones'][bone]['name']]+=1
    try:compatible(dict(model=reference),dict(model=model));strict=True;reason=None
    except ValueError as exc:strict=False;reason=str(exc)
    return dict(common_named_body_bind_matches=not differences,tolerance=1e-5,
                differences=differences,missing_reference_body_bones=sorted(refbody-set(bones)),
                extra_nonfacial_bones=[dict(name=n,parent=None if bones[n]['parent']==-1 else model['bones'][bones[n]['parent']]['name'],
                    weighted_vertex_records=active[n]) for n in sorted(body-refbody)],
                strict_full_rig_gate_matches=strict,strict_gate_reason=reason,
                meaning='A common-bind match is a candidate classification, not seam, face-controller or game compatibility approval.')


def scan(folder,output,reference=None,previews=False):
    folder,output=Path(folder).resolve(),Path(output)
    if not folder.is_dir():raise ValueError('Choose a PAC library directory.')
    if output.exists():raise FileExistsError('Choose a new report directory.')
    paths=sorted((p for p in folder.rglob('*') if p.is_file() and p.suffix.casefold()=='.pac'),key=lambda p:p.relative_to(folder).as_posix().casefold())
    if not paths:raise ValueError('No PAC files found.')
    ref=load_source(reference) if reference else None
    output.mkdir(parents=True);rows=[]
    for number,path in enumerate(paths):
        if path.is_symlink():raise ValueError('Library scan does not follow file symlinks.')
        data=path.read_bytes();row=dict(index=number,file=path.relative_to(folder).as_posix(),sha256=sha(data),pac_bytes=len(data),
            under_current_export_target=len(data)<=IN_RING_MAX_PAC_BYTES,models=[],texture_tables=[],nested_pacs=[],errors=[],creator_import_passed=False)
        try:
            entries=list(sections(data));row['sections']=[dict(id=s['id'],stored_bytes=s['size'],decoded_bytes=len(raw)) for s,raw in entries]
            decoded={s['id']:raw for s,raw in entries};model=None
            for sec,raw in entries:
                if raw.startswith(b'YOBJ'):
                    m,descriptor=read_for_study(raw);r=m['report']
                    item=dict(section=sec['id'],descriptors=descriptor,bones=len(m['bones']),
                              **{k:r[k] for k in ('meshes','vertices','triangles','material_records')})
                    if sec['id']==2:
                        model=m
                        if ref:item['reference_body']=body_comparison(ref['model'],m)
                    row['models'].append(item)
                elif raw.startswith(b'PAC '):
                    row['nested_pacs'].append(dict(section=sec['id'],children=[dict(id=s['id'],decoded_bytes=len(r),signature=r[:4].decode('ascii',errors='replace')) for s,r in sections(raw)]))
                elif len(raw)>=16 and raw[4:16]==struct.pack('<3I',256,0,16):
                    textures=[]
                    for t in parse_textures(raw):
                        blob=raw[t['offset']:t['offset']+t['size']]
                        record=dict(name=t['name'],bytes=len(blob),sha256=sha(blob))
                        try:
                            p,c=read_gim(blob);record.update(width=p.shape[1],height=p.shape[0],bits=4 if len(c)==16 else 8,
                                pixel_clut_bytes=len(blob)-208,alpha=bool(np.any(c[p][:,:,3]!=255)))
                        except ValueError as exc:record['error']=str(exc)
                        textures.append(record)
                    row['texture_tables'].append(dict(section=sec['id'],textures=textures))
            try:load_source(path);row['creator_import_passed']=True
            except ValueError as exc:row['creator_import_error']=str(exc)
            if previews and model is not None and 9 in decoded:
                table=decoded[9];g={t['name'].casefold():table[t['offset']:t['offset']+t['size']] for t in parse_textures(table)}
                textures={n:g[n.casefold()] for n in model['texture_names']};viewpaths={}
                for view in ('front','back'):
                    name=f'{number:03d}-{view}.png';preview(model,textures,view,320).save(output/name);viewpaths[view]=name
                row['previews']=viewpaths
        except (ValueError,IndexError,KeyError,struct.error,UnicodeError) as exc:row['errors'].append(str(exc))
        row['input_unchanged']=sha(path.read_bytes())==row['sha256']
        if not row['input_unchanged']:raise ValueError('Input changed during inventory: '+str(path))
        rows.append(row)
    textures=[t for r in rows for table in r['texture_tables'] for t in table['textures']]
    report=dict(schema='psp-model-creator.library-inventory/1',reference_sha256=None if ref is None else ref['sha256'],
        files=len(rows),originals_unchanged=all(r['input_unchanged'] for r in rows),
        creator_import_passed=sum(r['creator_import_passed'] for r in rows),
        texture_entries=len(textures),texture_decode_errors=sum('error' in t for t in textures),
        pac_rewrites=0,app_changes=0,gameplay_validation=False,pacs=rows)
    (output/'inventory.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    with (output/'inventory.csv').open('w',encoding='utf-8',newline='') as f:
        columns=['file','pac_bytes','creator_import_passed','creator_import_error','input_unchanged'];writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--reference',type=Path);p.add_argument('--previews',action='store_true');a=p.parse_args()
    r=scan(a.folder,a.output,a.reference,a.previews)
    print(json.dumps({k:v for k,v in r.items() if k!='pacs'},indent=2))

"""Separate lossless texture-storage trial, never a production packaging edit.

Consumes the withheld texture configuration's report/preview, rebuilds it using
the frozen model set, then compresses ONLY the decoded, named GIM table in 8.
All geometry, model bytes, rigging and every decoded section remain identical.
"""
import argparse
import json
from pathlib import Path

from desktop.core import validate_pac
from tools.pac_inspect import inspect_pac,parse_textures
from tools.pac_repack import replace_sections
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress,decompress
from .frozen import FrozenPac,digest
from .trial import save_candidate
from .metrics import encode
from app.ps2_textures import read_source


def lossless_table_trial(frozen,gims):
    before,report=frozen.build(gims)
    by_id={s['id']:(s,r) for s,r in sections(before)}
    info,raw=by_id[8]
    # Only a fully parsed texture table is eligible; never compress an unknown
    # animation/event payload under an inferred role.
    entries=parse_textures(raw)
    for entry in entries:
        if entry['extension']!='gim':raise ValueError('Retained section 8 is not exclusively GIM textures')
    packed=compress(raw)
    if decompress(packed)!=raw:raise ValueError('Lossless retained-table roundtrip failed')
    after=replace_sections(before,{8:packed})
    validate_pac(after,max_bytes=max(frozen.max_bytes,len(after)))
    rebuilt={s['id']:(s,r) for s,r in sections(after)}
    if set(by_id)!=set(rebuilt):raise ValueError('PAC section set changed')
    for i,(s,r) in by_id.items():
        if rebuilt[i][1]!=r:raise ValueError('Decoded section changed: '+str(i))
        if i!=8 and rebuilt[i][0]['sha256']!=s['sha256']:raise ValueError('Unrelated stored section changed: '+str(i))
    proof=dict(section=8,decoded_sha256=digest(raw),decoded_bytes=len(raw),
               stored_before_bytes=info['size'],stored_after_bytes=len(packed),stored_savings_bytes=info['size']-len(packed),
               exact_decoded_bytes_preserved=True,texture_names=[e['name'] for e in entries],
               baseline_geometry_model_and_rig_stored_bytes_preserved=all(rebuilt[i][0]['sha256']==frozen.sections[i][0]['sha256'] for i in frozen.models),
               native_precedent='Supplied SVR 2011 references use BPE-compressed section 8 named GIM tables; this exact combined candidate still needs PPSSPP testing')
    report.update(pac_bytes=len(after),sha256=digest(after),pac_budget_pass=len(after)<=frozen.max_bytes,
                  export_eligible=len(after)<=frozen.max_bytes and report['texture_observed_envelope_pass'],
                  retained_table_lossless_storage=proof)
    return after,report


def finish(frozen,gims,entries,after,result,output,label,input_hash=None):
    # Generate a matching preview first through the exact same frozen model set.
    report=save_candidate(output,label,frozen,gims,entries)
    folder=output/report['label'];report.update(result)
    if not report['export_eligible']:raise ValueError('Lossless storage candidate is not export eligible')
    filename='Rock-'+label+'-EXPERIMENTAL.pac'
    (folder/filename).write_bytes(after);(folder/(filename+'.sha256')).write_text(report['sha256']+'  '+filename+'\n')
    marker=folder/'NOT-FOR-INJECTION.txt'
    if marker.exists():marker.unlink()
    report.update(pac_file=filename,experiment_scope='Separate lossless storage factor: section 8 compression added to an aspect-preserving, existing-cranial-depth configuration. This factor was NOT applied to trials 01–07.',
                  input_configuration_sha256=input_hash)
    (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('pac_bytes','sha256','texture_section_stored_bytes','texture_pixel_palette_bytes','export_eligible','mean_ssim','retained_table_lossless_storage')},indent=2),flush=True)
    return report


def run(baseline,configuration,output):
    output.mkdir(parents=True,exist_ok=False)
    config=json.loads((configuration/'report.json').read_text())
    frozen=FrozenPac(baseline.read_bytes());gims={n:(configuration/'preview'/(n+'.gim')).read_bytes() for n in frozen.names}
    before,check=frozen.build(gims)
    if check['sha256']!=config['sha256']:raise ValueError('Withheld configuration reconstruction differs')
    after,result=lossless_table_trial(frozen,gims)
    return finish(frozen,gims,config['textures'],after,result,output,'08-face8-lossless-texture-storage',config['sha256'])


def run_search(source,baseline,search,output):
    """Re-evaluate already proposed configurations under the separate factor.

    Retains the baseline pixel/CLUT total as an additional conservative guard.
    """
    output.mkdir(parents=True,exist_ok=False);trace=json.loads(search.read_text())
    frozen=FrozenPac(baseline.read_bytes())
    if trace['source_sha256']!=digest(source.read_bytes()) or trace['baseline_sha256']!=digest(baseline.read_bytes()):raise ValueError('Input hashes differ from search')
    options=json.loads((search.parent/'options.json').read_text())['textures']
    rgba={n:p for i,n,r,p,d in read_source(source,texture_names=frozen.names)}
    _,baseline_report=frozen.build(frozen.gims);memory_cap=baseline_report['texture_pixel_palette_bytes']
    cache={};records=[];best=None
    for evaluation in trace['evaluations']:
        if not evaluation.get('aspect_ratio_pass'):continue
        entries=[rows[i] for rows,i in zip(options,evaluation['selection'])];gims={}
        for entry in entries:
            name=entry['name'];key=(name,entry['width'],entry['height'],entry['bits'],entry['quantizer'])
            if key not in cache:
                if entry['quantizer']=='Existing baseline':cache[key]=frozen.gims[name]
                else:cache[key]=encode(rgba[name],(entry['width'],entry['height']),entry['bits'])[0]
            gims[name]=cache[key]
        after,report=lossless_table_trial(frozen,gims)
        loss=evaluation['weighted_loss'];safe=report['export_eligible'] and report['texture_pixel_palette_bytes']<=memory_cap
        records.append(dict(selection=evaluation['selection'],weighted_loss=loss,pac_bytes=report['pac_bytes'],texture_section_stored_bytes=report['texture_section_stored_bytes'],texture_pixel_palette_bytes=report['texture_pixel_palette_bytes'],baseline_texture_memory_guard=report['texture_pixel_palette_bytes']<=memory_cap,export_eligible=safe))
        if safe and (best is None or (loss,report['pac_bytes'])<best[:2]):best=(loss,report['pac_bytes'],gims,entries,after,report)
    if best is None:raise ValueError('No measured configuration fits the storage and baseline texture-data guards')
    loss,size,gims,entries,after,report=best
    report.update(weighted_loss=loss,storage_search_measured_combinations=len(records),baseline_texture_memory_bytes=memory_cap,
                  baseline_texture_memory_guard=True,search_scope='Best measured preserved-depth proposal after separate lossless texture-table storage; not an exhaustive global search')
    final=finish(frozen,gims,entries,after,report,output,'09-adaptive-face8-storage-search')
    (output/'lossless-search.json').write_text(json.dumps(dict(source_sha256=trace['source_sha256'],baseline_sha256=trace['baseline_sha256'],evaluations=records,best=final),indent=2)+'\n')
    return final


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path)
    g=p.add_mutually_exclusive_group(required=True);g.add_argument('--configuration',type=Path);g.add_argument('--search',type=Path)
    a=p.parse_args()
    if a.search:
        if not a.source:p.error('--source is required with --search')
        run_search(a.source,a.baseline,a.search,a.output)
    else:run(a.baseline,a.configuration,a.output)

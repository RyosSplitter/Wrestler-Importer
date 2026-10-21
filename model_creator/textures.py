"""Creator adapter for the established texture-only Maximum Downgrade search."""
from desktop.limits import IN_RING_MAX_PAC_BYTES
import hashlib
import html
import json
from pathlib import Path

import numpy as np
from PIL import Image

from desktop.maximum_downgrade import candidates
from desktop.texture_optimizer.analysis import analyze, measure
from desktop.texture_optimizer.candidates import read_gim
from tools.pac_inspect import inspect_pac, parse_textures
from tools.pac_repack import replace_sections, texture_table
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress
from .native import audit_yobj


def validate_native(data, *, max_bytes, gim_reader=read_gim):
    info=inspect_pac(data)
    if len(data)>max_bytes or len(data)%2048:raise ValueError('Creator PAC size/alignment invalid')
    decoded={s['id']:raw for s,raw in sections(data)}
    if len(decoded)!=len(info['sections']):raise ValueError('Duplicate PAC sections')
    models=[audit_yobj(raw) for raw in decoded.values() if raw.startswith(b'YOBJ')]
    records=parse_textures(decoded[9]);gims={}
    for row in records:
        name=row['name'].casefold()
        if name in gims:raise ValueError('Ambiguous native texture dependency')
        raw=decoded[9][row['offset']:row['offset']+row['size']];gim_reader(raw);gims[name]=raw
    for model in models:
        if any(name.casefold() not in gims for name in model['texture_names']):raise ValueError('Missing model texture')
    return info


def fit_textures(pac, output, *, target=IN_RING_MAX_PAC_BYTES, progress=lambda _:None):
    """Retain best texture rescue with warning if fixed geometry cannot fit.

    The fitter proves non-texture stored payload identity, fixed bit depths,
    no upscaling, no runtime texture-allocation increase and sampled cutout alpha.
    Its ordinary converter path keeps its previous strict default behavior.
    """
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    validate_native(pac,max_bytes=max(target,len(pac)))
    before={s['id']:(s,raw) for s,raw in sections(pac)};table=before[9][1];entries=parse_textures(table)
    names=[r['name'] for r in entries];originals=[table[r['offset']:r['offset']+r['size']] for r in entries]
    rows=[];importance=[]
    if len(pac)>target:
        from desktop.source_reference_qa import safe_repack
        safe_repack(pac)
    for name,raw in zip(names,originals):
        p,c=read_gim(raw);features=analyze(c[p]);importance.append(features)
        if len(pac)>target:
            progress('Preparing maximum texture candidates: '+name);options=candidates(raw)
            for row in options:row['individual_bpe_bytes']=len(compress(row['raw'],max_distinct=220))
        else:
            options=[dict(raw=raw,dimensions=list(p.shape[1::-1]),bits=4 if len(c)==16 else 8,
                palette_entries=len(c),encoded_bytes=len(raw),pixel_palette_bytes=len(raw)-208,
                useful_colors=len(np.unique(c[p].reshape(-1,4),axis=0)),metrics=measure(c[p],c[p]),alpha_sampled_exact=True)]
        rows.append(options)
    decisions=[];cache={tuple([0]*len(rows)):(pac,before[9][0]['size'])}
    tested=[]
    def evaluate(selection,reason):
        selection=tuple(selection)
        if selection not in cache:
            table=texture_table(names,[rows[i][j]['raw'] for i,j in enumerate(selection)],gim_reader=read_gim)
            payload=min((replace_sections(pac,{9:compress(table,max_distinct=n)}) for n in (200,220)),key=len)
            cache[selection]=(payload,next(s['size'] for s in inspect_pac(payload)['sections'] if s['id']==9))
        payload,stored=cache[selection]
        quality=sum(importance[i]['importance_score']*rows[i][j]['metrics']['perceptual_loss'] for i,j in enumerate(selection))
        result=(selection,payload,stored,quality);tested.append(result)
        decisions.append(dict(reason=reason,pac_bytes=len(payload),stored_texture_bytes=stored,weighted_perceptual_loss=quality,selected_candidates=selection))
        progress('Maximum texture fitting: tested %s / %s bytes'%(len(payload),target))
        return result
    selected=tuple([0]*len(rows));final=pac;stored=before[9][0]['size']
    if len(pac)>target:
        evaluate(selected,'Original textures')
        minimum=[min(range(len(options)),key=lambda j:(options[j]['individual_bpe_bytes'],options[j]['metrics']['perceptual_loss'],j)) for options in rows]
        evaluate(minimum,'Smallest individually compressed legal textures; actual whole PAC measured')
        fixed=sum(s['size'] for i,(s,raw) in before.items() if i!=9)
        if fixed<=target:
            # Lagrange batches avoid recompressing the entire PAC separately
            # for every tiny per-map upgrade. Estimates only propose states;
            # every eligible result is measured with the real table/PAC writer.
            def proposal(penalty):
                return [min(range(len(options)),key=lambda j:(
                    importance[i]['importance_score']*options[j]['metrics']['perceptual_loss']+
                    penalty*options[j]['individual_bpe_bytes']/max(1,options[0]['individual_bpe_bytes']),
                    options[j]['metrics']['perceptual_loss'],j)) for i,options in enumerate(rows)]
            low=0.;high=.01;found=False
            for _ in range(12):
                result=evaluate(proposal(high),'Batch quality/byte tradeoff '+str(high))
                if len(result[1])<=target:found=True;break
                low=high;high*=2
            if found:
                for _ in range(8):
                    mid=(low+high)/2;result=evaluate(proposal(mid),'Refine fitting batch '+str(mid))
                    if len(result[1])<=target:high=mid
                    else:low=mid
        fitting=[r for r in tested if len(r[1])<=target]
        result=min(fitting,key=lambda r:(r[3],len(r[1]),r[0])) if fitting else min(tested,key=lambda r:(len(r[1]),r[3],r[0]))
        if fitting:
            # Spend spare blocks on a bounded set of the best detail upgrades.
            # This also explores non-convex one-map choices skipped by batches.
            for _ in range(2):
                current=result[0];upgrades=[]
                for i,options in enumerate(rows):
                    incumbent=options[current[i]]
                    for j,row in enumerate(options):
                        gain=importance[i]['importance_score']*(incumbent['metrics']['perceptual_loss']-row['metrics']['perceptual_loss'])
                        if gain<=1e-12:continue
                        extra=max(1,row['individual_bpe_bytes']-incumbent['individual_bpe_bytes'])
                        upgrades.append((-gain/extra,-gain,i,j))
                probes=sorted(upgrades)[:6]
                old_quality=result[3]
                for _,_,i,j in probes:
                    selection=list(current);selection[i]=j;evaluate(selection,'Restore source detail within spare actual PAC budget')
                fitting=[r for r in tested if len(r[1])<=target]
                result=min(fitting,key=lambda r:(r[3],len(r[1]),r[0]))
                if result[3]>=old_quality-1e-12:break
        selected,final,stored,_=result
    if len(final)>len(pac):raise ValueError('Texture rescue increased actual PAC size')
    after={s['id']:(s,raw) for s,raw in sections(final)}
    if list(before)!=list(after):raise ValueError('Texture fitting changed PAC section identity/order')
    for section,(s,raw) in before.items():
        if section!=9 and (after[section][0]['sha256']!=s['sha256'] or after[section][1]!=raw):raise ValueError('Texture fitting changed a non-texture payload')
    final_images=[rows[i][j]['raw'] for i,j in enumerate(selected)]
    memory=sum(len(raw)-208 for raw in final_images);initial_memory=sum(len(raw)-208 for raw in originals)
    if memory>initial_memory:raise ValueError('Texture fitting increased runtime texture allocation')
    validate_native(final,max_bytes=max(target,len(final)))
    report=dict(mode='Maximum Texture Downgrade',baseline_bytes=len(pac),pac_bytes=len(final),target=target,
        within_budget=len(final)<=target,over_by_bytes=max(0,len(final)-target),stored_texture_bytes=stored,
        texture_pixel_palette_budget=initial_memory,final_texture_pixel_palette_bytes=memory,
        unchanged_non_texture_payloads=True,structural_validation='passed',export_eligible=True,
        search='Bounded deterministic batch quality/byte search; real serialization per state; best tested result, not a global optimum',
        decisions=decisions,textures=[],changed_textures=sum(a!=b for a,b in zip(originals,final_images)),
        remaining_bytes=target-len(final),gameplay_validation='pending',sha256=hashlib.sha256(final).hexdigest())
    body=['<html><meta charset="utf-8"><h1>Maximum texture downgrade</h1>',f'<p>PAC: {len(pac):,} → {len(final):,} / {target:,} bytes. Geometry and all non-texture stored payloads unchanged.</p>']
    for i,(name,options,j) in enumerate(zip(names,rows,selected)):
        choice=options[j];public=lambda r:{k:v for k,v in r.items() if k!='raw'}
        report['textures'].append(dict(name=name,baseline_dimensions=options[0]['dimensions'],importance=importance[i],
            candidates=[public(row) for row in options],selected_candidate=j,selected=public(choice),changed=originals[i]!=final_images[i]))
        body.append('<h2>'+html.escape(name)+'</h2><p>'+str(options[0]['dimensions'])+' → '+str(choice['dimensions'])+'</p>')
        for prefix,raw in (('original',originals[i]),('final',final_images[i])):
            p,c=read_gim(raw);filename=f'{prefix}-{i:03d}.png';Image.fromarray(c[p]).save(output/filename)
            body.append(f'<img width="192" src="{filename}" alt="{prefix}">')
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (output/'report.html').write_text('\n'.join(body)+'</html>',encoding='utf-8')
    model=audit_yobj(after[2][1]);gims=dict(zip((n.casefold() for n in names),final_images))
    textures={n:gims[n.casefold()] for n in model['texture_names']}
    return final,report,textures

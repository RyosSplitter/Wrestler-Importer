"""Explicit last-resort texture fitting over immutable model/PAC payloads.

No new GIM bit-depth/material contracts. Native-observed dimensions may go below
64; fixed CLUT capacities remain overhead even when fewer colors are useful.
This is a deterministic greedy search, not a global optimum or game certificate.
"""
import hashlib
import html
import json
from pathlib import Path

import numpy as np
from PIL import Image

from desktop.texture_optimizer.analysis import analyze, measure
from desktop.texture_optimizer.candidates import read_gim, write_gim, OBSERVED_DIMENSIONS, OBSERVED_T8_DIMENSIONS
from tools.pac_inspect import parse_textures, inspect_pac
from tools.pac_repack import replace_sections, texture_table
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress


def candidates(raw, cancel=lambda:None):
    """Reduce the Default image; preserve nearest-sampled alpha exactly.

    RGB is filtered separately per alpha level to avoid padding color bleed.
    A cutout cannot vanish entirely in a candidate. All selected alpha values
    come from the incumbent; no opaque flattening or new alpha level is allowed.
    """
    p,c=read_gim(raw);image=c[p];h,w=p.shape;bits=4 if len(c)==16 else 8
    loss=lambda rgba:measure(image,rgba)
    rows=[dict(raw=raw,dimensions=[w,h],useful_colors=len(np.unique(image.reshape(-1,4),axis=0)),
               metrics=loss(image),sampling='Exact incumbent',alpha_sampled_exact=True)]
    native=OBSERVED_DIMENSIONS if bits==4 else OBSERVED_T8_DIMENSIONS
    sizes=sorted({(w,h)}|{s for s in native if s[0]<=w and s[1]<=h},key=lambda s:(s[0]*s[1],s))
    seen={raw}
    for size in sizes:
        cancel()
        alpha=np.asarray(Image.fromarray(image[:,:,3]).resize(size,Image.Resampling.NEAREST))
        if np.any(image[:,:,3]<128) and np.any(image[:,:,3]>=128) and (np.all(alpha<128) or np.all(alpha>=128)):
            continue  # Keep both sides of a real cutout represented.
        levels,counts=np.unique(alpha,return_counts=True)
        # Premultiplied per-level filtering prevents transparent RGB bleeding.
        rgb=np.zeros((*alpha.shape,3),np.uint8)
        for level in levels:
            if level==0:continue
            occupied=image[:,:,3]==level
            support=np.asarray(Image.fromarray(occupied.astype(np.float32)).resize(size,Image.Resampling.LANCZOS))
            for axis in range(3):
                values=image[:,:,axis].astype(np.float32)*occupied
                filtered=np.asarray(Image.fromarray(values).resize(size,Image.Resampling.LANCZOS))
                rgb[:,:,axis][alpha==level]=np.clip(np.rint(filtered[alpha==level]/np.maximum(support[alpha==level],1e-6)),0,255).astype(np.uint8)
        for limit in sorted({1,2,4,8,16,1<<bits}):
            if limit<len(levels):continue
            cancel();allocation=np.ones(len(levels),int)
            useful=len(np.unique(image.reshape(-1,4),axis=0))
            capacity=min(limit,useful,1<<bits)
            if capacity<len(levels):continue
            for _ in range(capacity-len(levels)):
                visible=[i for i,v in enumerate(levels) if v>0]
                if not visible:break
                j=max(visible,key=lambda i:counts[i]/(allocation[i]+1));allocation[j]+=1
            index=np.zeros(alpha.shape,np.uint8);palette=np.zeros((1<<bits,4),np.uint8);offset=0
            for level,slots in zip(levels,allocation):
                take=alpha==level
                if level==0:
                    index[take]=offset;offset+=1;continue
                values=rgb[take]
                q=Image.fromarray(values[None,:,:]).quantize(colors=int(slots),method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
                entries=np.asarray(q.getpalette(),np.uint8).reshape(-1,3);used=int(np.asarray(q).max())+1
                palette[offset:offset+used,:3]=entries[:used];palette[offset:offset+used,3]=level
                index[take]=np.asarray(q).reshape(-1)+offset;offset+=used
            try:payload=write_gim(index,palette,bits)
            except ValueError:continue  # Exact incumbent dimensions can be absent from corpus.
            if payload in seen:continue
            seen.add(payload);rgba=palette[index]
            if not np.array_equal(rgba[:,:,3],alpha):raise ValueError('Maximum downgrade changed sampled alpha.')
            colors=len(np.unique(rgba.reshape(-1,4),axis=0))
            if colors>useful:raise ValueError('Maximum downgrade exceeded incumbent color capacity.')
            rows.append(dict(raw=payload,dimensions=list(size),useful_colors=colors,
                metrics=loss(rgba),sampling='Per-alpha Lanczos RGB; nearest alpha; median-cut RGB palette',alpha_sampled_exact=True))
    for row in rows:
        row.update(bits=bits,palette_entries=1<<bits,encoded_bytes=len(row['raw']),
                   pixel_palette_bytes=len(row['raw'])-208,
                   aspect_preserved=row['dimensions'][0]*h==row['dimensions'][1]*w)
    return rows


def fit_pac(baseline, output, *, target=148000, cancel=lambda:None, progress=lambda message:None):
    """Fit by actual stored table costs; never edit anything outside section 9."""
    cancel()
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    before={s['id']:(s,raw) for s,raw in sections(baseline)}
    records=parse_textures(before[9][1]);names=[r['name'] for r in records]
    if len(names)!=len(set(names)):raise ValueError('Duplicate texture dependencies.')
    originals=[before[9][1][r['offset']:r['offset']+r['size']] for r in records]
    initial_memory=sum(len(g)-208 for g in originals)
    report=dict(mode='Maximum Downgrade',target=target,effective_aligned_target=target//2048*2048,
        baseline_bytes=len(baseline),baseline_sha256=hashlib.sha256(baseline).hexdigest(),
        texture_pixel_palette_budget=initial_memory,textures=[],decisions=[],gameplay_validation='pending',
        policy='Freeze the validated Default geometry candidate and all non-texture payloads; relax texture detail floors only. Fixed rendering depth, native-observed dimensions, sampled alpha preserved.',
        search='Deterministic greedy priority-adjusted perceptual loss per actual stored byte saved; not a global optimum.')
    cache={}
    def build(gims):
        key=tuple(hashlib.sha256(g).digest() for g in gims)
        if key not in cache:
            cancel();table=texture_table(names,gims,gim_reader=read_gim)
            trials=[replace_sections(baseline,{9:compress(table,max_distinct=n)}) for n in (200,220)]
            payload=min(trials,key=len)
            stored=next(s['size'] for s in inspect_pac(payload)['sections'] if s['id']==9)
            cache[key]=(payload,stored)
        return cache[key]
    try:
        from desktop.core import validate_pac
        validate_pac(baseline,max_bytes=max(target,len(baseline)),gim_reader=read_gim)
        # A strict lower bound: texture changes cannot shrink other stored
        # sections, even with completely free hypothetical textures/padding.
        fixed=sum(s['size'] for section,(s,raw) in before.items() if section!=9)
        report['non_texture_stored_lower_bound']=fixed
        if fixed>target:
            raise ValueError('Textures alone cannot fit: frozen non-texture data is %d / %d bytes before texture headers and padding. No additional geometry or rigging changes were made.'%(fixed,target))
        # A fitting baseline is left byte-identical; this is rescue, not an
        # unconditional quality downgrade or an opportunity to change effects.
        selected=[0]*len(names);choices=[];importance=[]
        payload=baseline;stored=before[9][0]['size']
        if len(payload)>target:
            for i,name in enumerate(names):
                progress('Evaluating maximum texture reductions: '+name);cancel()
                rows=candidates(originals[i],cancel);choices.append(rows)
                p,c=read_gim(originals[i]);features=analyze(c[p]);importance.append(features['importance_score'])
                # The estimator orders candidates only; every accepted step is
                # measured through the real whole-table compressor/PAC writer.
                for row in rows:
                    row['individual_bpe_bytes']=min(len(compress(row['raw'],max_distinct=n)) for n in (200,220))
                report['textures'].append(dict(name=name,baseline_dimensions=list(p.shape[1::-1]),
                    baseline_useful_colors=rows[0]['useful_colors'],importance=features,
                    candidates=[{k:v for k,v in row.items() if k!='raw'} for row in rows]))
            # Batch visually identical reductions (uniform maps/unused CLUT
            # entries) rather than spending a whole PAC search round on each
            # zero-loss move. Check the combined real cost before accepting.
            identical=[min((j for j,row in enumerate(rows) if row['metrics']['perceptual_loss']<=1e-12 and row['metrics']['alpha_mae']<=1e-12),
                key=lambda j:(rows[j]['individual_bpe_bytes'],j)) for rows in choices]
            exact_trial,cost=build([choices[i][j]['raw'] for i,j in enumerate(identical)])
            if cost<stored and len(exact_trial)<=len(payload):
                selected=identical;payload=exact_trial;stored=cost
                report['decisions'].append(dict(reason='Batched zero-measured-loss texture reductions',
                    selected_candidates=selected.copy(),pac_bytes=len(payload),stored_texture_bytes=stored))
            while len(payload)>target:
                cancel();options=[]
                current=[choices[i][j]['raw'] for i,j in enumerate(selected)]
                # Probe at most three progressively smaller candidates per map.
                # Use actual unpadded section savings to cross PAC block plateaus.
                for i,rows in enumerate(choices):
                    if i%8==0:progress('Measuring texture savings %d / %d; PAC %d bytes'%(i+1,len(names),len(payload)))
                    incumbent=rows[selected[i]];loss0=incumbent['metrics']['perceptual_loss']
                    proposals=[]
                    for j,row in enumerate(rows):
                        saved=incumbent['individual_bpe_bytes']-row['individual_bpe_bytes']
                        if saved<=0 or row['pixel_palette_bytes']>incumbent['pixel_palette_bytes']:continue
                        loss=max(0.,row['metrics']['perceptual_loss']-loss0)*importance[i]
                        proposals.append((loss/saved,-saved,j))
                    proposals.sort()
                    shortlist=[p[2] for p in proposals[:2]]
                    if proposals:shortlist.append(max(proposals,key=lambda p:-p[1])[2])
                    for j in dict.fromkeys(shortlist):
                        trial=current.copy();trial[i]=rows[j]['raw'];built,cost=build(trial)
                        saved=stored-cost
                        if saved<=0 or len(built)>len(payload):continue
                        loss=max(0.,rows[j]['metrics']['perceptual_loss']-loss0)*importance[i]
                        options.append((loss/saved,-saved,i,j,built,cost,loss))
                if not options:
                    # Last-resort simultaneous minima escape compressor/block
                    # interactions where no one-map move saves a stored byte.
                    minimum=[min(range(len(rows)),key=lambda j:(rows[j]['individual_bpe_bytes'],rows[j]['pixel_palette_bytes'],j)) for rows in choices]
                    smallest,cost=build([choices[i][j]['raw'] for i,j in enumerate(minimum)])
                    report['minimum_texture_trial_bytes']=len(smallest)
                    if len(smallest)>target:raise ValueError('The smallest tested texture-only configuration cannot fit the frozen model and retained data: %d / %d bytes. No additional geometry or rigging changes were made.'%(len(smallest),target))
                    selected=minimum;payload=smallest;stored=cost
                    report['decisions'].append(dict(reason='Simultaneous minimum-texture fallback',pac_bytes=len(payload)));break
                _,_,i,j,payload,stored,loss=min(options,key=lambda o:o[:4])
                report['decisions'].append(dict(texture=names[i],from_candidate=selected[i],to_candidate=j,
                    priority_adjusted_loss=loss,pac_bytes=len(payload),stored_texture_bytes=stored))
                selected[i]=j
                (output/'search-progress.json').write_text(json.dumps(dict(pac_bytes=len(payload),stored_texture_bytes=stored,decisions=report['decisions']),indent=2)+'\n',encoding='utf-8')
                progress('Maximum texture fitting: %d / %d bytes; stored textures %d bytes'%(len(payload),target,stored))
            # A large rescue move can cross several padding blocks. Spend the
            # remaining space restoring detail, rather than leaving an avoidable
            # coarse representation merely because it was the first to fit.
            while True:
                cancel();upgrades=[]
                current=[choices[i][j]['raw'] for i,j in enumerate(selected)]
                for i,rows in enumerate(choices):
                    loss0=rows[selected[i]]['metrics']['perceptual_loss']
                    for j,row in enumerate(rows):
                        gain=(loss0-row['metrics']['perceptual_loss'])*importance[i]
                        if gain<=1e-12:continue
                        trial=current.copy();trial[i]=row['raw'];built,cost=build(trial)
                        if len(built)>target:continue
                        upgrades.append((-gain/max(1,cost-stored),-gain,i,j,built,cost))
                if not upgrades:break
                _,gain,i,j,payload,stored=min(upgrades,key=lambda o:o[:4])
                report['decisions'].append(dict(reason='Restore texture detail within spare serialized budget',
                    texture=names[i],from_candidate=selected[i],to_candidate=j,
                    priority_adjusted_gain=-gain,pac_bytes=len(payload),stored_texture_bytes=stored))
                selected[i]=j
                progress('Restoring texture detail: %d / %d bytes'%(len(payload),target))
        else:
            for name,raw in zip(names,originals):
                p,c=read_gim(raw);rows=[dict(raw=raw,dimensions=list(p.shape[1::-1]),bits=4 if len(c)==16 else 8,
                    palette_entries=len(c),useful_colors=len(np.unique(c[p].reshape(-1,4),axis=0)),encoded_bytes=len(raw),pixel_palette_bytes=len(raw)-208,
                    metrics=measure(c[p],c[p]),alpha_sampled_exact=True,aspect_preserved=True,sampling='Exact incumbent')]
                choices.append(rows);report['textures'].append(dict(name=name,baseline_dimensions=list(p.shape[1::-1]),candidates=[{k:v for k,v in rows[0].items() if k!='raw'}]))
        final=[choices[i][j]['raw'] for i,j in enumerate(selected)]
        after={s['id']:(s,raw) for s,raw in sections(payload)}
        if before.keys()!=after.keys():raise ValueError('Maximum downgrade changed PAC section IDs.')
        for section,(s,raw) in before.items():
            if section!=9 and (after[section][0]['sha256']!=s['sha256'] or after[section][1]!=raw):raise ValueError('Maximum downgrade changed non-texture data.')
        memory=sum(len(g)-208 for g in final)
        if memory>initial_memory or len(payload)>target:raise ValueError('Maximum downgrade exceeded a serialized or texture allocation budget.')
        validate_pac(payload,max_bytes=target,gim_reader=read_gim)
        for i,row in enumerate(report['textures']):
            choice=choices[i][selected[i]];row.update(selected_candidate=selected[i],selected={k:v for k,v in choice.items() if k!='raw'},changed=final[i]!=originals[i])
            for prefix,raw in (('default',originals[i]),('final',final[i])):
                p,c=read_gim(raw);Image.fromarray(c[p]).save(output/('%s-%03d.png'%(prefix,i)))
        report.update(pac_bytes=len(payload),stored_texture_bytes=after[9][0]['size'],
            non_texture_stored_bytes=sum(s['size'] for i,(s,r) in after.items() if i!=9),
            final_texture_pixel_palette_bytes=memory,remaining_aligned_bytes=target//2048*2048-len(payload),
            unchanged_non_texture_payloads=True,structural_validation='passed',export_eligible=True,
            changed_textures=sum(r['changed'] for r in report['textures']),sha256=hashlib.sha256(payload).hexdigest())
    except ValueError as exc:
        report.update(error=str(exc),export_eligible=False)
        (output/'failure-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        raise ValueError(str(exc)+' Diagnostics: '+str(output/'failure-report.json')) from exc
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    body=['<html><meta charset="utf-8"><title>Maximum Downgrade</title><body><h1>Maximum Downgrade</h1>',
        '<p>PAC %d → %d / %d bytes. Model, rigging, UVs, materials and all non-texture payloads identical to the frozen baseline. Gameplay validation pending.</p>'%(len(baseline),len(payload),target),
        '<p>Texture detail floors are relaxed. Native-observed GIM layouts, fixed material depth, alpha sampling and allocation checks remain enforced. <a href="report.json">Full decisions and candidates</a>.</p>']
    for i,row in enumerate(report['textures']):
        final=row['selected'];body.append('<h2>%s</h2><p>%s → %s; %d useful colors in %d fixed palette slots. Quality %.3f; alpha nearest samples preserved. Aspect retained: %s.</p>'%(html.escape(row['name']),row['baseline_dimensions'],final['dimensions'],final['useful_colors'],final['palette_entries'],final['metrics']['quality_score'],final['aspect_preserved']))
        for prefix in ('default','final'):body.append('<figure style="display:inline-block"><figcaption>%s</figcaption><img width="256" style="image-rendering:pixelated" src="%s-%03d.png"></figure>'%(prefix,prefix,i))
    body.append('</body></html>');(output/'report.html').write_text('\n'.join(body),encoding='utf-8')
    return payload,report

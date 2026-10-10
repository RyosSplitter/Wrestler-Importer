"""Opt-in texture stage over frozen model/material/non-texture PAC payloads."""
import hashlib
import html
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

from tools.pac_inspect import inspect_pac,parse_textures
from tools.pac_repack import replace_sections,texture_table
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress,decompress
from .analysis import analyze,measure,model_usage,occupied
from .candidates import read_gim,generate
from .allocator import allocate


def sha(data):return hashlib.sha256(data).hexdigest()


def optimize_pac(baseline,decoded,output,*,target=148000,cancel=lambda:None,
                 progress=lambda message:None,max_pixel_bytes=None):
    """Preserve every stored section except costume texture table 9 exactly.

    Useful colors are bounded by actual source usage. Fixed native CLUT slots
    are format overhead and may remain unused. Rendering bit depth is immutable:
    changing it would violate the user's material-preservation constraint.
    """
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    unpacked={s['id']:(s,raw) for s,raw in sections(baseline)}
    models={i:audit_yobj(raw) for i,(s,raw) in unpacked.items() if raw.startswith(b'YOBJ')}
    names=models[2]['texture_names'];table=unpacked[9][1]
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+',n) for n in names):raise ValueError('Unsafe preview texture name')
    gims={r['name']:table[r['offset']:r['offset']+r['size']] for r in parse_textures(table)}
    sources={n:r for i,n,raw,r,d in decoded};details={n:d for i,n,raw,r,d in decoded}
    if set(sources)!=set(names) or set(gims)!=set(names):raise ValueError('Source/model/texture dependencies differ')
    retained_pixels=0;lossless_storage={};lossless_report=[]
    for section,(s,raw) in unpacked.items():
        if section!=9 and len(raw)>=16 and raw[4:16]==bytes.fromhex('000100000000000010000000'):
            records=parse_textures(raw)
            if not records or any(r['extension']!='gim' for r in records):continue
            for record in records:
                p,c=read_gim(raw[record['offset']:record['offset']+record['size']])
                retained_pixels+=((p.shape[1]*(4 if len(c)==16 else 8)+127)//128*16)*p.shape[0]+c.size
            # A separate lossless storage factor validated in the prior texture
            # research. Do not edit effect image pixels, palettes or generation.
            encoded=compress(raw)
            if len(encoded)<s['size']:
                if decompress(encoded)!=raw:raise ValueError('Retained texture table compression failed')
                lossless_storage[section]=encoded
                lossless_report.append(dict(section=section,before_stored_bytes=s['size'],
                    after_stored_bytes=len(encoded),decoded_sha256=sha(raw),decoded_bytes_identical=True))
    existing_pixels=0;usage=model_usage(models,sources);choices=[];reports=[]
    for n in names:
        cancel();progress('Analyzing texture '+n)
        p,c=read_gim(gims[n]);bits=4 if len(c)==16 else 8
        existing_pixels+=len(gims[n])-208
        features=analyze(sources[n],usage[n]['uv_mask'],usage[n]['surface_fraction'])
        scoring=dict(features,mask=occupied(sources[n],usage[n]['uv_mask']))
        try:rows,rejected=generate(sources[n],scoring,bits,c[p],usage[n]['head_fraction']>.5)
        except ValueError as exc:
            (output/'failure-report.json').write_text(json.dumps(dict(texture=n,error=str(exc),
                source_details=features,required_rendering_bits=bits,source_format=details[n]),indent=2)+'\n')
            raise ValueError(n+': '+str(exc)+'; diagnostics: '+str(output/'failure-report.json')) from exc
        choices.append(rows)
        reports.append(dict(name=n,source_palette_format=details[n],**features,
            head_fraction=usage[n]['head_fraction'],uv_coverage_used=usage[n]['uv_mask'] is not None,
            uv_coverage_fraction=None if usage[n]['uv_mask'] is None else float(usage[n]['uv_mask'].mean()),
            required_rendering_bits=bits,available_candidates=[r['entry'] for r in rows],
            rejected_configurations=rejected,current_configuration=dict(width=p.shape[1],height=p.shape[0],bits=bits,
                palette_entries=len(c),used_palette_colors=len(np.unique(c[p].reshape(-1,4),axis=0)),
                metrics=measure(sources[n],c[p],scoring['mask']))))
    limit=existing_pixels+retained_pixels if max_pixel_bytes is None else max_pixel_bytes
    # The baseline data footprint is a conservative experimental envelope, not
    # a measured SVR heap ceiling. Do not derive limits from generic PSP VRAM.
    measured_count=0
    def build(selection):
        nonlocal measured_count
        cancel()
        measured_count+=1
        if measured_count%20==0:progress('Measuring actual serialized texture combination %d'%measured_count)
        rows=[rs[i] for rs,i in zip(choices,selection)]
        raw=texture_table(names,[r['raw'] for r in rows],gim_reader=read_gim)
        encoded=compress(raw)
        # Same existing dictionary variant, only on the changed texture table.
        alternative=compress(raw,max_distinct=220)
        if len(alternative)<len(encoded):encoded=alternative
        pac=replace_sections(baseline,{**lossless_storage,9:encoded})
        info=inspect_pac(pac);stored=next(s['size'] for s in info['sections'] if s['id']==9)
        return pac,dict(pac_bytes=len(pac),texture_stored_bytes=stored,
                       texture_table_decoded_bytes=len(raw),encoded_gim_bytes=sum(len(r['raw']) for r in rows),
                       pixel_palette_bytes=retained_pixels+sum(r['entry']['pixel_palette_bytes'] for r in rows))
    progress('Allocating measured texture upgrades within the frozen model budget')
    try:
        payload,selection,allocation=allocate(choices,[r['importance_score'] for r in reports],build,target,limit,cancel)
    except ValueError as exc:
        (output/'failure-report.json').write_text(json.dumps(dict(error=str(exc),target=target,
            pixel_palette_budget=limit,textures=reports,lossless_texture_storage=lossless_report),indent=2,allow_nan=False)+'\n',encoding='utf-8')
        raise ValueError(str(exc)+'; diagnostics: '+str(output/'failure-report.json')) from exc
    from desktop.core import validate_pac
    validate_pac(payload,max_bytes=target,gim_reader=read_gim)
    final={s['id']:(s,raw) for s,raw in sections(payload)}
    proof=[]
    for i,(before,raw) in unpacked.items():
        if i==9:continue
        after=final[i][0]
        if i in lossless_storage:
            if final[i][1]!=raw:raise ValueError('Retained texture data changed during lossless storage')
            continue
        if before['sha256']!=after['sha256'] or final[i][1]!=raw:raise ValueError('Adaptive stage changed unrelated PAC data')
        proof.append(dict(section=i,stored_sha256=before['sha256'],byte_identical=True))
    for n,rows,index,row in zip(names,choices,selection,reports):
        selected=rows[index];row['selected_configuration']=selected['entry'];row['selected_candidate_index']=index
        row['decision']='Selected by measured marginal information/byte with immutable material, source, alpha and detail safeguards'
        row['quality_review_flags']=[]
        e=selected['entry'];b=row['current_configuration']['metrics'];m=e['metrics']
        if e['width']*e['height'] < sources[n].shape[0]*sources[n].shape[1]/8:
            row['quality_review_flags'].append('Retains less than one eighth of source pixels; inspect fine-detail legibility')
        if m['luminance_ssim'] < b['luminance_ssim']-.05 or m['fine_feature_loss'] > b['fine_feature_loss']+.15:
            row['quality_review_flags'].append('Individual detail metric regresses despite aggregate allocation; human visual review required')
        if m['alpha_mae']>0:row['quality_review_flags'].append('Near-opaque alpha was resampled/quantized; measured alpha MAE %.4f'%m['alpha_mae'])
        p,c=read_gim(selected['raw']);Image.fromarray(c[p]).save(output/(n+'.png'));(output/(n+'.gim')).write_bytes(selected['raw'])
        Image.fromarray(sources[n]).save(output/(n+'-source.png'))
        oldp,oldc=read_gim(gims[n]);Image.fromarray(oldc[oldp]).save(output/(n+'-current.png'))
    sizes=inspect_pac(payload)['sections']
    nontexture_stored=sum(s['size'] for s in sizes if s['id']!=9)+8+8*len(sizes)
    report=dict(version=1,experimental=True,baseline_sha256=sha(baseline),sha256=sha(payload),
        baseline_bytes=len(baseline),**allocation,textures=reports,unchanged_sections=proof,
        lossless_retained_texture_storage=lossless_report,
        configured_target=target,effective_padded_target=target//2048*2048,
        unused_aligned_bytes=target//2048*2048-len(payload),
        non_texture_stored_bytes_including_header=nontexture_stored,
        nominal_texture_budget=target//2048*2048-nontexture_stored,
        alignment_padding_bytes=len(payload)-nontexture_stored-allocation['texture_stored_bytes'],
        pixel_palette_budget=limit,pixel_budget_basis='Existing baseline padded pixels/CLUT plus retained texture tables; not actual runtime heap',
        scoring_formula='(.6 + 1.6*detail + .8*coverage + 1.2*half-resolution loss) * (.75 + .5*sqrt(min(surface fraction*20,4))); factor=1 without model coverage',
        loss_formula='.22*RGB_RMSE/255 + .15*(1-SSIM) + .30*min(oriented edge error,2)/2 + .23*fine-feature loss + .10*min(high-frequency error,2)/2',
        structural_validation='passed',gameplay_validation='pending',
        warnings=['No YOBJ/material mutation: incompatible palette storage depths are explicitly rejected.',
                  'Cutouts keep source dimensions and alpha samples exact; RGB may be palette-quantized. Near-opaque maps use nearest alpha sampling and source-level alpha quantization when fixed CLUT slots require it; alpha errors are reported.',
                  'Heuristic scores and triangle surface share do not guarantee perceptual quality or actual visibility.',
                  'Retained GIM tables may use proven lossless BPE storage; decoded texture bytes are unchanged.',
                  'PAC pointers may relocate during existing aligned repacking; non-texture section payloads are unchanged.'])
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    body=['<html><meta charset="utf-8"><title>Adaptive texture experiment</title><body><h1>Adaptive texture optimization — experimental</h1>',
          '<p>Actual PAC: %d / %d bytes. Current: %d bytes. Gameplay validation pending.</p>'%(len(payload),target,len(baseline)),
          '<p><a href="report.json">All candidate configurations, metrics, ceilings, allocation decisions and proofs</a></p>']
    for row in reports:
        n=row['name'];e=row['selected_configuration']
        body.append('<h2>%s</h2><p>Detail coverage %.1f%%; importance %.3f. Selected %dx%d, %d palette slots, %d used colors, %d encoded bytes.</p>'%(html.escape(n),row['detail_coverage_percent'],row['importance_score'],e['width'],e['height'],e['palette_entries'],e['used_palette_colors'],e['serialized_bytes']))
        for warning in row['quality_review_flags']:body.append('<p><strong>Review: '+html.escape(warning)+'</strong></p>')
        for label,suffix in [('Source','-source'),('Current','-current'),('Adaptive','')]:
            body.append('<figure style="display:inline-block"><figcaption>%s</figcaption><img style="width:256px;image-rendering:pixelated" src="%s%s.png"></figure>'%(label,html.escape(n,quote=True),suffix))
    body.append('</body></html>');(output/'report.html').write_text('\n'.join(body),encoding='utf-8')
    return payload,report

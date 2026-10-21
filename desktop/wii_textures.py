"""Experimental Wii allocator policy. Does not change HCTP/JBI texture paths.

Uses content/UV scoring, actual PAC measurements, source alpha (nearest), and
lossless T4 storage for 16-color opaque candidates. No character/name matching.
"""
import numpy as np
from tools.wwe13_wii_texture_refine import candidates as original_candidates
from tools.wwe13_texture_trial import allocate as original_allocate
from tools.wwe13_texture_format_trial import exact_indexed4
from tools.yukes_bpe import compress
from model_qa.palette_quality import representation
from desktop.texture_optimizer.analysis import model_usage


def candidates(model,images,contracts,progress=print):
    # A T8-dominated option may become useful once T4 cost and palette loss are
    # evaluated; prune only after those transformations, never before them.
    choices,importance,diagnostics=original_candidates(model,images,contracts,progress,keep_all=True)
    usage=model_usage({2:dict(model,texture_names=model['textures'])},dict(zip(model['textures'],images)))
    for i,(source,contract,rows,diag) in enumerate(zip(images,contracts,choices,diagnostics)):
        legal=[];rejected=[]
        for row in rows:
            entry=dict(row['entry'],metrics=dict(row['entry']['metrics']));row=dict(row,entry=entry)
            w,h=entry['width'],entry['height']
            if contract['cutout']:
                # A's accepted policy: preserve original nearest alpha and at
                # least half of each original atlas dimension, no upscaling.
                floor=(min(source.shape[1],max(32,source.shape[1]//2)),min(source.shape[0],max(32,source.shape[0]//2)))
                if w<floor[0] or h<floor[1]:
                    rejected.append(dict(width=w,height=h,reason='Cutout half-source axis floor (nearest-alpha trial A)'));continue
            if diag['model_usage']['head_fraction']>.15 and not contract['cutout'] and not diag['ocular_surface']:
                floor=(min(64,1<<(source.shape[1].bit_length()-1)),min(64,1<<(source.shape[0].bit_length()-1)))
                if w<floor[0] or h<floor[1] or entry.get('requested_useful_colors',256)<min(32,entry['source_quality_ceiling']['useful_colors']):
                    rejected.append(dict(width=w,height=h,reason='Experimental cranial resolution/color safeguard'));continue
            if not contract['cutout'] and entry['used_palette_colors']<=16:
                raw=exact_indexed4(row['raw'])
                entry=dict(entry,bits=4,palette_entries=16,serialized_bytes=len(raw),pixel_palette_bytes=len(raw)-208,
                           individual_bpe_bytes=len(compress(raw)),storage_policy='Lossless T4 re-encoding of these exact candidate RGBA pixels')
                row=dict(raw=raw,entry=entry)
            if not contract['cutout']:
                from desktop.texture_optimizer.candidates import read_gim
                ix,pal=read_gim(row['raw'])
                quantization=representation(source,pal[ix],usage[diag['name']]['uv_mask'])
                metrics=dict(row['entry']['metrics'])
                metrics['source_detail_loss_before_palette_penalty']=metrics['perceptual_loss']
                metrics['native_grid_quantization_rgb_rmse_255']=quantization['quantization_rgb_rmse_255']
                metrics['perceptual_loss']+=4*quantization['quantization_rgb_rmse_255']/255
                row=dict(row,entry=dict(row['entry'],metrics=metrics))
            legal.append(row)
        if not legal:raise ValueError('No texture candidate satisfies experimental safeguards: '+diag['name'])
        legal.sort(key=lambda r:(r['entry']['individual_bpe_bytes'],r['entry']['metrics']['perceptual_loss']))
        frontier=[];best=float('inf')
        for row in legal:
            loss=row['entry']['metrics']['perceptual_loss']
            if loss<best-1e-10:frontier.append(row);best=loss
        choices[i]=frontier
        diag['candidates']=[r['entry'] for r in legal];diag['frontier']=[r['entry'] for r in frontier]
        diag['rejected']+=rejected
    return choices,importance,diagnostics


def allocate(*args,**kwargs):
    kwargs['candidate_factory']=candidates
    return original_allocate(*args,**kwargs,format_aware=True)

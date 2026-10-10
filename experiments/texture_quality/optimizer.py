"""Research-only adaptive search, with measured whole-PAC acceptance.

Uses a bounded beam to propose combinations, then tests actual encoded PACs.
This is a heuristic search, not a proof of globally optimal visual quality.
No geometry fallback, no automatic application integration, no heap-limit claim.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import sobel

from app.ps2_textures import read_source
from tools.texture_convert import read_gim
from tools.yukes_bpe import compress
from .frozen import FrozenPac,digest
from .metrics import compare,encode
from .trial import dimensions,save_candidate,panels


def pareto(rows):
    """An ineligible legacy aspect ratio must not dominate a valid option."""
    frontier=[]
    for row in rows:
        a=row['entry']
        if a['quantizer']=='Existing baseline' or not any(
           (b['entry']['aspect_ratio_preserved'] or not a['aspect_ratio_preserved']) and
           b['entry']['weighted_loss']<=a['weighted_loss'] and
           b['entry']['proposal_stored_cost']<=a['proposal_stored_cost'] and
           b['entry']['pixel_palette_bytes']<=a['pixel_palette_bytes'] and
           (b['entry']['weighted_loss']<a['weighted_loss'] or b['entry']['proposal_stored_cost']<a['proposal_stored_cost'])
           for b in rows):frontier.append(row)
    return frontier


def importance(frozen,decoded):
    """Anatomical controller support + surface area + image edge complexity.

    No wrestler IDs or texture filenames determine priorities. Fine patterns
    such as tattoos and logos receive additional edge-sensitive loss weight.
    """
    head=set()
    for b in frozen.models[2]['bones']:
        p=b['index']
        while p!=-1:
            if frozen.models[2]['bones'][p]['name']=='atama':head.add(b['index']);break
            p=frozen.models[2]['bones'][p]['parent']
    torso={b['index'] for b in frozen.models[2]['bones'] if b['name'] in ('mune','koshi','hara','sebone')}
    area=defaultdict(float);head_area=defaultdict(float);torso_area=defaultdict(float)
    for model in frozen.models.values():
        for mesh in model['meshes']:
            for mat in mesh['materials']:
                name=model['texture_names'][mat['texture_id']]
                for tri in mat['triangles']:
                    vs=[mesh['vertices'][v] for v in tri];p=np.asarray([v['position'] for v in vs]);a=float(np.linalg.norm(np.cross(p[1]-p[0],p[2]-p[0]))*.5)
                    area[name]+=a
                    head_area[name]+=a*sum(sum(w for b,w in zip(mesh['bone_palette'],v['weights']) if b in head) for v in vs)/3
                    torso_area[name]+=a*sum(sum(w for b,w in zip(mesh['bone_palette'],v['weights']) if b in torso) for v in vs)/3
    average=sum(area.values())/max(len(area),1);out={}
    for i,name,raw,rgba,details in decoded:
        lum=rgba[:,:,:3].astype(float)@np.array([.2126,.7152,.0722])/255
        edge=float(np.hypot(sobel(lum,0),sobel(lum,1)).mean())
        h=head_area[name]/max(area[name],1e-12);t=torso_area[name]/max(area[name],1e-12)
        weight=(1+3*h+2*t)*(1+.35*min(area[name]/max(average,1e-12),3))*(1+min(edge,1))
        out[name]=dict(weight=weight,head_fraction=h,torso_fraction=t,surface_area=area[name],image_edge_mean=edge,
                       region='head' if h>.5 else 'torso' if t>.5 else 'other',
                       evidence='PSP bone support, decoded triangle areas and source-image edges, not filename matching')
    return out


def options(frozen,decoded,weights,folder,preserve_head_depth=True):
    choices=[];unsupported=[]
    for i,name,raw,rgba,details in decoded:
        rows=[];seen=set()
        p,c=read_gim(frozen.gims[name]);bits=4 if len(c)==16 else 8
        baseline=dict(name=name,index=i,width=p.shape[1],height=p.shape[0],bits=bits,palette_entries=len(c),
                      encoded_bytes=len(frozen.gims[name]),pixel_palette_bytes=p.size*bits//8+c.size,
                      quantizer='Existing baseline',metrics=compare(rgba,c[p]),source_dimensions=list(rgba.shape[1::-1]),
                      source_aspect_ratio=rgba.shape[1]/rgba.shape[0],aspect_ratio_preserved=p.shape[1]/p.shape[0]==rgba.shape[1]/rgba.shape[0])
        # Average SSIM may favor a blurred small face. Protect anatomical detail
        # independently of image loss, using the existing output's pixel count
        # as a floor (capped at original information content for upsampled maps).
        head_guard=weights[name]['head_fraction']>.5
        floor=min(p.size,rgba.shape[0]*rgba.shape[1]) if weights[name]['torso_fraction']>.5 else 0
        minimum_axis=min(*p.shape,*rgba.shape[:2]) if head_guard else 0
        def add(gim,entry):
            if digest(gim) in seen:return
            seen.add(digest(gim));entry=dict(entry);entry.update(name=name,index=i,source_dimensions=list(rgba.shape[1::-1]),source_aspect_ratio=rgba.shape[1]/rgba.shape[0],aspect_ratio_preserved=entry['width']/entry['height']==rgba.shape[1]/rgba.shape[0],importance=weights[name])
            # The sum of independently compressed GIMs is a proposal heuristic.
            # It is NEVER used as the final acceptance size.
            entry['proposal_stored_cost']=len(compress(gim))-16
            entry['weighted_loss']=entry['metrics']['loss']*weights[name]['weight']
            rows.append(dict(gim=gim,entry=entry))
        add(frozen.gims[name],baseline)
        sizes=set()
        for bits in (4,8):
            for level in range(5):
                try:size=dimensions(rgba.shape[1],rgba.shape[0],bits,level)
                except ValueError as exc:unsupported.append(dict(name=name,bits=bits,level=level,reason=str(exc)));continue
                sizes.add((size,bits))
        # Also evaluate better quantization at exactly the existing resolution.
        sizes.update([((p.shape[1],p.shape[0]),4),((p.shape[1],p.shape[0]),8)])
        for size,bits in sorted(sizes):
            if preserve_head_depth and head_guard and bits<baseline['bits']:
                unsupported.append(dict(name=name,size=size,bits=bits,reason='Preserve existing cranial palette depth independently of resolution'));continue
            if size[0]*size[1]<floor or min(size)<minimum_axis:
                unsupported.append(dict(name=name,size=size,bits=bits,reason='Anatomical detail guard: head minimum sampling axis or torso pixel-count floor',minimum_pixels=floor,minimum_axis=minimum_axis));continue
            try:gim,_,entry=encode(rgba,size,bits)
            except ValueError as exc:unsupported.append(dict(name=name,size=size,bits=bits,reason=str(exc)));continue
            # Prevent a large improvement elsewhere from hiding degraded tattoos,
            # eyes or small clothing marks. These research thresholds require
            # visual/gameplay calibration; they are not native loader limits.
            before=baseline['metrics'];after=entry['metrics']
            if (after['loss']>before['loss']*1.02+1e-6 or
                    after['luminance_ssim']<before['luminance_ssim']-.02 or
                    after['rgb_rmse_255']>before['rgb_rmse_255']*1.1+.1):
                unsupported.append(dict(name=name,size=size,bits=bits,reason='Per-texture baseline regression guard',baseline_metrics=before,candidate_metrics=after));continue
            add(gim,entry)
        rows.sort(key=lambda r:(r['entry']['weighted_loss'],r['entry']['proposal_stored_cost']))
        # Keep the baseline and Pareto options across loss, real GIM bytes,
        # independently compressed proposal bytes and uncompressed allocation.
        choices.append(pareto(rows))
    (folder/'options.json').write_text(json.dumps(dict(textures=[[r['entry'] for r in rs] for rs in choices],unsupported=unsupported),indent=2)+'\n')
    return choices


def propose(choices,capacity,memory,beam=160):
    # Diversity in actual encoded-size bins protects inexpensive combinations;
    # equal-cost states prefer lower weighted image loss.
    states=[(0,0,0.,())]
    for rows in choices:
        generated={}
        for cost,mem,loss,selection in states:
            for i,row in enumerate(rows):
                r=row['entry'];c=cost+r['proposal_stored_cost'];m=mem+r['pixel_palette_bytes']
                if not r['aspect_ratio_preserved']:continue
                if c>capacity or m>memory:continue
                state=(c,m,loss+r['weighted_loss'],selection+(i,))
                key=(c//128,m//512)
                if key not in generated or state[2]<generated[key][2]:generated[key]=state
        values=list(generated.values())
        if not values:return []
        lowloss=sorted(values,key=lambda x:(x[2],x[0]))[:beam//2]
        # Coverage by encoded cost provides alternatives for actual BPE fitting.
        buckets={}
        for s in values:
            key=s[0]//256
            if key not in buckets or s[2]<buckets[key][2]:buckets[key]=s
        diverse=sorted(buckets.values(),key=lambda x:(x[2],x[0]))[:beam//2]
        states=list({s[3]:s for s in lowloss+diverse}.values())
    return sorted(states,key=lambda x:(x[2],x[0]))


def run(source,baseline,output,*,label='05-adaptive',preserve_head_depth=True):
    output.mkdir(parents=True,exist_ok=False);frozen=FrozenPac(baseline.read_bytes());decoded=read_source(source,texture_names=frozen.names)
    weights=importance(frozen,decoded);choices=options(frozen,decoded,weights,output,preserve_head_depth)
    baseline_selection=tuple(next(i for i,r in enumerate(rows) if r['entry']['quantizer']=='Existing baseline') for rows in choices)
    records=[];tested={};best=None
    def evaluate(selection,reason):
        nonlocal best
        if selection in tested:return tested[selection]
        gims={n:rows[i]['gim'] for n,rows,i in zip(frozen.names,choices,selection)}
        pac,report=frozen.build(gims);loss=sum(rows[i]['entry']['weighted_loss'] for rows,i in zip(choices,selection))
        row=dict(selection=list(selection),reason=reason,weighted_loss=loss,pac_bytes=report['pac_bytes'],
                 texture_section_stored_bytes=report['texture_section_stored_bytes'],
                 texture_pixel_palette_bytes=report['texture_pixel_palette_bytes'],export_eligible=report['export_eligible'])
        records.append(row);tested[selection]=row
        aspect_ok=all(rows[i]['entry']['aspect_ratio_preserved'] for rows,i in zip(choices,selection))
        row['aspect_ratio_pass']=aspect_ok
        if report['export_eligible'] and (aspect_ok or selection==baseline_selection) and (best is None or (loss,report['pac_bytes'])<(best[0],best[1])):best=(loss,report['pac_bytes'],selection)
        return row
    initial=evaluate(baseline_selection,'Frozen existing output')
    base_cost=sum(rows[i]['entry']['proposal_stored_cost'] for rows,i in zip(choices,baseline_selection))
    slack=frozen.max_bytes-initial['pac_bytes']
    # Proposal capacities bracket imperfect per-GIM BPE estimates. Every final
    # candidate is rebuilt and measured, including control-word model changes.
    proposals=[]
    for cap in (base_cost+slack-2048,base_cost+slack,base_cost+slack+4096):
        proposals+=propose(choices,cap,frozen.max_texture_bytes-frozen.retained_texture_bytes)
    unique={s[3]:s for s in proposals};ranked=sorted(unique.values(),key=lambda x:(x[2],x[0]))
    # Include inexpensive fronts, not only over-budget low-loss combinations.
    selected=ranked[:16]+sorted(unique.values(),key=lambda x:(x[0],x[2]))[:5]
    for s in selected:evaluate(s[3],'Bounded beam proposal, measured whole PAC')
    if best is None:raise ValueError('No feasible texture-only configuration; geometry unchanged')
    for iteration in range(2):
        before=best;selection=best[2];neighbors=[]
        for j,rows in enumerate(choices):
            current=rows[selection[j]]['entry']
            for i,r in enumerate(rows):
                if r['entry']['weighted_loss']>=current['weighted_loss']:continue
                candidate=selection[:j]+(i,)+selection[j+1:]
                if not all(rs[k]['entry']['aspect_ratio_preserved'] for rs,k in zip(choices,candidate)):continue
                benefit=current['weighted_loss']-r['entry']['weighted_loss']
                extra=max(r['entry']['proposal_stored_cost']-current['proposal_stored_cost'],64)
                neighbors.append((benefit/extra,candidate))
        for _,candidate in sorted(neighbors,reverse=True)[:12]:evaluate(candidate,'Measured local quality improvement')
        if best==before:break
    selection=best[2];gims={n:rows[i]['gim'] for n,rows,i in zip(frozen.names,choices,selection)}
    entries=[rows[i]['entry'] for rows,i in zip(choices,selection)]
    final=save_candidate(output,label,frozen,gims,entries)
    final.update(weighted_loss=best[0],baseline_weighted_loss=initial['weighted_loss'],
                 measured_combination_count=len(records),search_algorithm='Deterministic bounded beam proposals plus exact whole-PAC checks and local improvements; not exhaustive/global-optimum proof',
                 warnings=[dict(texture=e['name'],message='Nonuniform baseline-sized option retained because it scored better within measured budget') for e in entries if not e['aspect_ratio_preserved']],
                 detail_guard='Head minimum sampling axis >= existing/source minimum; torso pixel count >= baseline capped by source information; all textures limited to 2% loss, .02 SSIM and 10% RMSE regressions',
                 quality_guard_scope='Research thresholds, not yet calibrated by PPSSPP visual testing',
                 all_aspect_ratios_preserved=all(e['aspect_ratio_preserved'] for e in entries),
                 cranial_palette_depth_preserved=preserve_head_depth,
                 optimization_improved=best[0]<initial['weighted_loss']-1e-12,
                 requested_profile_fitted=all(e['aspect_ratio_preserved'] for e in entries),
                 reduced_texture_details=[dict(texture=e['name'],source=e['source_dimensions'],output=[e['width'],e['height']],bits=e['bits'],retained_pixel_fraction=e['width']*e['height']/(e['source_dimensions'][0]*e['source_dimensions'][1])) for e in entries if e['width']*e['height']<e['source_dimensions'][0]*e['source_dimensions'][1]])
    if not final['requested_profile_fitted']:
        final['warnings'].insert(0,dict(message='Requested aspect/detail/palette guards could not fit in the evaluated search. Preserved the frozen baseline; no quality upgrade claimed. Review the evaluated size violations or explicitly allow cranial palette reduction for a separate trial.'))
    (output/label/'report.json').write_text(json.dumps(final,indent=2)+'\n')
    (output/'search.json').write_text(json.dumps(dict(source_sha256=digest(source.read_bytes()),baseline_sha256=digest(baseline.read_bytes()),importance=weights,evaluations=records,best=final),indent=2)+'\n')
    print(json.dumps({k:final[k] for k in ('pac_bytes','texture_section_stored_bytes','texture_pixel_palette_bytes','weighted_loss','baseline_weighted_loss','mean_ssim','mean_rgb_rmse_255','measured_combination_count','warnings')},indent=2),flush=True)
    return final


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--label',default='05-adaptive');p.add_argument('--allow-head-palette-reduction',action='store_true')
    a=p.parse_args()
    if not a.label or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-' for c in a.label):p.error('Label must contain only letters, digits and hyphens')
    run(a.source,a.baseline,a.output,label=a.label,preserve_head_depth=not a.allow_head_palette_reduction)

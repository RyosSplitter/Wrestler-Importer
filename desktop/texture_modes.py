"""Explicit texture modes; downgrade Default textures over a frozen PSP model.

No geometry/material edits and no automatic reduction beyond the selected
steps. Native observed layouts and the established texture allocation envelope
are policy guards, not claims about universal hardware or loader limits.
"""
import hashlib
import html
import json
from pathlib import Path

import numpy as np
from PIL import Image

from desktop.texture_optimizer.candidates import read_gim,write_gim
from tools.pac_inspect import parse_textures
from tools.pac_repack import replace_sections,texture_table
from tools.psp_mesh_merge_trial import sections
from tools.yukes_bpe import compress

MODES=('Default','ATO','Priority Selection','Downgrade','Maximum Downgrade')
HELP={
    'Default':'Best for most models. Uses the established texture pipeline.',
    'ATO':'Experimental content-aware optimization within the texture budget.',
    'Priority Selection':'Prioritize up to 3 source textures. Reallocate texture space from other maps where needed; all reductions are reported.',
    'Downgrade':'Reduce Default textures by 1, 2 or 3 sizes. Squares stop at 64×64; rectangles keep their aspect ratio. Smaller maps stay unchanged.',
    'Maximum Downgrade':'Last resort: keep the converted model unchanged and reduce texture resolution/colors below normal floors only as needed to fit. Quality losses are reported.'}


def downgrade_size(width,height,steps):
    if type(steps) is not int or steps not in (1,2,3):raise ValueError('Choose 1, 2 or 3 downgrade steps.')
    if width<1 or height<1:raise ValueError('Invalid source dimensions.')
    # Halve both axes together. Squares stop at 64x64; rectangles stop when
    # their longer axis reaches 64. Existing smaller maps are never enlarged.
    w,h=width,height
    for _ in range(steps):
        if max(w,h)//2<64:break
        w//=2;h//=2
    return w,h


def downgrade_texture(source,baseline,steps):
    p,c=read_gim(baseline);bits=4 if len(c)==16 else 8
    h,w=p.shape;size=downgrade_size(w,h,steps)
    if size==(w,h):raw=baseline
    else:
        # Resolution-only operation: preserve all existing CLUT bytes. Nearest
        # indexed sampling cannot invent colors or alpha levels and keeps the
        # sampled cutout mask exact, independently of RGB.
        pixels=np.asarray(Image.fromarray(p).resize(size,Image.Resampling.NEAREST))
        raw=write_gim(pixels,c,bits)
    sampling='Nearest existing indices; CLUT bytes and sampled alpha exact'
    index,palette=read_gim(raw)
    if index.shape[1::-1]!=size or len(palette)!=len(c):raise ValueError('Downgrade dimensions/material depth changed unexpectedly.')
    if not np.array_equal(palette,c):raise ValueError('Downgrade changed the existing palette.')
    expected=np.asarray(Image.fromarray(c[p][:,:,3]).resize(size,Image.Resampling.NEAREST))
    if not np.array_equal(palette[index][:,:,3],expected):raise ValueError('Downgrade changed sampled alpha.')
    return raw,dict(source_dimensions=list(source.shape[1::-1]),baseline_dimensions=[w,h],
        selected_dimensions=list(size),requested_steps=steps,
        actual_steps=int(round(np.log2(w/size[0]))),floor_reached=max(size)<=64,
        smaller_baseline_unchanged=max(w,h)<64,bits=bits,palette_entries=len(palette),palette_bytes_identical=True,
        used_colors=len(np.unique(palette[index].reshape(-1,4),axis=0)),
        encoded_bytes=len(raw),pixel_palette_bytes=len(raw)-208,sampling=sampling)


def downgrade_pac(baseline,decoded,output,*,steps,target=148000,cancel=lambda:None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    before={s['id']:(s,raw) for s,raw in sections(baseline)}
    table=before[9][1];records=parse_textures(table);names=[r['name'] for r in records]
    source={n:rgba for i,n,raw,rgba,d in decoded}
    if len(source)!=len(decoded) or set(source)!=set(names):raise ValueError('Downgrade source/texture dependencies differ.')
    old={r['name']:table[r['offset']:r['offset']+r['size']] for r in records}
    # Include retained effect texture allocations on both sides. Headers are
    # excluded; padded/swizzled pixels and CLUT slots use their actual bytes.
    retained=0
    for section,(s,raw) in before.items():
        if section!=9 and len(raw)>=16 and raw[4:16]==bytes.fromhex('000100000000000010000000'):
            for r in parse_textures(raw):
                if r['extension']!='gim':raise ValueError('Unsupported retained texture allocation.')
                gim=raw[r['offset']:r['offset']+r['size']];read_gim(gim);retained+=len(gim)-208
    limit=retained+sum(len(raw)-208 for raw in old.values())
    report=dict(mode='Downgrade',requested_steps=steps,source_based=False,reduction_basis='Default generated textures',
        configured_target=target,effective_padded_target=target//2048*2048,
        baseline_bytes=len(baseline),baseline_sha256=hashlib.sha256(baseline).hexdigest(),
        pixel_palette_budget=limit,pixel_budget_basis='Existing baseline padded pixels/CLUT; conservative policy, not measured game heap',
        retained_texture_pixel_palette_bytes=retained,textures=[],gameplay_validation='pending')
    try:
        gims=[]
        for name in names:
            report['active_texture']=dict(name=name,source_dimensions=list(source[name].shape[1::-1]),
                requested_steps=steps)
            cancel();raw,row=downgrade_texture(source[name],old[name],steps)
            row['name']=name;report['textures'].append(row);gims.append(raw)
            Image.fromarray(source[name]).save(output/('source-%03d.png'%(len(gims)-1)))
            p,c=read_gim(old[name]);Image.fromarray(c[p]).save(output/('default-%03d.png'%(len(gims)-1)))
            p,c=read_gim(raw);Image.fromarray(c[p]).save(output/('final-%03d.png'%(len(gims)-1)))
        report.pop('active_texture',None)
        cancel();new_table=texture_table(names,gims,gim_reader=read_gim)
        candidates=[replace_sections(baseline,{9:compress(new_table,max_distinct=n)}) for n in (200,220)]
        payload=min(candidates,key=len)
        memory=retained+sum(len(g)-208 for g in gims)
        report.update(pac_bytes=len(payload),pixel_palette_bytes=memory,
            unused_aligned_bytes=target//2048*2048-len(payload),
            encoded_texture_bytes=sum(map(len,gims)),texture_table_decoded_bytes=len(new_table))
        after={s['id']:(s,raw) for s,raw in sections(payload)}
        if before.keys()!=after.keys():raise ValueError('Downgrade changed the PAC section set.')
        for section,(s,raw) in before.items():
            if section!=9 and (after[section][0]['sha256']!=s['sha256'] or after[section][1]!=raw):
                raise ValueError('Downgrade changed non-texture data.')
        from desktop.core import validate_pac
        validate_pac(payload,max_bytes=max(target,len(payload)),gim_reader=read_gim)
        report.update(structural_validation='passed',unchanged_non_texture_payloads=True,
            pac_budget_pass=len(payload)<=target,pixel_budget_pass=memory<=limit)
        if len(payload)>target or memory>limit:
            raise ValueError('Selected Downgrade setting cannot fit: PAC %d / %d bytes; padded textures/CLUT %d / %d bytes. '
                'The 64-pixel floor was retained. Try more steps if an image is still above the floor, or use Default/ATO. No geometry was changed.'%(len(payload),target,memory,limit))
        report['sha256']=hashlib.sha256(payload).hexdigest()
    except ValueError as exc:
        report['error']=str(exc);report['export_eligible']=False
        (output/'failure-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        raise ValueError(str(exc)+' Diagnostics: '+str(output/'failure-report.json')) from exc
    report['export_eligible']=True
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    body=['<html><meta charset="utf-8"><title>Texture downgrade</title><body><h1>Texture downgrade</h1>',
        '<p>%d halving steps from Default textures; squares stop at 64x64, rectangles preserve aspect, no upscaling. Actual PAC %d / %d bytes. Padded pixels/CLUT %d / %d bytes.</p>'%(steps,len(payload),target,memory,limit),
        '<p><a href="report.json">Dimensions, palettes, alpha sampling, budgets and preservation proof</a></p>']
    for i,r in enumerate(report['textures']):
        body.append('<h2>%s</h2><p>Source %s; Default %s → Downgrade %s; %d effective steps; %d palette slots. %s.</p>'%(html.escape(r['name']),r['source_dimensions'],r['baseline_dimensions'],r['selected_dimensions'],r['actual_steps'],r['palette_entries'],html.escape(r['sampling'])))
        for label,prefix in (('Source','source'),('Default','default'),('Downgrade','final')):
            body.append('<figure style="display:inline-block"><figcaption>%s</figcaption><img style="width:256px;image-rendering:pixelated" src="%s-%03d.png"></figure>'%(label,prefix,i))
    body.append('</body></html>');(output/'report.html').write_text('\n'.join(body),encoding='utf-8')
    return payload,report

"""Assemble reproducible texture research evidence, not a Windows app release."""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile


def run(work,output):
    output.mkdir(parents=True,exist_ok=False)
    native=json.loads((work/'census/inventory.json').read_text())
    root=json.loads((work/'rock/report.json').read_text())
    folders=[work/'rock'/label for label in ('01-current','02-colors-only','03-moderate','04-original')]
    folders += [work/'optimized/05-adaptive',work/'head-depth-diagnostic/06-face8-over-budget',work/'face-only/07-face-quantizer-only',work/'storage/08-face8-lossless-texture-storage',work/'storage-search/09-adaptive-face8-storage-search']
    candidates=[]
    target=output/'candidates';target.mkdir()
    for folder in folders:
        report=json.loads((folder/'report.json').read_text());candidates.append(report)
        shutil.copytree(folder,target/report['label'])
        from tools.texture_convert import read_gim
        import numpy as np
        for texture in report['textures']:
            p,c=read_gim((folder/'preview'/(texture['name']+'.gim')).read_bytes())
            texture.update(used_palette_entries=len(np.unique(p)),unique_decoded_rgba_colors=len(np.unique(c[p].reshape(-1,4),axis=0)))
        (target/report['label']/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    census=output/'native-census';shutil.copytree(work/'census',census)
    search=output/'adaptive-search';search.mkdir()
    for label,parent in [('allow-palette-reduction','optimized'),('preserve-head-depth','face-depth')]:
        dest=search/label;dest.mkdir()
        for name in ('options.json','search.json'):shutil.copy2(work/parent/name,dest/name)
    shutil.copy2(work/'storage-search/lossless-search.json',search/'lossless-storage-search.json')
    views=output/'views';shutil.copytree(work/'matching-views',views)
    extra_views=work/'best-views'
    for path in extra_views.rglob('*'):
        if not path.is_file():continue
        dest=views/path.relative_to(extra_views);dest.parent.mkdir(parents=True,exist_ok=True)
        if len(path.relative_to(extra_views).parts)==1:
            # Summary panels intentionally contain different version columns.
            # Individual camera-matched images must still match byte-for-byte.
            dest=views/('final-'+path.name)
        if dest.exists() and path.suffix=='.png' and dest.read_bytes()!=path.read_bytes():raise ValueError('Matching view differs between render runs: '+str(dest))
        shutil.copy2(path,dest)
    shutil.copytree(work/'rock/comparisons',output/'texture-panels')
    summary=dict(classification='CONFIRMED binary/encoded measurements; runtime compatibility pending',
                 source_sha256=root['source_sha256'],baseline_sha256=root['baseline_sha256'],
                 native_summary=native['summary'],candidates=candidates,
                 tests=dict(total_passed=204,generated_texture_conformance_tests=13,platform='Linux CPython 3.13',windows_app_modified=False),
                 policy=dict(pac_ceiling_bytes=148000,effective_2048_aligned_ceiling_bytes=147456,
                             observed_texture_data_envelope_bytes=52992,scope='Observed native Rock aggregate pixels+palettes, NOT a measured SVR runtime allocator limit'),
                 baseline_preservation='Accepted desktop/app/tools/stable_pipeline/dependency files and existing PACs unchanged; research branch only',
                 unknowns=['Actual heap/VRAM peak and multi-wrestler allocation limits','Texture-loader limits beyond supplied references','Exact material-control semantics','PPSSPP and real PSP behavior of these new candidates'])
    (output/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (output/'candidate-textures.csv').open('w',newline='') as f:
        keys=['candidate','name','source_dimensions','width','height','bits','palette_entries','used_palette_entries','unique_decoded_rgba_colors','encoded_bytes','pixel_palette_bytes','quantizer','luminance_ssim','rgb_rmse_255','psnr_db','sobel_magnitude_mae','alpha_mae','alpha_coverage_delta']
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader()
        for r in candidates:
            for t in r['textures']:
                row={k:t.get(k) for k in keys if k in t};row['candidate']=r['label'];row.update({k:t['metrics'].get(k) for k in keys if k in t['metrics']});writer.writerow(row)
    descriptions={
        '01-current':'Current pipeline; original stored texture factor retained',
        '02-colors-only':'Existing resolutions; all maps use 256-entry palettes and improved quantization',
        '03-moderate':'Uniform half dimensions where writer permits; 256-entry palettes',
        '04-original':'Source dimensions/colors; one 8×8 opaque map uniformly upsampled to meet writer pitch',
        '05-adaptive':'Adaptive aspect/detail guards; cranial palette reduction allowed',
        '06-face8-over-budget':'Closest evaluated uniform profile preserving existing cranial depth',
        '07-face-quantizer-only':'Only dominant cranial quantizer changes; dimensions and bit depth fixed',
        '08-face8-lossless-texture-storage':'Trial 06 plus separate lossless encoding of retained blood texture table',
        '09-adaptive-face8-storage-search':'Best of 21 measured preserved-depth combinations after lossless texture storage; pixel/CLUT bytes additionally capped at baseline'}
    table='\n'.join('| %s | %s | %s | %s | %s | %.4f | %.2f | %s |'%(r['label'],f"{r['encoded_gim_bytes']:,}",f"{r['texture_section_stored_bytes']:,}",f"{r['texture_pixel_palette_bytes']:,}",f"{r['pac_bytes']:,}",r['mean_ssim'],r['mean_rgb_rmse_255'],'Fits; gameplay pending' if r['export_eligible'] else 'PAC export withheld') for r in candidates)
    s=native['summary'];baseline=candidates[0];best=candidates[-1]
    text=f'''# v0.25 texture-quality research — 2026-10-10

**Production status:** no v0.25 app implementation, converter rewrite, preset UI,
Windows rebuild, or merge into main. Experiments are isolated on
`experiment/texture-quality-v025`; all accepted baselines remain intact.

**Evidence labels:** CONFIRMED = binary measurement, decoded comparison or executed
test; INFERRED = supported interpretation/proposed policy; UNKNOWN = unmeasured
runtime or undocumented semantics. Native observations are from the user-labelled
SVR 2011 PSP corpus; retail provenance was not independently authenticated.

## Findings and actual budget

**CONFIRMED:** 110 supplied PACs contain 109 distinct PAC hashes and 2,008 GIM
records (1,463 distinct GIM hashes). The two CM Punk shirt PACs are byte-identical.
1,765 GIMs are in main costume table 9, 240 in effect table 8, and 3 in table 39.
The corpus covers women, different body sizes, ring/entrance costumes, masks,
accessories and NPCs. `native-census/inventory.json` records every input SHA-256,
section allocation, image header, dimension, palette and decoder result.

| Observed native property | CONFIRMED measurement |
|---|---|
| Image dimensions | 8×8 through 256×256; 22 dimension combinations |
| Aspect ratios | Square and rectangular; 830/2,008 images are nonsquare |
| Indexed4 / format 4 | 1,776 images; 16 RGBA8888 CLUT entries |
| Indexed8 / format 5 | 232 images; 256 RGBA8888 CLUT entries |
| Main costume table only | 1,534 indexed4 + 231 indexed8 images |
| Palette format/order | All format 3 / linear order 0 / 32-bit RGBA |
| Pixel order and levels | All swizzled order 1; one level and one frame |
| Images with used nonopaque pixels | 670 (includes effect/blood maps) |
| PAC sizes | 69,632–202,752 bytes |
| Texture records per PAC, all tables | 6–27 |
| Complete encoded GIM bytes per PAC | 35,424–91,200 bytes |
| Padded pixels + palettes per PAC | 34,176–87,872 bytes |
| Outer native section addresses | All 4-byte aligned; no PAC has every section 16-byte aligned |
| Outer PAC file padding | All 110 files are multiples of 2,048 bytes |
| Named GIM payload starts | All 2,008 are 16-byte aligned inside decoded tables |

**CONFIRMED:** Native Rock uses a 64×128 indexed8 torso, 64×128 indexed8 face,
128×64 indexed8 trunks, and 32×64 indexed8 tattoo map, among other images. Its
18 costume GIMs plus three effect maps occupy 57,360 encoded bytes and 52,992
padded pixel/CLUT bytes. Its PAC is 153,600 bytes. Seven corpus PACs exceed
148,000 bytes. Therefore 64-pixel body caps, universal 16-color body textures and
148,000 bytes are not universal native format restrictions.

**CONFIRMED:** This converter's 148,000-byte operational policy is unchanged.
2,048-byte final padding makes the largest eligible file 147,456 bytes. Our
converted Rock's body plus pads use **124,477 compressed model bytes**, versus
**74,488** in native Rock. The trial has 45 draw buffers / 2,473 vertices / 2,853
triangles; native Rock has 30 / 1,418 / 1,777. The native allocation does not
justify importing its larger texture budget into this larger converted model.

| Allocation | Native Rock | Current converted Rock |
|---|---:|---:|
| Compressed/stored model sections | 74,488 | 124,477 |
| Stored costume texture section 9 | 40,730 | 11,277 |
| Stored blood/effect section 8 | 4,008 | 7,072 |
| Other nested/event section 100 | 32,527 | absent in selected donor |
| Final PAC | 153,600 | 143,360 |
| Decoded model sections | 143,208 | 210,864 |
| Padded pixels + palettes, all tables | 52,992 | 28,224 |

**INFERRED:** Fixed reductions are overly conservative as a general quality policy,
but the frozen converted geometry leaves a genuinely small compressed texture
budget. The practical improvement is selective allocation, better quantization
and lossless storage where supported, rather than upgrading every map uniformly.

**UNKNOWN:** Actual game heap allocations, texture cache duplication, GE uploads,
VRAM placement, peak match memory and loader limits. Pixels+CLUT are a separately
reported resource estimate, not the actual allocator size. BPE reduces stored
bytes only. The 52,992-byte native Rock pixel/CLUT footprint is an experimental
comparison envelope, not a validated runtime ceiling. No claim of gameplay
compatibility follows from structural validation.

## Binary texture conventions and restrictions

**CONFIRMED:** Little-endian GIM layout in this corpus:

| File offset | Bytes | Meaning |
|---:|---:|---|
| 0 | 16 | `MIG.00.1PSP` signature allocation |
| 16 / 32 / 48 | 16 each | Root type 2 / picture type 3 / image type 4 headers |
| 52 | 4 | Image block bytes, measured from offset 48 |
| 64 | 4 | Image info value 48 |
| 68 / 70 | 2 each | Format 4 or 5 / swizzled order 1 |
| 72 / 74 / 76 | 2 each | Logical width / height / bits 4 or 8 |
| 78 / 80 | 2 each | Byte pitch alignment 16 / vertical alignment 8 |
| 92 / 96 | 4 each | Pixel start / end relative to info origin 64 |
| 104–110 | 2 each | Level type, level count, frame type, frame count |
| 128 | variable | Swizzled packed indices; includes row padding for narrow native images |
| 48 + image block bytes | 16 + 64 + CLUT | Palette block type 5, info and colors |
| Palette block + 20 / +22 | 2 each | RGBA8888 format 3 / linear order 0 |
| Palette block +24 / +26 / +28 | 2 each | 16 or 256 colors / height 1 / 32 bits |
| Palette block +80 | 64 or 1,024 | Linear RGBA8 CLUT, no PS2 alpha re-expansion |

**CONFIRMED/INFERRED:** Swizzle tiles are 16 bytes × 8 rows, 128 bytes each.
For byte pitch B, address is `((y//8)*(B//16)+x//16)*128+(y%8)*16+x%16`.
T4 packs `even_index | odd_index<<4`. Logical 8/16-pixel-wide T4 images use
16-byte physical row pitch: 8×8 uses 128 pixel bytes, not 32. The research reader
decodes all 2,008 records; it agrees exactly with the maintained decoder on its
1,972 supported images. Padded narrow image interpretation is also checked with
independent synthetic fixtures. This does not extend the production writer.

**CONFIRMED:** The current writer requires T4 width multiples of 32, T8 width
multiples of 16, and height multiples of 8. Those are implementation restrictions,
not general minimum native widths. Its encoded sizes are
`T4 = 272 + width*height/2`, `T8 = 1232 + width*height`. Palette/block overhead
means halving pixels does not halve a GIM. Raising T4 to T8 adds 960 CLUT bytes
per image, before accounting for doubled index data and changed compression.

**CONFIRMED external SDK contract:** PSPSDK's `sceGuTexImage` validates power-of-two
dimensions 1–512, texture pointers aligned to 16 bytes, and buffer widths 1–1024.
Pinned source: https://github.com/pspdev/pspsdk/blob/e2b2b313d4175823a263c2c6cf175311e824eb77/src/gu/sceGuTexImage.c
The header documents block-aligned buffer widths and texture/CLUT alignment.
**UNKNOWN:** This does not establish that SVR's loader supports every SDK texture
size/layout. No 512-pixel or direct-color GIM is observed in this corpus.

**CONFIRMED:** 31 native YOBJs exceed the strict converted-model reader's current
secondary-descriptor mesh-count assumption. Their texture data still parses and
is included. They are parser coverage gaps, not malformed game assets. The 84
audited models contain both T8/control-5 and T4/control-7 combinations, as well
as effect controls. **UNKNOWN:** Complete material-control semantics. The trials
retain the existing local converter profile (ordinary 5/7, alpha bits retained),
patching only relevant material control words when depth changes. This is not
claimed as a universal native bit-depth law. Trial 08 changes no YOBJ bytes.

## Controlled experiments — geometry frozen

**CONFIRMED:** Source `0000.pac` SHA-256 `{root['source_sha256']}`.
Baseline is the prior three-model Rock PAC SHA-256 `{root['baseline_sha256']}`.
All three rigs, draw buffers, vertices, UVs, colors, normals, weight records,
bone palettes, triangle strips, bounds, bind records and texture name arrays are
held exact. No Blender decimation/alignment/weight transfer is invoked. Trials
01–07 preserve all unrelated stored PAC sections. Bit-depth changes patch only
the existing material-control words; report JSON lists exact addresses and values.

**CONFIRMED:** All configurations pass structural checks: native pointers and
POF relocation, ranges and alignment, each vertex/index allocation, bone palettes,
normalized weights, texture names, GIM roundtrips and BPE roundtrips. Size/memory
policy failure is reported separately. Over-budget PACs are withheld; their
Noesis OBJ/YOBJ/PNG and diagnostic renders remain available.

| Trial | GIM bytes in 9 | Stored section 9 | Pixels+CLUT all tables | Final PAC bytes | Mean SSIM | Mean RGB RMSE /255 | Outcome |
|---|---:|---:|---:|---:|---:|---:|---|
{table}

Trial definitions:
'''+ '\n'.join('* **%s:** %s.'%(key,value) for key,value in descriptions.items())+f'''

**CONFIRMED:** Trial 04 reconstructs the original decoded source RGBA exactly
(mean SSIM 1, RMSE 0); its unsupported 8×8 opaque writer case is uniformly
upsampled to 16×16. This is documented, not described as native logical 8×8
output. Trials 02/03 exceed both the PAC ceiling and the native Rock texture-data
comparison envelope; 04 exceeds them substantially.

**CONFIRMED:** Trial 05 fits without a storage-factor change, improves aggregate
metrics and preserves all aspect ratios, but uses a 64×64, 16-color face. Its
left-shoulder tattoo SSIM drops from .6737 to .6588, despite lower RGB error.
Do not interpret a better average as a perfect visual result.

**CONFIRMED:** Keeping the existing cranial color depth at uniform resolutions
produced a closest evaluated 149,504-byte configuration (trial 06). Merely
improving the old face quantizer, at unchanged 128×64/T8, also reached 149,504
(trial 07). Neither fixed-storage trial is exported for injection.

### Separate lossless texture-storage factor, trial 08

**CONFIRMED:** The retained section 8 is a named table of `blood1`, `blood2`,
`blood_b1` GIMs. Its 7,072 uncompressed bytes reduce to 4,010 through the existing
BPE codec: **3,062 stored bytes recovered**. Every decoded table/GIM byte remains
exact. Native references already have BPE section 8 tables (native Rock uses
4,008 bytes). Trial 08 uses trial 06's texture configuration and adds only this
storage factor. It preserves every other stored section exactly versus trial 06,
and **all three stored YOBJ payloads are byte-identical to the original baseline**.
The packaging code is unchanged; the factor is a separate experimental caller.

**CONFIRMED:** Trial 08 fits at 147,456 bytes. Its face is 64×64/T8 (256-entry
palette), torso 64×64/T4, and all texture aspect ratios match source. Pixel/CLUT
data is 25,152 bytes, below baseline 28,224. Face SSIM improves .8560→.9132,
face RMSE 6.40→3.77; torso SSIM .8697→.9471. It retains the same small tattoo
SSIM regression as trial 05. Full individual dimensions, palettes, encoded
bytes and errors for all maps are in `candidate-textures.csv` and each JSON.

**UNKNOWN:** This exact combination's loader/event/memory behavior. Native
precedent and structural proofs justify an in-game trial, not production approval.

### Re-evaluating texture allocation after lossless storage, trial 09

**CONFIRMED:** Rebuilding 21 preserved-cranial-depth proposals with the separate
lossless texture-storage factor finds a better measured combination at 147,456
bytes. Its pixel/CLUT bytes equal baseline 28,224; no texture-memory increase is
used to achieve the improvement. All three stored YOBJs still match baseline
exactly. The main front trunks/logo map is restored to original 128×64/T4 with
pixel-exact source colors. Face and torso remain 64×64/T8 and 64×64/T4. Mean
SSIM rises .8055→.9025; mean RGB RMSE falls 10.71→5.90. The face now uses all
256 palette colors, whereas the old nominally T8 face used just 20 colors.
The old torso used 11 of 16 colors; the new torso uses 16. The small tattoo SSIM
regression persists and remains an explicit visual-review item. Trial 09 is the
recommended quality trial; 08 is a simpler independent storage-factor comparison.
**UNKNOWN:** In-game compatibility and subjective facial/tattoo legibility.

## Images, metrics and inspection

**CONFIRMED:** `views/` contains front, back, left, right and three-quarter images
at fixed 1,536-pixel orthographic cameras, plus matching face, torso, tattoo and
clothing-logo crops. Camera/crop metadata is recorded. The source comparison is
original HCTP **textures on the frozen converted PSP geometry**, so changes in
shape, camera or lighting cannot masquerade as better textures. These are CPU
previews, not Noesis screenshots, PPSSPP captures or emulated material flags.
`report.html` provides offline comparison controls; candidate preview folders
have combined `output.obj`, `preview.mtl`, PNGs and independent YOBJ files.

**CONFIRMED:** Quality metrics compare decoded candidates reconstructed to source
size with Lanczos: RGB RMSE/PSNR, luminance SSIM (Gaussian sigma 1.5, C1=.01²,
C2=.03²), Sobel-edge error, edge-weighted RGB error, alpha error/coverage. Exactly
matching images use null PSNR rather than non-JSON infinity. Means are arithmetic
across textures, not GPU-visible area. Adaptive loss also weights anatomical
bone support, triangle surface area and image edges, without wrestler IDs or
filename rules. Tattoo/logo priorities arise from edge-sensitive error; overrides
and visual review may still be necessary.

**INFERRED:** These measures rank useful proposals but do not measure perceived
identity/legibility perfectly. The first unguarded trial preferred a 32×32 face;
it was rejected. Current guards retain head minimum sampling axis, torso pixel
count and per-texture regressions within 2% loss, .02 SSIM and 10% RMSE (+.1).
Those are research thresholds, not game limits or in-game-calibrated tolerances.
There is no arbitrary displacement, geometry simplification or hidden alpha
flattening to force a fit. Unsupported exact-alpha palettes/layouts reject clearly.

## Adaptive optimizer and v0.25 recommendation

**CONFIRMED:** The prototype evaluates palette depth independently of uniform
resolution, compares median-cut/maximum-coverage/octree quantizers, preserves
exact nonopaque RGBA where encodable, and measures actual GIM bytes. A bounded
beam proposes combinations using per-GIM compression as a heuristic; each final
proposal is rebuilt using the **actual whole-table/model/PAC encoding**, including
material-word effects and final 2,048-byte padding. Only measured passing
combinations qualify. It reports both failed attempts and effective settings.
Its search is deterministic but not exhaustive/global-optimum proof. The original
baseline remains a fallback when requested guards cannot fit; no upgrade is claimed
for that fallback. Trial 05 evaluates 34 combinations; preserved-depth search 22.

**INFERRED recommendation:** Validate trial 09 in PPSSPP, using trial 08 as an
independent storage-factor comparison, particularly the
face/tattoo/logo comparison, entrances, match/victory, blood effects and pad-removal
events. Measure peak memory in one-on-one and multi-wrestler cases. If successful,
generalize lossless compression only for completely parsed texture tables,
independently roundtrip every byte, and retain the accepted PAC as backup.
Then add adaptive texture allocation as a reusable stage; do not alter geometry
or rigging to satisfy a texture preset. Calibrate per-region perceptual thresholds
using actual game screenshots. Investigate high-quality padded narrow GIM writing
separately before relying on it for budget fits.

Proposed v0.25 UI policy (not implemented, **INFERRED**, subject to that validation):

| Preset | Proposed behavior; all use the same validated compatibility limits |
|---|---|
| Compact | Favor smaller actual encoded size/headroom while retaining alpha and minimum anatomical/detail guards; uniform scaling and independent palette choice |
| Balanced, default | Favor visual quality under guards; preserve cranial depth when it fits, prioritize torso/face and edge detail, use selective resolutions/palettes |
| Maximum | Broader search toward original dimensions and more colors; same PAC/resource ceilings; never reduce geometry, bypass guards or invent a larger budget |

**INFERRED:** A tight budget may make presets converge. Show requested preset,
effective dimensions/depths, exact allocation and the constraint that caused any
fallback. A lower-resolution result must be visible in the report. Keep the planned
“Include accessory models” checkbox separate: it controls complete YOBJ models,
not draw-buffer merging, and changes the texture dependency set/budget honestly.

**CONFIRMED:** 204 tests pass, including 13 new synthetic cases for swizzle/padded
pitch, bounds, exact alpha, metrics, uniform dimensions, independent material-depth
editing, geometry preservation, size/resource separation, eligible Pareto pruning
and retained-table lossless storage. No proprietary native corpus PAC is included
in this report package. No Windows app modification or clean-machine/PPSSPP test
is claimed.

See `REPRODUCE.txt` for pinned dependencies, commands and artifact hashes.
'''
    (output/'analysis.md').write_text(text)
    (output/'README.txt').write_text('Open report.html for comparisons and analysis.md for the complete analysis.\nOnly 01-current, 05-adaptive, 08-face8-lossless-texture-storage and 09-adaptive-face8-storage-search contain PACs. All are experimental; only 01 is the unchanged baseline.\nRecommended first NEW trial: 09; compare 08 to isolate the storage factor. Keep backups and test in PPSSPP before adopting.\nNoesis: open the candidate preview/output.obj with preview.mtl and PNGs beside it. Use your usual orientation/culling/shading toggles.\nInject into the same known-working Rock EMD slot; follow your working archive rebuild/alignment and ARC-update process, save ISO, test entrances/match/victory/blood/pad removal.\nWithheld configurations are previews only and must not be injected.\nNative input corpus PACs are not redistributed.\n')
    choices=[('00-source-textures','Source textures on frozen geometry')]+[(r['label'],r['label']) for r in candidates if r['label']!='07-face-quantizer-only']
    options=''.join('<option value="%s">%s</option>'%(html.escape(k),html.escape(v)) for k,v in choices)
    trialrows=''.join('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%.4f</td><td>%s</td></tr>'%(r['label'],f"{r['pac_bytes']:,}",f"{r['texture_section_stored_bytes']:,}",f"{r['texture_pixel_palette_bytes']:,}",r['mean_ssim'],'Fits / game pending' if r['export_eligible'] else 'Withheld') for r in candidates)
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>v0.25 texture research</title>
<style>body{font:16px system-ui;margin:30px auto;max-width:1200px;background:#151515;color:#eee;padding:20px}a{color:#92cfff}select,input{font:inherit;margin:8px;padding:7px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #555;padding:8px;text-align:left}.pair{position:relative;max-width:800px;margin:auto;background:#484848}.pair img{width:100%;display:block}#over{position:absolute;top:0;left:0}pre{white-space:pre-wrap}small{color:#ccc}</style>
<h1>v0.25 texture research</h1><p>110 native reference PACs. Existing geometry and rigs frozen. Production app unchanged.</p>
<p><a href="analysis.md">Complete analysis</a> · <a href="report.json">Machine-readable report</a> · <a href="candidate-textures.csv">Every candidate texture</a> · <a href="native-census/textures.csv">Native texture census</a></p>
<p><strong>Suggested in-game trial: 09; compare 08 to isolate storage.</strong> Both preserve 256-color face depth and recover 3,062 stored bytes by losslessly encoding the unchanged blood texture table. Trial 09 restores the front logo to source resolution. All baseline YOBJ payloads remain exact. Compatibility remains pending PPSSPP testing.</p>
<table><tr><th>Trial</th><th>PAC bytes</th><th>Stored costume textures</th><th>All pixel/CLUT bytes</th><th>Mean SSIM</th><th>Export</th></tr>'''+trialrows+'''</table>
<h2>Matching comparisons</h2><p>Choose two versions and drag the slider. Crops share identical geometry, camera and lighting. Source means source textures on converted geometry, not original PS2 shape.</p>
<label>Left <select id="a">'''+options+'''</select></label><label>Right <select id="b">'''+options+'''</select></label><br>
<label>View <select id="view"><option>front</option><option>front-left</option><option>back</option><option>left</option><option>right</option></select></label>
<label>Detail <select id="detail"><option>face</option><option>torso</option><option>tattoo</option><option>clothing-logos</option><option>full</option></select></label><br>
<input id="split" type="range" min="0" max="100" value="50" style="width:95%"><div class="pair"><img id="base" alt="Left comparison"><img id="over" alt="Right comparison"></div>
<p><small>CPU static previews: nearest texture sampling; material-control behavior, mipmaps, actual game filtering and memory are not emulated. Inspect the tattoo: its small SSIM regression remains a human-review item.</small></p>
<h2>Quality limits</h2><p>The native corpus proves larger textures exist, not that larger converted PACs are safe. 148,000 bytes remains the policy ceiling. Pixel/CLUT totals are resource estimates, not heap/VRAM measurements. No app presets are implemented yet.</p>
<script>const a=document.getElementById('a'),b=document.getElementById('b'),v=document.getElementById('view'),d=document.getElementById('detail'),s=document.getElementById('split');a.value='01-current';b.value='09-adaptive-face8-storage-search';function update(){document.getElementById('base').src='views/'+a.value+'/'+v.value+'-'+d.value+'.png';document.getElementById('over').src='views/'+b.value+'/'+v.value+'-'+d.value+'.png';document.getElementById('over').style.clipPath='inset(0 0 0 '+s.value+'%)'}for(const e of [a,b,v,d,s])e.addEventListener('input',update);update();</script></html>'''
    (output/'report.html').write_text(page)
    print('Research evidence assembled: '+str(output),flush=True)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.work,a.output)

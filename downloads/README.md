## Chris Jericho PSP: unchanged preview

[Download OBJ, textures, native YOBJ and Noesis screenshots](Chris-Jericho-PSP-Noesis-preview.zip). The original PAC is unchanged; textures retain their original resolution. Includes the complete model and an additional viewing copy with inactive blood effects hidden. [Details and mesh-count comparison](../docs/jericho-psp-preview.md).

## 1800 hybrid: half-size textures

[Download the 136 KiB PAC](1800-PSP-hybrid-half-textures.pac) or [PAC and preview bundle](1800-PSP-hybrid-half-textures-test-bundle.zip). Combined GIM size is reduced from 47,088 to 23,536 bytes through lower resolution. Model section, weights, materials and palettes are unchanged from the 144 KiB trial. [Details and screenshots](../docs/1800-hybrid-half-textures.md). PPSSPP validation is pending.

## 1800 hybrid PSP size-budget trial

[Download the 144 KiB PAC](1800-PSP-hybrid-144KiB.pac) or [PAC and preview bundle](1800-PSP-hybrid-144KiB-test-bundle.zip). Retains 2,276 triangles, 80% of the head/arm regions, hybrid float weights and a 128×128 indexed8 face texture. Native BPE compression is used. PPSSPP validation is pending. [Report and screenshots](../docs/1800-hybrid-budget.md).

## 1800 hybrid weighting review

[Download the review bundle](1800-hybrid-weight-review.zip): original geometry and textures with the Benoit study’s hybrid weighting method, using the earlier PSP Kurt base. Includes T-pose and posed Noesis screenshots, textured OBJs, assigned weights and a rigged Blender file. This is a review, not a replacement PAC. [Details and checks](../docs/1800-hybrid-weight-review.md).

# Test downloads

[Download the five Benoit weighting trials](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/Benoit-five-weight-methods-review.zip).
Ten actual Noesis screenshots, identical source geometry under five weight
methods, posed OBJs/textures, weight data and four rigged Blender reviews.
The original HCTP weights are now decoded for this study. See
[methods, results and limitations](../docs/benoit-weight-trials.md).
Hybrid weighting is the most promising candidate; automatic heat binding
distorts the body. This is a weight-study bundle, not a replacement PAC or beta.

[Download the Slaughter PS2/PSP reference review](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/Slaughter-PS2-PSP-reference-review.zip).
Matched HCTP and native PSP ring/entrance models, textures, four Noesis screenshots,
and inspection reports show selective arm reduction and BPE compression in the
original PSP port. See [the comparison](../docs/slaughter-reference.md).
This is a reference bundle; the beta and all PACs are unchanged.

[Download the HCTP arm diagnostic review](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/HCTP-arm-diagnosis.zip).
Five controlled Noesis screenshots and stage geometry localize arm damage to
the reduction step in `1800` and show similar damage in `2900`. Inspection
reports cover all six new HCTP samples. This is a preview/report bundle, not
an app update or replacement PAC. See [diagnosis and evidence](../docs/arm-diagnosis.md).

[Download the 1800 Noesis review bundle](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/1800-HCTP-to-PSP-Noesis-review.zip).
This contains actual Noesis screenshots, the original YOBJ File Tool OBJ/MTL,
a separately labeled native-winding diagnostic OBJ, matching PNG/GIM textures,
and the unchanged 144 KiB beta 0.1.1 PAC. The original OBJ exporter reverses
317 native triangles; arm gaps remain visible in the previews.
See [review evidence and limitations](../docs/noesis-review.md).

[Download Wrestler Importer Windows beta 0.1.1](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/Wrestler-Importer-beta-0.1.1.zip).
This update decodes the mixed PSMT4/PSMT8 textures in the user's HCTP `1800.pac`.
It fits that source to the 144 KiB cap while retaining the unchanged RVD baseline.
[Download the 1800 test PAC and matching Noesis YOBJ/textures](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/1800-HCTP-to-PSP-beta-0.1.1-test-bundle.zip).
The 1800 export still needs PPSSPP testing; [format coverage and size fitting](../docs/texture-decoder.md) describe its reduced texture detail.

Extract and double-click `Start Wrestler Importer.cmd`. Python 3.13 is required
for this source distribution; first launch installs the pinned dependencies.
Select Blender 4.3.2 and your original PSP mesh editor in Tools & base setup.
The included Kurt base and Full Body reference are preselected. The beta uses
the working 144 KiB opacity-fix pipeline and reproduces that sample byte for byte.
See [Windows setup and beta scope](../docs/windows-beta.md).

[Download the smaller 140 KiB regional PAC and matching Noesis preview](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-region-small-test-bundle.zip).
The user reports this later regional variant does not run. It is retained for
comparison; the beta returns to the working opacity-fix build.
This is 8 KiB smaller than the 148 KiB build below.
Geometry, normals, weights, UVs, materials and texture payloads remain identical
after decoding. The savings come from joining triangle-strip records. Use
`RVD-HCTP-to-PSP-region-small-test.pac`; matching YOBJ/textures and a float-weight
Noesis fallback are included. The new regional export cap is 144 KiB.
See [checks and details](../docs/region-decimation.md). PPSSPP testing is pending.

[Download the 148 KiB regional PAC and matching Noesis preview](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-region-test-bundle.zip).
This is the preceding regional build: head 80%, torso 50%, arms/legs 35%, rebuilt
smooth normals, preserved cutout alpha and a better torso palette. It contains
1464 triangles and uses PSP U16 weights to fit the budget. Use the root PAC;
`preview` is its exact native YOBJ with textures. `preview-float` supplies the same
decoded model with float weights for older Noesis plugins. See
[regional checks and format details](../docs/region-decimation.md).
SVR 2011 PPSSPP testing of this candidate remains pending.

[Download the 146 KiB facial-detail PAC and matching Noesis preview](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-detail-test-bundle.zip).
This is the preceding appearance test: it restores eye/tooth/mouth geometry lost
in reduction, and improves the face to 128x64 with 256 colors. Body reduction
and two-influence skinning offset the extra detail to stay below the original
148.5 KiB slot size. See [details and checks](../docs/facial-detail.md).
The user confirms a better face, but reports worse body detail.

[Download the opacity-corrected 144 KiB PAC with matching Noesis YOBJ/textures](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-opacity-fix-test-bundle.zip).
This is the opacity-fixed baseline; the user confirms transparency is resolved.
The user reports that the preceding model
loads and animates in SVR 2011 PSP without crashes, but has see-through skin and
missing surfaces. This candidate changes only vertex opacity to the PSP base's
fully opaque convention. PAC size, geometry, weights, materials, UVs and every
texture byte stay unchanged. See [the opacity audit](../docs/opacity-correction.md).
Use `RVD-HCTP-to-PSP-opacity-fix-test.pac`; the matching Noesis YOBJ and named
PNG/GIM textures are in `preview`. In-game confirmation of this fix is pending.

[Download the material-corrected 144 KiB PAC with matching Noesis YOBJ/textures](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-material-fix-test-bundle.zip).
This is the preceding loading baseline. It corrects seven ordinary RVD materials
that accidentally inherited the base's blood-overlay settings and matches the
original PACs' sorted texture-table convention. The YOBJ differs from
the previous compact YOBJ in only 14 bytes; see the
[audit and validation](../docs/material-state-fix.md). The user reports successful
loading/entrance/match, with appearance defects. Extract the ZIP and use
`RVD-HCTP-to-PSP-material-fix-test.pac`.
The matching `preview/prepared.yobj` and named PNG/GIM textures are included.
An untouched copy of the supplied Kurt PAC is in `control` for testing the same
ARC-update/injection workflow before testing the converted model.

The user tests in SVR 2011 PSP using the supplied SVR 2007 PSP Kurt base.
Another 2011 base PAC is not required for the current investigation.

[Download the 144 KiB compact PAC with Noesis model/textures](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-compact-test-bundle.zip).
This older build was reported not working and contains the material-state defect
described above. It is retained for comparison. Extract the
ZIP and open `preview/prepared.yobj` in Noesis; its named PNG/GIM textures are
beside it. That YOBJ is byte-for-byte identical to the compact PAC's model.
See [compact conversion and archive checks](../docs/compact-candidate.md).
Compact playability is unverified; start from clean game archives for re-testing.

[Download the alignment-corrected HCTP RVD to PSP SVR 2007 test bundle](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-test-bundle-aligned.zip).

[Download the model with named preview textures](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-Noesis-texture-preview.zip).
Extract this preview ZIP to a folder and open `prepared.yobj` or `prepared.dae`
there. PNG/GIM textures sit beside the model under its expected texture names.
This fixes the original export's missing external image paths. Automatic YOBJ
texture loading still depends on your Noesis plugin. The aligned test PAC is
unchanged and already includes its 15 main GIM textures.

This experimental bundle includes the converted PAC, model and texture exports,
Blender review file, pose previews, reports, and installation/test instructions.
It replaces Kurt's slot using the supplied PSP SVR 2007 base. Playability has
not yet been confirmed in PPSSPP. Back up your original files and follow
`README-test.txt` inside the bundle.

The PAC is larger than the original base; the containing archive must be
repacked with updated offsets and sizes. See
[conversion status](../docs/conversion-status.md) for known limitations.

This bundle replaces the first download, which triggered an alignment warning
in PAC Editor v6.7.1. The native relocation chunk and PAC section starts are now
16-byte aligned; Windows editor verification is pending.

PAC SHA-256: `7250868aab7a728ebd7ef198421039ffbd1c2f90a42274c84be2a2f89e9e1c78`.

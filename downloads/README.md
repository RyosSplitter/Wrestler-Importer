# Test downloads

[Download the 148 KiB regional PAC and matching Noesis preview](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-region-test-bundle.zip).
This is the current appearance test: head 80%, torso 50%, arms/legs 35%, rebuilt
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

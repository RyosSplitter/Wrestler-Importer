# HCTP sample comparison and arm diagnosis

The six newly supplied PACs are all HCTP files, confirmed by the user. Comparing
them with `1800` localizes its static arm gaps to the existing Blender reduction
step. This revises the earlier suspicion that alignment or body-section mapping
was the primary cause. A reduction fix has not been implemented in the beta.

## Sample intake

All six containers and model geometries decode with the current read-only
inspectors. Internal model names are file metadata, not verified wrestler labels.

| PAC | Internal model name | Meshes | Bones | Triangles | Texture result |
| --- | --- | ---: | ---: | ---: | --- |
| 2800 | body0 | 12 | 83 | 2997 | 14 PSMT8 textures decoded |
| 2900 | rikishi | 13 | 79 | 2999 | 2 PSMT4 + 16 PSMT8 decoded |
| 2902 | rikishi | 13 | 77 | 2999 | 28 PSMT8 decoded |
| 3000 | ric2p | 13 | 71 | 2995 | 20 PSMT8 decoded |
| 3002 | ric2p | 3 | 25 | 677 | Six stored clothing textures; two declared references absent |
| 3010 | ric2p | 13 | 71 | 2995 | 20 PSMT8 decoded |

`3002` appears to be a partial clothing/accessory model rather than a standalone
body. Its materials use `g_01`–`g_06`; the model also declares `h_01` and `h_00`,
which its PAC does not contain. The beta's texture reader checks all declared
model textures and rejects this file on `h_01`. This does not establish a PS2
pixel-format decoding failure. A companion-asset workflow needs separate work.

`3000` and `3010` have identical decoded positions, UVs and triangle indices;
their PAC hashes differ. These are useful variant checks, but do not add another
independent body shape. `2900` and `2902` also belong to the same model family.

## 1800 stage isolation

The existing beta 0.1.1 output is unchanged: 147456 bytes (144 KiB), SHA-256
`340b1221ede95ed4bc5051661a35643c078274518cb56160285da275dc40c93f`.
Its saved intermediates allow inspection without rebuilding or modifying a PAC.

Three diagnostic OBJs isolate source geometry, final reduction, and final
preparation. All use native triangle winding, the same final rigid alignment,
and the same converted texture set. They are exported from decoded stage data,
not through YOBJ File Tool, to avoid that tool's known strip-winding bug.

For every screenshot, Noesis64 4.466 starts from fresh default settings. The
orientation, face-cull and shading buttons are clicked once each, in that order.
No camera movement is applied; Noesis automatically fits each loaded model.
Restarting matters because viewer settings can persist between model loads.
These are actual Noesis captures, not generated model illustrations.

- [Before reduction](../downloads/1800-arm-before-reduction.png): both arms intact.
- [After reduction](../downloads/1800-arm-after-reduction.png): arm gaps and large
  changes to the arm shape already visible.
- [After preparation](../downloads/1800-arm-after-preparation.png): those defects
  remain after body sectioning and weight transfer.

| 1800 material | Source triangles | Final reduced triangles | Retained |
| --- | ---: | ---: | ---: |
| l_ude (arm surface) | 238 | 35 | 14.7% |
| te (hand surface) | 198 | 26 | 13.1% |
| l-mune1 | 148 | 71 | 48.0% |
| l-mune2 | 168 | 86 | 51.2% |

These are texture-material counts, not bone-defined region counts. A requested
global ratio of 0.27 does not guarantee equal retention within each material.
The existing reducer protects shared vertex positions but does not check that
the arm surface or silhouette remains intact. Preserving seam vertices and
meeting the PAC size budget are insufficient quality checks.

After reduction there are 916 triangles. Every oriented triangle's positions
and material ID match the prepared model and native PSP YOBJ after the rigid
transform, including float32 serialization. Thus, the static arm damage is
already present before PSP sectioning, weight transfer or serialization. This
does not rule out separate animation/weight issues; no PPSSPP test was run.

## Additional reduction checks

The unchanged pinned Blender 4.3.2 reducer was run at ratio 0.3 on the five full
body samples. No PSP models or replacement PACs were built from these runs.

| PAC | Arm material | Source triangles | Reduced triangles | Retained |
| --- | --- | ---: | ---: | ---: |
| 2800 | tjarm | 452 | 154 | 34.1% |
| 2900 | rk_ude | 314 | 57 | 18.2% |
| 2902 | rk_ude | 314 | 57 | 18.2% |
| 3000 | ude | 414 | 93 | 22.5% |
| 3010 | ude | 414 | 93 | 22.5% |

Triangle counts alone do not prove visible damage. The extra controlled visual
check on `2900` does: [before reduction](../downloads/2900-arm-before-reduction.png)
and [after reduction](../downloads/2900-arm-after-reduction.png) show arm distortion
and additional torso/leg gaps. This pair uses the same original decoded PNG
textures and rigid alignment. The reduction failure is not confined to `1800`.

The next pipeline change should address reduction quality: preserve joints and
arm volume, allocate faces by region, and reject results that open gaps or
severely change the silhouette. Any replacement must retain the working PSP
serialization conventions and meet the PAC budget. A new successful conversion
or in-game result is not claimed here.

[Download the diagnostic review bundle](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/HCTP-arm-diagnosis.zip)
for stage OBJs/materials/textures, five controlled Noesis screenshots, sample
hashes, reduction metrics and triangle-preservation validation. This bundle is
for viewing, contains no replacement PAC, and does not update the app.

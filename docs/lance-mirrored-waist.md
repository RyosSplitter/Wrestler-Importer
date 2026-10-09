# Lance: match the left waist to the right contour

The left waistband was missing the front-side junction retained on the right.
Its torso and trunks faces stretched diagonally across that missing point. The
earlier shading/UV repair did not restore that geometry. This trial restores
the corresponding left point by reflecting the current right point across the
original source model's aligned bilateral plane.

## Local repair

- Add one seam vertex record to native mesh 53 (torso) and one to native mesh 55
  (front trunks). They share exactly the same position and dense PSP weights.
- Reflect right lower-abdominal vertex 53:5 onto existing left vertex 53:23.
- Replace four affected faces with six faces. Only the two material records
  53:0 (`l-se1`) and 55:0 (`l-pan2`) have changed primitive topology. Existing
  surrounding faces retain their original winding and ordered draw sequence.
- Mirror normals at eight existing left-side records from the corresponding
  right vertices. New and moved vertices also receive reflected normals.
- Derive the new/moved UVs from the original HCTP surface on the correct left
  side and same material, retaining the current PSP texture payloads.
- Retain every existing weight bit. New seam weights copy the right seam's
  values with right/left bone names exchanged. Both bones are already present
  in the existing palettes; the skeleton and palettes are unchanged.

The reflection direction is verified against `l_te` / `r_te` in the PSP
skeleton: anatomical left is positive X in this model's coordinate space.
The right side's vertex records are unchanged. Retained left anchors already
match their reflected counterparts to within 0.00015 model units; those tiny
original differences are retained rather than moving additional anchors.

| Property | Previous abdomen fix | Mirrored waist |
| --- | ---: | ---: |
| PAC bytes | 139,264 (136 KiB) | 139,264 (136 KiB) |
| Expanded model bytes | 196,256 | 196,848 |
| Stored BPE model bytes | 119,248 | 119,371 |
| Native meshes | 57 | 57 |
| Vertices | 2,277 | 2,279 |
| Triangles | 2,276 | 2,278 |
| Indices | 3,884 | 3,890 |
| Strips | 804 | 806 |
| Textures / material records / bones | 19 / 96 / 79 | 19 / 96 / 79 |

No mesh merge or decimation is performed. Material render properties, texture
bytes and alpha, skeleton bytes, model descriptor and existing palettes remain
unchanged. Bounding spheres contain the repaired vertices without expansion.
The writer rebuilds buffer allocations, section sizes, offsets, pointer aliases
and POF0 locations to reflect the two added records. Texture PAC sections 8 and
9 remain byte-identical. The preview YOBJ is exactly the final decompressed PAC
model. OBJ group counters in Noesis are not native YOBJ mesh counts.

## Validation

27 focused tests pass. They check the reflected contour, new topology, original
weight/vertex bits, texture/material preservation, final counts and size, and
the new seam's skinning. The strict output auditor validates palette/bone
indices, normalized weights, index ranges, allocations, sizes, pointers and
alignment. New faces retain the native front-face winding; no degenerate
geometric triangles are introduced. Both seam copies coincide exactly in all
four analytical poses (rest, elbow flex, arms up, knees bent). Reproduction
generates the identical PAC. Genuine Noesis captures use the requested three
toggles once. Detail OBJ files select waist triangles and therefore have cropped
outer boundaries; the complete model is in `waist-mirrored.obj`.

**PPSSPP testing remains pending.** This local geometry repair does not establish
the cause of the previously reported intermittent crashes.

## Downloads and reproduction

- [PAC](../downloads/1800-PSP-hybrid-mirrored-left-waist.pac)
- [Preview bundle](../downloads/1800-PSP-hybrid-mirrored-left-waist-test-bundle.zip)
- [Exact before/after report](../downloads/1800-PSP-hybrid-mirrored-left-waist-report.json)
- [Full Noesis screenshot](../downloads/1800-PSP-mirrored-left-waist-Noesis.png)

SHA-256:
`8e59fec71768b1c19bb890ceb1f66fd9735a60f8c0087b3f8a1b1b6a882335b0`

```bash
local/beta-runtime/bin/python -m tools.lance_waist_mirror \
  --source /path/to/original/1800.pac \
  --base downloads/1800-PSP-hybrid-waist-abs-fix.pac \
  --output /path/to/new-output-directory

local/beta-runtime/bin/python -m unittest \
  tests.test_lance_waist_mirror tests.test_lance_abs_fix \
  tests.test_lance_waist_fix tests.test_psp_mesh_merge tests.test_yukes_bpe
```

Inputs are hash-pinned. The beta application's conversion pipeline is unchanged.

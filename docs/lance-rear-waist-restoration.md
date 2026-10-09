# Lance: recover the rear waistband curve and its skinning

The previous mirror trial repaired the front waist but also mirrored normals
on vertices shared with the rear. It did not restore the back waistband curve:
decimation had removed six original rim points. Earlier position restoration
also retained collapse-interpolated weights at the rear seam. The center back
had approximately 42.6% root / 56.1% koshi influence rather than the original
82.35% root / 17.65% koshi profile. Those coordinates and weights no longer
represented the same original source point.

This trial retains the previous front geometry. It restores the original rear
curve and source weights mapped onto the existing PSP skeleton. No whole-body
re-rigging, texture change or additional decimation is performed.

## Exact scope

- Six original HCTP rear rim positions are restored, with one vertex record
  per point on the back torso and one on the trunks: **12 new vertex records**.
- Four existing rim-edge triangles are subdivided into 16 triangles following
  the recovered curved edge: **12 additional triangles**. Three existing
  material records are affected: 53:1 (`l-mune2`), 52:1 and 55:1 (`l-pan1`).
- **12 existing seam vertex records** receive the corresponding original
  source-to-PSP weights and smooth normals from the original surface. This
  includes all copies of the center back and two side anchors. Existing UVs,
  positions and colors stay byte-identical. The source rear rim intermediates
  and center use root 0.823529005 / koshi 0.176470995; original side anchors use
  root 0.5 / koshi 0.5.
- New vertices receive their original same-material UVs, source-mapped weights
  and original-surface smooth normals. Torso and trunks copies have identical
  positions and dense weights.
- Skeleton, palettes, bounding spheres, material render properties, texture
  payloads/alpha, model descriptor and unrelated vertex records remain intact.
- Four affected strips are rewritten using their existing opaque flags. Every
  unaffected triangle retains its winding and ordered draw sequence. All
  buffers, pointer aliases, sizes, alignment and POF0 relocations are rebuilt.
  PAC texture sections 8 and 9 are byte-identical to the previous trial.

| Property | Previous mirror trial | Rear restoration |
| --- | ---: | ---: |
| PAC bytes | 139,264 (136 KiB) | 139,264 (136 KiB) |
| Expanded model bytes | 196,848 | 198,304 |
| Stored BPE model bytes | 119,371 | 120,000 |
| Native mesh records | 57 | 57 |
| Vertices | 2,279 | 2,291 |
| Triangles | 2,278 | 2,290 |
| Indices / strips | 3,890 / 806 | 3,944 / 827 |
| Textures / material records / bones | 19 / 96 / 79 | 19 / 96 / 79 |

## Validation and limitations

31 focused tests pass, including four new rear-restoration checks. The final
decompressed PAC model passes the strict index/bone/weight, allocation,
alignment and pointer auditor. Compression round-trips exactly. Independent
reproduction produces the same PAC.

Eight analytical poses cover rest, elbow flex, raised arms, bent knees, forward
and backward spine bends, waist twist and side bend. The restored seam copies
have zero separation in each pose. New faces remain nondegenerate and preserve
their orientation relative to the skinned rest normals. The minimum normal
cosine in these checks is about 0.869, above zero.

The previous two straight rear rim edges missed the original source seam
samples by up to 0.456 model units at rest and 0.564 in the tested twist. The
restored nine-point rim reproduces those source seam positions and their mapped
skinning exactly in the analytical poses. This comparison concerns the seam
samples, not every triangle on the torso or original-game animation playback.

Genuine Noesis captures include rear rest and a rear three-quarter forward-bend
view, before and after, using the requested orientation/cull/shading toggles
once. Bend previews are analytical PSP-skeleton poses, not PPSSPP screenshots.
The detail OBJ is a selected waist section with cropped outer boundaries; use
`rear-waist-fixed.obj` for the complete model. Its YOBJ is exactly the final PAC
payload. Noesis OBJ mesh counters are not native YOBJ record counts.

**PPSSPP gameplay verification remains pending.** This trial does not establish
the cause of previously reported intermittent crashes or guarantee that every
game animation will look correct. It should replace the previous mirror trial
for the next controlled rear-waist test.

## Downloads

- [PAC](../downloads/1800-PSP-hybrid-rear-waist-restored.pac)
- [Preview bundle](../downloads/1800-PSP-hybrid-rear-waist-restored-test-bundle.zip)
- [Exact change report](../downloads/1800-PSP-hybrid-rear-waist-restored-report.json)
- [Rear bend before](../downloads/1800-PSP-rear-waist-before-bend-Noesis.png)
- [Rear bend after](../downloads/1800-PSP-rear-waist-after-bend-Noesis.png)

PAC SHA-256:
`f90f7532da39b283bdc9e1cae97aa91b1c3745aec728ea536bf4d538ddbdc844`

```bash
local/beta-runtime/bin/python -m tools.lance_rear_waist_fix \
  --source /path/to/original/1800.pac \
  --base downloads/1800-PSP-hybrid-mirrored-left-waist.pac \
  --output /path/to/new-output-folder

local/beta-runtime/bin/python -m unittest \
  tests.test_lance_rear_waist_fix tests.test_lance_waist_mirror \
  tests.test_lance_abs_fix tests.test_lance_waist_fix \
  tests.test_psp_mesh_merge tests.test_yukes_bpe
```

Inputs are hash-pinned. The beta app pipeline is unchanged.

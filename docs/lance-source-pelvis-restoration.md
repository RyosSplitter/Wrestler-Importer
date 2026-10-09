# Lance: restore the original HCTP posterior anatomy

**QA erratum:** The anatomical front/back labels in this historical analysis
were reversed. Native negative Z is **front**, and the restored `l-pan1` /
`l-mune2` surfaces are front trunks/torso. The numerical patch measurements
below describe those selected surfaces, not proof that the actual buttocks
were restored. The new [automated QA study](model-qa.md) measures the real rear
and still flags a depth deficit in this accepted PAC. The historical PAC and
patch data have not been changed. Treat subsequent posterior labels below as
historical descriptions affected by that mistake.

[Download the corrected PAC](../downloads/1800-PSP-hybrid-source-pelvis-restored.pac)
or [the complete Noesis preview and comparison bundle](../downloads/1800-PSP-hybrid-source-pelvis-restored-test-bundle.zip).
This is a controlled local repair of the newest rear-waist-restored candidate;
the beta app pipeline is unchanged. PPSSPP gameplay verification is pending.

## What the original comparison established

The original `1800.pac` is 553,728 bytes, with 2,410 UV-split vertices and 3,018
triangles. Its geometry is read directly from the uploaded PAC. Twelve matching
bone landmarks align this read-only reference into the existing PSP model space
using uniform scale 0.9848508359, a proper rotation, and translation. There is no
nonuniform reshaping or new alignment of the converted model. The full transform
is in the [JSON report](../downloads/1800-PSP-hybrid-source-pelvis-restored-report.json).
In this native space, Y increases toward the feet and negative Z is the front.

The two affected original materials are `l-pan1` (rear trunks/buttocks) and
`l-mune2` (back torso). Decimation removed interior points and replaced curved
surfaces with flatter triangles. Fixing only the waistband did not restore this
interior curvature. Retained source points in these materials already have the
original source weights mapped onto PSP bone names. Surface errors exist in the
rest geometry before any animation, so incorrect animation alone cannot explain
this discrepancy. No global axis reversal or scale mismatch was found.

Seven samples per original triangle—corners, edge midpoints, centroid—were
compared to the same-material converted surface, within the posterior body area:

| Region | Samples | Largest distance before | Largest distance after |
| --- | ---: | ---: | ---: |
| Lower back | 1,004 | 0.252293 | 0.000000197 |
| Rear hip | 181 | 0.294969 | 0.000000063 |
| Rear pelvis | 117 | 0.246303 | 0.000000046 |

Distances are model units. The inward displacement along Z reached 0.213694
on the lower back and 0.207698 on the rear pelvis. The corrected posterior
triangle sets, including their winding, exactly match the aligned source after
float32 storage. These are surface measurements, not a closed whole-body volume
measurement or proof of game animation correctness.

## Exactly what changed

- The rear trunks recover the original **47 triangles** from 31; back torso
  recovers **168 triangles** from 118. After the boundary anchor correction,
  86 already-correct posterior faces are retained. 63 simplified faces are
  replaced with 129 original faces. Native records 26:1, 53:1, 52:1 and 55:1
  receive the restored faces; existing palettes can represent all their weights.
- **48 vertex records** are added at original HCTP positions, with original
  material-specific UVs and original weights mapped by bone name. They use
  existing PSP palettes and the current opaque body color convention.
- Four lost side boundary points are inserted into adjacent retained faces:
  two on front trunks (`52:0`, `55:0`) and two on side torso (`53:0`). Each
  splits one triangle into two. These close the original posterior patch at
  its shared material joins without rebuilding the front body.
- One collapsed upper-back boundary anchor is restored from
  `(-0.01235781, -5.67771530, -1.30552018)` to the original
  `(-0.00776477, -6.01062679, -1.03181398)` on its **four existing copies**:
  `26:13`, `27:0`, `53:53`, `53:81`. This is necessary for the original back
  patch to meet the retained chest and neck surfaces. Three copies recover
  their original same-material UVs; the neck copy keeps its existing UV.
  Those four copies recover the source anchor's **100% mune weight** from
  the collapsed 21.145% koshi / 78.855% mune blend. Other existing weight bits
  are unchanged; there is no whole-body re-rigging.
- **94 existing normal records** are recalculated at the restored surfaces and
  their joins. New records also receive area-weighted shared smooth normals.
  Distant shading and every unrelated position/UV record stay intact.
- Selected triangle strips are rewritten with their existing rendering flags.
  Unrelated index sequences, palettes, bounding spheres, material state, bone
  records and model descriptor remain intact. Buffers, pointer aliases, sizes,
  alignment, offsets and POF0 relocations are rebuilt and audited.
- Every non-model PAC payload, including texture sections 8 and 9, is
  **byte-identical**. Existing texture resolution, alpha and materials remain
  intact. No additional decimation or texture reduction occurs.

The report lists every new/moved/normal vertex record, restored face, split
boundary face and changed strip. Native mesh/submesh/weight CSV audits are in
the bundle. All 215 posterior faces now carry the corresponding original
source-to-PSP weights within float32 tolerance. The front body retains its
previous reduction, apart from the shared boundary changes described above.

| Property | Newest previous PAC | Corrected PAC |
| --- | ---: | ---: |
| PAC bytes | 139,264 (136 KiB) | **141,312 (138 KiB)** |
| Expanded YOBJ bytes | 198,304 | 205,392 |
| Stored BPE model bytes | 120,000 | 122,898 |
| Native meshes | 57 | 57 |
| Vertex records | 2,291 | 2,339 |
| Triangles | 2,290 | 2,360 |
| Indices / strips | 3,944 / 827 | 4,262 / 951 |
| Textures / native material records / bones | 19 / 96 / 79 | 19 / 96 / 79 |

The PAC is below the requested **148,000-byte** cap. Size is a trial budget,
not a proven explanation for earlier intermittent crashes. OBJ/Noesis group and
material counters differ from native PSP records; no mesh-count target is used.

## Noesis views checked

Genuine Noesis screenshots were captured and inspected during the trial and
again after the final joining-point weight correction. Orientation, culling and
shading toggles are applied once, as requested. The screenshot PNGs are unedited.
All comparison views use the existing PSP-resolution texture set, including the
aligned HCTP reference, so texture resolution does not confound the shape check.

| View | Before | After |
| --- | --- | --- |
| Front | [Screenshot](../downloads/1800-PSP-source-pelvis-before-front-Noesis.png) | [Screenshot](../downloads/1800-PSP-source-pelvis-after-front-Noesis.png) |
| Rear | [Screenshot](../downloads/1800-PSP-source-pelvis-before-rear-Noesis.png) | [Screenshot](../downloads/1800-PSP-source-pelvis-after-rear-Noesis.png) |
| Side | [Screenshot](../downloads/1800-PSP-source-pelvis-before-side-Noesis.png) | [Screenshot](../downloads/1800-PSP-source-pelvis-after-side-Noesis.png) |
| Rear detail | [Screenshot](../downloads/1800-PSP-source-pelvis-before-detail-rear-Noesis.png) | [Screenshot](../downloads/1800-PSP-source-pelvis-after-detail-rear-Noesis.png) |
| Side detail | [Screenshot](../downloads/1800-PSP-source-pelvis-before-detail-side-Noesis.png) | [Screenshot](../downloads/1800-PSP-source-pelvis-after-detail-side-Noesis.png) |

The restored side/rear contour follows the HCTP reference. The front view retains
the previous appearance. The bundle contains reference images, complete OBJs,
viewing-only detail selections, and synthetic PSP-skeleton pose previews.
Detail selections intentionally omit other body regions; their cut boundaries
are not holes in the complete model. Use `source-pelvis-restored.obj` or the exact
PAC payload `source-pelvis-restored.yobj` with the adjacent PNG/MTL files.

## Validation and limits

35 focused tests pass, including four new delivery checks for source shape,
localized attributes, posed seams and the final PAC/preview bundle.

All final native indices reference allocated buffers; bone palettes reference
valid bones and have at most eight slots; weights are finite, normalized and
consistent at shared body points. The strict auditor checks internal pointer
aliases, disjoint allocations, alignment, sizes and relocations. Compression
round-trips exactly and the preview YOBJ is the decompressed final PAC model.
Independent reproduction produces the same PAC.

Twenty-two analytical poses cover rest, standing with lowered upper arms,
16 walking-cycle samples, forward bend, crouch, side bend and waist twist.
Shared local seam copies have zero separation. Restored/split faces remain
nondegenerate and do not invert relative to their skinned rest normals.
The script records pose angles and numerical results explicitly. Noesis previews
of these poses were also inspected.

**These are synthetic skeleton checks, not actual SVR 2011 animation playback.**
No game ISO, PPSSPP save-state or game animation data was available here.
Standing, walking, bending and crouching must still be checked in PPSSPP; this
trial does not establish the cause of prior crashes or arena geometry corruption.

## Reproduction

Inputs are hash-pinned. The original source is read-only; outputs require a new
folder. Use the supplied original `1800.pac`, not a previously converted PAC.

```bash
python -m tools.lance_anatomy_restore \
  --source /path/to/original/1800.pac \
  --base downloads/1800-PSP-hybrid-rear-waist-restored.pac \
  --output /path/to/new-output-folder

python -m unittest tests.test_lance_anatomy_restore tests.test_lance_rear_waist_fix \
  tests.test_lance_waist_mirror tests.test_lance_abs_fix tests.test_lance_waist_fix \
  tests.test_psp_mesh_merge tests.test_yukes_bpe
```

PAC SHA-256:
`dbe2e1e0bd1a78ac84c5c4ff5fb06cd8247aabea3f6dcf2cace34c965ac8f1e3`

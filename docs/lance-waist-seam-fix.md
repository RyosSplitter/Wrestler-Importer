# Lance Storm waistband seam repair

The circled hip/waist defect came from decimation collapsing material-boundary junctions and interpolating their UVs. Four resulting shared points had moved away from the original HCTP waist seam. At the right junction, for example, model depth changed from approximately `0.022` to `0.915`, and the front-trunks UV moved from approximately `(0.006, 0.020)` to `(0.209, 0.126)`. The defect was already present before mesh merging.

The repair restores those four junctions to original HCTP positions and restores each material's UV at the matching source point. The source is aligned read-only using the same recorded rigid fit as the existing conversion. The native PSP skeleton and existing serialized PSP weights are retained. No source weights are substituted, and the rest of the model is not repositioned.

Download the [recommended PAC](../downloads/1800-PSP-hybrid-waist-seam-fix.pac), [preview/audit bundle](../downloads/1800-PSP-hybrid-waist-seam-fix-test-bundle.zip), or [detailed change report](../downloads/1800-PSP-hybrid-waist-seam-fix-report.json). Actual Noesis views: [full repaired model](../downloads/1800-PSP-waist-seam-fix-Noesis.png), [waist before](../downloads/1800-PSP-waist-seam-before-detail-Noesis.png), [waist after](../downloads/1800-PSP-waist-seam-after-detail-Noesis.png).

## Scope and unchanged data

The recommended PAC applies the repair directly to the accepted **57-record, 136 KiB half-texture model**. The bundle also includes an optional repaired version of the 52-record mesh-merge experiment. Both have identical decoded geometry, per-bone weights, UVs, colors, normals and ordered triangles/material state after repair. The recommended version retains the smaller expanded model and separates this visual test from mesh merging.

| Measurement | Accepted baseline | Recommended repair |
|---|---:|---:|
| Native mesh records | 57 | 57 |
| Vertices | 2,277 | 2,277 |
| Triangles / indices | 2,276 / 3,884 | 2,276 / 3,884 |
| Strips / native material records | 804 / 96 | 804 / 96 |
| Textures / skeleton bones | 19 / 79 | 19 / 79 |
| Expanded YOBJ bytes | 196,256 | 196,256 |
| Stored BPE model bytes | 119,311 | 119,259 |
| PAC bytes | 139,264 (136 KiB) | 139,264 (136 KiB) |

Four geometric points are represented by **14 existing vertex records** at material/UV/palette boundaries. All copies move together. Nearby area-weighted smooth normals are updated on **61 existing records**, affecting the one-ring around the edited points. No faces or vertices are added, removed or merged. Forty triangles touch the moved junctions; none become degenerate or reverse their geometric normal relative to the baseline. The maximum normal-angle change is approximately 31.55 degrees.

Only **831 bytes** of the expanded YOBJ change, within the explicitly listed position, UV and normal fields. Headers, descriptor, mesh palettes, GE flags/strides, counts, allocations, pointer values, index buffers, material/strip metadata and POF0 bytes remain identical. Bounding spheres still contain the geometry and need no changes. Every weight byte and vertex RGBA byte is unchanged. Texture sections **8 and 9** remain stored byte-for-byte identical, including alpha. The PAC's section-2 compressed bytes, container offsets/size entries and zero padding are updated as necessary.

Rest, elbow-flex, arms-up and knees-bent analytical checks confirm **zero separation** between the duplicate records at each repaired seam. Five new fixture checks verify the exact byte-change scope, original reference points, unit normals, invariant indices/materials/weights/alpha, closed posed seams and rejection of unrecognized input hashes. Together with relevant merge, BPE and skinning tests, **23 focused tests passed**. Native allocation/index/palette/weight/relocation audits pass on the decompressed final PAC. PPSSPP runtime validation is still required; this is not a claim that prior crashes are fixed.

## Preview files

`preview/waist-fixed.yobj` is exactly the recommended PAC's decompressed model section. Open `preview/waist-fixed.obj` beside the PNGs and `preview.mtl` in Noesis; apply orientation, face-cull and shading toggles once. The full repaired OBJ reports 83 preview meshes; the native model still has 57 records. These importer counts are distinct.

`waist-detail-before.obj` and `waist-detail-fixed.obj` contain the **same 152 selected waist triangles**, at their original coordinates, for close inspection. The jagged upper/lower edges of these detail exports are selection boundaries; they are not holes in the full model. Full OBJ/YOBJ previews are also included. Diagnostic posed OBJs bake positions using the existing PSP weights; they do not contain a native animated skeleton.

`report.json` identifies every changed point, UV and normal record, all source/baseline hashes and validation. `audit/` contains complete before/after mesh, material, weight, pointer and allocation inventories. The original accepted PAC is included under `baseline/`. The optional merged variant and its report are under `optional-merged/`.

## Reproduction

From this repository with Python, NumPy and Pillow installed, using the original uploaded `1800.pac` and a new output directory:

```bash
python -m tools.lance_waist_fix \
  --source PATH_TO_ORIGINAL_HCTP_1800.pac \
  --base downloads/1800-PSP-hybrid-half-textures.pac \
  --output NEW_DIRECTORY
```

The tool pins the hashes of the original source and the two supported baselines, and refuses a different input or an existing output directory. It is a controlled Lance repair, not a general repair rule added to the beta app. The reference fit, original-material membership and exact source UVs determine the corrected junctions. A clean reproduction produces an identical recommended PAC. No Blender/editor re-export or texture reconversion is involved.

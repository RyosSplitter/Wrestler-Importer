# Lance Storm: local abdomen correction

This controlled trial starts with the 136 KiB waist-repaired PAC, retaining its
57 native mesh records. It corrects abdominal mapping and shading against the
original 1800 HCTP surface, without changing positions or the current rig.

The original body texture has some natural asymmetry. This repair removes
conversion distortion; it does not mirror or paint the anatomy.

## Changes

- Three UV records on native mesh 53 (vertices 5, 18, 23) are projected onto the
  nearest original triangle with the same material. The largest UV displacement
  is 0.040134, about 1.28 texels on the existing 32-pixel body texture.
- 82 front abdominal normal records use normalized barycentric interpolation
  of the original normals, tapered into the existing normals at the local
  patch boundary. Maximum donor distance is less than 0.15 model units.
- 739 bytes of the expanded YOBJ change. Only UV and normal fields change.
- The previous four original waistband junction positions and UVs stay intact.

| Property | Waist-fixed baseline | Abdomen correction |
| --- | ---: | ---: |
| PAC bytes | 139,264 (136 KiB) | 139,264 (136 KiB) |
| Expanded YOBJ bytes | 196,256 | 196,256 |
| Stored BPE model bytes | 119,259 | 119,248 |
| Native mesh records | 57 | 57 |
| Vertices | 2,277 | 2,277 |
| Triangles | 2,276 | 2,276 |
| Indices / strips | 3,884 / 804 | 3,884 / 804 |
| Texture names / material records | 19 / 96 | 19 / 96 |
| Bones | 79 | 79 |

Positions, weight bits, bone palettes, skeleton, all material/strip records,
index order/winding, vertex colors/alpha, texture payloads, bounding spheres,
headers, offsets, allocation sizes and POF0 relocation locations are preserved.
The model section is recompressed and PAC section offsets/padding are rebuilt;
texture sections 8 and 9 remain byte-identical.

## Validation and preview

The final decompressed PAC model passes the strict allocation, pointer,
alignment, index, bone palette and weight auditor. BPE compression round trips
exactly. Four analytical rest/elbow/arms-up/knee poses have identical vertex
positions before and after. These are structural and analytical checks, not an
in-game stability result. **PPSSPP validation remains pending.** This visual
repair does not diagnose the previously reported intermittent crashes.

23 focused tests pass, including four new delivery checks. The reproduction
command produces an identical PAC. Genuine Noesis captures use orientation,
face-cull and shading toggles once. Before/after/reference previews use the same
PSP-resolution texture files and explicit normals. Cropped detail OBJ files
include only the triangles touching the abdomen; their outer selection edges
are not missing geometry in the full model. Noesis OBJ mesh counters are not
native YOBJ mesh counts.

## Downloads

- [PAC](../downloads/1800-PSP-hybrid-waist-abs-fix.pac)
- [Preview bundle](../downloads/1800-PSP-hybrid-waist-abs-fix-test-bundle.zip)
- [Machine-readable changes](../downloads/1800-PSP-hybrid-waist-abs-fix-report.json)
- [Full Noesis preview](../downloads/1800-PSP-waist-abs-fix-Noesis.png)
- [Before detail](../downloads/1800-PSP-abs-before-detail-Noesis.png)
- [After detail](../downloads/1800-PSP-abs-after-detail-Noesis.png)

PAC SHA-256:
`e701ed84ea9388fab76c60259c07f72182dc71273a9120ed6db601068f88e41b`

```bash
local/beta-runtime/bin/python -m tools.lance_abs_fix \
  --source /path/to/original/1800.pac \
  --base downloads/1800-PSP-hybrid-waist-seam-fix.pac \
  --output /path/to/new-output-folder

local/beta-runtime/bin/python -m unittest \
  tests.test_lance_abs_fix tests.test_lance_waist_fix \
  tests.test_psp_mesh_merge tests.test_yukes_bpe
```

Inputs are hash-pinned. No beta application pipeline behavior is changed.

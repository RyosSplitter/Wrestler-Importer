# HCTP Chris Jericho: PSP hybrid trial

[Download the PAC](../downloads/0600-PSP-hybrid-Jericho.pac) or
[the PAC, Noesis preview, textures and comparison bundle](../downloads/0600-PSP-hybrid-Jericho-test-bundle.zip).
This uses the accepted Lance trial's Kurt PSP skeleton, source-derived body
weights, transferred facial weights and native float-weight/BPE workflow.
Actual SVR 2011 PSP gameplay testing is pending. This is a model trial; the
Windows beta is unchanged.

| Property | Original HCTP `0600.pac` | PSP candidate |
| --- | ---: | ---: |
| PAC bytes | 555,520 | **147,456 (144 KiB)** |
| UV-split / stored vertex records | 2,602 | 2,387 |
| Triangles | 2,981 | 2,413 |
| Native meshes | 13 | 54 |
| Texture entries | 20 | 20 |
| Skeleton bones | 77 | 79, from the PSP base |

The converted YOBJ expands to 200,688 bytes; its BPE stream is 123,138 bytes.
The compressed texture section is 17,120 bytes. The PAC is below the requested
148,000-byte ceiling and remains aligned to 2,048 bytes. No claim is made that
meeting this budget proves game stability.

## Shape, weights and reduction

Twelve corresponding bone landmarks supply one uniform scale (0.9768195507),
proper rotation and translation into PSP space. No anatomical reshaping occurs.
The whole original torso (`y2j_body`, 391 faces) and hips/tights (`y2j_mata`,
278 faces) bypass the decimation modifier and geometric welding. The eye,
teeth, mouth, scalp cutout, ponytail and top/scalp surfaces are also protected.
All protected oriented triangle positions and UVs match the aligned original
after float32 storage; their prepared hybrid weights survive serialization
within float32 tolerance. Their signatures are in the
[report](../downloads/0600-PSP-hybrid-Jericho-report.json).

The remainder uses PSP-weight regions and weighted Blender collapse. Shared
boundaries against protected surfaces are locked. Area-weighted smooth normals
are recalculated, including the shared torso/hip joins.

| Bone-weight region | Original faces | Final faces |
| --- | ---: | ---: |
| Head | 1,076 | 862 |
| Torso | 456 | 454 |
| Arms | 1,019 | 817 |
| Legs | 430 | 280 |

These regions include adjacent surfaces classified by weights; they are not
identical to texture/material names. Protected faces contribute to retention.

Original body weights map by matching bone names or named ancestors onto Kurt's
PSP skeleton. The facial region blends transferred PSP facial weights using
the original head-weight fraction. No source skeleton retarget is performed.
At most four active float influences are kept, with palettes limited to eight
slots. Source hair attachment is retained through ancestor mapping, rather
than nearest-body transfer. Kurt has no original `kami` ponytail chain, so it
attaches to `atama` and has no independent hair-bone motion. The supplied native
PSP Jericho reference also lacks this chain.

Native body-part provenance constrains buffer packing; there is no mesh-count
target. **135 byte-identical vertex records** share indices within compatible
buffers. Their positions, normals, UVs, colors and weights are identical.
Original coincident-corner faces retain distinct indices. No faces are removed
by this storage optimization.

## Textures and rendering

All source PS2 RTX3 textures decode as PSMT8 with 32-bit CSM1 palettes. They are
converted to native PSP GIM. The face keeps 128×64 indexed8 detail; most small
body maps use indexed4. Seven maps receive an additional nearest-neighbor
palette-index resolution step to 32×32 to meet the PAC budget: arm, body, eye,
head, unused beard, shin and top/scalp. Their already-converted palettes and
alpha values are unchanged by this final resolution step.

The cutout `y2j_hair` stays at its original 64×64 resolution, with **every original
decoded RGBA pixel and all 256 palette entries preserved**. Native PSP Jericho
hair materials use control `0x115`: indexed4 plus alpha flags `0x110`. This
candidate uses the same alpha flags with indexed8 control **`0x117`**. Regular
opaque materials use depth-matched `0x5` or `0x7`. Vertex alpha follows the
accepted opaque PSP body convention. PNGs are verified against final PAC GIM
payloads, including cutout transparency.

## Validation and previews

The final decompressed YOBJ passes the strict auditor: buffer allocations,
pointer aliases, POF0 relocation coverage, alignment, index ranges, bone
palettes, finite normalized weights and normalized normals. Its PSP skeleton
bytes match the original Kurt base. The auxiliary base section 8 remains
byte-identical; only model and texture payloads are replaced.

Twenty-three synthetic poses include standing, 16 walk samples, forward bend,
crouch, arm and knee poses. Coincident seam positions remain identical, all
posed positions are finite, and nonzero original torso/hip faces do not
collapse. These are analytical skinning checks, not captured game animations.

Genuine unedited Noesis captures show the final front, rear, side, standing,
forward bend and crouch, plus the aligned original geometry in front/rear/side
views using the same budgeted textures for comparison. The requested
orientation, face-culling and shading toggles are applied once. Original full
resolution source textures and an original front preview are also in the bundle.

The preview YOBJ is exactly the decompressed model inside the delivered PAC.
Front/rear/side OBJs regenerate byte-for-byte from that YOBJ. The manifest links
each screenshot to its actual OBJ, textures, YOBJ and PAC through SHA-256 hashes.
Noesis reports 87 OBJ groups, 19 loaded textures and 20 named materials; those
counters differ from 54 native meshes and 94 native material records. One of the
20 source texture entries is unused. Noesis OBJ views carry no PSP bones or
native material-state semantics and cannot prove in-game hair alpha behavior.

## Reproduce

Use the original supplied `0600.pac`, repository `assets/Kurt-Angle-Ring.PAC`,
and the supplied `yobj_mesh_editor_PSP_GUI.exe`. Source, base and editor hashes
are checked. Blender 4.3.2 and the repository CPython 3.13 runtime were used.

```bash
python -m tools.jericho_hybrid_trial \
  --source /path/to/0600.pac \
  --base assets/Kurt-Angle-Ring.PAC \
  --editor /path/to/yobj_mesh_editor_PSP_GUI.exe \
  --output /path/to/new-output --blender blender
```

The source and base are read-only; an existing output directory is refused.
The report includes alignment, region reduction, exact protected-face/UV
signatures, redirected bones, textures, pose checks and PAC hashes.

For testing, inject **`0600-PSP-hybrid-Jericho.pac`** using the same workflow that
loads Lance, rebuild/update the containing archive as required, and test
entrance, match movement and victory in PPSSPP. Open `preview/prepared.obj`
with its sibling PNGs and MTL for the Noesis rest preview.

# First conversion candidate

The supplied HCTP `0900.pac` contains `RVD1p_0100`. The first candidate replaces
Kurt's geometry and main textures in a copy of the SVR 2007 PSP base PAC.
It is not yet confirmed playable.

## Completed and checked

- HCTP geometry decoded with UV seams preserved.
- Twelve shared skeleton landmarks fitted with uniform scale, rotation, and
  translation. Scale is 1.01630064; landmark RMS is 0.114174 model units.
- Source faces assigned to nearest PSP base body sections. Palette grouping
  produces 58 chunks with at most eight bones and 254 triangles per chunk.
- Weights interpolated from nearest reference triangles and mapped by bone name
  to the target. Reference-only helpers collapse to matching target ancestors.
  Maximum four influences per vertex; pruning is reported, not hidden.
- All 2836 source triangles retained. Greedy oriented stripification reduces
  draw strips from one per triangle to 912 without losing faces or winding.
- All weights normalized, all bone references valid, and duplicate positions
  stay together in T-pose, raised-arm, and bent-elbow/knee Blender tests.
- Fifteen active RTX3 textures converted to PNG and indexed8 GIM. Every GIM
  decodes to exactly its converted source pixel indices and RGBA palette.
- Native YOBJ and DAE written using the supplied editor's inspected functions.
  Independent YOBJ re-reading checks positions, normals, colors, UV conversion,
  palettes, weights, material slots, triangle winding, and original bone bytes.
- PAC section 2 replaced with the serialized model and section 9 with the new
  named textures. Base section 8 preserved exactly; section starts and the model's
  final relocation chunk are 16-byte aligned, with total size 2048-byte aligned.
- Repacking the corrected native model reproduces the same PAC bytes.
- Twenty-seven unit tests pass. Original source/base PAC hashes remain unchanged.

Candidate: 434176 bytes, 58 meshes, 2825 sectioned vertices, 2836 triangles,
79 original PSP bones, and 15 main textures. SHA-256:

```text
7250868aab7a728ebd7ef198421039ffbd1c2f90a42274c84be2a2f89e9e1c78
```

## Alignment correction

PAC Editor v6.7.1 reported "This file has alignment issues" on the initial
candidate. Its final POF0 relocation payload had an unpadded length of 1490
bytes, leaving the following PAC sections at offsets 247298 and 254370, both
two bytes off a four-byte boundary. The corrected writer adds 14 zero padding
bytes and updates the POF0 length to 1504. Sections 8 and 9 now start at 247312
and 254384. Geometry, weights, bone records, and texture payloads are unchanged.
Regression tests cover relocation lengths and absolute PAC section alignment,
including a table whose own size is not 16-byte aligned. The corrected file has
not yet been opened in the Windows v6.7.1 GUI.

## What remains unverified

The original Kurt PAC is 180224 bytes with 29 meshes and 1488 triangles. The
candidate is larger; game allocation limits and performance need a real test.
The per-mesh caps above reflect observed format constraints/tutorial guidance,
not a measured global game budget. There has been no polygon decimation in this
candidate because each resulting chunk is already below the tutorial's approximate
per-object guidance. A lower total budget may be needed after game testing.

Section assignment uses whole triangles. Joint boundaries and unusual clothing
still need review. The bend checks exercise a Blender review rig rather than
the PSP's animation engine. Facial expressions, entrances, cloth motion, texture
orientation, transparency, and the game's reaction to the new section count
are unverified. DAE is serialized but not independently imported into Blender
(this build's Blender 4.3 has no Collada importer).

No original skeleton was retargeted or replaced. The editor bridge is tied to
the supplied executable's exact SHA-256 and CPython 3.13. Other tool releases,
source games, PSP versions, and Windows GUI execution are untested. The finished
drag-and-drop app and additional profiles are still future work.

## PPSSPP test

1. Keep a backup of the original Kurt PAC and game files.
2. Use your normal SVR 2007 PSP replacement/repacking workflow to install the
   test PAC in Kurt's slot. Use the original slot's expected filename. The PAC
   has grown, so repack with a tool that updates containing archive offsets/sizes.
3. Load Kurt in a match. Check appearance and textures before testing idle,
   walking, punches/grapples, elbow/knee bending, and entrances.
4. Report whether it loads, crashes, has texture/alpha problems, or deforms badly.
   PPSSPP error text is useful if loading fails.

The package contains the test PAC, native YOBJ/DAE, PNG/GIM textures, a Blender
review file with packed textures, pose previews, and diagnostic reports.

## External texture preview

The initial bundle's PNG/GIM exports used numbered filenames in a separate
folder, while the YOBJ texture names and DAE image references use names such as
`bn_arm` and `bn_arm.png`. The converter now also places named PNG/GIM copies
beside the native model. A separate preview download supplies these files;
all DAE image paths are checked to resolve, and the preview YOBJ and all named
GIMs match the corrected PAC's payloads. The PAC bytes are unchanged.
Open the supplied `prepared.yobj` or `prepared.dae` from the extracted preview
folder. Noesis YOBJ plugins differ in texture-loading support; the user's
Noesis preview and PPSSPP remain the visual checks for texture assignment.

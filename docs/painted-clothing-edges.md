# Painted clothing edge protection — v0.29.2

HCTP A-Train (`6400.pac`) exposed a gap in reduction protection. Its wristbands
and knee pads share maps with skin. Their border follows source triangle edges
but need not be a material split. Reduction could change the adjacent triangles
and interpolate their UVs across the painted border, turning straight bands into
diagonal, shortened shapes. Rendering both models with the original full-size
images reproduced the damage, isolating it from texture quantization.

The HCTP converter now samples original opaque images on source limb faces,
compares the median luminance of adjacent faces and retains both faces at strong
dark/light transitions. Shared edges are identified by original positions, not
native vertex indices or wrestler names. The worker receives explicit source
face selections in `painted_clothing_edge_guards`; each key includes the mesh,
material-record index, texture and triangle. Repeated strips using one texture
therefore have separate guards. Existing material, torso,
ocular, cutout, contact and attachment protections remain in force.

Each eligible face has 91 barycentric samples. A selected edge separates a face
with median luminance below 55 from one above 95, with a difference over 64.
Samples must be opaque (alpha at least 128). The scope is source bone-weight
Arms/Legs, including their hand descendants. Authored repeat UVs are honored.
These fixed thresholds target dark garments against lighter skin; they are not
automatic semantic clothing segmentation and do not cover every color scheme.
Dark limb artwork can also retain extra geometry. No source pixel, source UV,
source position or prepared weight is edited by the selection stage.

`painted-clothing-edges.json` records selections, per-texture counts, thresholds
and coverage. `reduced.json` carries the same evidence. The final QA page links
it alongside the final seam audit. The app still fits its established 152,064-byte
ring budget; additional held geometry can reduce the space available for texture
upgrades. No native validation, pose gate, head floor or size limit is relaxed.

## A-Train study

Input SHA-256: `85e3be421418d09972a20291f88dac82cea49a402a759e6fa3484931b2bbfbd5`.
The input identifies itself as `Atrain`, 3,000 triangles, 14 maps.
Kurt Angle base, Default textures reproduced the visual defect. The source-image
guard selects 160 faces at 80 edges: 46 on the arm map, 80 on the leg map and
34 on hand/boot maps. Some faces already meet existing guards. The first reduced
model grows from 2,586 to 2,626 triangles while restoring the painted borders.
Source-image leg sampling improves from p95 11.39 source texels of placement
error to 0.99 texels; original-image RGB error falls from 52.03 to 1.47/255
in the 4,000-sample diagnostic. These are analytical/CPU results, not game footage.

Source and previously exported PACs are retained. The corrected candidate is
separate and must pass serialized native structure/weight/ocular/size validation,
source-relative seams and all analytical poses before delivery. Actual gameplay
and final visual approval remain with PPSSPP testing.

Regression controls cover adjacent dark/skin faces in one material, unchanged
smooth skin, excluded head/torso regions, transparency, repeat UVs, record
reordering, repeated-strip disambiguation, immutable inputs and worker integration. The Windows HCTP conversion
also verifies guard report propagation through the frozen worker.

# WWE '13 / ch104 source feasibility study

This is an isolated, read-only study on branch `research/wwe13-ch104`.
The app, accepted HCTP/JBI pipelines, PSP writer, and accepted PACs are unchanged.
No PSP candidate has been built and no runtime compatibility is claimed.

Every technical statement below is classified by the label on its paragraph or
table row. CONFIRMED means demonstrated for this supplied file or procedural
fixture; it does not establish a game-wide format guarantee. INFERRED is a
supported interpretation needing independent verification. UNKNOWN is unresolved.

## Input and result

**CONFIRMED:** The uploaded `ch104.pac` is 9,289,728 bytes (0x8DC000), SHA-256
`2808111b6c9619cebe015bf8e05ee8cff195bee8f6d4f78bd2269fe00625ba65`.
It begins `EPAC`. Two independently valid, nonoverlapping, 2048-aligned `PACH`
containers were discovered at 0x4000 and 0x471800. They hold 15 and 14 sections.
All 29 sections have a `ZLIB` wrapper; all streams pass zlib checksums and exact
declared-output-size checks. Total expanded section data is 29,131,206 bytes.
The original input hash is unchanged after inspection.

**CONFIRMED:** Color DDS images decode in Pillow without reordering pixels or
byte swapping. The atlas has recognizable Jericho facial features and the text
`JERICHO` on the boots. A diffuse-only assembly of the main, hair/beard, and eye
shells produces a recognizable static model in front, back, side, and three-quarter
CPU previews. The PNG and OBJ previews are inspection assets, not PSP outputs.

**INFERRED:** This is a long-haired Chris Jericho source with two costume/model
bundles. The different color atlases support the costume interpretation.
**UNKNOWN:** The file alone does not authenticate the exact game/platform build,
ring/entrance roles, or the meaning of all EPAC directory fields. WWE '13 Xbox 360
is the user's supplied context, not a conclusion established merely by `JBOY`.

| Discovered bundle | Source section | Meshes | Stored vertices | Provisional strip triangles | Bones | Status |
|---|---:|---:|---:|---:|---:|---|
| 0, 0x4000 | 0 | 21 | 8,452 | 13,514 | 109 | Counts CONFIRMED; strip interpretation INFERRED |
| 0 | 10000 | 16 | 3,790 | 4,654 | 103 | Counts CONFIRMED; hair/beard role INFERRED |
| 0 | 20002 | 1 | 236 | 272 | 13 | Counts CONFIRMED; eye role INFERRED |
| 1, 0x471800 | 0 | 22 | 8,515 | 13,601 | 109 | Counts CONFIRMED; strip interpretation INFERRED |
| 1 | 10000 | 23 | 3,804 | 4,664 | 109 | Counts CONFIRMED; hair/beard role INFERRED |
| 1 | 20002 | 1 | 236 | 272 | 13 | Counts CONFIRMED; eye role INFERRED |

**CONFIRMED:** Bundle 0 has 12,478 stored vertices across 38 meshes, bundle 1
12,555 across 46 meshes. These include seam/mesh duplicates and auxiliary shells;
they are not unique welded-vertex counts. **INFERRED:** Strip decoding gives
18,440 and 18,537 triangles respectively, excluding repeated-index degenerates
but not all coincident-position/zero-area triangles. Triangle winding and source
render ordering still require an independent source renderer check.

## Container layouts

### Outer EPAC

| Absolute offset | Size | Bytes / value | Interpretation / status |
|---:|---:|---|---|
| 0 | 4 | `EPAC` | CONFIRMED signature |
| 4 | 4 | LE 0x34 | CONFIRMED value; meaning UNKNOWN |
| 8 | 4 | LE 0x8D7800 | CONFIRMED value; meaning UNKNOWN; differs from actual file size |
| 12 | 4 | LE 7 | CONFIRMED value; meaning UNKNOWN |
| 0x800 | variable | `EMD ` and ASCII directory-like records | CONFIRMED bytes; complete directory semantics UNKNOWN |
| 0x4000 | variable | first valid PACH | CONFIRMED by independent bounds/decompression checks |
| 0x471800 | variable | second valid PACH | CONFIRMED by independent bounds/decompression checks |

**CONFIRMED:** The research inspector discovers aligned signatures and validates
each candidate, rather than pretending to understand the EPAC directory. It is
not suitable as an app catalogue/parser yet. **UNKNOWN:** Directory offset/size
units, directory counts, outer padding requirements, and how alternate layouts
or compressed outer containers are represented. This file contains extensive
zero padding; archive size is not a useful prediction of PSP payload size.

### PACH and ZLIB

| Relative offset | Size | Field | Status |
|---:|---:|---|---|
| PACH+0 | 4 | `PACH` | CONFIRMED |
| PACH+4 | 4 | LE section count N | CONFIRMED, 15/14 |
| PACH+8+i*12 | 4 | LE section identifier | CONFIRMED |
| row+4 | 4 | LE offset relative to PACH+8+12*N | CONFIRMED |
| row+8 | 4 | LE stored bytes including wrapper/padding | CONFIRMED |
| section+0 | 4 | `ZLIB` | CONFIRMED |
| section+4 | 4 | LE 0x1230 | CONFIRMED value; precise version/flags meaning UNKNOWN |
| section+8 | 4 | LE compressed stream length | CONFIRMED |
| section+12 | 4 | LE expanded byte length | CONFIRMED |
| section+16 | declared compressed length | ordinary zlib stream | CONFIRMED checksum/size validated |
| stream end | 0–3 | zero padding to 4 bytes | CONFIRMED observed convention; engine requirement UNKNOWN |

**CONFIRMED:** IDs in both bundles include 0, 10, 12, 13, 14, 40, 50, 60, 61,
80, 110, 10000, 20002, 40010. Bundle 0 additionally has 40000. IDs 0/10000/20002
contain JBOY; 10/12/13/14 contain named DDS tables. Other sections contain text
hair/collision settings, animation-like `YANM`, `DUMY`, and binary data.
**UNKNOWN:** Full semantics and dependencies of those other sections. They cannot
simply be repackaged into a PSP PAC as if they were PSP-compatible.

## Source geometry and rig layout

**CONFIRMED:** `JBOY` numeric model fields are big-endian, despite LE container
and texture table fields. The inspected header is related to, but not compatible
with, the PSP YOBJ layout. Blanket whole-file byte swapping would corrupt text,
byte attributes, and nested LE structures.

| Model-relative offset | Size | Observed field | Status |
|---:|---:|---|---|
| 0 | 4 | `JBOY` | CONFIRMED |
| 4 | 4 | BE declared core byte count minus 8 | CONFIRMED bounded core; trailer semantics UNKNOWN |
| 24 | 4 | mesh count | CONFIRMED |
| 28 | 4 | mesh table pointer, origin byte 8 | CONFIRMED |
| 32 | 4 | bone count | CONFIRMED |
| 36 | 4 | texture-reference count | CONFIRMED |
| 40 | 4 | bone table pointer, origin byte 8 | CONFIRMED |
| 44 | 4 | 16-byte texture name table pointer, origin byte 8 | CONFIRMED |
| 48 | 4 | pointer into object-label data, origin byte 8 | First text decoded CONFIRMED; grouping semantics UNKNOWN |

**CONFIRMED:** The six models have 184-byte mesh records and 80-byte bone records.
Bone records contain 16-byte ASCII names, float3 local positions at +16,
float3 rotation-like fields at +32, signed parent indices at +48 and float3
global-position-like data at +64. Parent indices form acyclic hierarchies.
**INFERRED:** These are related to established YOBJ local/rest transform fields.
**UNKNOWN:** Rotation conventions, full bind reconstruction, controller semantics,
and animation interoperability for this platform have not been tested.

| Mesh-relative offset | Size | Observed field | Status |
|---:|---:|---|---|
| 0 | 4 | BE stored vertex count | CONFIRMED |
| 4 | 4 | BE draw-header count | CONFIRMED |
| 8 | 4 | BE palette length | CONFIRMED, up to 20 observed |
| 12 | up to 80 | inline BE bone references | CONFIRMED 1..bone_count; one-based interpretation INFERRED |
| 92 | 4 | BE per-vertex influence slots | CONFIRMED, 1/3/4 observed |
| 104 | 4 | vertex descriptor pointer | CONFIRMED: read BE u32 at pointer+8, then add 8 for vertex data |
| 108 | 4 | weight buffer pointer, add 8 | CONFIRMED |
| 112 | 4 | float2 UV buffer pointer, add 8 | CONFIRMED |
| 116 | 4 | float3 auxiliary-vector buffer pointer, add 8 | CONFIRMED address/shape; tangent role INFERRED |
| 120 | 4 | material/object ordinal-like value | UNKNOWN; explicitly NOT assumed to index texture table |
| 124 | 16 | shader name | CONFIRMED ASCII; full rendering behavior UNKNOWN |
| 148/152 | 4 each | parameter count/table pointer-like fields | INFERRED; parser preserves header bytes rather than interpreting bindings |
| 156 | 4 | draw-header table pointer, add 8 | CONFIRMED |
| other fields | variable | flags/grouping/bounds-like metadata | UNKNOWN; do not discard for future full IR |

**CONFIRMED:** Vertex buffer records are 28 bytes: BE float3 position at +0,
BE float3 unit normal at +12, and four byte attributes at +24. UVs are separate
BE float2 records. **UNKNOWN:** Full vertex-byte tint/alpha semantics. The CPU
preview uses white vertex tint deliberately and is not equivalent to source
shader rendering. No source values are changed by the inspection reader.

**CONFIRMED:** Each influence is eight bytes: one palette-slot byte, three zero
bytes, and a BE float weight. Slot 255 appears in unused records. Its largest
observed absolute residual is 6.332993507385254e-8; some residuals are negative.
All non-sentinel slots are in their mesh palettes, and raw per-vertex sums differ
from 1 by at most 1.1920928955078125e-7. **INFERRED:** 255 denotes unused padding,
with residuals from floating-point arithmetic. Treating every nonzero weight as
an active bone would generate false errors. The research reader preserves raw
records, tolerates only explicitly bounded tiny sentinel residuals, and rejects
significant sentinel weights and real out-of-range active indices.

**CONFIRMED:** Draw headers are 12 bytes: BE raw primitive 0x06000000, BE index
count, BE index pointer (add 8). Every decoded BE u16 index is inside its local
vertex buffer. **INFERRED:** Alternating triangle-strip assembly produces the
recognizable preview. **UNKNOWN:** Full primitive flags and culling semantics.

**CONFIRMED:** A native PSP Kurt base available locally exposes 79 bone records
through the existing native auditor. Its SHA is recorded in inventory.json.
Only 24 names match the 109-bone main source exactly, all facial controllers.
All 24 indices differ and 20 parent names differ. The source body uses names
such as `Bip Head`, `Bip L Forearm`, and extra twist/muscle helpers, whereas
the PSP base uses `atama`, `l_kote`, etc. **UNKNOWN:** Shared controller names
do not prove equivalent transforms or game animation behavior. Do not reuse
HCTP/JBI mappings by index or blindly preserve facial weights.

## Textures and materials

**CONFIRMED:** The existing bounded named-texture table reader works on these
expanded sections: LE count, marker 0x100, zero reserved word, offset 16;
32-byte rows contain name16, extension4, size4, offset4, reserved4. DDS payloads
decode successfully in Pillow. All 34 DDS payloads across both bundles decode.

| Section | Bundle 0 / 1 images | Observed formats and dimensions | Status |
|---:|---:|---|---|
| 10 | 15 / 13 | `normal` 2048x1024 DXT5; MF maps 128x256/256x128/128x512/256x256 DXT5; wrinkles 256x256 DXT5; Mask 512x512 DXT1; hair maps 256x256 DXT1 | CONFIRMED headers and decoding |
| 12 | 1 / 1 | `color` 2048x1024 DXT1, 1,392,768 DDS bytes each | CONFIRMED |
| 13 | 1 / 1 | Mask1 2048x1024, uncompressed 16-bit DDS, 4,194,432 bytes | CONFIRMED header/decoding; shader meaning UNKNOWN |
| 14 | 1 / 1 | Mask2 same size/type | CONFIRMED header/decoding; shader meaning UNKNOWN |

**CONFIRMED:** Encoded DDS bytes total 13,530,488 and 13,355,352 respectively,
including masks and DDS headers/mips. These are source allocations, not a PSP
texture-memory budget. Source shader names include `yCh_skin`, `yCh_skin_flex`,
`yCh_gear`, `yCh_Reflect`, `yCh_Aniso_trans`, and `yCh_trans`; shader parameter
strings include diffuse, normal, muscle, sweat, blood, hair shift/noise, and specular
controls. Model name tables also reference game-level resources such as
`cubemap_eyes`, `noise2`, and `sweat_bump` which are not individual images in the
observed local DDS tables. **UNKNOWN:** Exact binding, global resource lookup,
alpha-test/blend policy, and material baking requirements.

**INFERRED:** A PSP conversion can preserve much of the color atlas's appearance
by extracting UV charts and optimizing them, using the JBI atlas work as a starting
point. Normal/specular/muscle/hair effects need deliberate approximation or baking;
they cannot be reproduced by copying DDS files into PSP GIM slots. A single global
low-resolution atlas would lose much more face/clothing detail than localized
charts. Actual material/UV behavior must be verified before conversion.

## Research failures and corrections

**CONFIRMED:** Initial signature scanning found no uncompressed YOBJ/DDS data.
Following validated ZLIB wrapper records exposed the contents. No decompression
failure was worked around by truncating output or ignoring checksums.

**CONFIRMED:** A provisional interpretation of mesh+120 as a texture index failed
on valid hair meshes. It is now preserved as unknown metadata. Preview material
assignment is a documented color-only override, not a claimed source binding.

**CONFIRMED:** A naive `weight > 0`/palette check initially flagged unused sentinel
records. Inspection of raw bytes and all six models isolated tiny residuals. Real
active palette references have zero outliers. Tests retain raw residual values
and still reject significant invalid influences.

## Reproduce and verify

**CONFIRMED:** Existing `local/app-runtime/bin/python` and its NumPy/Pillow stack
were sufficient; no new runtime/dependency or environment configuration needed.
No third-party uploaded code was executed. Paths below require the owner's source;
no wrestler PAC, DDS, or geometry fixture is committed or bundled in the app.

```bash
local/app-runtime/bin/python -m tools.wwe13_inspect /path/to/ch104.pac \
  --output local/wwe13-inspection-new
local/app-runtime/bin/python -m tools.wwe13_source_preview \
  local/wwe13-inspection-new/bundle_00 --output local/wwe13-preview-new
local/app-runtime/bin/python -m unittest \
  tests.test_wwe13_inspect tests.test_pac_inspect tests.test_yobj_read -v
```

**CONFIRMED:** 27 focused tests passed, including 15 new procedural tests for
lossless decompression, truncation, expansion bounds, padding, container overlap,
declared-core bounds, index ranges, palette slots, significant sentinel influences,
unchanged tiny residuals, hierarchy cycles, metadata preservation, and no-overwrite
inspection. Real-sample checks validated all 29 streams and all six geometry
records. This is not a full platform-format or runtime validation suite.

**CONFIRMED:** [Detailed inventory](wwe13-ch104/inventory.json) records per-section
hashes and sizes, every mesh's counts/offsets/palette/weight stride/shader and
per-texture dimensions/formats. It intentionally omits raw source geometry and
image bytes. Local inspection output additionally contains lossless section
extractions, DDS/PNG images, raw-influence IR, and provisional views/OBJ/MTL.

## Recommended isolated conversion experiment

**INFERRED — proposed work, not implemented:** First complete a bounded EPAC
directory reader and verify material bindings/strip winding against a source
renderer. Then normalize source pose with one uniform scale and proper rotation,
build an explicit semantic body/finger/helper mapping to the PSP base, and test
head/jaw/eye controllers separately. Unify auxiliary shells by verified bone names
and bind transforms, never by local bone numbers. Protect hair cutouts and UV seams.
Reduce geometry using anatomical QA and preserve meaningful atlas charts, then use
the existing PSP writer, texture optimizer, PAC packer and native audits unchanged
where their contracts apply. Measure actual stored and runtime allocations against
the established PSP profile. Compare static and posed front/back/side face, hands,
shoulders and pelvis before an in-game experiment.

**UNKNOWN:** Whether a visually acceptable result fits 148,000 bytes, the required
reduction ratio, facial compatibility, hair motion, actual in-game appearance,
and runtime stability. The initial source-readability barrier is cleared; an
in-game compatible WWE '13 conversion has not yet been demonstrated.

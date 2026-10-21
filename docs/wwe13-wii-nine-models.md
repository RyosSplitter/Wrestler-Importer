# WWE '13 Wii nine-model trial and HBK facial-color regression

Work is isolated on `experiment/wwe13-wii-nine-models`. No app registration,
release binary, default texture policy, or accepted PAC was replaced. Optional
experimental behavior is added to shared helpers with legacy defaults retained.
Source-derived game assets stay in private `local/` outputs; repository tests
use procedural fixtures. See [source hashes](wwe13-wii-nine-models/sources.json)
and [candidate results](wwe13-wii-nine-models/results.json).

## Findings and confidence

**CONFIRMED:** nine uploads contain 15 independently bounded PACH containers:
Billy Gunn 1, Booker T 1, Bradshaw 2, Bret Hart 2, Jericho 1999 2, CM Punk 3,
Edge 2, Orton 1, Barrett 1. Variant indices are discovery order, not proven
ring/entrance slot IDs. WWE '13 Wii identity is supplied by task context;
filenames alone do not authenticate the source game.

**CONFIRMED:** Orton has no auxiliary section 10000 or `trans` image. The reader
must not require or invent them. CM Punk uses `Color` in one model binding while
the texture table uses `color`. Case-insensitive lookup resolves this observed
binding; case-ambiguous duplicate table names still fail.

**CONFIRMED:** Bret alternate auxiliary geometry has four material records but
three draw records. Draw material IDs, not loop indices, select material states.
Unused records remain source provenance rather than becoming phantom meshes.
Source color/UV/position buffers, skin counts, pointer bounds and hierarchy checks
are retained. Unknown auxiliary model sections are errors, never silently dropped.

**CONFIRMED:** Edge alternate auxiliary root word is `0x00070002` and root 0x38
is 2. Two 64-byte geometry headers at YOBJ offsets 0x40 and 0x80 reference shared
absolute-origin buffers. Packet 0 decodes 673 triangles bound to `color`; packet
1 decodes 441 triangles bound to `trans`. Both have valid referenced indices,
palettes, blend coefficients and unit normals; all nondegenerate source face
windings agree with source normals. **UNKNOWN:** complete semantics of these
root fields for unobserved packet/version combinations. Do not accept arbitrary
counts merely because these two layouts decode.

**CONFIRMED:** the experimental reader makes a private single-header view for each packet to
reuse the existing strict packet decoder. It normalizes root count/version words
only in that view and places the selected packet header at 0x40. Buffer offsets
and bytes remain unchanged; the original PAC is never rewritten. Mesh/vertex
provenance records the packet index, and texture IDs are remapped explicitly.

**CONFIRMED:** several repeating 128×256 hair maps use UVs at the image boundary.
The cropper's bilinear guard then asks for 129×257, which cannot fit below the
source ceiling. An opt-in fallback reuses the entire original image and original
UVs, only for bounded edge-padding cases with observed aspect ratios. Seven
corner/edge/centroid RGBA samples per triangle must still match exactly. This
does not enlarge textures, clip faces, or clamp repeat coordinates.

**CONFIRMED:** CM Punk exposed a reducer accounting mismatch: Blender's evaluated
loop-triangle count included triangles rejected by the output corner-key filter.
The opt-in `export_face_floor` counts the same position/UV/color loop identities
the exporter retains before applying the modifier. It raises retention until the
requested exported floor is met; the final floor check remains enabled. This is
not a lowered tolerance or permission to emit degenerate indices.

## Source layout supplement

**CONFIRMED in this corpus:** offsets below are relative to the inner `YOBJ`,
after the 24-byte DUMY prefix. Wii fields shown are big-endian; pointers marked
`+8` address the shared YOBJ origin, even in packet 1. PACH wrapper fields remain
little-endian, discovered containers are 2,048-byte aligned. These observations
do not establish every alignment constraint of the original loader.

| Offset | Size | Meaning / confidence |
|---|---:|---|
| 0x00 | 4 | `YOBJ` signature, CONFIRMED |
| 0x04 | 4 | Declared inner end minus 8, CONFIRMED |
| 0x08 | 4 | Observed `0x00070001` / `0x00070002`; full version/count semantics UNKNOWN |
| 0x0c | 4 | Observed header size 0x40, CONFIRMED |
| 0x10 / 0x14 | 4 each | Bone count / bone table pointer +8, CONFIRMED |
| 0x18 / 0x1c | 4 each | Material count / 20-byte table pointer +8, CONFIRMED |
| 0x20 / 0x24 | 4 each | Texture-slot count / 16-byte names pointer +8, CONFIRMED |
| 0x30 | 4 | Footer pointer; `GCTC` at value+16, CONFIRMED |
| 0x38 | 4 | Observed 1/2, correlated with geometry headers; interpretation INFERRED |
| 0x3c | 4 | Model label pointer +8, CONFIRMED |

Each observed geometry header starts at `h = 0x40 + 64*packet_index`:

| Offset | Size | Meaning / confidence |
|---|---:|---|
| h+0x08 | 2 | Position/normal record allocation, CONFIRMED |
| h+0x0c, +0x0d | 1 each | Observed attribute tags 2,7; full semantics UNKNOWN |
| h+0x0e / +0x0f | 1 each | Skin-group count / draw-record count, CONFIRMED |
| h+0x10 / +0x11 | 1 each | Observed 10,0; full semantics UNKNOWN |
| h+0x14 | 4 | Position/normal buffer pointer +8, CONFIRMED |
| h+0x1c | 4 | 20-byte skin-group table pointer +8, CONFIRMED |
| h+0x20 | 4 | 8-byte draw-record table pointer +8, CONFIRMED |
| h+0x28 / +0x2c | 4 each | RGBA-byte / signed UV buffer pointers +8, CONFIRMED |
| h+0x30 / +0x32 | 2 each | Color / UV allocation counts, CONFIRMED |

Draw record: material ID `u8`, opaque byte `u8` (UNKNOWN purpose), strip count
`u16`, strip-data pointer `u32 +8`. Each strip has a `u32` corner count then
three `u16` indices per corner (position/normal, color, UV). Position/normal
record is six signed 16-bit values: position /128; normals reorder/negate stored
components `[-4,-5,-3]/4096` then normalize. UV is signed 16-bit /1024.
Source strip parity and zero-index padding handling are inherited unchanged.

**INFERRED, not runtime-proven:** three-bone coefficients are successive lerps,
`[(1-a)(1-b), a(1-b), b]`, with `a,b = u16/4096`; two bones use `[1-a,a]`.
The new samples satisfy the existing normalization/bounds checks, but do not
independently prove Wii animation semantics. Existing bone/palette/texture/PAC
tables remain in [the earlier format study](wwe13-wii-psp-trial.md).

## Geometry and pose refinement

**CONFIRMED:** baseline body retention requests are .45 for variant 0 and .35
for other variants; Head .6, Hands .5, Mouth .6, Eyes/Hair 1. Material/chart
boundaries and incompatible source skinning domains remain protected. Ratios
are experimental requests, not exact final global triangle percentages.

**CONFIRMED stage evidence:** Billy grip area ratio increases 1.6497 source →
5.8808 reduced → 5.8432 packed. Booker increases 2.4430 → 12.7423 native.
The first substantial deviation is reduction, not serialization. Source/native
donor envelopes reject these candidates before a PAC is written. Raising Hands
retention to .75 passes the same gates for Billy, Booker, Jericho and the extra
CM Punk costumes; Barrett .75 also improves hand geometry relative to .5.
This is localized retention, not a manual shape/weight displacement.

**CONFIRMED:** keeping all hand faces alone does not fix Edge wrist flex or Bret
alternate forearm twist. Their worst triangles are in the Arms region; one spans
the forearm between incompatible motion fields after simplification. Edge Arms
.75 passes. Bret Arms .75 passes the pose gate but its measured minimum PAC is
149,504 bytes, so it is rejected. Arms .65 passes and fits. No unrelated body
ratio is lowered to make room. The candidate table records the selected settings.
**INFERRED general rule:** localize a failed pose to its actual triangles/region,
then test greater retention there. Do not assume a hand-labelled probe implies
the Hands region is responsible, or that retention monotonically fixes error.

**CONFIRMED unresolved Edge alternate:** the position-only area-normal smoother
produces a zero sum on opposing garment surfaces even when run on the full-detail
source. The initial suspicion of decimation-only volume loss was too strong.
Domain-only smoothing and a simple opposed-normal seam experiment do not resolve
all affected corners. A separate `--source-normals` experiment transports source
FLOAT_VECTOR CORNER normals through Blender and renormalizes them after reduction;
it gets past smoothing and native pose gates. However, the resulting extra normal
corners/compressed data make the smallest PAC 180,224 bytes. No PAC is released.
No arbitrary fallback normal, inward/outward displacement, or budget bypass is
used. This remains a format/normal-preservation and size-fitting research case.

## HBK in-game discoloration: do not dismiss as preview lighting

The user confirmed the latest entrance geometry is acceptable but its face is
severely discolored **in-game**. This supersedes the earlier report limited to
offline comparisons. **CONFIRMED:** the face-bearing crop was 32×32 /32 useful
colors, while its source chart is 273×273 and the face occupies only part of it.
**INFERRED:** under-resolution and quantization contribute to the reported effect;
they are not proved to be its only runtime cause. No warm tint is applied.

**CONFIRMED:** the first 64×64 /64-color trial improves the main facial region but
increases another cranial/neck region's p95 Lab error 11.709 → 13.237. That trial
is not promoted. The selected regional-color-guard trial retains the neck, eye,
hair and other unchanged GIMs exactly, upgrades the main face page to 64×64 /32
colors, and reduces one clothing page 64×64 → 32×32 /16 to pay for it.

Main facial p95 Delta-E76 improves 14.717 → 13.592; maximum local tile Lab bias
9.162 → 6.673. The neck metrics are byte-equivalent. The face still exceeds the
new provisional review threshold: this is an improved test candidate, not a
claim that discoloration is fixed. Native body/ocular/hand replay passes again.

PAC: 147,456 bytes, SHA-256
`cef485d3e6f60f6314fda1f8527b47535c9c4ddb4160ca2775c2f8e41e6ae3a8`.
Expanded YOBJ remains byte-identical, SHA-256
`503687950984889149d3a2c596ad11cda00b888518552419fbe5bcfd36406110`.
Only texture section 9 changes; model section 2 and retained section 8 are exact.
Original baseline is preserved. Shape, rig, UVs, normals and all weight bytes are
unchanged. The source/before/after pictures use identical unlit CPU lighting.

## Separate facial texture QA

`model_qa.texture_color` extracts front-facing cranial UV coverage from verified
head ancestry, excludes pure eyeball/separate hair surfaces, and compares decoded
GIMs against the original source at those UVs. No vertex-index correspondence
between LODs is assumed. Source-relative RGB errors, D65 Lab Delta-E76 and local
tile color biases expose localized hue loss that global means can cancel.
The sRGB/D65 interpretation is an **INFERRED diagnostic convention**, not a
demonstration of either game's gamma/shader behavior.

Thresholds (p95 Delta-E76 >12 or local tile bias >8) are **provisional review
heuristics**, motivated by this known failure, not calibrated acceptance limits.
They flag both the original failure and remaining loss in the improved candidate.
The report never prescribes a universal skin tone, recolors a texture, or calls
an uncovered region a zero-error pass. The nine-model outputs receive read-only
facial-color reports; these do not silently rewrite their textures.

**CONFIRMED:** the guarded texture experiment rejects a candidate that worsens either measured
cranial color region beyond .01 metric units relative to its tested baseline.
Pure-eye identity is recovered from original source atlas provenance, because
compatible donor transfer can reduce eye-bone amplitudes below a post-transfer
"pure eye" classifier's threshold. It preserves that existing eye GIM exactly.
This experiment remains separate from the accepted app texture behavior.

## Results, limitations and reproduction

**CONFIRMED:** 14 experimental PACs, covering all nine main variants and five
additional costumes, pass native structure, pointers/offsets/alignment, indices,
bone palettes, influence bounds, texture-memory envelope and analytical replay.
Every exported PAC is 147,456 bytes. Model, decoded texture and final PAC hashes
are tied to Noesis OBJ/MTL/PNG exports and full body/head comparison QA reports.
**UNKNOWN:** actual PPSSPP stability, animation/controller semantics, blood and
spring-hair behavior. Source dynamic blood overlays are explicitly excluded;
Wii lighting/normal/specular shaders are not emulated by the PSP approximation.

Source-fidelity review findings remain in every candidate, including recurring
opposed head-fold/winding findings, hand/foot and garment shape differences, pose
errors and facial texture loss. A native/serialization pass is not a clean QA
approval. Read metrics and comparison renders rather than ranking only flag
counts. The 54,016-byte pixel/CLUT envelope is a conservative native-base
observation, not a demonstrated universal SVR limit or total peak game heap.

```
python -m tools.wwe13_wii_corpus_trial OWN_SOURCE.pac --base OWN_BASE.PAC \
  --variant 0 --hand-floor .75 --out NEW_WORK
python -m tools.wwe13_wii_export NEW_WORK --base OWN_BASE.PAC --out NEW_EXPORT --unlit
```

Use the per-candidate configuration table for exact ratios. Do not overwrite an
existing work directory. A failing build intentionally retains diagnostic files
and withholds the PAC. QA compares full-detail Wii geometry already adapted to
the PSP reference pose against the final PAC with 6,000 surface samples per
direction, rest +14 body poses, cranial controller probes and hand stress tests.
This does not reproduce actual Wii or PSP animation clips.

HBK texture-only trial, after reproducing the earlier gentler entrance baseline:

```
python -m tools.wwe13_wii_face_texture_trial BASELINE_WORK --base OWN_BASE.PAC \
  --regional-color-guard --out NEW_TEXTURE_WORK
```

**CONFIRMED regression evidence:** the generic corpus loader reproduces the old
HBK source meshes, weights, UVs, bones and source pixels exactly for both variants.
The final repository suite passed **573 tests**; **154 focused checks** also
exercise the new paths, including normal transport in actual Blender.
Procedural tests cover absent auxiliary models, case collisions, draw IDs,
unused materials, multi-packet private views, repeat boundaries, source ceilings,
local color errors hidden by global means, alpha handling and opposed normals.
Final test logs and every private export's file manifest accompany the test pack.

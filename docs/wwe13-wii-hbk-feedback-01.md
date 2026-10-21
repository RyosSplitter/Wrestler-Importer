# HBK Wii feedback iteration 01

**User baseline:** ring geometry was accepted visually, but the face received too
much of the effective texture budget and the other images looked smeared. The
entrance model was not accepted. Neither accepted app behavior nor prior PACs
are overwritten. Work is isolated on `experiment/wwe13-wii-hbk-refinement`.

## Ring: change textures only

**CONFIRMED:** all stored PAC sections except section 9 compare byte-for-byte,
including the complete model section 2. Expanded YOBJ hash remains
`8e2d8637bae783021f51d7ef6875938e878ba100bd554f74fec71de7f6920487`.
Thus geometry, normals, UVs, topology, materials, skeleton and effective skinning
remain exactly the user-tested ring baseline. Native structural/bounds/size and
analytical body/eye/hand replay were checked again. Baseline numerical geometry
QA is retained with explicit provenance, not relabeled as a run on new textures.

**CONFIRMED:** the previous Wii experiment always requested the maximum useful
color count available in a T8 palette. It unnecessarily coupled high color
capacity with the available resolution budget. These experiments already use
BPE on textures losslessly; the useful tradeoff is resolution versus lossy color
quantization, not choosing which pictures get archive compression.

The separate candidate factory now explores 16, 32, 64, 128 and 256 useful colors
independently of observed source-bounded T8 dimensions. The physical GIM CLUT
remains 256-entry RGBA32; unused entries are padding, not useful source detail.
Using fewer colors can improve BPE compression enough to fit a larger index plane.
All upgrades still measure actual serialized PAC bytes and the observed native
54,016-byte texture pixel/palette envelope. No PSP format/material changes occur.

**INFERRED tuning choices:** remove the opaque head 64-axis floor, multiply the
head-bearing page's importance by .65, ordinary pages by 1.25, and independently
identified eye surfaces by 1.5. Eye detection uses area-weighted native eye-bone
mass >.9, not an image name. Eye crops retain their source dimensions and request
at least 64 useful colors when source usage permits. Hair keeps per-level source
alpha and source useful-color ceilings. Scoring remains heuristic; these choices
are for visual feedback, not a proven optimum or a new app default.

| Crop | Previous | Revised |
|---|---|---|
| Head-bearing | 64×64, 256 used colors | 64×64, 16 used colors |
| Torso | 32×32, 256 | 64×64, 16 |
| Back/boots | 32×32, 256 | 64×64, 16 |
| Tights designs | 32×32, 256 | 128×128, 16 |
| Iris | 32×64, 214 | 32×64, 58 used / 64 requested |
| Hair | 32×64, 125 | Byte-identical GIM |

**CONFIRMED:** final ring PAC is 147,456 bytes, SHA-256
`a2d3b0a58b34c2841d65c473aa9343dbebc002954606762aa18baa1f20ae9b80`.
Pixel/palette allocation including retained base textures is 45,248 bytes.
Tights fine-feature loss falls .721 → .095; torso .686 → .386; back/boots
.694 → .421. These are deterministic occupied-area metrics, not game proof.
Renders show readable clothing outlines/logos. Smaller palettes cause some skin
posterization: this tradeoff is explicit and needs user/game review.

Reproduce with the previous work directory and the owner's PSP base:

```
python -m tools.wwe13_wii_texture_refine PREVIOUS_RING_WORK --base OWN_BASE.PAC --out NEW_RING_WORK
```

## Entrance: geometry experiments remain separate

**CONFIRMED rejected experiment:** nearest-source projection constrained to the
same original UV domain/material moved 545 records and worsened overall rest
surface p95 from .009982 to .011856 of height. Most torso/pelvis/foot metrics
worsened. The candidate is retained privately for diagnosis and is not promoted
or included as the recommended download. **INFERRED:** moving coarse vertices
onto a source surface cannot recover missing faces and can worsen the interiors
of the remaining triangles; it is not a substitute for silhouette-aware LOD.

**CONFIRMED promising experiment:** increase requested Torso/Arms/Legs retention
from .22 to .35, retaining Head .6, Hands .5, Mouth .6 and Eyes/Hair 1. Atlas
material boundaries remain protected. No manual displacements or projection are
used. The new texture candidate factory makes room for the extra geometry.

The revised model has 3,159 triangles versus 2,987. It fits 147,456 bytes and
passes native structural, bounds, bone-palette and analytical replay/hand gates.
Source-texture renders isolate geometry from the simultaneous texture change.
Overall rest p95 falls .998% → .440% of source height; waist 2.637% → .426%,
pelvis 2.264% → .492%, buttocks 1.383% → .395%. All previously passing p95
regions remain below the existing threshold across rest and 14 analytical poses.
No absolute p95 increase exceeds max(5% relative, .025% height).

**Unresolved:** still not QA-approved. Six high-review shape findings remain
(pelvis, shoulders, hands, feet). The 70 report flags versus 54 include 15 new
insufficient-sampling chin coverage flags; do not silently waive them. Some
pose-extra findings are new because rest improved more than posed error; for
example crouched pelvis absolute p95 improves 2.299% → .932% while still
exceeding the pose-extra threshold. Actual source/PSP animation semantics and
PPSSPP runtime remain unverified. Baseline acceptance still requires user testing.

Reproduce the gentler candidate with the owner-supplied original Wii sample:

```
python -m tools.wwe13_wii_entrance_refine OWN_CH145.pac --base OWN_BASE.PAC --out NEW_ENTRANCE_WORK
```

Then run the separate QA stage against `charted.json`, with 6,000 samples per
direction, 128-pixel diagnostics, all body/cranial poses. Existing reproduction,
format and source-weight interpretation limitations remain in
[wwe13-wii-psp-trial.md](wwe13-wii-psp-trial.md). Numeric decisions and metrics
are in [wwe13-wii-hbk-feedback-01](wwe13-wii-hbk-feedback-01).

## Dull/gray appearance in comparison images

The user located this symptom in the comparison images, rather than reporting
an in-game result. The initial explanation over-attributed it to palette
reduction; checking the actual colors did not support a grayscale conversion.

**CONFIRMED:** the offline preview multiplies sampled RGB by
`.4 + .6 * abs(N dot L)` (`desktop/preview.py`). This neutral directional
lighting can darken the diffuse texture substantially. An unlit diagnostic of
the exact same PAC removes that multiplier, with no color tint or texture edit.
It uses a disposable display copy with camera-light-aligned normals; that copy
must never be serialized. Positions, UVs, alpha and texture sampling are retained.
Production preview defaults and actual model normals remain unchanged.

**CONFIRMED limited color check:** mean RGB over source-occupied warm pixels
(R > G+10, G > B+8, R < 2G, G < 2B) stays close to the source. Rounded means:

| Crop | Source | Previous encoded | Revised encoded |
|---|---|---|---|
| Head | 119.84, 77.87, 55.58 | 118.82, 77.07, 55.24 | 118.19, 76.70, 56.04 |
| Torso | 131.62, 82.59, 59.91 | 131.02, 82.16, 59.67 | 131.83, 82.28, 59.84 |
| Back | 136.43, 85.38, 64.03 | 136.10, 85.03, 63.79 | 136.23, 85.06, 64.48 |

This checks overall color bias, not local fidelity: the 16-color skin images
still have visible posterization. **INFERRED:** preview lighting contributes to
the reported dull appearance. **UNKNOWN:** the exact perceived contribution of
lighting versus palette banding, and appearance under actual PSP game lighting.
The CPU preview does not emulate the original Wii skin/material shader.

**CONFIRMED tests:** 117 focused tests passed across Wii readers/model adapter,
texture candidates/allocation, BPE, materials and the new unlit diagnostic. The
diagnostic test reproduces a known solid texture color within one byte value
and verifies that the input model is not mutated. Native format and analytical
pose results for the candidate PACs are separate evidence, not game validation.

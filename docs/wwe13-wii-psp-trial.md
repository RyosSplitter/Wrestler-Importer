# WWE ’13 Wii ch145 → PSP experiment

This experiment lives on `experiment/wwe13-wii-hbk-psp`. It is not app support,
not an accepted conversion, and not evidence of an in-game pass. No production
converter, packaging implementation, or accepted HCTP/JBI PAC was changed.
The two variants are independent outputs, not a single combined costume PAC.

Classification throughout: **CONFIRMED** means checked binary/math behavior on
this supplied sample; **INFERRED** means a supported interpretation; **UNKNOWN**
means not independently established. A confirmed structural check is not a
confirmed game compatibility claim.

## Inputs and scope

- **CONFIRMED:** `ch145.pac` is 585,728 bytes, SHA-256
  `feeea42460893cf577b3aa2ffadb239462538be18e822e33d051e096445df542`.
- **CONFIRMED:** its two PACH containers start at `0x4000` and `0x48000`.
  IDs 2 and 10000 contain separate body and transparent models. ID 9 contains
  TPL textures. See [container/texture study](wwe13-wii-ch145-study.md).
- **INFERRED:** the visually identified HBK black outfit is the ring variant;
  the red outfit is entrance gear. These are filename conveniences, not a
  decoded original-game costume-selection rule.
- **CONFIRMED:** the owner-provided native PSP base used here is
  `Kurt-Angle-Ring.PAC`, SHA-256
  `bf935a51fe30bfd2df929f8eb9e50be5d793426ea05125ca9411ce21b19ead80`.
  Its observed indexed pixel/CLUT allocation is 54,016 bytes including retained
  section 8. This is a conservative comparison envelope, not a proven heap cap.
- **UNKNOWN:** outer EPK costume-selection semantics, source-game execution of
  skin controllers, complete TEV/material behavior, and actual PSP runtime heap.
  The trial reader therefore pins the inspected source hash and variant index.

## GCTC geometry continuation

All offsets below are relative to YOBJ after its 24-byte DUMY prefix. Integers
are big endian. Pointer values are relative to YOBJ + 8. These observations are
**CONFIRMED** for all four body/trans model payloads in this PAC. They are not
claims that every Wii model uses this layout.

| Offset | Bytes | Observed meaning |
|---|---:|---|
| `0x18` | 4 | Material/draw-group count (not texture-name-slot count) |
| `0x1c` | 4 | Pointer to 20-byte material headers |
| `0x20`, `0x24` | 4 each | Texture-name-slot count and 16-byte-name table pointer |
| `0x48` | 2 | Position/normal record capacity, including zero padding |
| `0x4c`, `0x4d` | 1 each | Observed 2 and 7; attribute convention / position fractional bits |
| `0x4e`, `0x4f` | 1 each | Skin-group count and draw-group count |
| `0x50` | 1 | Observed UV fractional bits 10 |
| `0x54` | 4 | Pointer to packed 12-byte position/normal records |
| `0x5c` | 4 | Pointer to 20-byte skin-group records |
| `0x60` | 4 | Pointer to 8-byte draw-group records |
| `0x64` | 4 | Two values with UNKNOWN semantics; not used to invent geometry |
| `0x68`, `0x6c` | 4 each | Color-array / UV-array pointers |
| `0x70`, `0x72` | 2 each | RGBA8 color count and signed-i16-pair UV count |

**CONFIRMED:** positions are the first three signed i16s / 128; UVs are signed
i16 pairs / 1024. The last three i16s have near-unit length when divided by
4096. **INFERRED:** convert their axes as `[-stored4,-stored5,-stored3]`;
this gives positive geometric-winding agreement on every nonzero tested source
triangle across all four models. The initially assumed direct XYZ basis gave
approximately 50% agreement and was rejected. Wii runtime lighting was not
independently emulated.

**CONFIRMED:** every draw-group record has a material byte, a u16 strip count
at +2 and a pointer at +4. Each strip is a u32 count followed by count triples
of u16 position/color/UV indices. Ordinary alternating strip parity is used;
repeated-position degenerates do not become output faces. All corner indices
are checked against their own attribute buffers. Each material block ends at
the next pointer. Source UV/color corners are independent from position IDs.

**CONFIRMED:** material headers point at +16 to a 72-byte state; its u16 at +70
selects a texture-name slot. Repeated `color` names in that table are not extra
meshes. Body/trans bindings were decoded rather than inferred from mesh order.

## Skin groups: two discoveries that matter

**CONFIRMED:** a group starts with three u16 bone IDs (unused = 0xffff), u16
width 1–3, u32 vertex count and u32 coefficient pointer. Its final four bytes
remain **UNKNOWN** and are retained as provenance. Rigid groups imply weight 1.
Other groups have two u16 coefficients per vertex, each in [0,4096].

**CONFIRMED:** all-zero 12-byte position/normal records are unused allocation
padding, sometimes in the middle of an array. Groups consume the sorted
nonpadding referenced positions. Assigning weights sequentially through those
padding records shifts subsequent bone assignments and is incorrect.

**INFERRED:** with `a=A/4096`, `b=B/4096`, the coefficients are successive lerps:

```
1 bone:  [1]
2 bones: [1-a, a]
3 bones: [(1-a)(1-b), a(1-b), b]
```

The flat `[a,b,1-a-b]` hypothesis produces 1,243 negative remainders across
the four source models and is rejected. Reproduce the numerical hypothesis
search with `python -m tools.wwe13_wii_weights OWN_CH145.pac --out NEW.json`.
Cross-body/trans/costume evidence contains 171 coincident-position pairs with
different palettes/codes. The selected formula gives 48 agreements within .001,
versus 31 for the next distinct candidate in the searched family; many other
pairs legitimately have different costume skinning. These differences are not
averaged or welded. This is strong consistency evidence, not original-runtime
proof. `blend_weights` has procedural coefficient, normalization, ordering and
boundary tests. Preserve raw coefficient records for future runtime verification.

## Conversion and rejected trials

1. **CONFIRMED:** decode both body and transparent geometry; unify bones by name
   only after verifying common world binds (maximum difference zero here).
   Body has 88 bones, transparent model 110. Keep independent corner identity.
2. **CONFIRMED:** body/trans textures decode from source CMPR and C8/RGB5A3.
   Use ordinary opaque PSP vertex tint, retaining original shader color bytes
   as provenance; transparency comes from the actual trans texture.
   **INFERRED:** those source color alpha bytes serve shader-specific purposes
   and cannot be blindly multiplied into PSP body opacity.
3. **CONFIRMED:** six source triangles with >.98 average eye-bone mass get a
   separate binding to the exact same source color atlas. Whole-triangle UV
   charts crop original context without resampling; seven barycentric samples
   per triangle verify RGBA equivalence. This preserves tiny irises that became
   blank when their surrounding 260-pixel atlas crop was reduced to 32 pixels.
   Texture extraction does not move vertices or invent higher source detail.
4. **CONFIRMED:** existing isolated Biped→PSP adapter supplies uniform .1 scale,
   pelvis translation, minimal arm/leg segment rotations and finger-landmark
   hand orientation. Explicit role/name mapping and nearest mapped ancestors
   produce the native 79-bone rig. **INFERRED:** missing hair spring controllers
   may attach to the head ancestor; source dynamic hair is not reproduced.
5. **CONFIRMED:** native donor eye pivots were too far forward for this head;
   synthetic eye turns exceeded the donor envelope. Four eye/lid controller
   origins are fitted to decoded, scaled source world binds, retaining native
   controller axes/parents and all nonocular bind bytes. Selective ocular
   transfer retains source-supported roles, protects jaw/body mass, and does
   not add eyelid roles to rigid eyes. Subsequent native ocular envelopes pass.
   **UNKNOWN:** whether real SVR animation-controller semantics agree perfectly.
6. **CONFIRMED:** full ring model alone BPE-compressed to 170,092 bytes before
   textures, so full geometry cannot fit this 148,000-byte trial profile.
   Moderate reduction also failed before further tuning. Existing Blender
   regional weighted collapse and smooth-normal recomputation are reused.
   Eye/hair faces retain ratio 1. Face/hand/mouth floors are reported explicitly.
7. **CONFIRMED:** decimating across new atlas-material boundaries made visible
   black wedges at waist/wrists. Restoring UVs from the nearest same-domain
   source surface did not fix those artifacts and was rejected. Splitting
   regional reduction buffers by material lets the reducer's existing shared
   position guard protect chart boundaries. This removes visible wedge artifacts.
   Splitting every UV-connected component preserved too much fragmented entrance
   geometry, failed size fitting in some trials, and worsened some metrics.
   Material-boundary mode was selected; neither method changes production.
8. **CONFIRMED:** existing packer limits vertices to four active influences and
   triangles to eight-bone palettes, with identity-aware seam consistency.
   Collapse can create extra influences: maximum removed mass is recorded in
   `packed.preparation_report`, not claimed to be exact source skinning.
   Tiny bounded position/UV/normal precision fitting remains within existing
   error gates; topology/weights are not changed by that precision step.
9. **CONFIRMED:** native bounds spheres must enclose new geometry. Only listed
   nonshrinking radius floats at bone-record +76 change; centers and axes stay
   native. An independent allowlist checks every bone byte: reported ocular
   +16..27 positions and reported +76..79 radii are the only exceptions. The
   production byte-identical-base-skeleton guard remains unchanged.
10. **CONFIRMED:** serialize through existing PSP writer, short-palette padding,
    GIM writer, BPE compressor and PAC packager. Only section 2/9 payloads are
    replaced. Unrelated retained stored sections must compare byte-for-byte.
    POF0/pointers/alignment/allocations/indices/palettes/weight sums are audited.
11. **CONFIRMED:** all output texture candidates are source bounded, observed
    native T8 dimensions with 256-entry RGBA32 CLUT envelopes. Useful allocated
    colors are capped by actual source RGBA usage. Fractional hair alpha levels
    are preserved at nearest-resampled sample positions; RGB is quantized per
    alpha level. Opaque charts with >15% head-weighted surface retain at least
    a 64-pixel axis where the source permits it; tiny eye charts retain their
    source-bounded 32-pixel axis. Hair has a separate alpha-preserving candidate
    floor instead of consuming the face safeguard budget. There is no binary-alpha bake. The allocator measures actual
    GIM/BPE/PAC bytes and retains the observed base texture-memory envelope.
12. **CONFIRMED:** read back the final PAC; verify attribute/weight correspondence
    and analytical body/ocular replay. Independent digit, grip, wrist and twist
    tests must pass the source/native donor reference envelope. Run the separate
    comparison-only QA suite against full-detail Wii geometry already adapted to
    the same PSP reference pose. Keep every review finding.

**CONFIRMED:** ring body material 5 is a 254-triangle source blood overlay, not
ordinary skin. It is excluded from the static trial to avoid permanent blood.
Source totals including that overlay are 5,933 triangles; the ordinary static
reference has 5,679. Entrance body+trans reference has 5,936 triangles. Dynamic
blood behavior is **UNKNOWN/unimplemented** in this Wii trial.

## Reproduction (owner supplies both files)

Run with the existing compatible Python dependencies and Blender 4.3.2 available.
Never reuse an output directory; every experiment keeps earlier attempts.

```
python -m tools.wwe13_wii_trial OWN_CH145.pac --base OWN_KURT_BASE.PAC \
  --variant 0 --ratio .45 --material-only --out NEW_RING_WORK
python -m tools.wwe13_wii_trial OWN_CH145.pac --base OWN_KURT_BASE.PAC \
  --variant 1 --ratio .22 --material-only --out NEW_ENTRANCE_WORK
```

Run `model_qa.pipeline.run` on `charted.json` and the resulting PAC with
`samples=6000, resolution=128, animations=True, renders=False`. This runs all
numerical/regional/body/head-controller tests; textured comparisons and clay
heatmaps are generated by the exporter, not by pretending to run Noesis.

```
python -m tools.wwe13_wii_export NEW_RING_WORK --base OWN_KURT_BASE.PAC --out NEW_RING_EXPORT
python -m tools.wwe13_wii_export NEW_ENTRANCE_WORK --base OWN_KURT_BASE.PAC --out NEW_ENTRANCE_EXPORT
python -m unittest tests.test_wwe13_wii_model tests.test_wwe13_wii_inspect
```

The exporter rejects a PAC whose hash differs from the build, whose model differs
from the audited YOBJ, whose metadata/replay checks fail, or whose QA references
a different PAC hash. Preview YOBJ is the exact expanded section 2. OBJ/MTL/PNGs
are static Noesis-previewable exports. Images are explicitly CPU renders.

**UNKNOWN:** loading/animation/stability in SVR 2011 PSP until the owner tests.
Do not integrate this into the app, claim a clean QA pass, or replace accepted
HCTP/JBI baselines merely because native checks pass. The old QA report's generic
HCTP wording is inherited; actual source input paths/hashes identify Wii data.
See the numeric result supplement and private test bundle for remaining findings.

## Selected results (CONFIRMED binary/math, not in-game validation)

| Variant | PAC bytes | Static source → final triangles | Final vertices / buffers | Texture count |
|---|---:|---:|---:|---:|
| 0 (ring) | 145,408 | 5,679 → 3,242 | 3,296 / 60 | 6 |
| 1 (entrance) | 147,456 | 5,936 → 2,987 | 3,328 / 53 | 6 |

These counts are independent corner/serialized records, not assumed one-to-one
position correspondence. Both are sector aligned and below 148,000 bytes.

- Variant 0 SHA-256 `d46e6164939767d4339841cdc638a85fb249f0cfc1d7b4e20dd759780b23283e`. Bidirectional rest surface p95 is 0.477% of reference height. 47 QA findings retained; maximum pack-pruned weight mass 0.00946794.

- Variant 1 SHA-256 `46539c2ea1affe1bd27662f33c6350b71230d3d319a0d65922608d9bd288eed2`. Bidirectional rest surface p95 is 0.998% of reference height. 54 QA findings retained; maximum pack-pruned weight mass 0.06319774.

The 105 focused tests cover procedural Wii textures/geometry/skin coefficients,
source identity, rig adaptation, GIM generation, native precision/skinning,
accessory packaging and BPE. Native serialization/body/ocular replay and the
independent finger/reference-envelope gates pass for both selected PACs.
The full comparison suite retains shape, material-boundary, opposed head-fold,
and coverage findings. It does not declare either model QA-approved. Regional
and pose metrics, exact texture choices, hashes, and useful-color ceilings are
in [ring-result.json](wwe13-wii-psp-trial/ring-result.json) and
[entrance-result.json](wwe13-wii-psp-trial/entrance-result.json). The private owner
bundle additionally contains full HTML/JSON QA, heatmaps and textured renders.
No game-derived geometry or textures are committed to the repository.

Display-only ROI renders clip crossing triangles with interpolated corner
attributes. Dropping whole crossing faces made coarse-LOD crops show artificial
holes; that rejected display method must not be mistaken for missing PAC faces.
This clipping never touches PAC/YOBJ or Noesis OBJ exports.

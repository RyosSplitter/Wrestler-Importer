# Edge texture refinement, round 4

**CONFIRMED — user feedback:** The user tested hair trial **A (Nearest Alpha)**
and approved its hair, while finding the other textures inadequate. A is the
immutable starting point, SHA-256
`a793f19d73a76300560dd3a82e7faa3e6ab6295a9acac7747d35c9224fb480b4`.
Approval of the hair is not an endorsement of the old body textures.

**CONFIRMED — scope:** This is a separate texture/storage experiment. No
production converter, application default, packaging implementation, geometry
reduction, weighting or main branch was changed. UV-layout changes were
considered but were not performed. No existing accepted/test PAC was replaced.

## Actual bottleneck

**CONFIRMED — stored allocations in A:**

| Stored section | Bytes |
| --- | ---: |
| Main YOBJ, section 2 | 128,003 |
| Existing effect table, section 8 | 7,072 |
| Costume textures, section 9 | 16,117 |
| Final aligned PAC | 151,552 |

The configured cap is **152,064 bytes**, whose largest 2,048-byte-aligned output
is 151,552. Section 9 starts at 135,120, leaving 16,432 bytes before that aligned
boundary. Only 315 bytes remain after its current payload. Simply trying the
existing monotonic texture upgrader cannot buy an upgrade: the first diagnostic
reproduces the same poor-body PAC unchanged. Configured 512-byte unused space
is not permission to emit the next 153,600-byte sector-padded file.

**CONFIRMED — original allocation:** The face-dominant page is 32×32 with 32
used colors. Three body/clothing pages use only 16 colors despite indexed8
storage. The source pages are mixed atlas crops: labels such as “face” or
“torso” describe their main contents, not isolated anatomical regions.

**INFERRED:** This combination of resolution reduction and limited color
allocation explains much of the visible blur/contouring. It is not evidence
that every appearance defect is a texture error or that 16-color pages are
inherently unsuitable. Native PSP models frequently use indexed4 textures.

## Rejected attempts and a QA lesson

**CONFIRMED — diagnostic builds and CPU comparisons:**

- Merely retaining baseline GIMs as monotonic upgrade candidates yields no
  change within the existing space.
- A mixed-depth candidate with a 64×64/16-color face and a 128×128/16-color
  torso fits and passes native checks. Its whole geometric QA is unchanged,
  but face close-ups look more posterized. It is rejected.
- A color-first candidate improves face/torso colors but reduces the clothing
  design page from 128×128 to 64×64. Close-ups show worse logos/stripes. It is
  rejected rather than silently exchanged for the tested appearance.
- Diagnostic compression of unused guarded opaque texels saves only 103 bytes
  in the complete texture table. It is not used in the final candidate.
- Sampled model BPE parameter changes yield insufficient savings. The final
  model and texture encoder keep the existing block-size 4000 / distinct-symbol
  200 compressor policy; there is no new codec or longer-block requirement.

**CONFIRMED — why one combined score was insufficient:** On the rejected
16-color face, combined perceptual loss improves about 0.4183→0.3213, but color
quantization RMSE at its own native pixel grid worsens **5.279→8.863**. Increased
resolution conceals the palette regression in the aggregate score. The native
structural and geometric checks cannot detect that visual compromise.

The new independent read-only `model_qa/palette_quality.py` compares source RGB
resampled to each representation's own grid. It reports palette error,
resolution changes, source ceilings and optional sensitive-page color-count
reductions independently. This supplements the existing
`model_qa/texture_color.py` source-relative Lab/local-color diagnostics; that
original module and its tests remain intact.

**INFERRED — provisional review rule:** An RMSE increase greater than 10% plus
0.5 RGB units requests review. This is not calibrated perceptual acceptance.
More detail at higher resolution can itself require more palette colors.
Sensitive-page color counts and resolution decreases also request review;
visual comparisons remain mandatory.

## Recovering space without dropping data

**CONFIRMED — binary proof:** The base's effect table is stored uncompressed.
Existing BPE compresses it **7,072→4,010 bytes**, recovering **3,062 stored bytes**.
Every decoded byte, entry, GIM, palette and alpha sample is preserved. No blood
or other effect asset is removed or simplified. BPE affects stored size, not
the expanded texture-memory allocation or model shape.

**CONFIRMED — native corpus evidence:** The previously measured user-labelled
SVR 2011 `Rock.PAC`, SHA-256
`30825f27cc19cbb5e4339e4244aaf650c34b1a30183a8b7567d326c7aaffd165`,
already stores section 8 compressed: **4,008 stored / 7,072 decoded bytes**.
All three GIM hashes match the base's `blood1`, `blood2`, and `blood_b1` exactly.
The 2-byte compressed-size difference reflects the encoder output, not changed
assets. See [native-effect-storage-evidence.json](wwe13-wii-nine-models/native-effect-storage-evidence.json).
Retail provenance of the user-labelled corpus was not independently authenticated.

**CONFIRMED — validation boundary:** The existing `validate_trial` requires
unrelated *stored* section bytes to match its input base. It is not weakened.
The separate wrapper `compact_effect_storage` first creates an experimental
reference base and independently proves every decoded section unchanged and
every other stored payload exact. Canonical construction and ordinary native
validation then use that reference base. Reports retain both original and
experimental base hashes and explicitly record section 8's storage change.
There is no claim that stored effect bytes are unchanged from the original base.

**INFERRED:** Native use of the same compressed section and identical decoded
assets strongly supports compatibility. **UNKNOWN:** this specific new PAC's
actual gameplay behavior until tested in PPSSPP. Preserving effect assets does
not create missing blood-overlay geometry or prove every blood behavior.

## Selected candidate

**CONFIRMED — exact serialized build:**

`Edge-WWE13-Wii-Ring-Texture-Revision-A-Hair.pac`

SHA-256: `2a15b830a03edf0a82a9d14778cc37a421bd49fbbd46a1e741e79e4b031e1076`

| Atlas page | A | Revision |
| --- | --- | --- |
| `w13_00`, face-dominant/mixed | 32×32, 32 used colors, indexed8 | 64×64, 64 used colors, indexed8 |
| `w13_01`, torso/mixed | 64×64, 16 used colors, indexed8 | 64×64, 32 used colors, indexed8 |
| `w13_02`, arm/tattoo/mixed | 64×64, 16 used colors, indexed8 | 64×64, 32 used colors, indexed8 |
| `w13_03`, clothing-design/mixed | 128×128, 16 used colors, indexed8 | 128×128, **exact same RGBA pixels**, indexed4 |
| `w13_04`, eyes | 32×64 | Exact original A GIM bytes |
| `w13_05`, hair | 64×128 | Exact approved A GIM bytes |

Used-color counts are not declared CLUT capacity. Indexed8 retains its observed
256-entry RGBA CLUT contract, indexed4 its 16-entry contract. All dimensions,
formats and aspects follow the existing observed-native whitelist and remain
at/below source ceilings. Palettes are selected from actual source usage, not
upscaling or invented source detail.

**CONFIRMED — material metadata only:** Indexed4 needs the corresponding
observed regular material control **0x5**, rather than indexed8's **0x7**.
`patch_regular_depths` updates only the audited 32-bit material-control word at
material-record offset +24 for affected clothing draws. Every other YOBJ byte
is exact, including vertex/index buffers, UVs, positions, colors, normals,
weights, bone palettes, complete skeleton/binds, headers, pointers and POF0.
No mesh is re-decimated, re-packed, merged or re-rigged. The expanded YOBJ hash
changes because of that explicit texture-format metadata; a full-YOBJ identity
claim would be incorrect.

| Measurement | A | Revision |
| --- | ---: | ---: |
| PAC bytes | 151,552 | 151,552 |
| Stored main model | 128,003 | 128,006 |
| Stored effects | 7,072 | 4,010 |
| Stored costume textures | 16,117 | 19,347 |
| Padded pixels/CLUT, all retained tables included | 48,320 | 42,240 |
| Native donor comparison envelope | 54,016 | 54,016 |
| Native buffers / vertex records / triangles | 55 / 3,457 / 3,415 | Identical |
| Material records / textures | 81 / 6 | Identical |

The existing packer and compressor produce the exact final bytes independently
in both the cached search and the standalone reproduction tool. The smallest
native-grid color floors tested without effect compression still produce
153,600-byte files, **1,536 bytes over the configured cap**. These oversized
diagnostics are not exported as user test PACs.

## QA and uncertainty

**CONFIRMED — final actual PAC checks:** All pointer/allocation/alignment,
relocation, index-range, palette, normalized-weight, GIM/material-depth,
nonshrinking-bound and independent native serialization/hand/body/ocular gates
pass. The final file is sector aligned and obeys the actual encoded-size and
independent pixel/CLUT envelope checks. The original packaging code is unchanged.

Complete 6,000-sample rest / 14 analytical body poses / facial-controller and
material-boundary QA is rerun on the final PAC. Whole-surface p95 is exactly
**0.001971138865206544** reference heights in both A and the revision. All **47**
existing geometric review findings are identical, with **zero new findings**.
Those old findings remain unresolved; this is not a claim of a flawless model.
Analytical poses are not actual SVR animation clips.

| Native-grid quantization RMSE, RGB units | A | Revision |
| --- | ---: | ---: |
| Face page | 5.279 | 3.254 |
| Torso page | 6.246 | 3.797 |
| Arm/tattoo page | 8.718 | 5.642 |
| Clothing-design page | 7.614 | 7.614 |
| Eye page | 2.461 | 2.461 |

All opaque pages pass the new baseline-relative palette/resolution review.
Existing absolute source-color or opacity findings can remain: the conversion
is still a reduced representation. No metric proves the final appearance.
Matching front/back/left/right/three-quarter, face, torso and clothing views use
**identical PSP geometry** in all columns: full source textures / tested A /
exact decoded revision. These are CPU unlit previews, not Noesis or game
screenshots. A Noesis-previewable OBJ/MTL/PNG export and exact final YOBJ are
included. Actual GPU filtering, lighting, cutout ordering, animation and peak
runtime allocations still require PPSSPP testing.

**CONFIRMED — tests:** All **611** repository tests pass in the available Linux
runtime, including the original color diagnostics. New procedural tests cover
lossless indexed4 pixel equivalence, matched material-depth changes without
geometry changes, unchanged cutouts, effect-table round trips/idempotence,
unrelated payload preservation, and independent palette-versus-resolution QA.
No new Windows/clean-install or actual PPSSPP run was performed here.

## Reproduction

The checked A work directory must contain its PAC/result hash, exact
`candidate.yobj`, `packed.json`, native checks, ocular manifest and original
cropped atlas PNGs in `source-images`. These private game assets are not
committed. Use the same original PSP donor, not a different skeleton.

```sh
python -m tools.wwe13_texture_revision_trial BASELINE_A_WORK \
  --base YOUR_ORIGINAL_KURT_BASE.PAC --out NEW_EMPTY_DIRECTORY \
  --configuration docs/wwe13-wii-nine-models/edge-texture-revision-04-config.json \
  --compact-effects --costume-role ring \
  --filename Edge-WWE13-Wii-Ring-Texture-Revision-A-Hair.pac
```

`--compact-effects` is explicit and affects only the isolated tool. Configuration
policies are `preserve`, `lossless-indexed4`, and `source` with independently
specified dimensions, native depth and useful colors. The tool never changes
UVs or model topology and writes no PAC if the measured final size is too large.
The provided Edge configuration is an experiment, not a wrestler-name patch or
an app default. General allocation/integration awaits additional visual and
PPSSPP regressions. Machine-readable before/after results are in
[edge-texture-revision-04.json](wwe13-wii-nine-models/edge-texture-revision-04.json).

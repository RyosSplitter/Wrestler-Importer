# Texture modes and optional source review (v0.25.3)

The **Textures** section has four established mutually exclusive modes: **Default** (best for most models; selected on startup), **ATO** (the existing experimental adaptive system), **Priority Selection** (use when Default and ATO do not give good visual results), and **Downgrade** (one, two or three halving steps). Default and ATO retain their existing algorithms. The previous separate adaptive/review checkboxes are replaced by this selector; skin compatibility remains independent.

Choose **Priority Selection**, then a source and your own PSP base, and press **Convert**. The dialog shows decoded PS2 textures before conversion, including accessory dependencies. Click a thumbnail to enlarge it. Check zero to three maps and select **Continue conversion**; **Cancel** starts no job. A fourth checkbox is disabled until a selection is cleared. Changing the source clears selections. Priority Selection starts with the established Default conversion, then applies manual priorities. The worker still accepts historical advanced requests that combine adaptive analysis and priorities for reproducible older A/B jobs; the UI no longer combines those modes.

Selections are quality priorities, not a promise of lossless source preservation. After conversion, the output summary states how many selected textures remain reduced. Open **QA report**, then **Manual texture priorities**, for source/current/final images, settings, quality metrics and rejected-upgrade reasons. All previews are local; no PAC or image is uploaded.

## Contracts and evidence

**CONFIRMED by generated fixtures and native reference A/B checks:** No selections bypass the new allocation stage. Existing geometry, decimation, weight transfer, materials, UVs, skeleton, accessory handling, skin compatibility and PAC packaging are unchanged. With ordinary textures selected, unselected costume GIM bytes stay exact. With adaptive textures selected, unselected maps remain eligible for the established adaptive allocator; their settings may change to fund selected quality. Every non-texture decoded payload must remain identical. The only optional other storage change is the already validated lossless compression of retained GIM tables.

**CONFIRMED implementation:** `desktop/texture_review.py` exports original decoded RGBA to PNG using generated filenames, provides the classic Tk chooser, and enforces the three-name limit. Inspection stamps a source SHA-256; both request validation and the worker reject stale selections or unknown names. Alpha checkerboards affect display only. `Request.priority_textures` is a JSON list of unique names, accompanied by `texture_review_sha256`. Empty defaults preserve existing behavior.

**CONFIRMED implementation:** Manual priorities run after existing texture allocation and single-slot skin compatibility, against their real final model/storage overhead. `optimize_pac(..., priority_textures=names, freeze_unselected=not adaptive)` reuses the source analysis, observed native GIM candidates and exact serialized PAC allocator. Selected importance is multiplied by **8**; candidate perceptual loss must be no worse than that map's chosen-pipeline incumbent. Ordinary unselected candidate lists contain their exact incumbent only. Adaptive unselected lists use established safeguards. No geometry is reduced to fund this additional stage.

The objective is unchanged weighted perceptual loss, with the selected multiplier: `.22*RGB_RMSE/255 + .15*(1-SSIM) + .30*min(oriented_edge_error,2)/2 + .23*fine_feature_loss + .10*min(high_frequency_error,2)/2`. Importance uses detail, occupied-area detail coverage, half-resolution sensitivity and model surface share as documented in [portable-adaptive-textures.md](portable-adaptive-textures.md). The deterministic allocator measures whole-PAC byte cost per proposed combination and chooses weighted improvement per additional serialized byte. It is greedy, not a global optimum. The multiplier is a tunable heuristic, **INFERRED** to reflect user preference; it is not a validated human perception scale.

## Limits that still apply

- No upscaling beyond source width/height or invented useful palette capacity.
- Generated T4/T8 dimensions are restricted to native SVR 2011 observations. Those observations are conventions, not proven universal limits.
- Existing material storage depth stays fixed. Selecting a T4 torso does **not** silently turn its material into T8; palette quantization may remain visible even at original dimensions.
- Exact source cutout alpha and existing cranial/detail safeguards remain required.
- Final PAC is checked against **148000 bytes**, including real compression, pointers, alignment and padding; with 2048-byte alignment its effective maximum is **147456 bytes**.
- Padded pixel/CLUT allocation cannot exceed the current pipeline's baseline envelope, including retained texture tables. That is a conservative **INFERRED** compatibility envelope; the game's actual runtime allocation ceiling is **UNKNOWN**. Unused compressed PAC bytes do not imply unused texture RAM.
- If no source-bounded, baseline-quality-preserving selection fits, export is withheld with a diagnostic report. Three maps are a UI limit, not a proof that all three can fit at source quality.
- Numerical improvement does not certify visual equivalence or game compatibility. PPSSPP testing remains required.

## Reproduce and diagnose

Run `python -m unittest tests.test_texture_review tests.test_adaptive_textures`. Synthetic fixtures cover exact source alpha/previews, path-safe filenames, zero-selection equivalence, selected quality floors, fixed non-texture data, unselected default payloads, invalid names, stale checksums, limits and final-size enforcement. `python -m tools.ci_tests` runs all existing geometry/skinning/native regression tests. Frozen Windows smoke checks dialog selection, fourth-checkbox blocking, deselection, Continue and Cancel.

For an isolated priority-only A/B over your own accepted PSP PAC:

```
python -m experiments.texture_fidelity_selection source-HCTP.pac accepted-PSP.pac fresh-output --select texture_name_1 texture_name_2
```

Add `--adaptive` when testing an adaptive baseline. The script refuses an existing output directory, proves decoded non-texture identity, audits the candidate, checks source/baseline immutability and renders matching before/after views. It does not rerun geometry. `textures/report.json` lists all supported candidates, selected/rejected upgrades, source ceilings, selected/current loss and `priority_reduction_report`. `summary.json` records hashes, size and selected-map settings. These generated source-dependent reports/images are not redistributed inside the application.

## Development failure retained as evidence

The first Jericho ordinary-mode priority trial was correctly withheld at 26304
pixel/CLUT bytes against a 25792-byte envelope, although its PAC fit. Investigation
showed that the candidate generator had excluded the accepted near-opaque
incumbents for `y2j_body` and `y2j_hiji`: their source alpha levels were respectively
239/255 and 219/233/237/239/255. Requiring a source-sized exact-alpha replacement
unnecessarily added 512 allocation bytes. The priority stage now permits exact
existing incumbent bytes when **both source and incumbent stay >=128 alpha**.
This introduces no new alpha loss; remaining incumbent alpha differences are
reported. True cutouts still require exact source dimensions and alpha. The
ordinary/adaptive zero-selection behavior remains unchanged. A generated
near-opaque fixture reproduces and verifies this fallback without game assets.
The original failed report remains in the local trial evidence; no PAC was exported.

An initial Windows test also compared short-name (`RUNNER~1`) and long-name
(`runneradmin`) aliases of the same temporary directory. Resolving both sides
fixed the test assertion; PNG output paths were already canonical.

## Downgrade mode (v0.25.3)

**CONFIRMED implementation and reference checks:** Downgrade starts from the
textures generated by **Default**, including its selected budget-fit attempt,
then the existing skin compatibility stage. It halves both image axes one,
two or three times. Square maps stop at 64×64. Rectangular maps preserve aspect
and stop when their longer axis reaches 64 (e.g. 128×64 → 64×32). Maps already
at or below that extent remain byte-identical; no texture is enlarged to meet
the floor. The report states requested versus effective steps individually.

This is a resolution-only operation: nearest sampling of existing palette
indices, with every CLUT byte and material bit depth preserved. The sampled
alpha plane must match nearest sampling of the incumbent alpha exactly. No
new colors or alpha values are introduced. The selected step count does not
guarantee every map shrinks: existing smaller maps stop at the floor. New
layout/bit-depth pairs must be observed in the native corpus; absence is not
proof of hardware incompatibility, so unsupported pairs are withheld with the
active texture and dimensions in a diagnostic report rather than invented.

`desktop/texture_modes.py` operates only on costume texture table 9 using the
existing texture-table builder, BPE variants and aligned section repacker.
Every other stored and decoded payload must remain exact. Actual final size
must stay ≤148000 bytes, and padded pixels/CLUT cannot exceed the unchanged
Default baseline envelope. Compression is measured: reducing pixel count is
not assumed to reduce final PAC bytes monotonically. No additional decimation,
weight changes, material edits or silent extra reductions fund this stage.
`texture-downgrade/report.html` shows source/Default/Downgrade images and exact
dimensions, palettes, effective steps, allocation and size checks. Failed
settings write `failure-report.json` without exporting a candidate PAC.

**CONFIRMED development trial; rejected design:** Starting from original PS2
textures with a 64×64 floor for square maps exceeded both compressed size and
baseline texture allocation for Rock, Lance and Jericho. At two reductions,
Rock was 167936 bytes and 47808 padded pixel/CLUT bytes versus 148000 and 28224
respectively. This was not literally every texture set to 64×64: small source
maps remained small and rectangular aspect was preserved. Default uses smaller
representations, including 64×32 ordinary maps. The user selected reducing
Default output after reviewing that result. The failed source-based trial is
retained as development evidence; it is not an available production mode.

**CONFIRMED tests:** `tests/test_texture_modes.py` covers default/legacy request
behavior, exclusive mode validation, 1/2/3 levels, rectangular dimensions,
floors/no upscaling, exact CLUT retention, sampled cutout alpha, source versus
incumbent reduction basis, native layout rejection, immutable non-texture PAC
payloads, independent texture allocation, serialized size enforcement and
determinism. Frozen Windows CI also runs an actual Downgrade worker conversion
and proves payload identity. Static previews and analytical QA cannot prove
runtime memory safety; actual game heap limits remain **UNKNOWN** and new
outputs need PPSSPP testing.

The request schema adds optional `texture_mode` and `downgrade_steps` (1–3 only
in Downgrade mode). New explicit modes are exclusive. Old JSON jobs without a
mode retain their existing adaptive/priority booleans and behavior. The UI
always writes an explicit mode, initializes Default on every launch and opens
the chooser only in Priority Selection. Save As selects the extended verified
GIM reader for any optional texture stage before copying the reviewed output.

## Verified Windows release and regression evidence

**CONFIRMED:** Windows run [38110923042](https://github.com/RyosSplitter/Wrestler-Importer/actions/runs/38110923042)
completed successfully for converter commit `caeb76bdf16000aebcbeb727aff7c2ef22bfa41b`.
All 274 unit tests passed on both local Linux and the Windows build runner.
Frozen Windows checks passed: native Vista UI/DND/bundled Blender, Default mode
initialization and all four choices, downgrade controls, minimum-window sidebar
access, three-selection/deselect/Continue/Cancel, single-slot preservation,
Lance/Jericho/multi-model conversion and complete reference/pose QA, explicit ATO,
source previews and both historical priority job paths, plus an explicit Downgrade
worker and immutable-payload/palette/budget proof. Runner checks use modified
HCTP fixtures built from development IR and generated checker textures; they
are not a clean user Windows installation or an in-game PPSSPP trial.

**CONFIRMED:** All 15 isolated texture-only Downgrade checks on the real Rock,
Lance, Jericho, Benoit and 0401 accepted baselines passed (each at 1/2/3 steps).
The reports verify all non-costume-texture stored/decoded payloads exactly and
preserve every palette byte. PAC bytes respectively: 143360, 135168, 145408,
120832 and 137216. The three choices produce the same result for these samples
because their Default maps reach the floor after at most one effective step.
The selected level never bypasses a floor to force additional reduction.
Generated fixtures independently exercise all three mathematical levels.
`downloads/texture-modes-update/reference-results.json` contains sizes, hashes,
actual dimensions, effective steps and structural/preservation proof. Rejected
source-based trials are retained alongside it as a separate JSON record.

The release ZIP is 556771433 bytes. Runner checksum and GitHub
asset digest match SHA-256 `188f5fdb9b6d191caa8e7f51f3fd5fd40cccd4ec7c60064b0aa59f6a9f2b4d3b`.
The large ZIP was not independently downloaded/rehashed locally; the producer
checksum was compared to GitHub's computed asset digest. The actual Windows UI
and chooser screenshots were downloaded and visually inspected. See
`downloads/texture-modes-update/windows-release.json`, its checksum file and
screenshots. Release remains a prerelease on the isolated experiment branch;
main and accepted reference PACs were not modified. Game runtime limits beyond
the existing demonstrated envelope remain **UNKNOWN**.

## Maximum Downgrade addition (v0.25.4)

A fifth, explicitly selected rescue mode relaxes texture detail floors while
freezing the validated Default model candidate. Default remains selected at
startup; prior modes are unchanged. See [Maximum Downgrade](portable-maximum-downgrade.md)
for source ceilings, alpha semantics, existing precision-stage caveats, measured
size allocation, immutable model evidence and known limitations.

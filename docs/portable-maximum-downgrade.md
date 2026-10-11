# Maximum Downgrade (v0.25.4, experimental)

Choose **Textures → Maximum Downgrade** when normal texture modes cannot fit.
Default remains selected at startup. The 1/2/3-step Downgrade mode and its
64-pixel floor are unchanged. Maximum chooses reductions automatically and
stops at the first fitting candidate; maps are not all forced to their minimum.
It is a rescue mode, not a guarantee that every source can fit or load in-game.

## What is preserved

**CONFIRMED implementation:** The existing Default preparation, anatomy guards,
geometry fitting, source-derived body/jaw weights and donor ocular policy remain
in place. Maximum does not introduce another geometry downgrade. If all normal
size trials exceed the cap, it retains a validated smaller bounded-precision
trial that Default already attempted, instead of rejecting before textures can
be fitted. This preexisting lossy attribute-precision step is reported separately
in `precision.json` and `precision-validation.json`; it must not be described as
an exact copy of original PS2 positions/UVs/normals. Weights, topology, skeleton
and protected ocular records are preserved by its existing checks.

Existing single-slot compatibility runs before texture fitting so its actual
storage overhead is included. An oversize intermediate is permitted internally;
this is not an exception to the final export cap. Maximum saves that internal
baseline as `before-maximum-downgrade.pac` and edits only costume texture table 9.
All other stored and decoded sections, including every main/accessory YOBJ,
materials, effective weights, UVs, draw metadata and retained base data, must
remain byte-identical to that baseline. The existing repacker/compressor is reused
without changes. Existing modes take their old branches and retain behavior.

## How far textures may shrink

**CONFIRMED implementation/native observations:** GIM candidates use the existing
4-bit or 8-bit material contract. Changing bit depth would require modifying
YOBJ material controls and is outside this texture-only experiment. CLUT capacity
stays 16 or 256 RGBA8888 slots; **useful colors** may be reduced to 16/8/4/2/1,
or up to 256 for indexed8. Fewer occupied slots can improve compression but do
not reduce the allocated fixed CLUT capacity.

New dimension/format pairs must be in the native SVR 2011 corpus whitelist in
`desktop/texture_optimizer/candidates.py`, below both incumbent dimensions.
Indexed4 includes 8×8. Indexed8 includes 32×8 and 32×32, but not 8×8. These are
observed conventions, not proven hardware or loader minima. Existing exact
incumbents can be retained even if their layout was absent from the corpus.
The search includes rectangular representations and independent axis reductions;
any changed aspect is reported. Normalized UV coordinates are not edited.

**CONFIRMED implementation/tests:** RGB is filtered with Lanczos separately per
source alpha level to avoid transparent-padding color bleed, then median-cut
quantized per level. Alpha is sampled by nearest neighbor and must match exactly
at the new dimensions; no new alpha levels or opaque flattening is permitted.
Candidates that erase all visible pixels or all holes of a mixed cutout are
rejected. Downsampling can still remove tiny individual cutout details: this is
explicitly a lossy mode, not exact source-mask preservation. Alpha preservation
means exact *sampled* alpha, not unchanged full-resolution silhouettes.

No candidate exceeds its Default incumbent's width, height, useful RGBA count
or padded pixel/CLUT allocation. Retained effect tables remain unchanged, so
aggregate texture allocation cannot increase either. Actual runtime heap limits
and all animation-dependent texture-loader behavior remain **UNKNOWN**.

## Search and diagnostics

**CONFIRMED implementation:** The heuristic combines the existing occupied-area
RGB, SSIM, oriented-edge, fine-feature and high-frequency losses. Content-derived
importance weights the incremental loss. All candidate GIMs are serialized;
individual BPE cost orders candidates, then at most three alternatives per map
are probed through the complete texture table and actual aligned PAC writer.
Both established 200/220 dictionary variants are tried. Zero-measured-loss
reductions are batched and independently checked through the real PAC writer
before spending further rounds on individual quality losses. The chosen move minimizes
importance-adjusted incremental loss per actual stored-table byte saved.
Unpadded table savings let the search cross a 2048-byte PAC plateau. It repeats
until the real PAC fits; no further reduction is performed after fitting.
A recovery pass spends spare serialized space on measurable quality upgrades
without crossing the cap. The report records every restoration move.

This is deterministic greedy/shortlisted search, **not a proof of the globally
best quality or smallest possible PAC**. A simultaneous per-map minimum-cost
fallback handles some compressor interactions. Failed fitting means the tested
texture-only configurations did not fit; it does not prove every conceivable
configuration is impossible. A non-texture stored lower bound above the entire
cap, however, establishes that section-9-only changes cannot fit that baseline.

`maximum-downgrade/report.html` contains Default/final PNGs and settings.
`report.json` contains all candidates, quality metrics, fixed palette slots,
useful colors, alpha/aspect checks, selected decisions, actual size, allocation,
SHA-256 and non-texture identity proof. `search-progress.json` records completed
moves during lengthy searches. Failures write `failure-report.json` and export
no PAC. The final QA report links this independent stage. Save As uses the
extended audited GIM reader and retains its existing atomic backup behavior.

The final cap is **148000 bytes**, with the existing 2048-byte archive padding
making the largest fitting whole PAC **147456 bytes**. This is project policy
supported by prior trials, not a proven universal PSP hardware ceiling.

## Reproduction

Run `python -m unittest tests.test_maximum_downgrade tests.test_texture_modes`.
Fixtures are generated synthetic GIMs and PACs; no game assets are required.
Tests cover sub-64 native candidates, useful colors, fixed material depth,
source/incumbent ceilings, alpha sampling and cutout survival, serialized rescue,
impossible budgets, cancellation, deterministic output, and exact non-texture
identity. Existing mode and portable suites remain applicable.

For an already constructed PSP candidate, run:

    python ps2psp_converter.py --maximum-downgrade INPUT.pac NEW_OUTPUT_DIRECTORY

An optional final argument sets the test cap. The input is read-only and the
output directory must not exist. Full HCTP conversions use a worker request with
`"texture_mode": "Maximum Downgrade"`; no downgrade step count is required.
Windows CI runs both a frozen synthetic oversize rescue and a complete frozen
HCTP worker conversion. Structural/analytical checks do not certify gameplay;
test entrances, matches, victory animations and repeated loads in PPSSPP.

## Geometry downgrade follow-up

A separate opt-in geometry mode is a sensible next experiment. It should use
silhouette/curvature-aware decimation with source-region regression checks,
protect joints, facial/ocular surfaces, posterior volume and material/UV seams,
and recalculate shading normals afterward. Smoothing vertex positions is a
shape change, not a substitute for reducing triangles. This update adds no new
geometry mode; preserving shape must be measured against the accepted baseline
before any future simplification is enabled.

## Supplied Black Biker Shorts trial

**CONFIRMED local binary/QA evidence:** Source SHA-256
`962311ecf26ef5b686cd83e08d689087b478676888416ebdf96b30a17eff9e94`.
Using the existing Kurt PSP donor, unmodified Default fitting reproduced the
reported151552-byte rejection. Its first unbounded-precision model alone plus
retained data exceeded the cap, so texture fitting uses the established
bounded-precision candidate, not an undocumented extra anatomy operation.

| Quantity | Frozen candidate | Maximum final |
|---|---:|---:|
| PAC bytes |151552|147456|
| Stored model bytes |109803|109803|
| Stored costume texture table bytes |34390|29084|
| Padded costume pixels/CLUT bytes |50304|41984|
| Meshes |51|51|
| Vertices |2875|2875|
| Triangles |2576|2576|
| Textures |27|27|

Final PAC SHA-256:
`513df934d4da2820c337911b1670a8a47bbfae82608f318eaa9a2800bf503e27`.
The stored and decoded model section2 and retained section8 are exact. Nine
GIMs changed: eight changes have zero measured occupied-area information loss;
the meaningful tradeoff is `kami_b`128×128→64×128, retaining256 useful RGBA
colors/slots. A first fitting64×64 candidate143360 bytes was refined upward;
the final fills the largest allowed padded archive block. Hair-detail loss is
reported, not called lossless. CPU front/rear renders show the same geometry.

The complete static, regional, analytical-pose and head QA was run on both
texture candidates. `rest`, `poses`, `head_diagnostics`, `flags` and
`unresolved_review` are numerically identical. **47 existing review findings
remain**; this is a no-new-geometric-regression result, not an all-regions-pass
claim. Native structural, material-depth, palette, weight, eye replay, size and
non-texture preservation checks passed. Actual PPSSPP compatibility remains
**UNKNOWN** until the user tests this output.

**CONFIRMED local regression evidence:** All282 tests passed before adding the
independent recovery-optimality check; the expanded nine-test Maximum suite
also passed. Existing accepted Rock, Lance, Jericho, Benoit and0401 current PACs
are byte-identical when selected for Maximum and already fitting. The Tk smoke
verified Default startup, five exclusive modes, conditional fixed-step controls,
three-priority limit and the existing sidebar. A Windows build/verification run
is tracked separately; local Linux evidence is not called a clean-Windows test.

See `downloads/maximum-downgrade/verification.json`, its texture report and the
separate test bundle. This output does not overwrite any accepted PAC. The user
chose to keep this update texture-only; Geometry Downgrade remains a separate
future experiment.

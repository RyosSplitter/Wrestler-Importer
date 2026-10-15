# PSP Model Creator 0.3 — donor binds and optional texture rescue

This release includes the in-app **Add donors…** button and size-warning exports
from 0.2.2, plus **Maximum texture downgrade** and improved native donor bind
handling. All 31 supplied models remain preloaded. Previous accepted releases and
source PACs are preserved; the production PS2 converter is unchanged.

## Install and use

Extract the complete Windows 0.3 ZIP and run `PSP-Model-Creator.exe`. Keep
`_internal` and `creator_library` beside it. Existing 0.2-series users can instead
close the app and extract the separate 0.3 patch into their existing folder,
replacing the executable. The patch does not replace their runtime, library,
catalog or added donor PACs. Keep a backup of the previous executable.

1. Select Head, Torso, Arms and Legs, or click **Add donors…** to register more
   native PSP PACs. Import generates previews, copies immutable source snapshots,
   skips duplicate contents and backs up/atomically updates the catalog.
2. Leave **Maximum texture downgrade** unchecked for original native textures.
   Check it to try fitting an oversized assembly using texture changes only.
   A model already under the target retains its original textures and PAC bytes
   where it did before. Fitting runs during **Assemble and validate**, not during
   the preliminary donor-selection preview.
3. Review the rendered result and its actual PAC size. If fitting cannot reach
   the 148,000-byte target, the best tested smaller result is retained and the
   app warns with the exact excess. **Save PAC as** remains available. Native
   structural, rigging, palette, pointer, index and pose failures still block export.
4. Export the preview folder for native YOBJ, OBJ/MTL, PNGs, camera views and QA.
   `maximum-textures/report.html` compares each original/final texture;
   `report.json` records legal candidates, dimensions, fixed depth, useful colors,
   quality/detail metrics, decisions, actual serialized costs and remaining bytes.
   Changing the texture checkbox invalidates an older build for export.
5. Save choices to preserve the texture option with the source snapshots. Test
   new mixes in SVR 2011 PSP/PPSSPP before accepting them. File-size compliance and
   analytical poses do not establish in-game compatibility or a safe game heap.

Library jobs are in `%LOCALAPPDATA%\PSP Model Creator\jobs`; each has independent
source snapshots and a build folder. Import logs are in
`%TEMP%\psp-model-creator-donor-import.json`; error tracebacks are in
`%TEMP%\psp-model-creator-last-error.txt`.

## Why Hardy and JBL were blocked

**CONFIRMED:** The old common-body-bind gate compared every named body bone,
including bones unrelated to the selected donor part. Jeff/Matt Hardy have a
native neck translation differing by approximately 0.2159 local units. JBL Suit
has different leg/foot translations/rotations. Those native differences alone
made the old gate reject the entire pair. It did not establish that a particular
selected arm or leg was incompatible.

**CONFIRMED:** The old library skeleton policy copied `kubi` (neck) from the torso,
while copying the head/facial subtree from the head. Preserving the selected
head's neck pivot improves the Hardy head combinations. JBL's native leg/foot
branch can follow the selected legs while other parts keep their own branches.

The new general rule copies the selected parts' native bind branches and remaps
palettes by name, including the head's neck and face and the arms' clavicles.
Body hierarchy mismatches and conflicting required extra controllers still fail.
Different bind values are recorded as evidence rather than automatically treated
as corruption. Source interior positions, normals, UVs, colors and named nonzero
weights remain checked exactly after serialization. No vertex offset, scaling,
weight averaging, decimation or source-shape compensation is introduced.

**CONFIRMED:** A harder cross-source Hardy torso case needs a shared neck pivot.
Using either complete native pivot alone cannot satisfy all retained records in
that case. Local-axis neck posing with the head endpoint produced a maximum
0.0401937-unit difference, exceeding the existing **0.03** tolerance. The general
solver evaluates both measured native neck positions and chooses the point along
that segment minimizing the worst source-record pose error. The observed torso
fraction is about 0.30, reducing the measured error to **0.0281356**. This adjusts
one shared bone translation; it does not move mesh vertices or change weights.
The native selected-head pivot is kept when it already passes. Neck rotations,
hierarchy and all other branch records are preserved. Unsolvable cases remain
blocked; the tolerance was not increased.

**CONFIRMED:** Pose comparisons now include two independent conventions: the ten
existing model-axis probes and ten probes rotating directly in native bone-local
axes. This matters because a model-axis-only probe can hide differences in native
rest rotations. Shared seam positions are also checked under both conventions.
The final serialized/read-back model, not just the proposed skeleton, must pass.

**UNKNOWN:** Exact correspondence between these analytical controls and all real
SVR animation clips, including extreme neck rotations. The probes cover their
recorded controls/angles, not every possible game pose. Native culling-sphere
semantics beyond the observed fields remain **INFERRED**; conservative enclosure
is retained. No in-game acceptance of the new Hardy/JBL mixed models is claimed.

## Maximum texture downgrade

The new creator stage reuses the established `desktop.maximum_downgrade.candidates`
for native-observed T4/T8 dimensions, alpha-aware resampling and quantization.
It does not modify the existing converter's Maximum Downgrade path.

**CONFIRMED:** Candidate resolutions do not exceed their input; material depth and
16/256-slot palette contracts stay fixed. Actual used colors do not exceed input
usage. Alpha values come from nearest source samples, with both sides of a real
cutout retained. The optional maximum mode may use small native-observed sizes and
reduced useful colors; visual detail can be substantially reduced and is reported.

The creator scores loss with the existing edge/detail/image metrics and importance
analysis. Bounded batches trade weighted perceptual loss against individually
compressed texture cost, followed by a bounded source-detail restoration pass.
Every tested state is measured through the actual texture table, BPE compressor
and PAC writer. The best-quality tested state fitting the target is chosen; if
none fit, the smallest tested state is retained with an over-budget warning.

**CONFIRMED:** Fitting modifies only texture section 9. Every other stored and
expanded section must remain byte-identical, including model/YOBJ, skeleton,
weights, UVs, materials and donor auxiliary data. Texture allocation cannot grow,
PAC size cannot grow and the final preview decodes the textures actually in the
final PAC. An already fitting candidate stays byte-identical.

**INFERRED:** The combined image/detail score is useful for choosing candidates;
it is not a complete predictor of tattoo/logo/face legibility. The bounded search
is not a proof of global optimality. Whole-table compression is non-additive;
individual costs only propose candidates and never authorize an oversized result.

## Validation and remaining limits

- 426 repository tests passed during development. New regression tests cover the
  real Hardy/JBL part cases, local-axis checks, shared-pivot fitting, texture
  no-op behavior, impossible-fit warnings and non-texture preservation.
- 48/48 combinations passed for the three two-donor pairs Batista/Jeff,
  Batista/JBL, and Jeff/JBL, with all 16 four-part choices per pair. These are
  native/static/analytical-pose checks, not gameplay certification.
- All 31 originals were checked. The 124 donor-part trials against Batista now
  have **120 passing**, up from 108 in 0.2. Four remain blocked: Carlito, Dolph and
  Yoshi torso mixes exceed the jaw-pose tolerance, and Cena's neck contour is not
  star-shaped under the current seam algorithm. They were not forced through.
- The original contour cut planes and retained internal/ambiguous seam records
  remain documented in QA. Clothing/body-shape combinations still need visual
  review. Non-torso donor auxiliary nested models are not assembled; torso
  auxiliary payloads remain byte-identical.
- The frozen Windows self-check uses the real released 0.2 runtime/library for
  patch testing. It exercises Add donors, duplicate/rejection handling, saved
  oversized exports, the actual texture checkbox rescuing a synthetic oversized
  texture table, stale-option export prevention, a real Hardy shared-neck build,
  native buffers/palettes/descriptors and texture-edit roundtrip.

Reproduce from the repository:

```sh
python -m unittest discover -s tests -q
python -m tools.creator_library_check --output NEW_REPORT_DIRECTORY
python psp_model_creator.py --smoke-test NEW_REPORT_DIRECTORY/gui.json
```

Evidence: `creator-library-validation-030.json`,
`creator-bind-combinations-030.json` and the release validation record. Original
0.2 reports remain historical evidence; they are not rewritten to claim new
support existed then.

The measured four-donor texture trial (Yoshi head, Batista torso, Benoit arms,
Christian legs) changed from **161,792** bytes to **143,360** with the checkbox
on. Eleven textures changed; all non-texture stored payloads stayed identical.
The remaining 4,640 bytes reflect the bounded tested search, not a claim that no
better allocation exists. Per-texture visual comparisons are in its export report.

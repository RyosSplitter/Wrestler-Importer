# Optional source texture review (v0.25.2)

Enable **Review textures before conversion (up to 3 priorities)**, choose a source and your own PSP base, then press **Convert**. The dialog shows the decoded PS2 textures before conversion, including accessory dependencies. Click a thumbnail to enlarge it. Check zero to three maps and select **Continue conversion**; **Cancel** starts no conversion. A fourth checkbox is disabled until a selection is cleared. Changing the source clears selections. Review defaults OFF each session. Adaptive Texture Optimization remains an independent option and defaults OFF.

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

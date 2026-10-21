# PSP Model Suite v0.27.1 — experimental WWE ’13 Wii support

The [Q7/Q8 hotfix](wwe13-wii-packet-scale-hotfix.md) reads source position scale
per geometry packet and audits the source IR against original bytes. Transparent
draws are cutouts, not necessarily hair. Existing Q7 geometry behavior is preserved.

This preview integrates the bounded Wii research engine alongside HCTP and JBI.
It does not merge the rejected global UV-lock, UV-island or hand-transition
experiments into existing converters. Accepted PACs remain unchanged. Xbox 360
and PS3 WWE ’13 are not supported by this adapter; EPK8 magic alone is insufficient.

## Use

1. Extract the complete Windows ZIP; run `PSP-Model-Suite.exe`.
2. Select **WWE ’13 (Wii) — Experimental**, then your original Wii PAC.
3. Select the two-digit costume index. These are discovered bounded PACH
   containers, not inferred ring/entrance labels.
4. Select **ring** (152,064-byte cap) or **entrance** (180,000-byte cap)
   explicitly. Sector alignment makes the largest outputs 151,552 / 178,176
   bytes. Entrance is a configured experimental policy, not a proven heap limit.
5. Choose the geometry profile. **Standard** uses the study's .45 reduction
   for container 00 / .35 for other containers, .6 head and mouth, .5 hand
   floors, full eyes/hair, material domains, hand-weighted collapse, and export
   face floors. **Preserve Hands** raises the hand floor to .75. **Preserve
   Arms** raises the arm floor to .75 (the profile used for the approved Edge
   hair/geometry baseline). Profiles do not alter weights or manually move
   body parts. They are experimental retention choices, not guaranteed repairs.
6. Choose your own compatible PSP base and click **Convert** above the preview.
7. Review all views and **QA report**, then **Save PAC As...**. Test every
   costume in PPSSPP. Save As preserves inputs and backs up replaced exports.

Only **Default** textures are exposed for Wii in this preview. HCTP/JBI keep
their existing texture choices and behavior. Single-slot skinning is already
part of Wii construction and its checkbox is disabled for Wii. Other source
platforms do not receive the Wii entrance budget or geometry options.

## Texture rules and diagnostics

The separate `desktop/wii_textures.py` stage reuses the measured atlas allocator
and conventional image/UV analysis. It considers source-bounded native dimensions,
16–256 useful colors, occupied-image detail, source/edge/perceptual error and
native-grid quantization RMSE. The latter adds `4 × RMSE / 255` to the existing
detail loss. This coefficient and cranial safeguards are **INFERRED**, provisional
quality heuristics, not calibrated perceptual guarantees. Source ocular ownership
is tracked before donor weight amplitudes change; eyes retain the largest legal
source-bounded dimensions and at least 64 requested colors where warranted.

**CONFIRMED** in the source/fixture trials: half-source cutout-axis floors,
Lanczos RGB and original nearest alpha reproduce Edge trial A's selected hair
GIM when the same 64×128 candidate is selected. No component-support expansion or
binary-alpha bake is enabled. Other cutout candidates still receive source-level
alpha checks and thin-edge/component QA; runtime filtering/cutoff is **UNKNOWN**.

Opaque candidates using at most 16 actual colors can use exact T4 storage, with
only matching material depth control words patched. All other YOBJ bytes are
checked unchanged by that step. Candidate pruning happens after depth and palette
scoring. Each accepted upgrade measures the actual complete PAC and independent
donor pixel/CLUT envelope. No geometry reduction is added to fund textures.
Greedy allocation is not a global optimum proof; inspect texture diagnostics.

The private reference base may losslessly BPE-compress verified section 8 using
the existing compressor/packager. **CONFIRMED**: native SVR 2011 Rock stores this
table as BPE; round-trip tests preserve every decoded effect and all other stored
payloads. The original base on disk is never modified. Unknown section 8 layouts
are rejected. This does not add missing blood overlay geometry.

## QA and limits

The worker runs native structure, offset/allocation/alignment, palette, normalized
weight, bounds, eye and independent digit/hand stress gates, then the reusable
static/14-pose/head comparison, fixed-camera renders/heatmaps, source UV sampling,
palette-loss and cutout support reports. Review findings remain visible; native
validity is not an appearance pass or proof of runtime safety.

Known study defects remain review items on some Billy/Bret/Jericho costumes,
Booker's elbow region and Bradshaw's Acolyte wristbands. Rejected fixes are
documented in `wwe13-wii-geometry-opacity-03.md`. This release does not claim
they are fixed. Spring-hair animation, full source shader behavior, original
Wii blood events and many controller semantics remain **UNKNOWN** or unsupported.
No approved PAC, UV/layout experiment or main branch is overwritten.

## Reproduction and frozen checks

`python -m tools.ci_tests` runs automated regressions including procedural
GCTC/TPL fixtures. Windows workflow `windows-suite.yml` builds the frozen app,
then runs existing GUI/Blender, suite editor/validator, JBI all-mode tests and
`--wii-smoke-test OUTPUT_JSON DEVELOPMENT_BASE_PAC`. The Wii test executes
selection, real decoding/Blender/packing/full analytical QA, final renders,
entrance export and cancellation with procedural panels and colors. Its supplied
development rig and generated PACs are excluded from the ZIP. Hosted Windows
testing is not a clean user PC or PPSSPP session.

Example source job:

```python
from desktop.core import Request, run_job
result = run_job(Request('source.pac', 'my-psp-base.pac',
    source_format='wwe13-wii', source_entry='00', costume_role='ring',
    wii_geometry='Preserve Arms'), 'new-empty-job-directory')
```

The separately authorized UV/page-layout investigation remains an isolated
experiment. It is not enabled in this build and must pass comparisons before
any future integration.

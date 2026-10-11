# PS2PSP v0.25.1 — scalp compatibility and full-head QA

This isolated Windows app update incorporates the single-slot control that the
user reported looked good in SVR 2011 PSP. It does not merge experiments into
main or overwrite accepted PACs. Both existing texture algorithms remain intact.

## User controls

**Single-slot skinning compatibility** defaults ON. It examines the actual native
YOBJ buffers after the existing conversion and optional adaptive texture stage.
Only float32 skinned buffers with exactly one palette entry receive two distinct
existing bone entries with zero weights. This includes supported accessory
models if needed. Rigid buffers and two-slot palettes are unchanged. Disable the
checkbox for an explicit comparison with the previous conversion path; with it
OFF the prior geometry, packing and texture behavior is retained.

**Adaptive Texture Optimization (Experimental)** still defaults OFF. Either
texture mode can use the new compatibility handling. The Windows 7-style light
interface and Convert button above the preview remain. Run on Windows 10/11 x64;
this is not a claim of Windows 7 OS support.

## Exact changes and constraints

The adapter in `desktop/skinning.py` adds zero float weights without altering
existing nonzero weight bits. For an affected one-slot buffer its stride changes
from 40 to 48 bytes and vertex flag from `0x17ff` to `0x97ff`. Positions, normals,
UVs, colors, ordered primitives, materials, bounding spheres, skeleton and opaque
metadata are independently verified after native serialization. The existing
native writer, compression and PAC replacement functions rebuild the required
pointers, allocations and relocation data; packaging code is unchanged.

The stage keeps unrelated PAC sections exact in both stored and decoded form.
Every affected model undergoes exact dense-weight/geometry comparison, 14 body
pose replays and the applicable facial/head-controller probes. The final PAC
passes the existing native offset, alignment, allocation, index, palette, weight,
material/texture and model-set checks. Its preview comes from the final embedded
YOBJ, including independent accessories.

The maximum PAC size remains 148000 bytes (147456 after 2048-byte alignment).
The compatibility stage tries the existing lossless BPE settings. If its overhead
cannot fit, it blocks export rather than reducing geometry, textures or weights.
`skin-compatibility.json` reports the changed meshes, palettes, strides, flags,
additional decoded vertex-buffer bytes, PAC sizes, hashes and preservation checks.
The pre-adaptation PAC is kept at `before-skin-compatibility.pac`. The QA report
links this evidence separately from the adaptive texture stage's immutable-model
A/B comparison. `size-fit.json` covers the preceding converter's fitting attempts;
the compatibility report records the subsequent final layout budget.

## Head QA shipped in this update

QA now selects the entire head through cranial bone ancestry, including the rear
scalp, before applying poses. Vertices that escape the original head bounds
remain selected. It checks reference surface distances, vertex outliers and
opposed nearby face normals, with matched front, back, side and three-quarter
renders under both face-culling conventions as well as uncullled views. Head,
neck, jaw, eye, eyelid and eyebrow probes exercise facial deformation. Synthetic
regressions demonstrate detection of stored spikes, inverted faces and defects
that only appear under controller motion. Stage attribution matches region,
pose and finding kind so a layout warning is not mistakenly blamed on decimation.

The unchanged body, pelvis, jaw, eye, seam and material-boundary checks continue.
Small skinned palettes still produce review findings where appropriate; rigid
one-slot buffers are not flagged. Surface and coverage thresholds remain
provisional review thresholds rather than calibrated game acceptance limits.

## Evidence classification

- **CONFIRMED:** The uploaded failing Rock PAC stores a smooth scalp. Its main
  and accessory geometry match the prior developer reproduction exactly.
- **CONFIRMED:** Applying the app's adapter to that exact upload reproduces the
  isolated control SHA-256
  `b23c97770203e517eb26f64c61aad88cf9661e157957bf49979e705264107fbf`.
  The user subsequently reported that the Rock model looked good. This is visual
  acceptance of this control, not a recorded exhaustive animation or crash test.
- **CONFIRMED:** The audited native subset contains skinned palettes with 3–8
  entries and rigid one-slot examples. The observed convention is not a hardware
  limit. The Rock control adds 1048 decoded vertex-buffer bytes; its decoded YOBJ
  grows by 1056 bytes including layout changes, and PAC size stays 147456 bytes.
- **INFERRED:** The SVR loader's single-slot skinned path caused or contributed to
  the spikes. Visual acceptance supports the compatibility adaptation but does
  not fully decode that loader path.
- **UNKNOWN:** Exact game-side loader semantics, available expanded runtime heap
  and safety for every wrestler/animation. CPU QA does not emulate PSP GPU state
  or the actual game's animation streams. A smooth offline render alone could
  not detect the original runtime spikes, so the layout review is essential.

Do not impose a universal three-slot requirement or extrapolate to two-slot or
other weight encodings without evidence. The previous accepted PACs and original
source files remain read-only baselines.

## Reproduction and tests

```sh
python -m unittest discover -s tests
python ps2psp_converter.py --skin-compatibility input.pac fresh-output-directory
```

The diagnostic command refuses existing output directories and writes a validated
PAC and preservation report. Normal app conversions run this same adapter.
Regression evidence is in `downloads/scalp-compatibility-update/` in the repository.
The Windows workflow also tests the frozen executable with a generated one-slot
native fixture, the packaged GUI/runtime, full converted Lance/Jericho/multi-model
fixtures and adaptive texture A/B preservation. No game assets are distributed
inside the app.

See [original control evidence](rock-scalp-layout-control.md) and
[head QA investigation](rock-head-qa-investigation.md) for binary observations,
historical failures and initial unresolved hypotheses.

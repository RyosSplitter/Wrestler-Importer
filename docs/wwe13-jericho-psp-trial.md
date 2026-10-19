# ch104 → PSP: isolated compatibility experiment

This extends [the source study](wwe13-ch104-study.md). It does not add WWE '13
support to the app. Source game/platform provenance remains user-supplied.
The experiment stays on `experiment/wwe13-jericho-psp`, with accepted HCTP/JBI
outputs, production app code, native writer and PAC packaging code unchanged.

Each paragraph/table row's label classifies its technical claims for this sample.
CONFIRMED means demonstrated by executed code/binary checks or measured tests;
INFERRED means supported interpretation; UNKNOWN means unverified behavior.

## Scope and source representation

**CONFIRMED:** Input SHA-256 is
`2808111b6c9619cebe015bf8e05ee8cff195bee8f6d4f78bd2269fe00625ba65`.
The builder deliberately accepts only that inspected EPAC and converts bundle 0.
It uses the owner's original float-weight Kurt PSP base, SHA-256
`bf935a51fe30bfd2df929f8eb9e50be5d793426ea05125ca9411ce21b19ead80`.
No game assets are included as code/test fixtures or bundled into the app.

**CONFIRMED:** The selected PACH has three JBOY models, sections 0, 10000, 20002.
The decoded representation has 12,478 stored vertices across 38 source meshes.
**INFERRED:** The verified strip interpretation gives 18,440 triangles, with
main/body, anisotropic hair/beard and eye-shell roles. The preview is recognizable
Jericho; a separate original-game renderer has not verified all source semantics.

**CONFIRMED:** Auxiliary skeletons are unified by names and checked global bind
matrices, not by coincident local indices. This produces 204 source bone records.
Shared global matrices must agree within 1e-3 source units. Each source influence
uses its own model's palette before conversion into the unified source rig.
Only negligible unused-255 records are dropped; active weights are retained and
normalized for source floating-point roundoff. No incompatible vertices are welded.

## Material and opacity adaptation

**CONFIRMED:** The mesh shader parameter table at +148/+152 contains pointers to
records beginning with a 16-byte parameter name, BE u16 type at +16, BE u16 record
size at +18, and BE value at +20. All selected `g_mDiffusePrm` records are type 15,
size 24, value 0, referencing texture name `color`. The adapter rejects other
bindings/shaders instead of silently assigning a plausible atlas.

**INFERRED:** The `normal` DDS's alpha provides strand opacity for
`yCh_Aniso_trans`: its mask visually matches hair/beard ends. The adapter uses it
only for those shaders. Skin and opaque eyes retain opaque alpha. Applying this
utility channel globally would erase ordinary body surfaces.

**CONFIRMED:** Source color and opacity are combined without changing source
geometry. Native hair candidates use premultiplied RGBA Lanczos resizing, then
binary alpha threshold 128 for the existing PSP cutout material contract. Metrics
compare against the unbaked source image; the original fractional alpha is NOT
claimed to remain exact. **UNKNOWN:** Exact source shader equivalence, reflections,
anisotropy, normal/specular/muscle effects, sweat and source hair physics are not
implemented by this diffuse/cutout approximation.

## Skeletal bind and coefficient conversion

**CONFIRMED:** Source limb segment lengths are close to PSP lengths after a
uniform scale of 0.1. Translation aligns source `Bip Pelvis` with PSP `root`.
Body scale is uniform; no nonuniform scale hides anatomical differences. Origins
come from composed local hierarchy transforms, not the legacy +64 sphere-like
fields. Explicit mapping includes:

| Source | PSP role | Status |
|---|---|---|
| Bip / Bip Pelvis | root | CONFIRMED implemented and inspected; game semantics INFERRED |
| Bip Spine / Bip Spine1 | koshi / mune | CONFIRMED chain/position comparison |
| Bip Neck / Bip Head | kubi / atama | CONFIRMED role/bind comparison; animation equivalence UNKNOWN |
| Bip L/R UpperArm / Forearm / Hand | l/r_ninoude / kote / te | CONFIRMED chain mapping and analytical replay |
| Bip L/R Thigh / Calf / Foot / Toe0 | l/r_momo / sune / ashi / tsumasaki | CONFIRMED chain mapping and analytical replay |
| Bip L/R FingerD, FingerD1, FingerD2 | l/r_yubiD0, D1, D2 | CONFIRMED labels/hierarchies checked; game grips need testing |

**CONFIRMED:** Source helper roles have an explicit allowlist; unrepresented helpers collapse only through a
mapped ancestor. Spring hair attaches to its mapped head ancestor. An unmapped
active source hierarchy is an error, not a closest-position guess.

**CONFIRMED:** Source legs are angled and forearms bent in their reference pose.
Minimal proper rotations map the source upper-arm, forearm and thigh directions
onto PSP rest segments. Wrist-anchored hand rotations fit physical finger-base
landmarks, avoiding incompatible local-axis assumptions. Positions/normals are
blended by the original source support. This is a reported skeletal bind-pose
conversion, not manual sculpting or source-index correspondence after decimation.

**CONFIRMED:** Directly preserving same-name source eye coefficients failed
native ocular stress envelopes. The correction queries ordinary PSP donor
surfaces only on the original source eye/lid support. It retains donor amplitudes
only for roles already supported by that source record; unrelated donor mass goes
to `atama`. It never renormalizes a small donor eye coefficient into a large one.
Rigid eyeballs cannot acquire eyelid controllers or another eye's controller.
All other coefficients, including jaw coefficients, remain bit-for-bit unchanged
at this stage; positions, UVs, normals and materials also stay unchanged.

**UNKNOWN:** Actual WWE '13 and SVR facial-controller animation semantics are
not established by names or analytical probes. The eye policy is a conservative
native-donor compatibility experiment, not original facial animation preservation.

## Geometry reduction and native construction

**CONFIRMED:** A separate Blender worker reuses the established reducer and
source skinning-identity module. Classification uses target-rig support, source
hair/eyeball roles and independent topology domains. Faces around conflicting
source skinning points are held: 103 source faces in this case. UVs/colors remain
corner attributes; weights remain distinct across incompatible source records.

**CONFIRMED:** Experimental retention floors are Head 25%, Torso 20%, Arms 11%,
Legs 10%, Hands 13%, Eyes 8%, Mouth 8%, Hair 7%, plus held faces. These are this HD
source experiment's settings, NOT replacements for accepted HCTP/JBI defaults.
The resulting representation has 2,472 triangles. It is a substantial reduction;
the report must retain the resulting source-fidelity findings.

**CONFIRMED:** Uniform hand collapse produced excessive finger stretch. For
Hands only, collapse strength becomes
`0.01 + 0.99 * (sum(weight_i**2))**8`. Mixed joint/web support is harder to collapse
than single-bone phalange surfaces, with the same regional triangle floor. The
total triangle count remains 2,472. In the executed control/candidate comparison,
worst fist triangle area ratio improves 4.86→1.59; reverse-extension ratio
8.03→3.17. Ten independent digit probes show zero foreign-digit motion, and grip,
wrist and twist probes introduce no collapsed triangles. These are synthetic
PSP-rig tests, not captured gameplay. Wrist-boundary normals can change through
normal recomputation; unrelated body regions are not resculpted.

**CONFIRMED:** The unchanged native `pack`/`serialize` stages create float-weight
PSP buffers and preserve the selected base's bone bytes. The existing bounded
precision helper is explicitly lossy: position/UV/normal errors are measured
against its existing limits, with protected source points held. No integer-weight
vertex format or undocumented GPU format is introduced to force a fit.

**CONFIRMED:** A short cranial palette is padded to three entries using explicit
zero coefficients for existing native head/neck/jaw bones. Effective influences
are unchanged; the existing writer rebuilds stride, flags and pointers.
**INFERRED:** This follows the observed native skinned-draw convention.
**UNKNOWN:** A two-slot draw is not proven illegal; this is not a hardware limit.

## Texture allocation

**CONFIRMED:** Atlas pages are shared across source mesh boundaries. The first
per-mesh crop experiment generated 134 redundant images. Global sharing reduced
this to 38, and larger shared source cells to 11. UVs are remapped affinely; whole
triangles remain intact. Seven barycentric samples per triangle must reproduce
original bilinear RGBA within 1e-6. No model vertices move during charting.

**CONFIRMED:** Only encoded GIMs need observed POT layouts. Rounding intermediate
source crops to POT wasted context (e.g. a 522×522 crop became 1024×1024). The final
experiment instead chooses the smallest source-context rectangle with an observed
output aspect ratio. Pixels remain exact source samples; final resampling remains
uniform and source-bounded. Final GIM dimensions/bit depth combinations still use
the native corpus whitelist and the existing indexed4/8 swizzled RGBA-CLUT writer.

**CONFIRMED:** Whole-crop CLUT training turned ordinary torso skin yellow: unused
atlas padding/logos consumed palette capacity. Re-rendering the same geometry
with original source images isolated this to texture quantization, not UVs or
skinning. The experimental opaque encoder now trains on UV-occupied colors only,
and adds an occupied-cell low-frequency RGB bias penalty to existing detail loss.
Both palettes and actual decoded-PAC previews confirm the yellow cast is removed.
No production texture encoder was changed.

**CONFIRMED:** Candidate color methods are median cut, maximum coverage and fast
octree, with exact nearest-palette reassignment. Palette training handles fewer
returned colors than requested. Useful color capacity and output dimensions are
bounded by source usage/dimensions. Mandatory unused native CLUT slots do not
represent additional source detail. Head pages have a 64-pixel minimum axis;
hair uses explicit cutout candidates. No source texture is upscaled.

**CONFIRMED:** Actual individual GIM/BPE costs rank marginal upgrades, but every
accepted upgrade is measured through the unchanged BPE and aligned PAC writer.
Final bytes must equal canonical `package_models` output. Allocation enforces
148,000 PAC bytes and a 54,016-byte padded pixel/CLUT envelope observed in the PSP
base, including retained base texture memory. **UNKNOWN:** This conservative
envelope is not a universal runtime heap limit. Stored PAC size does not establish
expanded geometry allocation, GPU stability or game compatibility.

## Rejected controls and remaining QA

| Experiment | Observation | Disposition / status |
|---|---|---|
| Initial float-weight native model | compressed geometry alone exceeded 148,000 bytes | CONFIRMED rejected |
| 38-page fitting PAC | 147,456 bytes but eye stress exceeds donor envelope and several textures too coarse | CONFIRMED withheld |
| Shared 11-page crop with whole-crop palettes | yellow torso despite correct unquantized UV render | CONFIRMED withheld; occupancy-aware training fixes cause |
| Source-surface projection | global p95/height worsens .00520→.00671; torso and buttocks regress even when jaw improves | CONFIRMED rejected; never used in final pipeline |
| Uniform hand collapse | worst synthetic finger-flex area ratio 4.86 and reverse-extension ratio 8.03 | CONFIRMED replaced by deformation-aware hand retention |

**CONFIRMED:** Structural checks validate PAC section bounds/order/nonoverlap,
alignment, BPE round trips, native pointers/relocations, vertex/index allocations,
palette indices, normalized effective weights and GIM/material contracts. Unrelated
base sections and input files remain unchanged. Exports verify that the YOBJ used
in previews is exactly the decompressed final PAC section 2.

**CONFIRMED:** Full comparison QA uses the full-detail source in the adapted PSP
reference pose, rather than comparing a source A-pose directly with a target T-pose.
It runs static regional distances/curvature/depth/seams, 14 body/jaw poses and 37
cranial/controller probes. Extra independent finger and grip/wrist/twist probes
compare the source control, candidate and native base. The source-comparison
thresholds are not relaxed to turn a flagged model into a pass.

**CONFIRMED:** Source-fidelity findings remain, particularly face/jaw/hand shape
and culled head-surface coverage after heavy reduction. The build is NOT
QA-approved, NOT a replacement accepted baseline and NOT game-tested. Some
coverage findings involve layered, alpha-masked hair surfaces; **UNKNOWN** whether
each corresponds to a visible game defect. They are retained for inspection, not
silently dismissed. Match movement, eye tracking/blinks, jaw expressions, grips,
hair rendering/culling, entrances/victory and total runtime stability require
PPSSPP validation by the owner.

## Reproduce

**CONFIRMED:** Uses the existing app Python runtime and Blender 4.3.2; no new
dependency, environment setup or Windows app build is required. All new modules
are separate experimental CLI tools. No source archive or donor PAC is shipped
as a fixture. The following end-to-end workflow was executed with supplied files:

```bash
local/app-runtime/bin/python -u -m tools.wwe13_trial /path/to/ch104.pac \
  --base /path/to/OWN-Kurt-Angle-Ring.PAC --out local/NEW-wwe13-trial \
  --qa-samples 12000 --qa-resolution 128 --no-qa-renders

local/app-runtime/bin/python -m tools.wwe13_export_trial local/NEW-wwe13-trial \
  --base /path/to/OWN-Kurt-Angle-Ring.PAC --out local/NEW-owner-test-bundle
```

**CONFIRMED:** `--no-qa-renders` disables the expensive clay gallery, not numerical
static/pose/controller tests. The exporter supplies matching textured front/back/
sides/three-quarter views, face/pelvis close-ups and analytical pose views. Omitting
that switch generates the full clay/heatmap gallery as in the earlier controls.
`--uniform-hands` recreates the hand-retention control. `power2_context=True` on
`chart_atlas` recreates the old source-padding policy. Output directories must be
new; accepted files are never overwritten.

**CONFIRMED:** 83 focused existing/new tests passed after the final build and
export. Integration results and artifact hashes are recorded
with the final evidence. New procedural checks cover bounds, sentinel semantics,
digit mapping, proper rotation, shared-page sampling, role-selective ocular
transfer, unchanged jaw mass, no cross-eye spill, source ceilings and masked-palette
training. Real-file structural/pose/render evidence is separate from unit tests.

## Final experimental artifact

**CONFIRMED:** The final owner test PAC is 145,408 bytes, with 59 native meshes,
2,921 stored vertices, 2,472 triangles, 11 GIM textures and 79 PSP bones. Its
SHA-256 is `68fe2e27be4ad20ca26fe64e6b43b6539e527295362c96314018586d0d1f8837`.
The matching preview YOBJ is recovered directly from that PAC. Pixel/CLUT
allocation is 52,864 bytes within the base's observed 54,016-byte envelope.

**CONFIRMED:** Native structure, eye-motion and calibrated synthetic hand checks
pass. Source-comparison QA retains 574 review findings, including seven regions
with high-review findings: face, jaw, chin, buttocks, shoulders and both hands.
These findings do not establish 574 independent visible defects. They also do
not constitute a QA pass. **UNKNOWN:** Actual SVR 2011 runtime compatibility
until the owner tests this candidate in PPSSPP.

See [numerical final evidence](wwe13-ch104/psp-trial-evidence.json). Game-derived
PACs, geometry, textures and comparison images remain in the private owner
bundle and are not committed as reference fixtures. Production app code and
accepted baseline assets remain unchanged.

# Separate QA stage and acceptance gates

## What QA compares

**CONFIRMED [E15/E21]:** `model_qa` is independent of conversion and packaging.
It reads original weighted HCTP geometry and decoded candidate PSP YOBJ/PAC,
applies one uniform landmark fit, exports comparable geometry and measures
surfaces without assuming matching indices. Original source weights can be
mapped onto the **same PSP rig** as a primary control; original-rig poses are a
separate secondary control. This separates geometry/transfer changes from
unproven cross-rig animation semantics.

**CONFIRMED [E15]:** Fifteen fixed reference-space anatomical ROIs cover face,
jaw, chin, nose, eyes, neck, shoulders, torso, waist, pelvis, buttocks, left/right
hands and left/right feet. Anchors come from shared PSP bones and source extents;
pose analysis tracks ownership from bind geometry. Anatomical proportions are
not fitted away. Missing required anchors or insufficient head extent are
reported rather than inventing landmark correspondence.

| Diagnostic | Algorithm / meaning | Status |
|---|---|---|
| Surface distance | deterministic area samples in both directions to closest triangles; p95/p99/max and height normalization | CONFIRMED E15 |
| Local depth | paired orthographic ray/depth comparison with identical camera/masks; signed inward and absolute differences | CONFIRMED E15 |
| Silhouette | matched coverage overlap/edge distances; complements depth | CONFIRMED E15 |
| Curvature | integrated discrete mean curvature on a diagnostic position-welded copy, at radius0.012*height and divided by that radius | CONFIRMED implementation E15; physical interpretation INFERRED |
| Topology | finite points, index validity, degeneracy, components, boundaries and nonmanifold diagnostics | CONFIRMED E15 |
| Seams | bind-position aliases tracked within each model through poses | CONFIRMED E15/E21 |
| Facial proportions | bone-anchored ROIs plus matched face/jaw/chin/nose/eye surfaces and views | CONFIRMED E15; not a learned face detector |
| Local volume | depth/surface proxy on open segmented model | CONFIRMED available diagnostic E15; true closed anatomical volume UNKNOWN |
| Texture/shader appearance | geometry-only QA renderer does not simulate native shader/alpha | UNKNOWN from this renderer E15/E25 |

**CONFIRMED [E15]:** Trimesh uses `process=False` to avoid unrequested welding,
SciPy supports neighborhoods/components and Rtree accelerates triangle queries.
Seeds are fixed (including2718/3141) and reports retain coverage. Finite sampling
can miss a tiny corner. Multiple views and material-boundary maxima were added
because a high whole-model similarity score is insufficient.

## Matching renders and previews

**CONFIRMED [E15]:** Rest renders include front/back/left/right and four
three-quarter views, plus ROI close-ups; candidate and reference use identical
camera, lighting and pose. Heatmaps show measured geometry error. CPU clay
renders are explicitly labeled and are not Noesis or PPSSPP screenshots.
`--save-depth` preserves float32 view depth arrays. The same full model can
occlude an ROI from a particular angle; retain measured coverage/unmeasured
states instead of claiming every close-up guarantees inspection.

**CONFIRMED [E25]:** A Noesis-previewable OBJ needs its MTL and named PNGs in the
same directory. Native YOBJ and GIMs in that directory come from the actual
finished PAC. The established inspection sequence is orientation F3 once,
face-cull F4 once and shading F5 once on fresh viewer settings. OBJ previews
have zero bones by design and do not imply the native YOBJ lacks a skeleton.
Noesis can split OBJ meshes by material; its mesh count is not native draw count.
The inspector exporter preserves reconstructed native strip winding; a supplied
YOBJ File Tool export previously showed inconsistent winding.

**CONFIRMED [E16/E20/E25]:** Before publishing, decompress the final PAC model
again, prove equality with the QA candidate and preview YOBJ, and include all
preview texture hashes. Matching file names alone are insufficient to prove an
image depicts the delivered PAC. For true Noesis screenshots, record actual
application/version/toggles; do not label CPU renders as viewer screenshots.

## Static and posed controls

**CONFIRMED [E15/E21]:** QA0.2 has14 analytical poses: standing; walk-left/right;
bend; crouch; shoulders-up; neck-turn; head-tilt; jaw6/12/18/25 degrees; and
elbow-flex-left/right. The source/candidate use identical local controls and LBS:

```text
p_posed = sum_b w_b * (Mworld_posed[b] * inverse(Mworld_bind[b])) * p_bind
```

**CONFIRMED [E18]:** `model_qa.ocular` adds16 specific eye/lid/neck/jaw/brow
compatibility probes, including local translations and opposing turns. This
module is a separate reusable suite, not automatically run by every
`model_qa compare` call. The experiment checks selected ocular motion against
the proven previous PSP reference, while unselected jaw/facial motion must match
the jaw-fixed reference. The old jaw-only candidate fails14/16 probes; the
selective ocular candidate fails0. Frozen-topology checks precede copying.
When accessory topology later changes, eye regression can use exact retained
facial signatures instead of assuming the whole model remains frozen.

**UNKNOWN [E22]:** These poses are not decoded SVR animation clips. Native facial
controller semantics, real game physics, engine memory and every expression
cannot be certified by analytical LBS. PPSSPP tests remain required for entrance,
walking, crouching, gameplay, camera expressions and victory. A rest pose uses
identity skinning and can completely hide a wrong weight map.

## Material/accessory boundary checks (QA0.2)

**CONFIRMED [E21]:** Group triangles by texture/material identity and extract
geometric boundary segments. Query every endpoint and midpoint against exact
segments in the other mesh, **bidirectionally**, retaining maximum as well as
p95. This tolerates vertex reordering and boundary subdivision. It does not
require source/native vertex-index correspondence. Missing materials and changed
coverage are review findings; closed materials are explicitly unmeasured by
this edge diagnostic, not silently passed.

**CONFIRMED [E21]:** Virtual bind grouping uses1e−7 reference height and records
same-model aliases shared by multiple materials. In each pose, track those exact
records and report seam opening/drift. It does not weld or modify the model.
The former `y2j_hiji` pad receives four findings; the accepted pad receives none.
The accepted Jericho still has six other material-boundary review findings on
simplified hands/fingers/lower legs. Keep these visible. "Perfect" user gameplay
appearance is not evidence that every geometric metric equals the source.

## Provisional tolerances and regression policy

| Metric (divided by source height) | Default review threshold | Status |
|---|---:|---|
| Surface p95 |0.0015|CONFIRMED configured floor E15|
| Surface p99 |0.004|CONFIRMED configured floor E15|
| Absolute depth p95 |0.003|CONFIRMED configured floor E15|
| Inward depth p95 |0.002|CONFIRMED configured floor E15|
| Silhouette edge p95 |0.002|CONFIRMED configured floor E15|
| Added posed p95 over rest |0.002|CONFIRMED configured floor E15|
| Boundary maximum |0.003|CONFIRMED configured floor E21|
| Boundary p95 |0.0015|CONFIRMED configured floor E21|
| Added boundary maximum during pose |0.002|CONFIRMED configured floor E21|
| Added shared-material seam gap |0.0002|CONFIRMED configured floor E21|

**CONFIRMED [E15/E21]:** Profiles can override regional/per-texture thresholds.
The provisional profile uses1.5× observed errors from independently trusted
regions with engineering floors; deliberately defective jaw/rear regions were
excluded from calibration. Foot thresholds differ from defaults. Calibration
path strings document original provenance; those cloud paths are not required
input locations for a new checkout. Minimum surface/render coverage is explicit.
Animation limits remain provisional engineering floors because no verified
animation clips were provided.

**INFERRED [E15/E21]:** Treat significant findings as suspicious differences needing
review, not proof every intended LOD change is wrong. A correction is eligible
only when defect metrics and matched renders improve, passing regions remain
within their established tolerance, static/posed checks pass elsewhere and
native structure/size constraints remain valid. Never tune thresholds using the
defect to make it pass. Record every attempted/rejected correction and retain
best previous model.

**CONFIRMED [E16]:** Changing triangle counts can change area-sample allocation
and create an unrelated raw flag even when local geometry/weights are identical.
The Lance experiment retained such a neck-turn flag and proved unchanged local
triangle/weight/pose signatures and fixed-reference errors. That proof is not
permission to hide the raw flag or broadly dismiss sampling failures.

## Stage trace, reports and commands

**CONFIRMED [E15]:** Persist at least decoded/aligned source, transferred weights,
post-reduction, post-packing and decoded serialized model. QA traces the first
supplied stage where a deviation appears. It cannot certify unsaved stages.
CLI `--stage LABEL=PATH` expects target-space stages; the Python API can label a
source-space stage so the saved reference alignment is applied once.

**CONFIRMED [E15/E21]:** Run from the repository root to a new directory:

```sh
python -m model_qa compare --source ORIGINAL/0600.pac --converted downloads/Jericho-SVR2011-PSP-elbow-pad-TEST.pac --output NEW/jericho-qa --profile model_qa/profiles/hctp-provisional-v1.json --samples 24000 --resolution 320 --stage transferred=EVIDENCE/corrected-weight-transfer.json --fail-on-review
```

**CONFIRMED [E15]:** JSON/HTML reports include input/profile/version hashes,
uniform alignment, per-region rest/pose metrics, coverage, topology, influence
mass, severity/findings, views/heatmaps, stage trace and native audit. QA is
read-only: automatic correction and automatic replacement are disabled.
`--fail-on-review` returns2 **after** saving reports if findings exist; otherwise
the CLI can return0 even with findings. Exit0 is not an assertion of no defects.
`--no-renders`/`--no-animation` are diagnostic options, not the full acceptance run.

**CONFIRMED [E16/E20]:** Historical QA0.1 experiment bundles have12 poses and
lack the later material-boundary diagnostic. Do not relabel their zero flags as
QA0.2 zero flags. The recorded QA0.2 regression identifies old/new pad input hashes
and preserves other findings. Final stored PAC bytes are unchanged by QA.

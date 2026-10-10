# Material/accessory boundary QA regression

The user confirmed the Jericho pad correction works in SVR 2011 PSP. QA 0.2
now checks this class of defect automatically in the normal `model_qa compare`
stage, independently of the converter. All accepted PACs remain unchanged.

Whole-arm surface percentiles passed while a small elbow-pad corner stretched
toward the shoulder. The new diagnostic groups triangles by their material's
texture name and extracts geometric boundary segments. Every boundary endpoint
and midpoint is queried against the other model's boundary segments in both
directions. It retains the maximum error alongside percentiles, so an isolated
corner is not lost in area-weighted whole-body sampling. Subdivided boundary
edges and reordered vertices can compare exactly; source/native indices are
never assumed to correspond.

For animation, each model tracks its own verified bind-position records along
shared material seams. Identical analytical poses test edge drift and whether
pad/skin aliases separate. Virtual grouping uses a tolerance of `1e-7` reference
height and does not weld or alter geometry. Left and right elbow-flex poses
join the existing standing, walking, bending, crouching, shoulder, neck, head
and jaw controls, bringing the standard suite to 14 poses.

The JSON report's rest, poses and saved-stage measurements include
`material_boundaries`. Review findings use `region: material:<texture>` and
carry evidence for maximum/p95 edge drift, increased pose drift or seam opening.
Missing materials and changed boundary coverage are explicitly flagged for
review. Closed materials without boundaries are reported as unmeasured by this
diagnostic; existing surface, topology and anatomical checks still apply.
The HTML report lists material boundaries and creates matching front/back/side
close-ups for flagged materials whenever rendering is enabled.

## Provisional tolerances and review policy

Defaults, relative to original reference height:

| Metric | Review threshold |
|---|---:|
| Maximum boundary drift | 0.003 |
| P95 boundary drift | 0.0015 |
| Additional maximum drift during pose | 0.002 |
| Additional shared-material seam gap | 0.0002 |

Profiles may override `material_boundaries` or individual entries under its
`per_texture` mapping. Invalid/nonpositive thresholds are rejected. Existing
profiles inherit these defaults without requiring edits to converter profiles.
These are engineering review floors, not thresholds fitted to accept a defect.
Matched texture names are comparison evidence, not a guarantee of identical
material semantics. Intentional LOD or atlas changes and overlays may warrant
human review. No findings automatically edit, reject or replace an accepted
PAC. `--fail-on-review` still allows explicit automation to return a flagged
status after preserving a complete report.

The accepted Jericho still has other material-boundary review findings, such
as simplified finger/hand and lower-leg boundaries. They are retained rather
than hidden by relaxing tolerances; this QA change does not modify those areas.

## Verification

The actual old pad PAC is
`Jericho-SVR2011-PSP-eye-compatibility-TEST.pac`; the user-validated corrected
reference is `Jericho-SVR2011-PSP-elbow-pad-TEST.pac`. The automatic boundary
check flags `y2j_hiji` in the former and clears it in the latter, including
standing, raised-arm and elbow-flex checks. Its 21 shared boundary groups
remain joined. Tests also cover an isolated peak despite a permissive p95
limit, reordered/subdivided topology, posed seam opening, unmatched materials,
profile validation and the default pipeline's JSON/HTML integration.

85 tests passed across the QA, weight, native-format, texture, PAC and compression
suites. The new comparisons are available in
[the QA regression report](../downloads/QA-material-boundaries-Jericho-regression.json).
All PAC packaging and converter code remains unchanged. This update is
published on `experiment/qa-material-boundaries`, without merging into main.

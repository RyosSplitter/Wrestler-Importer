# Isolated Lance posterior decimation experiment

Branch: `experiment/lance-posterior-decimation`, based on QA baseline commit
`28a6227`. The QA system, Windows beta, PAC packaging code and all accepted
PACs remain unchanged. No experimental PAC is written.

[Download before/after QA, YOBJ, textured Noesis OBJ and replay evidence](../downloads/Lance-QA-decimation-experiment.zip).
Extract and open `index.html`. The clay images are CPU QA renders; the
`preview/` OBJ/MTL/PNG files support separate Noesis inspection.

## Root cause

The original collapse process measures local quadric surface error, protects
shared region seams and enforces a whole-region face floor. Its weight is the
body-region membership strength, not anatomical curvature or local depth.
It has no posterior surface/depth constraint. A broad Torso/Legs floor does
not guarantee retention of the points that define a curved gluteal surface.
Rear trunks lose 23 of 55 faces (41.8%); back torso loses 37 of 110 (33.6%).
Boundary endpoints can survive while larger replacement triangles span and
flatten the interior. The QA trace detects this before packing. Later waist
edits worsen the geometric deviation. This is not evidence of a PAC-offset or
texture defect.

## Process change and isolation

The guarded reduction profile excludes the original `l-pan2` / `l-se1`
posterior surfaces from the collapse modifier. They retain their input faces,
UVs and source-derived PSP weights. Other regions retain their existing
retention ratios: preserving extra posterior faces does **not** force more
aggressive reduction elsewhere. The worker now also expands local palette
weights when copying a protected input with a sparse palette; dense inputs
retain the same values. The original default budget-redistribution behavior
remains the default on this experimental branch.

The profile is actually executed in Blender. A controlled patch replay then
applies only those guarded posterior surfaces to the accepted native model,
preserving later unrelated improvements instead of replacing them with an
earlier full conversion. Existing weights, UV and vertex-color bits remain
unchanged. New points use the input-to-decimation weights, with existing seam
weights retained. Native bone palettes, skeleton and material state remain
unchanged. Existing unrelated triangle-strip sequences are preserved.

The first full-surface replay corrected the pelvis but moved an upper seam
into the retained neck/head, worsening neck p95 surface error from 0.207% to
0.487% of height. That version was rejected. The final replay retains the
accepted superior boundary outside the pelvis target. Original lower
posterior faces and positions remain intact; only the source patch's upper
closure joins the existing neck boundary. No buttocks offset, inflation or
volume displacement is applied. A tiny prior waistband edit is matched back
to its original source anchor below 0.001% of height.

This is a conservative source-surface preservation policy, not a new
volume-constrained simplifier. It deliberately spends a small number of faces
to retain proven source geometry. A future adaptive policy can use the same
QA evidence to accept simplification only when posterior error remains within
the established limits.

## Validation and constraints

Both reports use the unchanged provisional profile, 24,000 surface samples in
each direction, all 15 regions, eight full views, all anatomical close-ups and
the complete 12-pose QA set. Input hashes are checked and the accepted PAC is
preserved. Exact changes, stage evidence and the regression gate are included.
The full QA/reader/weight/native-format regression set and five additional
experiment-specific checks pass: **43 tests** in total.
The report retains any pre-existing unrelated review flags; it does not
misrepresent analytical poses as a PPSSPP test.

Rear p95 distance decreases from **2.4473% of height to float32 roundoff**;
pelvis p95 decreases from **1.6624% to float32 roundoff**. Rear-view inward depth
p95 decreases from 3.3752% to approximately 0.03% of height. Rear and crouched
comparison renders now follow the original surface rather than spanning its
interior with flat replacement faces.

One raw facial neck-turn review crosses the 0.2% added-motion threshold after
global area-weighted candidate samples change from 663 to 691 in that region.
The experiment's separate regression review verifies identical local triangle
positions, bone weights and analytical poses for all 593 intersecting faces,
plus identical fixed reference-sample errors. That establishes no actual local
change; the raw QA flag remains visible with this sampling explanation. No
threshold or baseline QA result is changed. All other previously passing
regions retain their passes. Existing unrelated facial/neck review flags are
still unresolved, not certified as correct.

Only an experimental YOBJ is emitted. Native pointers, allocations, alignment,
indices, palettes and weight sums pass the existing auditor. Its compressed
model size is used for an arithmetic budget projection with the unchanged
PAC layout and payload sizes; no PAC is constructed or repacked.

## Reproduce

Install `requirements-qa.txt`, extract the bundle and use its `evidence/` inputs:

```powershell
blender --background --python-exit-code 1 --python tools/blender_hybrid_reduce.py -- evidence/input-to-reduction.json NEW/guarded-reduction.json evidence/profile.json
py -3.13 -m tools.lance_decimation_guard_trial --baseline downloads/1800-PSP-hybrid-source-pelvis-restored.pac --guarded NEW/guarded-reduction.json --output NEW/trial
py -3.13 -m model_qa compare --source ORIGINAL/1800.pac --converted NEW/trial/candidate.yobj --output NEW/qa --profile model_qa/profiles/hctp-provisional-v1.json --samples 24000 --resolution 320
```

Every output must be new. This experiment is independent of the Jericho
weight-transfer branch and has not been promoted to the main converter.

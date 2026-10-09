# Isolated Jericho facial weight-transfer experiment

Branch: `experiment/jericho-facial-weights`, independently based on QA commit
`28a6227`; it contains no Lance decimation change. All accepted PACs, the QA
package, Windows beta and PAC packaging code remain unchanged. No PAC is written.

[Download before/after QA, weight comparisons, YOBJ and textured Noesis OBJ](../downloads/Jericho-QA-facial-weights-experiment.zip).
Extract everything and open `index.html`. The CPU clay render comparisons are
distinct from the supplied Noesis-previewable OBJ/MTL/PNG files.

## Root cause

The old hybrid formula is:

```text
head_fraction = source weight mass in the atama subtree
hybrid = mapped_source * (1 - head_fraction) + nearest_PSP_donor * head_fraction
```

For a vertex fully weighted to the original head, this discards all original
facial-controller weights. The donor query knows neither source facial
controller identity nor anatomical ownership. It selects the nearest ordinary
triangle on Kurt's PSP geometry and interpolates its weights. Near a jaw/neck
join this can introduce `kubi` / `mune` influences and replace original mouth
controllers with Kurt's different distribution. The continuous blend is not
an anatomical safety constraint.

The original jaw surface has approximately 98.07% cranial / 0% neck / 1.93%
body influence mass. The old converted jaw has 80.67% cranial / 10.69% neck /
8.64% body. Static vertices still look good because rest skinning is identity;
the error becomes visible when the neck or jaw moves. The saved-stage QA
detects it in hybrid weight transfer before simplification. The same-PSP-rig
source-weight control separates this effect from different HCTP/PSP rig pivots.

## Transfer correction and isolation

An explicit experimental opt-in preserves the original normalized source
cranial controller weights through the already verified bone-name/ancestor
map. It disables nearest-body substitution for that source-supported cranial
data. The old behavior remains the default. Source-only hair bones continue
to use the same established head-ancestor mapping.

The corrected transfer stage is saved before reduction. To isolate this change,
its weights are replayed over the **existing** reduced geometry: exact original
float32 positions are verified when available; other records use same-material
nearest source triangles and barycentric interpolation. Vertex-index
correspondence is not assumed. The existing geometry is not decimated again,
and there is no compensating jaw/neck position edit.

Every position, UV, normal, vertex-color record, material state and triangle-strip
sequence remains byte-identical after decoding. Bones and the texture table are
unchanged. Weights outside the source/current cranial support are retained.
The archive includes original HCTP weights, mapped source weights, nearest donor
weights, old hybrid weights and corrected weights with their aligned positions.
Per-record changes include source-provenance method and both named distributions.

Several native draw palettes need the original source mouth/eyelid controllers.
Unused old slots are replaced with required bones, never exceeding the PSP
eight-bone limit. Vertex strides/flags, offsets and relocations are rebuilt by
the existing model writer and independently audited. Mesh and material counts
do not change. This is model serialization, not a change to PAC packaging.

## Validation

| Region / pose | Before p95 / height | After p95 / height |
| --- | ---: | ---: |
| Jaw / static | 0.0380% | 0.0380% |
| Jaw / 18° opening | 0.2485% | 0.0425% |
| Jaw / neck turn | 0.3350% | 0.0386% |
| Chin / 18° opening | 0.1767% | 0.0172% |
| Chin / neck turn | 0.3898% | 0.0123% |

All 15 regions and 12 poses have **zero review flags** under the unchanged
profile. Every static QA metric and render remains identical. Animated jaw,
chin and neck comparison renders now track the original source-weight control.
The experiment changes 637 weight records and 18 native palettes while
preserving all 2,387 vertex positions and 2,413 triangles in 54 native meshes.
The projected unchanged-layout PAC size is **143,360 bytes (140 KiB)**,
compared with the accepted baseline's 147,456 bytes; no PAC is produced.
The complete QA/reader/weight/native-format regression set and five new
experiment-specific checks pass: **43 tests** in total, including unchanged
legacy defaults and deterministic weight replay.

Before and after use the same provisional tolerances, 24,000 surface samples in
each direction, all anatomical regions, matching view/close-up cameras, and all
12 analytical poses. Static geometry is exactly unchanged. The comparison gate
checks improvement of the jaw and chin in jaw-opening and neck-turn poses and
rejects newly failing regions or excessive error increases elsewhere. Any raw
sampling-only threshold crossing can be explained only by exact local posed
geometry/weight signatures and unchanged fixed-reference errors; it stays
visible in the raw report, and thresholds are not relaxed.

Original-HCTP-rig controls remain available. A preserved source weight map does
not prove every PSP facial animation uses the same controller semantics.
Analytical LBS checks are not a PPSSPP test, and this candidate is not promoted
to a baseline. Native structure and projected size use the unchanged container
layout and payload sizes; no PAC is constructed or repacked.

## Reproduce

```powershell
py -3.13 -m pip install -r requirements-qa.txt
py -3.13 -m tools.jericho_weight_guard_trial --source ORIGINAL/0600.pac --base ORIGINAL/Kurt-Angle-Ring.PAC --baseline downloads/0600-PSP-hybrid-Jericho.pac --output NEW/trial
py -3.13 -m model_qa compare --source ORIGINAL/0600.pac --converted NEW/trial/candidate.yobj --output NEW/qa --profile model_qa/profiles/hctp-provisional-v1.json --samples 24000 --resolution 320
```

The experimental argument to `prepare_hybrid` is `preserve_source_cranial=True`.
Default conversions remain on the previous hybrid behavior on this branch.

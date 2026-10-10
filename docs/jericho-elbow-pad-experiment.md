# Jericho elbow-pad preservation experiment

The accepted Jericho pad acquired a pointed upper edge during decimation.
This isolated candidate restores its original aligned HCTP surface and three
shared skin anchors, while retaining the accepted eye/jaw correction.
Branch: `experiment/jericho-elbow-pad`; PPSSPP testing is pending.

[Download PAC](../downloads/Jericho-SVR2011-PSP-elbow-pad-TEST.pac) ·
[Preview, backups, QA and import instructions](../downloads/Jericho-SVR2011-PSP-elbow-pad-TEST-bundle.zip) ·
[Actual PAC validation](../downloads/Jericho-SVR2011-PSP-elbow-pad-TEST-validation.json) ·
[Standing comparison](../downloads/Jericho-SVR2011-PSP-elbow-pad-TEST-comparison.png) ·
[Rear comparison](../downloads/Jericho-SVR2011-PSP-elbow-pad-TEST-rear-comparison.png).

PAC SHA-256:
`369ee95ed12c58c7c4d91f9ae26590bb2e4469a3abd31e8312d043bfe27533e8`

## Cause and controlled change

The source `y2j_hiji` material contains 54 records and 73 triangles. The accepted
PSP version contained 52 records and 69 triangles. Three boundary points moved
by 0.423525, 0.317730 and 0.007060 model units. The first moved toward the
shoulder, producing the pointed edge visible in the user's screenshot.
Its weights also acquired 2.421% `r_sakotsu` influence.

`make_regions` groups arm and pad materials into one Arms entry. The existing
Blender reducer welds coincident positions within an entry and protects seams
between entries; that ownership check does not protect a material boundary
inside the same entry. The pad was absent from the protected-material list.
Collapse decimation consequently moved these shared anchors and interpolated
their corner attributes. The discrepancy is already present in rest geometry;
changing the whole arm's skeleton or translating the entire pad is unnecessary.

The opt-in profile adds `y2j_hiji` to material preservation. A real Blender run
retained all original pad triangles. Oriented position/UV/weight triangle
signatures verify this without assuming source/native vertex-index agreement.
Only that preserved pad is replayed onto accepted native mesh 28; other regions
from the new Blender run are discarded.

Three skin copies must recover the same original anchors to maintain the seam:
mesh 27 vertex 5; mesh 28 vertices 7 and 16. Material-specific source UVs,
restricted to the missing source boundary corners, identify these points
uniquely despite mirrored arm UVs. Their original UVs, normals and mapped
weights are restored along with their positions. The pad's original positions,
UVs, normals, colors, weights and oriented triangles replace only its trailing
vertex block and primitive strips. Existing material rendering bytes survive.
Every other vertex record and every other material's indices remain exact.

The source and donor elbow bind pivots differ by about 0.155 model units, but
this candidate leaves the accepted PSP skeleton and all palettes unchanged.
All original pad weights fit its existing five-bone palette. The shared upper
corner recovers 5% `r_ninoude`, 95% `r_ninoude_x`, removing the interpolated
shoulder influence. The prior eye/jaw records are bit-identical.

## Before and after

| Measurement | Accepted eye/jaw PAC | Pad candidate |
|---|---:|---:|
| Native meshes | 54 | 54 |
| Vertex records | 2,387 | 2,389 |
| Triangles | 2,413 | 2,417 |
| Strip indices, including connectors | 4,085 | 4,087 |
| Bones | 79 | 79 |
| Textures / distinct texture materials | 20 / 20 | 20 / 20 |
| Native material records | 94 | 94 |
| Expanded YOBJ bytes | 194,688 | 194,784 |
| Stored BPE model bytes | 119,350 | 119,470 |
| PAC bytes | 145,408 | 145,408 |

The PAC remains 142 KiB, below the strict 148,000-byte budget. The original
accepted PAC is unchanged and included as a backup, SHA-256
`da7a9fa75b0941e58aba86881472f40129448b22880b5cc4fba478b265961bd9`.
Source HCTP `0600.pac` SHA-256:
`052da6cb97e1adcf865a89fd8d7d8544de8298025b36344f38de74ec600e9b1e`.

## Validation

- Existing full QA: 24,000 surface samples, 320-pixel renders, 15 anatomical
  regions, rest and 12 poses; zero flags, unchanged thresholds, no regressions.
- Pad-specific QA: 10,000 samples per direction, six analytical poses covering
  standing, elbow flexion, forearm twist and raised arms. Rest bidirectional
  surface p95 improves from 0.0049064 units to numerical roundoff. Across these
  poses the restored pad differs from the original surface on the same PSP rig
  by at most `2.53e-15` units. All 21 source boundary groups have zero skin gap.
- All 16 eye/eyelid/neck/jaw controller probes and the 12 full-suite facial
  poses have zero facial position difference versus the accepted candidate.
- 76 regression tests pass. The six new pad tests were repeated after the
  final reporting edit. Native audit validates pointers, POF0 relocation,
  alignment, allocations, index ranges, palettes and normalized finite weights.
  The corrected meshes fit their retained native culling spheres.
- Existing BPE and PAC packaging code is unchanged. Compression roundtrip,
  section overlap/ranges, 16-byte section alignment and 2,048-byte PAC alignment
  pass. Stored texture sections 8 and 9, including alpha, are byte-identical.
- The YOBJ extracted from the final PAC equals the full-QA candidate and
  `preview/candidate.yobj` exactly. Bundle CRCs, manifest hashes and PAC/preview
  identity checks pass.

The blue-pad comparison images are CPU QA renders with identical camera,
lighting and pose; they are not Noesis or gameplay screenshots. The original
aligned HCTP surface uses the same PSP skeleton here to isolate the pad
geometry/weight change. These analytical tests cannot certify actual SVR
animation semantics; that remains the purpose of the user's PPSSPP test.

## Preview and import

Extract the bundle. Open `preview/candidate.obj` in Noesis with its MTL and
PNGs alongside it, applying the established orientation/cull/shading toggles.
`before.obj` is the accepted version; `original-aligned-reference.obj` is the
HCTP geometry displayed with the same retained PSP texture images. The bundle
also contains the exact actual-PAC YOBJ and GIM textures.

Back up the ISO, CH.PAC, ARC and destination wrestler entry. Inject the test
PAC into the intended ring-model entry with the established PAC Editor
workflow; use `EMD\00010001.pac` only if it is still the intended test slot.
Rebuild CH.PAC as needed, update ARC against that resulting archive and save
the ISO. Verify that the entry does not overlap the following entry. Restart
PPSSPP and start a fresh match. Check the right elbow pad standing, bending,
raising the arms, entrance and victory, and recheck the fixed eyes and jaw.
The accepted PAC in `backups/` allows an exact rollback.

## Reproduction and scope

The bundle preserves the aligned source-weight stage, protected Blender output,
opt-in profile, worker log, exact changed-record report, before/after audits,
full QA, local pad/facial QA and tests. Run the unchanged Blender worker with
that source and profile, then use `tools.jericho_elbow_guard_trial` to replay
only the pad onto the pinned accepted PAC. `tools.jericho_elbow_review` runs
the separate surface/seam/facial regression checks.

No converter defaults, packaging implementation or existing baselines changed.
This branch is independent and has not been merged into main. Material-boundary
preservation is a potential general conversion rule, pending in-game validation
and evidence from other accessories; this trial does not activate it globally.

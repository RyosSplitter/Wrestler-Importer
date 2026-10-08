# Benoit HCTP to PSP: five controlled weight trials

All five trials are complete. **Hybrid weighting (trial 3) is the strongest
starting candidate:** it retains the mapped source arm/body weights and reduces
facial edge stretching with native PSP head weights. Redistribution alone also
preserves the body well. Whole-body PSP transfer works reasonably on this matched
pair. Pure direct mapping is incomplete, and the tested automatic heat bind
visibly distorts the model. These are preview findings, not in-game approval.

[Download all ten screenshots, posed models, weight data and rigged reviews](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/Benoit-five-weight-methods-review.zip).

The user supplied HCTP `0900.pac` and SVR 2007 PSP `Chris-Benoit.PAC` for five
weighting trials. This study isolates weight assignment: all methods retain
the full **2,836 source triangles and 2,016 UV-split vertices**, use one common
rigid alignment (scale 1.0176969394), and retain the same source textures and UVs.
The target is the supplied **77-bone PSP Benoit skeleton**. No decimation,
texture budget fitting, PAC rebuilding or in-game test is part of these previews.
The beta backend remains unchanged.

The source has 71 bones and 1,722 native position records. Its internal model
name is `RVD1p_0100`, but the `bn_*` textures and visible face identify Benoit;
the internal name alone was misleading. Original input sizes are 457,984 bytes
(PS2) and 100,352 bytes (PSP). The original PACs are not modified.

## Source weight decoding

The new analysis-only [HCTP weight reader](../tools/hctp_weights.py) reads original
VIF V4-32 weight packets by destination address. The VU weight base is fixed at
`0x280`, even in meshes containing fewer than 160 vertices. Single-bone groups
have implicit weights of one. The source contains **856 explicitly blended
position records and 866 implicit rigid records**. UV-split vertices retain
the weights of their original position index. Maximum source weight-sum error
is below 5e-8; a common normalization corrects that float roundoff for the study.

All eleven mesh streams pass bounds, exact packet/group coverage, bone-slot,
finite/nonnegative value and normalization checks. The reader also decodes both
Slaughter source variants. This validates the observed structural interpretation;
source animation playback is not an independent validation of it.

## Preview controls

Each trial exports the same rest, elbow-flex, arms-up and knees-bent poses with
analytical linear blend skinning. The two arm poses also turn the neck and open
the jaw to exercise facial weights. Joint rotations are defined in model axes,
converted to each bone's rest frame, with inherited parent motion.

The posed OBJs bake these calculated deformations. They are read-only inspector
exports, not YOBJ File Tool exports or native PSP serialization. Noesis generates
preview normals. Each screenshot uses a fresh Noesis64 4.466 instance, then one
click each on orientation, face cull and shading. Bone count zero in the OBJ
viewer does not describe the native rig: the pose is already baked into geometry.

Deformation metrics compare against analytical skinning of the original PS2 rig
with its decoded weights. This is a useful controlled reference, not original
HCTP animation playback or a proof of PSP game compatibility. Matching rest
geometry alone cannot establish correct weights.

## 1. Direct bone-name mapping

[Elbow-flex screenshot](../downloads/benoit-weight-trials/method-1-elbow-flex.png)
and [report](../downloads/benoit-weight-trials/method-1-report.json).

Eight source bone names are absent from the PSP rig: `atama_d`, `d_ha`, `l_mayu`,
`l_sakotsu_d`, `r_mayu`, `r_sakotsu_d`, `root_d`, `u_ha`. **52 UV-split vertices
have unmapped influence; ten have no mapped influence at all.** This method is
therefore an incomplete direct mapping, not a valid complete PSP weight export.
To display its failure without silently substituting another method, unmatched
weight mass stays at its rest position in the diagnostic pose. No extra bone is
added to the target skeleton. Other weights keep their mapped values.

The screenshot shows largely intact arms, but unresolved facial/helper weights
need explicit handling. The later trials below compare alternatives on the same
geometry.

## 2. Bone mapping with ancestor redistribution

[Elbow-flex screenshot](../downloads/benoit-weight-trials/method-2-elbow-flex.png)
and [report](../downloads/benoit-weight-trials/method-2-report.json).

Missing shoulder helpers map to the matching clavicle; missing tooth, eyebrow
and head helper bones map to `atama`; `root_d` maps to `root`. Every vertex now
has normalized PSP bone influences. No influence is held at rest, all 2,836
triangles remain, and duplicate-position seams stay together in the test poses.
These ancestor choices are explicit in the report, not inferred game semantics.

The elbow-flex pose's RMS displacement from the analytical original rig falls
from 0.09065 model units to 0.07574. The arms appear intact. Small facial edges
still stretch during the jaw test; a complete mapping is not sufficient evidence
of good facial deformation. Trial 3 replaces the head region's weighting
with interpolation from the native PSP model.

## 3. Hybrid source-body and PSP-head weighting

[Elbow-flex screenshot](../downloads/benoit-weight-trials/method-3-elbow-flex.png)
and [report](../downloads/benoit-weight-trials/method-3-report.json).

Trial 2's mapped/redistributed weights remain on the body. The source's original
`atama`-subtree influence mass defines a continuous head mask: **608 vertices**
receive some head-region blending with weights interpolated from the nearest
ordinary PSP body surface. Blood overlays are excluded from the donor. The
interpolated/blended result is limited to four active influences and normalized.

The elbow-flex pose's worst edge-length ratio falls from 6.25 in trial 2 to 2.77;
its 95th percentile falls from 1.040 to 1.010. The jaw/face appearance changes
while the mapped arms remain intact. This is promising for facial compatibility,
but neither edge ratios nor resemblance to the analytical original rig alone
prove animation quality. Head turns, raised arms and bent knees are also saved
for the final comparison.

## 4. Whole-body transfer from the PSP base

[Elbow-flex screenshot](../downloads/benoit-weight-trials/method-4-elbow-flex.png)
and [report](../downloads/benoit-weight-trials/method-4-report.json).

Every source vertex receives barycentrically interpolated weights from the
nearest ordinary PSP body triangle. No source weight values are used for
assignment; source bones contribute only to the common alignment and analytical
reference. Blood overlays are excluded, identical seam positions share weights,
and the result is capped at four active influences and normalized.

The preview keeps the arm surfaces intact without decimation. Its elbow-flex
RMS difference from the analytical original rig is 0.08855, versus 0.08136 for
the hybrid and 0.07574 for redistribution. Its edge-stretch 95th percentile is
1.040. These controlled metrics distinguish the weights, but a smaller distance
to the source rig is not necessarily better PSP facial animation. The matched
Benoit donor is a more relevant transfer reference than the earlier Kurt base.

## 5. Automatic heat rebinding

[Elbow-flex screenshot](../downloads/benoit-weight-trials/method-5-elbow-flex.png)
and [report](../downloads/benoit-weight-trials/method-5-report.json).

Blender 4.3.2 `ARMATURE_AUTO` bone heat binds a disposable proxy with duplicate
positions welded: 1,449 proxy vertices and 2,836 faces. All original 2,016 output
vertices receive their proxy vertex's weights; final geometry and UVs are not
modified. The bind succeeds with no unweighted vertices on its first attempt.

The target rig retains 77 bones. This automatic configuration seeds 51 body and
finger bones, using anatomical segment tails inferred from the target bone
positions; facial and twist helpers are retained but excluded as heat seeds.
No source or PSP donor weights are used. The generated values are normalized,
limited to four influences, then normalized again. At the worst vertex, this
limit removes 40.8% of the initial weight mass, so pruning is a material part of
the tested configuration.

**This automatic result visibly fails the posed shape check:** the neck stretches
and the waist/torso flares. Elbow-flex edge-stretch p95 is 1.637 and RMS distance
from the analytical original rig is 0.8274, substantially worse than trials 2–4.
No missing triangles or changed rest geometry caused this deformation. A
successful bind and normalized weights are not an appearance pass. This result
does not establish that all heat or voxel binding configurations would fail.

The saved heat proxy retains the **unpruned** Blender groups, enabling a separate
audit without replacing trial 5. They use up to eleven active influences. Before
pruning, elbow-flex RMS error is already 0.8615 and edge-stretch p95 is 1.316.
After pruning, RMS is 0.8274 but edge-stretch p95 rises to 1.637. Pruning changes
positions by 0.4956 units RMS and up to 1.9215 units. Thus the raw heat result
already differs greatly from the source rig, and the influence limit changes
it substantially again. A binding failure cannot be attributed only to pruning.

## Comparison and checks

| Method | Elbow-flex RMS difference from analytical source rig | Elbow-flex edge stretch p95 | Raised-arm edge stretch p95 | Outcome |
| --- | ---: | ---: | ---: | --- |
| 1. Direct mapping | 0.09065 | 1.091 | 1.118 | Incomplete: 52 unresolved vertices |
| 2. Redistribution | 0.07574 | 1.040 | 1.062 | Complete mapped source weights; facial review needed |
| 3. Hybrid | 0.08136 | 1.010 | 1.019 | Promising body/face combination |
| 4. PSP-base transfer | 0.08855 | 1.040 | 1.055 | Reasonable matched-donor result |
| 5. Automatic heat bind | 0.82737 | 1.637 | 1.470 | Visible neck/torso deformation |

RMS is in native model units; the model is approximately 19 units tall. Edge
stretch is a ratio to each edge's rest length. These are diagnostic measurements,
not a quality score. Source and PSP facial rigs differ, so matching the analytical
source deformation is not the sole objective. All duplicate-position seams stay
together in the evaluated poses; all five rest poses reproduce common aligned
geometry. No triangle, UV or texture changes distinguish these trials.

The bundle includes a second actual Noesis screenshot for each method with
raised arms, plus rest, bent-arm, raised-arm and bent-knee OBJs. `comparison-summary.json`
also groups deformation metrics by source bone-weight regions. Trials 2 and 3
have identical arm-region deformation in these checks. Whole-body transfer
changes it modestly; the automatic bind changes it much more.

For trials 2–5, `weighted-review.blend` contains the same 77-bone target review
rig, original mesh/UV buffers, packed textures and keyframed checks: frame 1 rest,
21 elbow-flex, 41 arms-up, 61 knees-bent. A real Blender armature modifier was
evaluated at all four poses and compared with the analytical OBJ coordinates:
maximum difference is below **0.000004 model units**. This validates the pose
calculation; it does not validate PSP serialization or game animation. Trial 1
has no complete rigged review file because its unresolved influences are only
represented by explicitly held-at-rest mass in the diagnostic.

Original input hashes remain unchanged. The packet decoder and skinning/mapping
checks, together with relevant existing HCTP/prepare-model tests, pass. The
pinned beta backend and app are unchanged. There is **no replacement PAC** in
this study: native palette/mesh packing, compression, the stored-file budget
and PPSSPP testing remain separate steps for a chosen weighting candidate.

# Benoit HCTP to PSP: five controlled weight trials

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
need explicit handling. Subsequent trials will test redistribution, hybrid
weighting, PSP-base transfer and automatic binding on the same geometry.

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
of good facial deformation. Trial 3 will replace the head region's weighting
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

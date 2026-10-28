# Final export seam checks — v0.29.1

Every HCTP, JBI and experimental WWE '13 Wii conversion now checks the decoded
final PAC against its source reference. Single and batch results show a seam
finding count and unmatched/ambiguous coverage. The existing save warning
includes these counts. Findings require review; they do not silently repair,
weld or repaint a model. Existing structural, pose and size gates still apply.

The QA report includes **Export seam checks**, per-pose measurements, the worst
local openings and `export-seams.json`. HCTP/Wii reports also include bounded
source-framed seam close-ups when a finding has a location. JBI checks each
independent main/accessory model against its prepared source on the target rig.
The HCTP reference is uniformly aligned source geometry; the Wii reference is
the source-derived charted target-rig model. This audit checks conversion loss,
not whether the original or an earlier rig-adaptation stage was correct.

## What changed

- Seam networks include UV islands within the same texture, material borders
  and open surface edges. Position/UV/material corners are virtually joined
  across native palette splits; vertex indices need not match.
- Every edge is sampled at its ends, quarter points and midpoint, in both
  directions. Maximum drift is retained so a small wristband or knee-pad corner
  cannot disappear in a whole-body average.
- Coincident source corners with different UV/material sides are matched to
  final boundary segments in bind space. Candidate interpolation is then fixed
  for all poses, including wrist flex, forearm twist, knee flex and the existing
  walking/crouching/bending/elbow probes. Subdivided edges are supported.
- Additional gap is measured **per source contact pair**, not against the
  largest source opening anywhere on the body. An already-open export can be
  measured even when its two sides are no longer coincident.
- Missing material/UV sides and ambiguous same-UV weight branches are reported
  as unmeasured coverage. They are never reported as a confirmed closed seam.

Provisional review floors: maximum edge drift 0.3% of reference height; extra
local contact gap 0.02%. Correspondence accepts at most 0.3% height distance and
0.035 UV distance. These fixed, reported floors do not relax any export gate.
The analysis changes no geometry, UV coordinates, normals, textures or weights.

## Limits

This is geometric/UV-boundary analysis. Texture-color continuity, normal shading,
unmatched atlas changes, intentional overlapping surfaces, unsampled edge
interiors and real game animation still need visual/PPSSPP review. Candidate
edges outside correspondence tolerance produce a coverage finding rather than
a fabricated gap measurement. Equal UV/material source branches with different
weights are ambiguous here; the existing source-skinning identity gate remains
independent. Source contacts without duplicate corners are covered by boundary
drift where visible, not by a guaranteed paired-contact measurement.

The optional Wii **Protect clothing seams** setting still controls reduction.
The new final export audit runs whether that setting is on or off. Budgets
remain 152,064 bytes for ring PACs and 180,000 for explicit Wii entrance PACs.

## Validation

Regression controls cover same-texture seams, small pre-opened outputs, local
pose cracks hidden by unrelated source gaps, authorized source movement,
subdivision/reordering, missing sides, displaced edge interiors, harmless native
palette splits, immutable inputs and finite serialized reports. Frozen Windows
JBI/Wii/batch smoke checks require the final audit, visible seam summary, per-model
coverage, stress poses and unchanged checked exports.

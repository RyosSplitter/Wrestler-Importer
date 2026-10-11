# Priority texture reallocation experiment — v0.25.5

## Failure and cause

**CONFIRMED:** The user-selected `y2j_mata` in the uploaded Jericho PAC was
32×8/T4 (16 CLUT slots), versus 256×128 in the original HCTP source. The design
was barely legible. The previous Priority Selection stage froze every unselected
costume GIM and capped total padded pixels/CLUT to the Default baseline. At that
already-full memory allocation, any selected upgrade needing more pixel bytes
was blocked, irrespective of spare compressed PAC bytes. The 8× importance
multiplier could not overcome this constraint. This was a policy/allocation
failure, rather than failure to recognize the selected name.

**INFERRED:** The conservative baseline pixel envelope is a useful experimental
guard. It is not a measured game heap limit. **UNKNOWN:** The actual SVR 2011
texture heap ceiling and runtime safety of any newly generated combination
until tested in PPSSPP.

## Separate texture-only correction

**CONFIRMED implementation:** `desktop/texture_optimizer/priorities.py` starts
from exact Default GIM incumbents. For each selected upgrade it attempts to
reclaim space from unselected candidates. Selected maps never become worse
according to the existing perceptual loss. Only exchanges with positive net
8× priority-weighted improvement are accepted. Donors cannot increase their
pixel allocation or resolution. Existing cranial quality floors and new-cutout
alpha safeguards remain active. No geometry processing is involved.

The bounded deterministic greedy search shortlists donors by quality loss per
GIM/pixel byte, then measures actual whole-PAC storage, including compression
and alignment, before accepting them. It enforces both PAC bytes and padded
pixel/CLUT allocation. It does not prove an optimal allocation or impossibility
when no upgrade is found. Rejected upgrades and donor changes are reported.

**CONFIRMED:** Default, ATO without selections, Downgrade and Maximum Downgrade
do not call the new allocator. Existing `optimize_pac` behavior remains available
without `rebalance_priorities=True`, for reproducible historical comparisons.
The app's Priority Selection worker opts in. Zero selections still bypass it.
The review dialog now explicitly says other maps may fund selected fidelity.
Results show chosen dimensions/colors, donor count and selections with no gain.

## Jericho trial on the exact user-supplied output

**CONFIRMED binary/metric results:**

| Property | Uploaded output | Reallocation |
|---|---:|---:|
| PAC bytes | 143360 | 147456 |
| `y2j_mata` dimensions | 32×8 | 128×64 |
| `y2j_mata` CLUT slots / used colors | 16 / 13 | 16 / 16 |
| Occupied-area luminance SSIM | 0.497653 | 0.865370 |
| Fine-feature loss (lower is better) | 0.841749 | 0.116416 |
| Aggregate perceptual loss | 0.488422 | 0.168169 |
| Total padded pixel/CLUT bytes | 25792 | 25664 |

Only two costume maps changed: selected tights and unselected face. The face
changes from 128×64/31 used colors to 64×64/256 used colors, reclaiming 4096
pixel bytes. Face RGB RMSE and SSIM improve, but aggregate loss increases by
0.020066 and fine-feature loss increases by 0.199355. The existing cranial
aggregate/SSIM guard accepts it, and the per-detail regression warning flags it.
This tradeoff is exposed in the face comparison; it is not claimed lossless.
Materials keep T4/T8 depth; changing a T4 material to T8 is outside this trial.
The original tights' 256-color fidelity is therefore not fully preserved.

**CONFIRMED:** All stored and decoded non-costume section payloads, including
the complete YOBJ, are identical to the uploaded PAC. Native pointer, buffer,
index, palette, material, weight, alignment and size validation passed. CPU
renders use the actual extracted final model/textures. They are offline
comparisons, not Noesis or game screenshots. Accepted PACs and main stay intact.

Candidate SHA-256:
`ac659abb25d00d9fb832ec97de8e7ab007fc36d3b63823d9cca6a8dec6509ac0`.
Evidence, PAC and comparisons: `downloads/priority-reallocation/`.
**UNKNOWN:** In-game appearance/stability of this texture exchange, pending
the user's PPSSPP trial. Use a separate ISO and existing successful CH/ARC
injection procedure; retain the uploaded PAC as backup.

## Reproduce and test

```
python -m experiments.texture_fidelity_selection original-0600.pac user-output.pac fresh-directory --select y2j_mata --rebalance
python -m unittest tests.test_priority_reallocation tests.test_texture_review tests.test_adaptive_textures
python -m tools.ci_tests
```

Omit `--rebalance` to reproduce frozen-unselected allocation. Generated tests
cover full-budget exchanges, multiple donors, selected protection, deterministic
results, harmful exchanges, independent RAM limits, non-additive serialized
costs and cancellation. Real trials verify native structure and exact unrelated
payloads. Allocator coefficients and safeguards remain perceptual hypotheses;
review the selected texture and every donor, not just the aggregate score.

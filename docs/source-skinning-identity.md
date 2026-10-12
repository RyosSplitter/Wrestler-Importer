# Source-authorized skinning contacts — isolated 0101 experiment

This experiment lives on `experiment/source-skinning-identity`. It does not merge
main, replace an accepted PAC, or publish a new Windows application release.
The source was the user's original HCTP `0101.pac`; the PSP donor was the existing
`assets/Kurt-Angle-Ring.PAC`. Filenames do not select any correction behavior.

## What failed

**CONFIRMED:** The original source has 15 bind-coincident positions containing
33 separately indexed records with different effective bone influences. They
occur at pelvis/thigh, ankle/toe, knee/thigh and mouth/face contacts. The binary
source has 23 meshes, 4,096 vertex records, 4,974 triangles, 17 textures and 71
bones. The source PAC is 669,696 bytes, SHA-256
`985e0cb5614bc5dc26547aca8f985d7ce661d701e939d9c525c49173c1b2dd12`.

**UNKNOWN:** Whether every difference implements an intentional engine feature,
an authoring seam, a contact or another convention. Its presence in the original
is sufficient reason to preserve it; it is not sufficient evidence to repair it.

**CONFIRMED:** At parent commit `e7513e1`, `tools/blender_reduce.py` used
`tuple(v['position'])` as a geometric point key. Its per-bone first-record
assignment then combined incompatible records. `tools/jericho_hybrid_trial.py`
cached pruned weights by position and raised `Conflicting seam weights` when
another source branch arrived. `tools/region_mesh.py::pack_regions` also cached
by position. `pose_checks` required every coincident pair to remain closed.
Those assumptions were stronger than the source format warrants.

**CONFIRMED:** The pinned old reducer at the same minimum-limb profile retained
only 12/33 records with verified face/weight correspondence. The old packer
aborted, so there is no valid before PAC. All before images and metrics identify
that failed intermediate explicitly. Missing correspondence is not a zero-error
observation or proof of exactly which operation moved each missing record.

## Revised identity and preservation

**CONFIRMED (implementation and generated tests):** `tools/vertex_identity.py`
resolves local palette slots to normalized global bone influences. A geometric
point key includes its source topology domain, float32 position and effective
influences. A separate provenance key identifies supposed copies independently
of their current weights, so a changed copy still fails validation.

**CONFIRMED (implementation):** Original index connectivity defines initial
domains. Two storage components can share a domain only through a two-face
manifold edge with opposite directed orientation, identical endpoint positions
and global influences, matching exposed rendering controls/flags, and different
triangle geometry. Coincident overlays and nonmanifold contacts remain separate.
UVs/colors/normals remain separate corner records. Final packing additionally
requires matching serialized attributes and domain before sharing an index.

**INFERRED:** This edge evidence identifies continuous source surfaces across
storage chunks. It is more conservative than position-only welding, but is not
a complete specification of every undocumented HCTP mesh semantic. The converter's
existing render-template selection and material grouping are not rewritten here.

**CONFIRMED:** Each original divergent record receives `skin_locked`, exact bind
position, expected sparse influences, `skin_id`, `skin_domain`, and source IDs.
Blender carries provenance in an integer point attribute. Faces incident to a
locked record are held out of collapse. Locked records are checked after export,
packing and native decoding; no weights are averaged or changed to make contacts
agree. Existing nonprotected influence pruning/interpolation stays in place.

**CONFIRMED:** Protecting contact points alone did not protect adjacent surface
volume. Early candidates passed contact checks but failed pelvis/right-foot
regional nonregression and were rejected. `contact_shape_guards` now freezes
source faces in existing pelvic/foot reference regions only when those regions
contain original differing contacts. Foot influence support extends the foot
selection beyond the landmark box. For this input it selects 592 source faces.
No outward displacement, altered proportions or weight averaging is used.

**CONFIRMED:** An initial requirement that UVs and normals also match before
joining geometric storage chunks disconnected otherwise continuous UV seams and
caused decimation regressions. The rejected design is not the shipped policy:
corner attributes remain distinct while compatible geometric edges can connect.

**CONFIRMED:** Position rounding during budget fitting introduced new coincident
weight conflicts and was rejected. For source-contact models, fitting now tries
bounded normal precision first, then normal/UV precision, while keeping every
position exact. Entire protected contact faces and ocular records are excluded.
Other models keep the existing precision policy.

## Validation and measured result

**CONFIRMED:** Final `0101-PSP-source-skinning-identity-TEST.pac` is 145,408 bytes,
2,592 below the configured 148,000-byte policy. SHA-256:
`ac79307a694234dabb43e43266e22c64eea52d7607d4f841d66f5443cb81d21f`.
It contains 41 native vertex-buffer meshes, 3,264 vertex records and 3,675
triangles, with 17 textures. Noesis lists 88 material draw groups; this is not
the same count as native vertex-buffer meshes.

**CONFIRMED:** All 33 records and all 80 incident source faces match after native
serialization by cyclic material/float32-position/UV face correspondence and
global weights. Original/native indices are not assumed equal. Seven analytical
poses cover standing, alternating walking, bending, crouching, toe flexion and
mouth/neck stress. Maximum added motion error and contact-gap error are zero.
The comparison also rejects a new differing weight branch at any other coincident
position, altered bind transforms, invalid weights or missing protected faces.

**CONFIRMED:** The final regional comparison uses 24,000 samples in each direction
per pose and existing provisional tolerances. No regional p95 regression exceeds
its threshold. Standing left/right foot p95 distances, normalized by height,
improve from 0.00486568/0.00529822 to numerical roundoff; pelvic error remains
roundoff. This is tolerance-based nonregression, not a claim that every individual
sample or every unrelated metric improved.

**CONFIRMED:** Native audit checks internal pointers, allocation bounds,
relocations, vertex/index alignment and ranges, bone palettes, finite normalized
weights, texture/material consistency and actual padded PAC size. Unrelated base
section stored bytes and donor bone records remain exact. Existing single-slot
compatibility pads two meshes with zero influences: 392 vertex-buffer bytes,
with effective positions, triangles, weights and analytical motion unchanged.
PAC packaging code is unchanged.

**CONFIRMED:** Budget fitting uses the existing Default texture path at its
32-cap setting and existing free-limb 0.35 fallback. It applies only normal
precision to the final candidate: zero position or UV changes, unchanged weights,
maximum normal angular error 0.183586 degrees (limit 0.25). This is disclosed
shading precision loss, not a change in geometry to hide source contacts.

**CONFIRMED:** The full existing QA suite includes static/multiview comparisons,
14 body/facial poses and cranial/ocular probes. Native, ocular, source-record and
precision checks pass; the report still contains 47 review warnings, including
ordinary limb/material-boundary differences and open-surface topology. They are
retained for human review. The experiment is not marked universally clean.
The final automated test run passes 312 tests, including a real Blender worker
test and generated incompatible-contact/overlay/UV-seam regression fixtures.

**UNKNOWN:** Actual SVR 2011 animation semantics, runtime safety and this
candidate's appearance in PPSSPP remain untested. Analytical poses are not captured
game animation. The 148,000-byte budget is the established project policy, not a
proved universal hardware or game heap maximum. Static Noesis previews do not
emulate skinning or game material/alpha behavior; visible boot/knee cutouts remain
items to inspect in-game rather than silently smoothing or changing them here.

## Files and reproduction

**CONFIRMED:** The separate test PAC and review ZIP are in
`downloads/source-skinning-identity/`. The ZIP includes all 15 location tables,
120 matching clay comparisons, native mesh/submesh/weight tables, full QA HTML
and images, the actual embedded preview YOBJ, OBJ/MTL/PNGs, source-derived JSON
controls, pinned old reduced JSON, diagnostics, hashes and import instructions.
It does not include the original source PAC, donor PAC or third-party tools.

With an independently obtained source/base and the repository's existing Python
dependencies/Blender setup, run:

```python
from pathlib import Path
from desktop.core import Request, run_job
run_job(Request(source=Path('0101.pac'), base=Path('Kurt-Angle-Ring.PAC')),
        Path('new-job-directory'))
```

**CONFIRMED:** Default settings reproduce this experiment's texture policy.
For comparisons from the supplied intermediate files:

```sh
python -m tools.source_skinning_report prepared.json before-minimum-reduced.json \
    0101-PSP-source-skinning-identity-TEST.pac new-contact-report
python -m tools.source_skinning_region_review prepared.json before-minimum-reduced.json \
    0101-PSP-source-skinning-identity-TEST.pac new-regional-report.json --samples 24000
python -m unittest discover -s tests
```

**CONFIRMED:** These commands refuse to overwrite report outputs. To recreate
the old reduction, obtain the worker, reducer, region helper and stripifier from
commit `e7513e1`, keeping their relative directories; run that worker with the
provided `profile-2.json` and `prepared.json`. The old files do not consume the
new provenance/contact-guard fields. Blender 4.3.2 was used for this comparison.
Inspect source/raw and prepared weights independently using the included
`all-15-source-native-records.json`; source-to-preparation ordinal IDs are used
only after unchanged mesh/material index topology is verified. Native matches
use face correspondence rather than ordinal assumptions.

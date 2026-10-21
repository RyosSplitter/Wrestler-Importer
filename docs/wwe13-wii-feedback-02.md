# WWE ’13 Wii feedback round 2

This is a separate experiment on `experiment/wwe13-wii-feedback-02`. It does
not register WWE ’13 conversion in the production application or merge any
trial into main. No accepted PAC is overwritten.

## User observations and immutable baselines

**CONFIRMED — user report, not independent runtime reproduction:** The user
tested the previous nine-source PAC pack in PPSSPP. The exact PAC hashes and
per-variant observations are recorded in
[user-feedback-02.json](wwe13-wii-nine-models/user-feedback-02.json).

- Barrett: good. Bradshaw APA: perfect. Preserve these complete baselines.
- Edge: textures good, hair needs work. Preserve the tested texture baseline.
- Orton: overall good, left wristband needs work.
- Booker: overall good, elbow pad region needs work.
- Bradshaw Acolyte: close, wristbands ride too high.
- Jericho ring: substantial texture problems. Entrance: problems throughout.
- CM Punk ring: rear trunks and overall textures need work. Entrance: textures.
- Bret ring and Billy: distorted shape and textures. Bret entrance: bare textures.

**CONFIRMED — source previews:** Bradshaw variant 0 is Acolyte, variant 1 is
APA. These are different attires, not automatically ring/entrance counterparts.
CM Punk has two entrance variants in the source. **UNKNOWN:** which of those
two the user reviewed. Do not infer costume purpose solely from bundle index.

## Explicit costume budget

**CONFIRMED — configuration and serialized builds:** The user requested
180,000 bytes for WWE ’13 entrance PACs. The subsequent user correction sets ring to 152,064 across all formats. The independent
WWE ’13 policy in `tools/wwe13_budget.py` now supplies the same limit to texture
allocation, native validation, result manifests, and exact-PAC exports.

| Role selected explicitly | Configured PAC cap | Largest 2,048-byte-aligned PAC |
| --- | ---: | ---: |
| Ring | 152,064 | 151,552 |
| Entrance | 180,000 | 178,176 |

**CONFIRMED:** 180,224 bytes still exceeds the new entrance cap. Raising this
setting does not make the previously blocked Edge alternate fit automatically.

**UNKNOWN:** 180,000 is not a newly discovered loader or runtime heap limit.
It is the user's experimental output policy. The native donor's independently
measured 54,016-byte pixel/CLUT envelope is unchanged; extra file space does not
authorize extra runtime texture memory. Structural and analytical success does
not prove an entrance PAC can be used safely in a match slot.

**CONFIRMED — backward compatibility:** Old reports retain their original attestations and are never reinterpreted
from their variant index. New validation and conversion use the corrected
shared ring limit; see [current size policy](pac-size-policy.md). HCTP/JBI
changes are limited to the shared byte cap; their conversion algorithms remain unchanged.

## Texture-only entrance trials

**CONFIRMED — binary comparison:** `tools/wwe13_texture_upgrade.py` wraps the
existing independent resolution/palette candidate generator. It retains each
baseline GIM as a candidate and permits only lower combined detail/color loss
for additional candidates. The allocator still measures the actual complete
PAC through the existing packer, checks decompression round trips, and enforces
the donor texture-memory envelope separately.

**INFERRED:** The combined loss is a useful nonregression safeguard. It cannot
guarantee a subjective visual improvement. It is not an in-game acceptance test.

The source, old PAC and candidate are rendered with a common camera. Model
YOBJ bytes and every non-texture stored PAC section must remain byte-identical.
Native structural checks and pose replay are rerun against each final PAC.
Full static/analytical comparison QA is rerun for Bret entrance and CM Punk
entrance variant 1. For the other texture-only candidates the complete previous
geometry QA is inherited by verified exact YOBJ identity, with the original
report retained unmodified and explicit baseline/final hashes. This inheritance
does not relabel an old report as a new runtime test. Existing source-shape
findings remain unresolved in texture-only trials.

Reproduction, using the original geometry work directory:

```python
from tools.wwe13_texture_upgrade import factory
from tools.wwe13_wii_texture_refine import run
run("BASELINE_WORK", "YOUR_PSP_BASE.PAC", "NEW_EMPTY_OUTPUT",
    candidate_factory=factory("BASELINE_WORK"),
    filename="Entrance-180K-Texture-Trial.pac", costume_role="entrance")
```

The baseline work contains the checked PAC, `candidate.yobj`, `packed.json`,
contracts, native checks, atlas/source images, and texture report. Rebuild it
from the source PAC using the original study's settings if those private files
are unavailable. Source assets remain private and are not repository fixtures.

## Why geometric distance alone was insufficient

**CONFIRMED — stage measurements:** The new reusable read-only
`model_qa/surface_attributes.py` samples the candidate surface, finds nearest
reference triangles on the *same atlas page*, interpolates reference UVs, and
measures source-texel displacement and sampled source-color differences. Both
models use the full original images. This isolates geometry/UV placement from
palette and resolution reduction. It never assumes vertex-index correspondence.

The controlled baseline-to-itself check yields approximately zero UV error.
With 12,000 deterministic area-weighted samples, the previous builds show:

| Model | UV displacement p95 after decimation, original texels | After packing |
| --- | ---: | ---: |
| Billy ring | 18.98 | 19.17 |
| Bret ring | 13.08 | 13.70 |
| Bret entrance | 76.80 | 68.15 |
| Jericho entrance | 23.62 | 23.63 |

**INFERRED:** Decimation is a major contributor to their visible texture
placement defects: the deviations already exist before serialization and
before texture reduction. This does not prove that all their shape defects
come from decimation. Source-to-PSP retargeting still requires independent
inspection; the existing full QA primarily compares the already adapted source
against the final model.

**CONFIRMED:** Edge's hair-page UV displacement after decimation is about
0.00010 original texels, consistent with the existing unreduced Hair region.
**UNKNOWN:** this does not establish whether his reported hair problem comes
from source retargeting, lost dynamic hair controllers, layered geometry,
alpha reduction, native rendering settings, or some combination. Do not label
it a hair-decimation defect without further evidence.

**INFERRED — provisional diagnostic threshold:** p95 exceeding two source
texels or surface error exceeding 0.5% of reference height requests review.
These are not calibrated acceptance gates: even the user-approved Barrett and
APA builds can trigger review. Overlapping cloth/skin surfaces on the same
page can make nearest-surface correspondence ambiguous. The report explicitly
states this limitation. No automatic repair follows from this metric.

The isolated corpus runner now writes `qa/surface-attributes.json` alongside
the existing QA and includes its review state in its result. The 14 older PACs
were inspected read-only at three stages: reference control, after decimation,
and after packing. Wrist, elbow and knee ROIs supplement the existing regions.

## Source UV seam protection experiment

**CONFIRMED — code inspection:** Source UVs are corner attributes, while
compatible geometric points can share a Blender point. Grouping source
components into region/material reducer meshes does not by itself impose an
explicit lock on every distinct source UV corner contact.

**INFERRED:** Protecting those contacts may reduce UV migration. The opt-in
`--preserve-uv-seams` experiment conservatively adds coincident referenced
corners with different UVs or material bindings to the reducer's existing
protected-point set. It does not weld vertices, average weights, or apply a
manual displacement. Default behavior remains unchanged.

**CONFIRMED — rejection:** Booker's first seam-protection candidate fails the
existing native analytical pose gate. It is retained for diagnosis and is not
distributed as a repaired PAC. Do not relax the gate to make the trial pass.

**CONFIRMED — additional trials:** Bret ring and Orton also fail grip-area
envelopes; Booker fails grip and wrist-flex envelopes. Billy and Bradshaw
Acolyte pass native gates. Billy's original-image placement p95 improves from
19.17 to 5.65 texels, and original-image placement RGB RMSE from 27.44 to 11.28.
His full-source-texture preview removes the large misplaced black knee-pad
triangles visible in the baseline. Bradshaw's whole-surface p95 changes only
3.69 to 3.64 texels, insufficient evidence that the wristband complaint is fixed.
No seam-protection trial is promoted or substituted for a tested baseline.

**INFERRED:** Additional seam locks change which remaining hand edges the
decimator collapses at the same face-count floor. The new failures show why a
global seam policy needs region-specific nonregression checks, rather than
being accepted solely because Billy's static appearance improved.

## Entrance candidate sizes

**CONFIRMED — serialized files and stored-section comparison:**

| Texture-only trial | Old PAC | New PAC | Pixel/CLUT bytes, including retained tables |
| --- | ---: | ---: | ---: |
| Bret entrance | 147,456 | 169,984 | 51,392 |
| CM Punk entrance 1 | 147,456 | 167,936 | 51,392 |
| CM Punk entrance 2 | 147,456 | 167,936 | 51,392 |
| Jericho 1999 entrance | 147,456 | 161,792 | 51,392 |
| HBK entrance, previously studied | 147,456 | 176,128 | 51,392 |

All remain under the unchanged 54,016-byte donor texture envelope. **UNKNOWN:**
the new files' actual SVR 2011 gameplay behavior until tested. They are entrance
trials only. Geometry defects in the previous entrants are deliberately
unchanged, so they cannot be described as complete model repairs.

**UNKNOWN:** Seam locks alone have not been demonstrated to correct all the
reported geometry issues. Billy/Bret shape, bands, pads, hair and CM Punk's
rear trunks remain separate appearance investigations until comparison renders,
regional metrics, structural checks and PPSSPP review support accepting a fix.

## Tests

Procedural repository tests cover explicit role selection, native validation
limit routing, unchanged handling of historical manifests, topology-independent
UV comparisons, UV drift with identical positions, missing images, and seam
lock identity without modifying distinct weights. No game-derived test fixture
is committed. Private source PACs and all original test PACs remain hash-checked.

## Follow-up evidence

See [geometry and opacity round 3](wwe13-wii-geometry-opacity-03.md) for the
rejected global seam/component policies, region-isolated wrist experiment,
Edge opacity-support QA and controlled hair A/B candidates. None is a new
production default; the app release remains held.

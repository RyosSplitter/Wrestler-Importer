# Standalone PAC validator (experimental)

Open **Quality Assurance → Validate PAC...**. Select an existing PSP wrestler
PAC, optionally its original HCTP PAC, and a parent folder for a new results
directory. The configured size budget defaults to **148000 bytes**. This is the
existing conversion target, not a universal native PSP loader limit. A larger
native reference can be inspected using an explicitly larger budget; doing so
does not establish game compatibility.

**Apply verified repairs to a new copy** defaults on. Turn it off for report-only
inspection. The validator runs separately from the converter and folder packer.
Its output never overwrites its input or an existing results directory.

## Checks and outputs

- `original.pac`: exact input snapshot and SHA-256 provenance.
- `before/`: all supported native YOBJ structural audits, OBJ/MTL/PNG exports and
  five textured CPU rest views per model; texture inventory includes extra tables.
- Native pointer ranges, allocation overlaps, index ranges, palettes, finite
  attributes and weight sums use the established strict binary reader.
- Material controls are checked against the resolved GIM palette depth. Texture
  resolution is case-insensitive and requires an unambiguous mapping, preferring
  section 9. Unknown layouts and decode failures block repairs.
- Every supported model receives analytical standing, walking, bending, crouching,
  shoulder, neck, head, jaw, elbow and ocular/controller probes. Missing bones are
  **unsupported**, never silently counted as passing. Seam displacement is a
  diagnostic; coincident vertices are never averaged or welded.
- `after/`: corresponding inspection when a repair candidate exists.
- Optional HCTP reference: existing `model_qa.pipeline.run` surface/depth/curvature,
  regional anatomy, silhouette, head/culling and posed comparisons, matched clay
  renders and heatmaps in `reference-before/` and `reference-after/`. This existing
  comparator evaluates the **main model**; auxiliary models receive native and
  analytical checks, without an invented HCTP correspondence.
- `report.html` and `report.json`: findings, unsupported checks, exact changes,
  sizes, hashes, repair rejection reasons and links to reference reports.
- `repaired.pac`: emitted only when an allowlisted repair passed revalidation,
  preservation checks, the configured byte budget and optional reference review.
  No redundant PAC is emitted if no repair was performed.

The UI retains the report under **Last validation report**. Folder navigation
remains live; a requested PAC loads after validation, without discarding the
completed validation report. Closing the app terminates the worker. Any incomplete
results folder is not a successful report; a published PAC is an atomic full-file
write, never a partial named PAC.

## Repairs currently implemented

1. **PAC outer alignment**: rebuild with the existing section writer, align section
   addresses to 16 bytes and the file to 2048 bytes. Verify section IDs/order and
   every stored section hash remain exact. Refuse nonzero unclassified gaps or
   trailers that the writer cannot preserve. These alignments are converter
   conventions, not proof that every unaligned native PAC is defective.
2. **Single-slot rendering compatibility**: reuse
   `desktop.skinning.apply_single_slot_compatibility`. Supported one-slot float32
   skinned buffers are padded to three slots using exact zero weights and existing
   bones. Re-serialize/compress only changed models with the established writer.
   Verify positions, faces, UVs, normals, material state, skeleton and effective
   nonzero weights remain exact; compare analytical body/head motion exactly.
   Unrelated stored and decoded sections remain exact. No two-slot, integer-weight
   or rigid layout is generalized into this policy without evidence.

If any attempted repair fails, no repaired PAC is published. Candidates that
would exceed the budget are withheld without reducing textures or anatomy. With a
source reference, new `(region, pose, kind, severity)` findings also block export.
Layout-only transformations additionally require exact effective geometry/weight
preservation; this is stronger than relying on flag counts to hide small geometric
regressions. The current repair set never changes anatomical vertex positions.

## Evidence and limits

**CONFIRMED:** synthetic conformance tests exercise no-op preservation, exact
single-slot repair, multi-model/unrelated-section preservation, alignment repair,
unsafe-gap rejection, invalid-container/size failure, report-only mode and input
protection. The same previously user-accepted Rock compatibility implementation
is reused. Native regression inspections cover Lance, Jericho, Rock (three
models), Benoit/blood and Kurt references. Tests and runtime smoke evidence are
in `downloads/model-suite-validator/`.

**CONFIRMED:** when supplied a real HCTP reference, the validator invokes the
existing comparison/report system without modifying that source or converter.
Matched images are CPU geometry renders, **not Noesis or PPSSPP captures**.

**INFERRED:** extending the accepted Rock rendering-layout policy to other models
with the same verified one-slot record layout is useful; it is an experimental
compatibility policy, not a fully decoded SVR engine requirement.

**UNKNOWN:** a finite analytical pose does not prove correct game facial-controller
semantics or animation. A standalone PSP PAC does not establish its intended
anatomical shape. Even with an HCTP reference, a previously exported PAC has no
saved intermediate stages to identify where anatomical damage first occurred.
Automatic jaw/pelvis reshaping, arbitrary weight replacement, invalid pointer
reconstruction and texture redesign are deliberately unsupported repairs. Such
findings require review/reconversion through the established guarded pipeline.
Real game clips, runtime memory pressure and engine behavior require PPSSPP tests.

## Reusable API / worker

```python
from desktop.pac_validator import validate_pac
report = validate_pac(
    'Existing.pac', 'Existing-qa-new',
    reference='Original-HCTP.pac',  # optional
    repair=True, max_bytes=148000, resolution=256, samples=4000,
)
```

Frozen and source worker entry:
`PSP-Model-Suite.exe --suite-validate REQUEST.json EXISTING_JOB_DIRECTORY`.
The request contains the API arguments above; the job receives `result.json` and
worker failures receive `error.log`. A completed report requiring human review
is a successful inspection job, not a claim that its PAC passed.

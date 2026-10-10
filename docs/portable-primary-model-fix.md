# Source PACs with auxiliary YOBJ models

Evidence date: 2026-10-10. Isolated branch: `fix/hctp-primary-model`.
The portable app's conversion, geometry, weight-transfer, texture conversion,
native serialization and PAC packaging algorithms are unchanged by this fix.
The historical `stable_pipeline/` snapshot and its integrity manifest are also
unchanged. This change is confined to source-model selection and regression tests.

## Reproduced failure

**CONFIRMED:** The uploaded `0000.pac` is 542,976 bytes, SHA-256
`d1d5ca744b5a793743851c142bf273554c81076ae3b8231834364559e048a973`.
Its outer PAC ranges validate. It has YOBJ payloads in sections 2, 6 and 7.
The previous source geometry/weight reader rejected it with
`Expected one uncompressed HCTP model section`; the texture reader separately
rejected it with `Expected exactly one YOBJ model section in PAC`.

**CONFIRMED:** Decoding section 2 directly yields a model internally named
`hogan`, with 13 source meshes, 2,013 original position records, 2,308
UV/color-split vertices, 3,077 triangles, 71 bones and 18 referenced textures.
Sections 6 and 7 are additional models named `l_pat` and `l_pat01`; each has
one mesh and 64 triangles. The costume texture table contains 19 entries,
but the main model references 18. All 19 images decode with the existing
PSMT4/PSMT8 texture implementation.

**INFERRED:** These additional models serve accessory/effect purposes; their
precise in-game use is not established by their names. The main-model selector
does not need to assume their purpose or decode their geometry.

## Selection policy

**CONFIRMED:** `tools.pac_inspect.select_model_section` selects exactly one
uncompressed YOBJ in section 2 when that section exists. Other YOBJ sections
do not make the main model ambiguous. Selection is independent of file order,
model/character names, texture names and payload size.

**CONFIRMED:** Duplicate section-2 entries, a non-YOBJ section-2 payload, and
multiple YOBJs without a main section are rejected. A malformed selected model
still fails its normal geometry/skeleton/weight validation; it is never replaced
with an auxiliary model. The previous single-model fallback remains available
when no section 2 exists. Raw YOBJ inputs retain their previous behavior.

**CONFIRMED:** Both maintained HCTP geometry and weight loaders and the maintained
YOBJ loader use the selector. The shared PS2 texture reader now uses that
maintained YOBJ loader for its referenced-texture list, while retaining the pinned
texture codec and its public exception type. Source QA already uses the maintained
weight reader, so it selects the same main model as conversion. Unreferenced
auxiliary textures are not decoded or incorporated into the main model.

**CONFIRMED:** The original PAC is read-only. Additional source sections are not
deleted, rewritten or copied blindly into a PSP PAC. As before, PSP output is
built from the user's PSP donor with the established main-model/texture section
replacement process. This fix does not add source accessory conversion support.

## Verification

**CONFIRMED:** All 177 repository tests pass after the change. New original,
synthetic multi-YOBJ fixtures cover reordered auxiliaries, main-only geometry,
weights and textures, QA source loading, unchanged source bytes, auxiliary layouts
and images unsupported by the main-model decoder, corrupt main models, duplicate
main IDs, ambiguous main selection, invalid auxiliary ranges and unchanged
single-model/raw inputs. No new game assets are needed or redistributed.

**CONFIRMED:** The uploaded original file now passes the desktop adapter's
inspection and read methods, all original weight checks, main-model texture
decoding and the existing uniform-alignment/selective-weight preparation stage
with the supplied Kurt PSP development base. Its 18 referenced textures are
decoded independently of the auxiliary models.

**CONFIRMED:** The original `0000.pac` also completes the unchanged Blender 4.3.2
conversion and full QA stage locally: the resulting PAC is 133,120 bytes, with
43 native draw meshes, 2,331 vertices and 2,725 triangles. It passes native
pointer/range/alignment/relocation/bone-palette/normalized-weight checks, the
148,000-byte constraint and all 16 existing ocular compatibility probes.
QA runs all 14 body/jaw poses at 24,000 samples and 320-pixel render resolution.
Source and donor hashes remain unchanged.

**CONFIRMED:** The full geometric QA report retains five unresolved visual-review
flags: neck, pelvis, buttocks and both hand regions in the rest pose. Pelvis and
buttocks are marked high-review. Thus this evidence establishes the import fix
and successful native output, not visual perfection or game compatibility. No
anatomy, weight-transfer or tolerance changes were made to suppress these flags.

**CONFIRMED:** Across 13 uploaded numbered reference inputs, main-model parsing
matches direct section decoding (or preserves the same malformed-weight
rejection); the texture-model descriptors of all 12 single-model inputs also
match the previous pinned reader exactly. Eleven desktop source inspections
pass. Existing rejections remain for `3002.pac` (missing `h_01` texture) and
`2902.pac` (unnormalized source weights). These independent source-support issues
are recorded rather than broadened into this repair.

The [machine-readable validation evidence](portable-primary-model-validation.json)
contains source/output hashes, reference counts, native checks, analytical poses,
review flags and preservation checks for the accepted Lance/Jericho baselines.

**UNKNOWN:** Actual accessory/effect behavior, support for every HCTP PAC variant,
and in-game correctness of newly generated outputs. A successful source import
does not certify a conversion or replace native/size/QA/PPSSPP validation.

**CONFIRMED about test design:** The Windows release workflow includes a frozen
conversion of the existing Lance development fixture with two additional,
reordered synthetic YOBJ sections. It compares the final PAC hash with the
single-model fixture and requires identical output, in addition to the existing
frozen UI/runtime, Lance/Jericho conversions, native checks and complete QA.
Actual build outcomes are recorded in the GitHub Actions run for the release.

```text
python -m unittest tests.test_main_model_selection -v
python -m tools.ci_tests
```

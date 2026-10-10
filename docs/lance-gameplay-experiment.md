# Lance: isolated SVR 2011 PSP gameplay experiment

This packages the final reviewed posterior-decimation trial from `566030c57c7ff4c0579975d1eb6f686eaea2f7d2`, using `trial-02/candidate.yobj`. It does not use the rejected first trial. No further geometry, rigging or texture processing was performed. The converter and packaging implementations were not changed, the accepted PAC was not overwritten, and this branch remains separate from main.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `Lance-SVR2011-PSP-posterior-guard-TEST.pac` | 145408 (142 KiB) | `807d60134bb91071f01a28381dd0368214ecfb5c57b3713ae3829203f1568700` |
| Accepted PAC / bundled `backups/Lance-ACCEPTED-BACKUP.pac` | 141312 | `dbe2e1e0bd1a78ac84c5c4ff5fb06cd8247aabea3f6dcf2cace34c965ac8f1e3` |
| `Lance-SVR2011-PSP-posterior-guard-TEST-bundle.zip` | 1101497 | `7966c5e4d2ce751f1ad246e6cd79f7782b3026042245de6ae97b4be89c306364` |

[Download test PAC](../downloads/Lance-SVR2011-PSP-posterior-guard-TEST.pac), [bundle with backup, preview and instructions](../downloads/Lance-SVR2011-PSP-posterior-guard-TEST-bundle.zip), [validation report](../downloads/Lance-SVR2011-PSP-posterior-guard-TEST-validation.json), [hash file](../downloads/Lance-SVR2011-PSP-posterior-guard-TEST.sha256).

## Packaging and validation

The existing `tools.yukes_bpe.compress` and `tools.pac_repack.replace_sections` functions replaced only section 2 of `downloads/1800-PSP-hybrid-source-pelvis-restored.pac`. Section table offsets/sizes and padding were rebuilt using the unchanged packer. Stored sections 8 and 9 remain byte-identical, preserving every native GIM texture including alpha. Native GIM images and texture-table ranges were decoded and checked.

The final PAC contains exactly the reviewed YOBJ, SHA-256 `b591b1b0386462d1beaac0188a617c1dfb90b04925c9c5d16bee53a179a3f849`. Its preview YOBJ is extracted from the finished PAC and matches that hash. The full static and analytical-pose QA evidence therefore applies to the actual packaged model without a new geometry-processing step. The prior gate found posterior-region improvement and no regressions. Existing unrelated review flags remain documented. One new raw face/neck-turn sampling flag was retained and separately proven to have unchanged local posed triangle/weight signatures and unchanged fixed-reference errors; no tolerance was relaxed.

Auditing the actual decompressed PAC model passed allocation bounds, disjoint ranges, pointer/POF0 relocation consistency, alignment, index ranges, valid skeleton/palette entries, finite vertex attributes and normalized weights. The PAC table is in bounds, nonoverlapping, section addresses are 16-byte aligned and the final file is 2048-byte aligned. It is below the strict 148000-byte budget. All 79 skeleton records, bone palettes, texture metadata and material/render controls match the accepted baseline.

Native meshes stay at 57. The accepted model had 2339 vertices / 2360 triangles / 4262 indices; the reviewed correction has 2385 vertices / 2420 triangles / 4318 indices. Textures remain 19 and material records remain 96. The corrected expanded YOBJ is 208384 bytes, stored as 125059 BPE bytes. These are the previously reviewed geometry changes, not new packaging changes. The bundle includes detailed mesh/submesh/vertex-weight CSVs and pointer/allocation reports for accepted and finished models.

Validation: the unchanged packaging/audit path passed `python -m unittest tests.test_pac_inspect tests.test_textures_and_repack tests.test_yukes_bpe tests.test_psp_mesh_merge` — **31 tests passed**. The complete experiment QA suite had already passed **43 tests**. No PSP game-engine or PPSSPP run was performed here.

## Import into SVR 2011 PSP

1. Back up your working ISO, CH.PAC, ARC and wrestler slot.
2. Inject only `Lance-SVR2011-PSP-posterior-guard-TEST.pac` into your intended ring-model entry using PAC Editor v6.7.1 and your established working workflow. Use `EMD\00010001.pac` only if it remains your intended test slot.
3. Resolve archive alignment/space changes with Rebuild as needed, then update ARC against the resulting CH.PAC and save the ISO. Confirm the entry size and that its allocation does not overlap the next entry. Do not reuse ARC data from a differently sized archive.
4. Restart PPSSPP fully and begin a fresh match; do not load a save state created with another model version.
5. Inspect the rear pelvis standing, walking, bending and crouching. Check seams and shading, entrance, match, victory and unrelated arena/turnbuckle geometry. Repeat cycles to check intermittent crashes.
6. Restore the accepted baseline before testing Jericho independently. Report which version, motion and repeat count produced any defect or crash.

Open `preview/candidate.obj` in Noesis with the supplied MTL/PNGs alongside it, then apply the established orientation/cull/shading toggles once. OBJ shows static geometry; animation validation must come from PPSSPP. The existing [full QA experiment bundle](../downloads/Lance-QA-decimation-experiment.zip) retains before/after renders.

Neither experimental branch is merged. General decimation-preservation rules will be considered after successful in-game validation and sufficient evidence from reference models; this packaging task does not enable the experimental rule for normal conversions.

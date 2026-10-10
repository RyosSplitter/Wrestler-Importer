# Jericho: isolated SVR 2011 PSP gameplay experiment

This packages the reviewed facial-weight experiment from `4373b5eb15818d84b23ef313fb6ce72f8a1446d2`. No further geometry, rigging or texture processing was performed. The converter and packaging implementations were not changed, the accepted PAC was not overwritten, and this branch remains separate from main.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `Jericho-SVR2011-PSP-facial-weights-TEST.pac` | 143360 (140 KiB) | `f4f60125520f48285b4d03cd59abc21b980af4eca24124bc5a29423108aa3f1e` |
| Accepted PAC / bundled `backups/Jericho-ACCEPTED-BACKUP.pac` | 147456 | `1715f8f2768dbe1c8293461dd10c72d383397d660b8c61689365683bbf2f5729` |
| `Jericho-SVR2011-PSP-facial-weights-TEST-bundle.zip` | 1064650 | `314d87fffed5a97af3782893acbe4ebf1a740cfac74f6dc5c4a69eb1c00b8d37` |

[Download test PAC](../downloads/Jericho-SVR2011-PSP-facial-weights-TEST.pac), [bundle with backup, preview and instructions](../downloads/Jericho-SVR2011-PSP-facial-weights-TEST-bundle.zip), [validation report](../downloads/Jericho-SVR2011-PSP-facial-weights-TEST-validation.json), [hash file](../downloads/Jericho-SVR2011-PSP-facial-weights-TEST.sha256).

## Packaging and validation

The existing `tools.yukes_bpe.compress` and `tools.pac_repack.replace_sections` functions replaced only section 2 of `downloads/0600-PSP-hybrid-Jericho.pac`. Section table offsets/sizes and padding were rebuilt using the unchanged packer. Stored sections 8 and 9 remain byte-identical, preserving every native GIM texture including alpha. Native GIM images and texture-table ranges were decoded and checked.

The final PAC contains exactly the reviewed YOBJ, SHA-256 `7f574a73249a4344d1523922d8626f39a4c666b562c44fa32759b0649f70017c`. Its preview YOBJ is extracted from the finished PAC and matches that hash. The full static and analytical-pose QA evidence therefore applies to the actual packaged model without a new geometry-processing step. The earlier gate had no regressions or review flags.

Auditing the actual decompressed PAC model passed allocation bounds, disjoint ranges, pointer/POF0 relocation consistency, alignment, index ranges, valid skeleton/palette entries, finite vertex attributes and normalized weights. The PAC table is in bounds, nonoverlapping, section addresses are 16-byte aligned and the final file is 2048-byte aligned. It is below the strict 148000-byte budget. All 79 skeleton records, texture metadata and material/render controls match the accepted baseline. The previously reviewed changes to 18 bone palettes are preserved; packaging adds none.

Native counts stay at 54 meshes, 2387 vertices, 2413 triangles, 4085 indices, 20 textures and 94 material records. The corrected expanded YOBJ is 193488 bytes, stored as 119105 BPE bytes. The bundle includes detailed mesh/submesh/vertex-weight CSVs and pointer/allocation reports for accepted and finished models.

Validation: `python -m unittest tests.test_pac_inspect tests.test_textures_and_repack tests.test_yukes_bpe tests.test_psp_mesh_merge` — **31 tests passed**. The complete experiment QA suite had already passed **43 tests**. No PSP game-engine or PPSSPP run was performed here.

## Import into SVR 2011 PSP

1. Back up your working ISO, CH.PAC, ARC and wrestler slot.
2. Inject only `Jericho-SVR2011-PSP-facial-weights-TEST.pac` into your intended ring-model entry using PAC Editor v6.7.1 and your established working workflow. Use `EMD\00010001.pac` only if it remains your intended test slot.
3. Resolve archive alignment/space changes with Rebuild as needed, then update ARC against the resulting CH.PAC and save the ISO. Confirm the entry size and that its allocation does not overlap the next entry. Do not reuse ARC data from a differently sized archive.
4. Restart PPSSPP fully and begin a fresh match; do not load a save state created with another model version.
5. Test jaw/chin movement in entrances, taunts, neck turns and victory motions, plus standing, match behavior, eyes, scalp and hair. Repeat entrance/match/victory cycles to check intermittent crashes and inspect arena geometry.
6. Restore the accepted baseline before testing Lance independently. Report which version, motion and repeat count produced any defect or crash.

Open `preview/candidate.obj` in Noesis with the supplied MTL/PNGs alongside it, then apply the established orientation/cull/shading toggles once. OBJ shows static geometry; animation validation must come from PPSSPP. The existing [full QA experiment bundle](../downloads/Jericho-QA-facial-weights-experiment.zip) retains before/after renders.

Neither experimental branch is merged. General weight-transfer rules will be considered after successful in-game validation and sufficient evidence from reference models; this packaging task does not enable the experimental rule for normal conversions.

# Evidence ledger and scope of claims

**CONFIRMED:** Paths below are repository-relative. Evidence IDs qualify the
claims in this book. Code/tests prove a supported implementation contract;
archived binary reports prove observations on identified samples; user gameplay
reports prove only the reported test outcome. None implies exhaustive game
coverage. Historical notes may contain superseded conclusions; use the qualified
current book and retained errata when interpreting them.

| ID | Subject | Executable evidence / archived record | Claim scope |
|---|---|---|---|
| E01 | beta/current branches |`stable_pipeline/profile.json`, `app/pipeline.py`, `app/size_fit.py`, `docs/beta-validation.md`, Git commits in reproduction guide|CONFIRMED pinned backend and branch separation; newer fixes not default beta|
| E02 | PAC/table/packer |`tools/pac_inspect.py`, `tools/pac_repack.py`; `tests/test_pac_inspect.py`, `tests/test_textures_and_repack.py`|CONFIRMED observed layout and writer checks; universal ID semantics UNKNOWN|
| E03 | BPE |`tools/yukes_bpe.py`; `tests/test_yukes_bpe.py`; `docs/slaughter-reference.md`|CONFIRMED bounded codec/sample wrappers; engine RAM policy UNKNOWN|
| E04 | common YOBJ/bones |`tools/yobj_read.py`, `tools/psp_mesh_audit.py`; `tests/test_yobj_read.py`|CONFIRMED parsed offsets/parents; opaque fields UNKNOWN|
| E05 | HCTP corners/VIF |`tools/hctp_read.py`, `tools/hctp_weights.py`; `tests/test_hctp_read.py`, `tests/test_hctp_weights.py`|CONFIRMED supported packets and source-weight provenance; full VU semantics UNKNOWN|
| E06 | PSP buffers/native writer |`tools/psp_mesh_audit.py`, `tools/psp_mesh_merge.py`; `tests/test_psp_mesh_merge.py`|CONFIRMED sample allocation/layout/palette contracts; rigid attachment UNKNOWN|
| E07 | POF0/alignment |`tools/psp_mesh_audit.py::relocations/encode_relocations`, `tools/yobj_alignment.py`; merge/texture/repack tests|CONFIRMED pointer-field encoding and writer padding|
| E08 | RTX3/GIM |`app/ps2_textures.py`, `tools/texture_convert.py`, `tools/reduce_psp_textures.py`; `tests/test_ps2_textures.py`, `tests/test_textures_and_repack.py`; `docs/texture-decoder.md`|CONFIRMED supported real/synthetic subset separately identified; unsupported formats UNKNOWN|
| E09 | coordinates/fit/IR |`tools/prepare_model.py`, `tools/lance_abs_fix.py`, `model_qa/geometry.py`, `tools/psp_mesh_merge_trial.py`; prepare/model-QA tests|CONFIRMED implementation conventions; native controller matrix semantics INFERRED|
| E10 | five weight methods |`tools/weight_trial_review.py`, `tools/blender_weight_study.py`, `tools/hctp_weights.py`; `tests/test_weight_trial_review.py`; `docs/benoit-weight-trials.md`|CONFIRMED trial/decoder results; universal best method UNKNOWN|
| E11 | region/reducer |`tools/region_mesh.py`, `tools/blender_reduce.py`, `tools/blender_hybrid_reduce.py`; `tests/test_region_mesh.py`; `docs/region-decimation.md`, `docs/1800-hybrid-budget.md`|CONFIRMED code, recorded worker/count results; native studio decimator UNKNOWN|
| E12 | inherited overlay state |`tools/psp_materials.py`; `tests/test_psp_materials.py`; `docs/material-state-fix.md`|CONFIRMED words/mismatch; crash causality and full bit semantics INFERRED/UNKNOWN|
| E13 | vertex opacity |`docs/opacity-correction.md`, stable opacity profile and sample report|CONFIRMED alpha histogram/edit and reported gameplay resolution|
| E14 | paired native Slaughter |`docs/slaughter-reference.md`, `downloads/Slaughter-PS2-PSP-reference-review.zip`|CONFIRMED measured layouts/counts; art/production workflow intent INFERRED|
| E15 | original QA/stage trace |`model_qa/{geometry,regions,metrics,render,pipeline}.py`; `tests/test_model_qa.py`, `tests/test_model_qa_case_studies.py`; `downloads/HCTP-Model-QA-0.1-study.zip`|CONFIRMED reference comparison and saved-stage evidence; sampling/pose limits explicit|
| E16 | Lance posterior success |immutable commit `27e2f1364dda8f76a940d80e188da07a0d619d86`: `tools/lance_decimation_guard_trial.py`, `tests/test_lance_decimation_guard.py`, `docs/lance-decimation-experiment.md`, `docs/lance-gameplay-experiment.md`, gameplay/QA bundles|CONFIRMED isolated source guard, rejected neck regression, final structure; user reported perfect-looking posterior|
| E17 | Jericho jaw |`tools/jericho_weight_guard_trial.py`, opt-in `prepare_hybrid`; `tests/test_jericho_weight_guard.py`; `docs/jericho-weight-transfer-experiment.md`, `docs/jericho-gameplay-experiment.md`, facial experiment bundle|CONFIRMED weights/pose improvements and reported jaw fix; whole-cranial preservation superseded by selective policy|
| E18 | Jericho eye |`tools/jericho_eye_guard_trial.py`, `model_qa/ocular.py`; `tests/test_jericho_eye_guard.py`; `docs/jericho-eye-compatibility-experiment.md`, eye bundle|CONFIRMED changed records/pivots/probe regression; exact SVR motion semantics UNKNOWN|
| E19 | mesh merge |`tools/psp_mesh_merge.py`, `tools/psp_mesh_merge_trial.py`; `tests/test_psp_mesh_merge.py`; `docs/lance-compatible-mesh-merge.md`|CONFIRMED lossless semantic audit; crash/arena symptom cause UNKNOWN|
| E20 | accepted pad |`tools/jericho_elbow_guard_trial.py`, `tools/jericho_elbow_review.py`; `tests/test_jericho_elbow_guard.py`; `docs/jericho-elbow-pad-experiment.md`, elbow bundle and validation JSON|CONFIRMED exact source pad/seam replay, unchanged jaw/eyes, user accepted gameplay|
| E21 | QA0.2 boundaries |`model_qa/material_boundaries.py`; `tests/test_material_boundaries.py`; `docs/qa-material-boundaries.md`, `downloads/QA-material-boundaries-Jericho-regression.json`|CONFIRMED old-pad findings cleared, other six review findings retained; thresholds provisional|
| E22 | runtime uncertainty |symptoms and limits recorded in compact/conversion/material/mesh docs, user gameplay reports summarized here|CONFIRMED reported symptoms only; no game ISO, exact fault matrices or memory trace in portable fixtures; causes UNKNOWN|
| E23 | synthetic conformance |`tools/generate_conformance_fixtures.py`, `tests/fixtures/hctp_psp/*`, `tests/test_documented_conformance.py`|CONFIRMED independent known-answer byte contracts; no in-game certification|
| E24 | environment/tool bridge |requirements files, `tools/editor_bridge.py`, beta workflow/docs; checked editor digest|CONFIRMED observed tool/dependency contracts; undistributed editor functions not a standalone spec|
| E25 | inspection/import |`docs/noesis-review.md`, gameplay bundle READMEs, actual-PAC audit/hash reports|CONFIRMED preview provenance/recorded controls; Noesis output not shader/animation proof|

## Artifact provenance and exact identification

**CONFIRMED [E16/E20]:** Final accepted artifact identities are listed in
[pipeline/reproduction](pipeline-and-reproduction.md). To inspect Lance's
branch-local evidence without merging it, use `git show COMMIT:path` or a detached
worktree. The GitHub immutable directory is
[the pinned Lance tree](https://github.com/RyosSplitter/Wrestler-Importer/tree/27e2f1364dda8f76a940d80e188da07a0d619d86).
The current accepted Jericho asset is
[its PAC](../../downloads/Jericho-SVR2011-PSP-elbow-pad-TEST.pac) and
[complete evidence bundle](../../downloads/Jericho-SVR2011-PSP-elbow-pad-TEST-bundle.zip).

**CONFIRMED [E01/E10]:** A `.pac` filename is not an identity. Several supplied
0900 files and early RVD-named artifacts reflect different provenance labels.
Use manifest SHA-256, game/platform and model/texture observations together.
Do not infer a source character solely from an internal model name.

## Unknowns that an independent implementation must retain

**UNKNOWN [E04/E06/E22]:** Header reserved fields, native material/primitive bits,
rigid attachments, unused native channels, actual game controller semantics and
runtime allocation limits remain incompletely decoded. Native donor copying is
a compatibility strategy, not an explanation of these bytes.

**UNKNOWN [E05/E08/E22]:** Full HCTP VIF/GS/TEX0 coverage, generic TIM2/DDS,
source animation decoding, SYM/JBI/PS2-SVR differences and all PSP editions have
not been established. Reject unknown variants with a bounded diagnostic and
retain originals; never interpret "HCTP support" as complete game-family support.

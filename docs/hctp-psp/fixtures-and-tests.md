# Conformance vectors and regression tests

**CONFIRMED [E23]:** `tests/fixtures/hctp_psp` contains eight tiny binary files
plus `expected.json`. `tools/generate_conformance_fixtures.py` uses the standard
library, documented layouts and synthetic quad/color/weight data. It imports
no project decoder, native writer, compressor, game file or editor. These are
original test vectors, not extracted wrestler art. The opaque synthetic native
render state is zeroed for parser testing; do not inject the fixture into a game.

| Fixture | Known answer / purpose | Status |
|---|---|---|
| hctp-quad.yobj |4 native positions,4 UV records,2 triangles,2 bones; explicit VIF rows|CONFIRMED E23|
| psp-quad.yobj |same quad,1 mesh,44-byte stride,2 one-based palette entries,POF0 aliases|CONFIRMED E23|
| psp-quad.pac |BPE model,named T4 texture,opaque section50; absolute16/final2048|CONFIRMED E23|
| literal.bpe |literal-only valid skip dictionary; expands `ABAB!`|CONFIRMED E23|
| pair.bpe |independent full dictionary with entry250=`A+B`; expands `ABAB!`|CONFIRMED E23|
| weights-offset.vif |command0x6c020282; first vertex2,not mesh-dependent address|CONFIRMED E23|
| skin-t4.rtx3 |compact16-color palette,low-first nibbles,alpha0/64/128|CONFIRMED E23|
| skin-t4.gim |32×8 index ramp,block/palette layout,RGBA alpha0/127/255|CONFIRMED E23|
| expected.json |literal counts,positions,weights,triangles,all sizes/digests and POF0 width vector|CONFIRMED E23|

**CONFIRMED [E23]:** The eleven conformance tests assert known answers, source
UV-split weight provenance, original-index strip degeneracy, fixed VIF addressing,
PSP aliases/stride, all three relocation widths, compression decode, alpha/nibble
order and untouched unrelated PAC data. Mutations test invalid indices, palettes,
weight ranges, aliases, offsets and expanded lengths. This is deliberately more
than a production-writer roundtrip that could reproduce its own bug.

**CONFIRMED [E23/E24]:** Run from the repository root:

```sh
python -m pip install -r requirements.txt
python -m tools.generate_conformance_fixtures --check
python -m unittest tests.test_documented_conformance -v
```

**CONFIRMED [E23]:** The generator itself needs no third-party dependency;
the texture test needs NumPy/Pillow. `expected.json` gives independently
implementable answers without importing Python production code. For example,
weights are `[1,0],[.25,.75],[.5,.5],[0,1]`, triangles are
`[0,1,2],[1,3,2]`; POF0 field addresses `[12,268,65804]` encode
`41 80 40 c0 00 40 00`. A new reader should pass these before game assets.

## Broader verification and asset requirements

**CONFIRMED [E02–E23]:** The following suite combines portable conformance,
QA/unit tests and integration against **already tracked** published PAC/report
fixtures. It does not require a game ISO or the third-party editor executable:

```sh
python -m unittest tests.test_documented_conformance tests.test_material_boundaries tests.test_model_qa tests.test_model_qa_case_studies tests.test_hctp_weights tests.test_weight_trial_review tests.test_psp_mesh_merge tests.test_jericho_hybrid_trial tests.test_jericho_weight_guard tests.test_jericho_eye_guard tests.test_jericho_elbow_guard tests.test_pac_inspect tests.test_textures_and_repack tests.test_yukes_bpe
```

**CONFIRMED [E16]:** Lance-specific guard tests belong to its detached branch;
run `python -m unittest tests.test_lance_decimation_guard` there. Other
`unittest discover` suites include tests requiring user-provided originals or
local historical review data; a missing asset must be reported separately from
a codec assertion failure. See individual test setup/skip conditions. Never
report an unrun asset-dependent or PPSSPP test as passed.

**INFERRED [E15/E21/E23]:** For an independent implementation, add fuzz/bounds
checks, per-bone semantic-preservation tests, topology-changing reference-distance
tests, material peak/seam tests and selective ocular/jaw regressions. Use new
original/native pairs to broaden format coverage; do not train tolerances on
known defects. Keep input and accepted-output SHA-256 hashes in every experiment.

**CONFIRMED [E16/E20]:** The accepted game-derived bundles preserve their archived
QA, worker inputs/logs, before/after native audits, changed records and previews.
They are reference evidence rather than redistributable synthetic source fixtures.
No original full game PACs or third-party binaries are added by this documentation
work. Obtain originals/tools separately for full conversion reproduction.

**CONFIRMED [E16/E20/E23]:** A machine-readable accepted-output manifest is
[accepted-baselines.json](accepted-baselines.json). The read-only checker below
verifies both final PAC/YOBJ hashes, exact counts and native structure. It reads
Lance from the pinned Git commit when that separate branch's artifact is absent
from this worktree; fetch the named experiment branch if the Git object is missing.

```sh
python -m tools.verify_documented_baselines
```

**CONFIRMED [E23]:** Documentation verification ran 160 repository tests without
skips/failures in the audited environment, including the eleven new conformance
tests. The added mixed-width POF0 decoder assertion was subsequently verified by
rerunning those eleven tests. No new PPSSPP run was performed for documentation.

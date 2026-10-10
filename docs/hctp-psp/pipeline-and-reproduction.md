# Pipeline, pinned baselines and reproducibility

## Accepted targets versus historical app

**CONFIRMED [E01/E16/E20]:** These are the reference outputs chosen for future
work. Acceptance here includes the user's SVR2011/PPSSPP report, not a claim of
universal engine certification. Older accepted versions remain backups.

| Reference | Final PAC bytes | SHA-256 | Status |
|---|---:|---|---|
| Lance posterior guard |145408|`807d60134bb91071f01a28381dd0368214ecfb5c57b3713ae3829203f1568700`|CONFIRMED E16|
| Jericho jaw/eye/elbow guard |145408|`369ee95ed12c58c7c4d91f9ae26590bb2e4469a3abd31e8312d043bfe27533e8`|CONFIRMED E20|
| Lance expanded accepted YOBJ |208384|`b591b1b0386462d1beaac0188a617c1dfb90b04925c9c5d16bee53a179a3f849`|CONFIRMED E16|
| Jericho expanded accepted YOBJ |194784|`0a85f249b8336c07a4f22e01a6e7cafbba683565e8008d1469d5202d3305a77a`|CONFIRMED E20|

**CONFIRMED [E01]:** The independent Lance branch contains assets/tools absent
from the Jericho branch. Use immutable Git history, not an assumption that both
are in main:

- Lance: commit `27e2f1364dda8f76a940d80e188da07a0d619d86`, branch
  `experiment/lance-posterior-decimation`.
- Jericho accepted pad: commit `9c4212ee01ba322b1296119852d91e3da736bb15`,
  branch `experiment/jericho-elbow-pad`.
- Reusable QA0.2: commit `a565300993df0f6fae84a4179f7d7fa53e89b9cc`,
  branch `experiment/qa-material-boundaries`; this documentation descends from it.
- Unmerged main baseline: `28a6227f26865efaefe10255e5d6348e27228ef3` at this audit.

**CONFIRMED [E01]:** Create a separate worktree to reproduce Lance without merging:

```sh
git worktree add --detach ../Wrestler-Importer-Lance 27e2f1364dda8f76a940d80e188da07a0d619d86
```

**CONFIRMED [E01]:** Beta0.1.1 is a separate GUI around
`stable_pipeline/profile.json`: `opacity-fix-v1`, backend
`866f9bf65ae06a025160c0f7257944c1fd2111b1`, thirteen hashed modules,
retain ratio0.30, max4 influences, float weights,64-pixel/T4 textures,
Blender4.3.2 and147456-byte beta cap. Its app-side expanded RTX3 decoder and
size-fit stage handle cases the original pinned decoder did not. It does **not**
include the accepted hybrid/posterior/facial/pad refinements. A GUI run therefore
cannot currently be promised to reproduce the latest perfect-looking PACs.
The user's requested forward workflow is those successful steps plus QA;
integration into beta/main is a separate implementation decision.

## Inputs, tools and dependency boundaries

| Input/tool | Identity or contract | Status |
|---|---|---|
| HCTP Lance `1800.pac` |553728 bytes; `fe1073d97e9301c62226d611d174324d74cb5223669f3bbeed8a6660bcb80495`|CONFIRMED E16|
| HCTP Jericho `0600.pac` |`052da6cb97e1adcf865a89fd8d7d8544de8298025b36344f38de74ec600e9b1e`|CONFIRMED E17/E20|
| PSP Kurt base |`bf935a51fe30bfd2df929f8eb9e50be5d793426ea05125ca9411ce21b19ead80`|CONFIRMED E01|
| Supplied PSP mesh editor executable |`1e6fe5db14eae75ebfa853c0a1ec74b1895531db75b037fa63728cbf6ae6129f`|CONFIRMED E24|
| CPython3.13 |required for pinned editor bytecode extraction; tested runtime3.13.5|CONFIRMED E24|
| Blender4.3.2 |actual automated reducer version, not tutorial2.79|CONFIRMED E11/E24|
| NumPy/Pillow |core numerical/image dependencies; requirements.txt|CONFIRMED E24|
| SciPy/Trimesh/Rtree |optional separate QA dependencies; requirements-qa.txt|CONFIRMED E24|
| Noesis/YOBJ File Tool |external static inspection tools, not native rig/engine validators|CONFIRMED E25|

**CONFIRMED [E24]:** Install from the repository root, for example on Windows:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-qa.txt
.venv\Scripts\python -m unittest tests.test_documented_conformance
```

**CONFIRMED [E24]:** Initial exports use `tools.editor_bridge`: it accepts only
the checked executable hash, extracts selected functions from the PyInstaller
archive using CPython3.13 marshal code and invokes them without executing the
GUI/top-level program. The executable is user-supplied and not distributed by
this documentation. This dependency explains current reproduction constraints;
it is not a from-scratch specification. A new implementation can instead use
the native PSP writer contract in [binary formats](binary-formats.md) with known
PSP opaque templates. Do not claim the editor's undistributed code is required
knowledge for understanding the format.

## Intermediate representation

**CONFIRMED [E05/E09/E10]:** Current model dictionaries/JSON use these semantic
fields; they are an implementation IR, not a literal disk layout:

```json
{
  "bones": [{"index": 0, "name": "root", "parent": -1,
             "local_position": [0,0,0], "rotation": [0,0,0]}],
  "bone_count": 1,
  "textures": ["skin"],
  "uv_v_flipped": false,
  "weight_encoding": "float",
  "meshes": [{"index": 0, "bone_palette": [0],
    "vertices": [{"position": [0,0,0], "normal": [0,0,1],
                  "uv": [0,0], "color": [255,255,255,255],
                  "weights": [1], "source_vertex_index": 0}],
    "materials": [{"texture_id": 0, "triangles": [], "strips": []}]}]
}
```

**CONFIRMED [E05/E06/E09]:** `weights` corresponds to the mesh-local ordered
`bone_palette`; some processing stages expand that palette to every target bone
for dense computation. Source index exists only while correspondence is known.
The audit representation additionally stores raw header/material/palette/vertex/
strip/bone/name bytes and uses `texture_names` rather than `textures`. Preserve
those opaque bytes alongside semantic fields. Persist coordinate convention,
source/base/profile hashes, transforms, per-mesh provenance and counts at each
stage. Sparse palettes must be expanded correctly before protected copying.

## Forward conversion sequence

**CONFIRMED [E02–E21]:** The successful components form this sequence, with
experiment-specific replay needed to reproduce the accepted artifacts:

```text
original HCTP PAC + PSP base (hash and preserve)
 → bounded PAC extraction / optional BPE
 → HCTP positions, corners, weights + RTX3 → RGBA
 → uniform rest-landmark alignment to preserved PSP rig
 → name/ancestor source weights + selective donor/controller compatibility
 → save pre-reduction geometry/weights
 → region decimation with source-surface and accessory preservation
 → recompute appropriate smooth normals, keep UV/color/material corners
 → target part/palette packing (≤8), native weighted buffers and local strips
 → native material templates + verified GIM textures
 → strict YOBJ audit and stage-traced static/posed/material/ocular QA
 → unchanged BPE and PAC replacement on copy of known PSP base
 → decode actual final PAC, rerun identity/structural/size checks
 → Noesis OBJ/MTL/PNGs from that exact PAC + matched QA comparison renders
 → user PPSSPP validation; promote only the tested hash, preserve old baseline
```

**INFERRED [E16/E18/E20/E21]:** Future general implementation should enforce the
successful protection/compatibility policies before producing a candidate,
rather than routinely reproducing failed intermediate geometry and patching it.
The current replay tools deliberately isolate causal changes on accepted
geometry; they are reference experiments, not a new universal end-to-end command.

## Replaying accepted experiments

### Lance

**CONFIRMED [E16]:** In the pinned Lance worktree, extract
`downloads/Lance-QA-decimation-experiment.zip`. Its `evidence/input-to-reduction.json`
and `evidence/profile.json` preserve the aligned source-derived weight stage
and guard profile. Run to new directories:

```sh
blender --background --python-exit-code 1 --python tools/blender_hybrid_reduce.py -- evidence/input-to-reduction.json NEW/guarded.json evidence/profile.json
python -m tools.lance_decimation_guard_trial --baseline downloads/1800-PSP-hybrid-source-pelvis-restored.pac --guarded NEW/guarded.json --output NEW/trial
python -m model_qa compare --source ORIGINAL/1800.pac --converted NEW/trial/candidate.yobj --output NEW/qa --profile model_qa/profiles/hctp-provisional-v1.json --samples 24000 --resolution 320
```

**CONFIRMED [E16]:** The accepted archived model is `trial-02/candidate.yobj`,
not rejected trial01. Final native counts:57 meshes,2385 vertex records,
2420 triangles,4318 indices,79 bones,19 textures,96 material records.
The gameplay bundle contains the accepted PAC, exact extracted preview and old
baseline. Its projected/actual size agreement is not a new simplification step.
Use the current QA0.2 worktree to run additional material-boundary QA on the
extracted final PAC without altering it.

### Jericho

**CONFIRMED [E17–E20]:** Legacy hybrid construction is still available:

```sh
python -m tools.jericho_hybrid_trial --source ORIGINAL/0600.pac --base ORIGINAL/Kurt-Angle-Ring.PAC --editor ORIGINAL/yobj_mesh_editor_PSP_GUI.exe --blender /path/to/blender --output NEW/hybrid
python -m tools.jericho_weight_guard_trial --source ORIGINAL/0600.pac --base ORIGINAL/Kurt-Angle-Ring.PAC --baseline downloads/0600-PSP-hybrid-Jericho.pac --output NEW/jaw
```

**CONFIRMED [E18/E20]:** Extract `Jericho-QA-facial-weights-experiment.zip` into `EVIDENCE/facial`
and the final elbow-pad bundle into `EVIDENCE/pad`. Their exact archived stages
support controlled replay (every `NEW/` output must be new):

```sh
python -m tools.jericho_eye_guard_trial --previous downloads/0600-PSP-hybrid-Jericho.pac --jaw NEW/jaw/candidate.yobj --source-stage EVIDENCE/facial/trial/input-source-weighted.json --donor-stage EVIDENCE/facial/trial/input-psp-donor.json --output NEW/eyes
blender --background --python-exit-code 1 --python tools/blender_hybrid_reduce.py -- EVIDENCE/pad/trial/source-aligned-weighted.json NEW/pad-guard.json model_qa/profiles/jericho-elbow-decimation-experiment.json
python -m tools.jericho_elbow_guard_trial --baseline downloads/Jericho-SVR2011-PSP-eye-compatibility-TEST.pac --source-stage EVIDENCE/pad/trial/source-aligned-weighted.json --guarded-stage NEW/pad-guard.json --output NEW/pad
```

**CONFIRMED [E18/E20]:** The facial-weight bundle contains `trial/input-source-weighted.json`,
`trial/input-psp-donor.json` and `trial/corrected-weight-transfer.json`.
The eye bundle retains `trial/original-HCTP-source-weighted.json` and its
changed-record report, while the pad bundle contains
`trial/source-aligned-weighted.json`, `trial/guarded-reduction.json` and
`trial/guard-profile.json`. Check bundle manifests/hashes before replay.
For exact already-produced results, extract `preview/candidate.yobj` from the
final accepted gameplay bundle and compare the hash above. The final pad candidate
has54 meshes,2389 records,2417 triangles,4087 indices,79 bones,20 textures and94
material records. None of these asset-specific scripts is a universal game profile.

## Unchanged packaging and final-PAC identity

**CONFIRMED [E02/E03/E16/E20]:** To package a reviewed YOBJ, retain the corresponding
accepted baseline's other stored sections and use the existing functions:

```python
from pathlib import Path
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.pac_repack import replace_sections
from tools.yukes_bpe import compress, decompress
from tools.pac_inspect import inspect_pac

base = Path("BASELINE.pac").read_bytes()
yobj = Path("REVIEWED.yobj").read_bytes()
audit_yobj(yobj)
stored = compress(yobj)
assert decompress(stored) == yobj
final = replace_sections(base, {2: stored})
assert len(final) <= 148000 and len(final) % 2048 == 0
before = {s['id']: base[s['offset']:s['offset']+s['size']]
          for s in inspect_pac(base)['sections']}
after = {s['id']: final[s['offset']:s['offset']+s['size']]
         for s in inspect_pac(final)['sections']}
assert before.keys() == after.keys()
assert all(after[i] == before[i] for i in before if i != 2)
assert all(s['offset'] % 16 == 0 for s in inspect_pac(final)['sections'])
actual = next(raw for s, raw in sections(final) if s['id'] == 2)
assert actual == yobj
audit_yobj(actual)
# Only write to a new path after QA/semantic gates; preserve existing PACs.
with Path("NEW-EXPERIMENT.pac").open("xb") as f:
    f.write(final)
```

**CONFIRMED [E02]:** `replace_sections` takes the original PAC bytes plus a
replacement mapping; no custom packaging implementation is needed. The old
`repack` helper expects raw section2/id9 and ordinary-depth materials and is not
the accepted BPE/cutout packaging path. Do not accidentally decompress unrelated
sections and change their storage form.

## Size and import constraints

**CONFIRMED [E01/E16/E20]:** Current strict experiment policy is≤148000 **bytes**,
with final2048 alignment;145408 meets it. Historical caps included148KiB=151552,
144KiB=147456 and a user-reported original148.5KiB slot. These are distinct.
Native Kurt180224 and Slaughter104448 demonstrate variable stored sizes.
**UNKNOWN:** No universal PSP wrestler-size, mesh-count or expanded-RAM ceiling
has been established. Record stored PAC, stored section and expanded YOBJ/texture
sizes separately.

**CONFIRMED [E25]:** For SVR2011 tests, back up ISO/CH.PAC/ARC/slot, inject the
PAC into the intended ring entry, resolve archive alignment/space using the
working PAC Editor workflow, update ARC against the resulting archive, save
ISO and verify no neighboring entry overlap. `EMD\00010001.pac` was the user's
test slot, not every wrestler's destination. Restart PPSSPP, start a fresh match,
repeat entrance/match/victory and inspect arena geometry. Log exact PAC hash,
game build, motion and repeat count. Original unconverted donor injection is a
useful archive workflow control when diagnosing crashes.
**UNKNOWN:** This repository does not implement or certify every PAC Editor
version's ISO/ARC behavior; a valid inner PAC cannot repair a bad outer archive.

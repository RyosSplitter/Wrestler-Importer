# 0401: guarded fit exceeded the archive budget

Status: **isolated experiment awaiting PPSSPP validation**, not merged into main.
The existing accepted Lance/Jericho files and frozen `stable_pipeline` are unchanged.
The report concerns the uploaded file with SHA-256
`38723589baa316ba57d10b9361d248045fcdb6748edfb590cb6c8b6a9bfda471`
and the original user-selected Kurt PSP base with SHA-256
`bf935a51fe30bfd2df929f8eb9e50be5d793426ea05125ca9411ce21b19ead80`.
Hashes identify evidence, never select conversion behavior.

## Diagnosis

**CONFIRMED:** This was a successful source decode followed by a genuine size-fit
rejection. The source contains 20 meshes, 3,191 vertex records, 4,812 triangles,
78 bones and 19 referenced textures. Source archive length is 658,432 bytes.
Its internal model label is `Y2J`; texture names include `rvd_*`. Neither label
is treated as reliable wrestler identity.

**CONFIRMED:** The existing fitter tried its original regional profile, then free
arm/leg retention 50% and 35%, each with ordinary texture caps 64 and 32. It held
2,342 source faces and retained the complete-head 80% floor: 1,142 of 1,426 head
faces, including 528 protected faces. The smallest existing attempt was 184,320
bytes, 36,320 beyond the configured 148,000-byte cap. Its compressed model alone
was 155,149 bytes. Texture reduction alone could not make that attempt fit.

**CONFIRMED:** Lossless strip joining, dictionary-symbol sweeps and smaller BPE
blocks did not make the original attributes fit. Joining reduced raw YOBJ size
but did not reduce the best final aligned PAC length. No such layout changes
were retained in the delivered experiment.

## Bounded precision experiment

**CONFIRMED:** The float32 native vertex format and the existing PAC construction
code remain unchanged. After exhausting the guarded size fits, the experiment
rounds non-ocular vertex attributes onto explicitly bounded grids. It removes
no additional triangles and does not change weights or textures. This is **lossy
attribute precision**, not lossless compression and not a claim of bit-identical
protected body positions.

| Attribute | Quantization used for this file | Actual maximum change | Enforcement |
|---|---:|---:|---:|
| Position, non-ocular | Step 0.00048828125 in target units; binary grid <= height/32768 | 0.002036817% of model height | <= 0.003% of height |
| UV, non-ocular | Step 1/16384 | 1/32768 UV units; <= 0.00390625 texel at width/height 128 | <= 1/32768 |
| Shading normal, non-ocular | Component step 1/256, stored as float32 | 0.170473063 degrees; length change <= 0.002666752 | <= 0.25 degrees; length change <= 0.007 |
| Eye/eyelid-selected records | None | Zero: all 166 serialized records retained exactly | Exact native record comparison and ocular replay |
| Weights, colors, bone palettes | None | Zero | Exact decoded comparison |
| Converted GIMs, texture table payload | None | Zero | Exact decompressed payload comparison |

All values in the table are **CONFIRMED** for this file by independent native
decoding and measurement. Ocular selection uses original source controller
support before donor-eye replacement; it uses native coordinates, avoiding the
QA axis-conversion mistake that appeared in an early disposable measurement
script. That early unheld candidate was not delivered. The maintained selection
has a coordinate-system regression test.

**CONFIRMED:** Rounding is consistent across coincident vertex records. The
implementation rejects new nonzero-face collapse or reversal, excessive position,
UV or normal error, altered weights, changed draw/material records and excessive
analytical-pose displacement. It does not weld vertices or change connectivity.
The shader-normal grid is deliberately not renormalized into new high-entropy
floats; the bounded length error is recorded. Native layout, alignment, offsets,
pointer ranges, relocations and bone indices are checked by the existing auditor.

| Measurement | Existing smallest attempt | Precision experiment | Classification |
|---|---:|---:|---|
| Native meshes | 47 | 47 | CONFIRMED |
| Native vertices | 3,316 | 3,316 | CONFIRMED |
| Native triangles | 3,508 | 3,508 | CONFIRMED |
| Textures | 19 | 19 | CONFIRMED |
| Expanded YOBJ bytes | 257,536 | 257,536 | CONFIRMED |
| Stored BPE model bytes | 155,149 | 118,352 | CONFIRMED |
| Stored BPE texture bytes | 21,910 | 21,928 | CONFIRMED |
| Retained base section 8 bytes | 7,072 | 7,072 | CONFIRMED |
| Complete aligned PAC bytes | 184,320 | 147,456 | CONFIRMED |
| BPE maximum distinct symbols | 220 | 200 | CONFIRMED |
| BPE expanded block cap | 4,000 | 4,000 | CONFIRMED |

**CONFIRMED:** The texture stored-size difference results from dictionary setting
200 versus 220; the decoded texture table and all GIMs are unchanged. Base
section 8 is unchanged byte for byte. PAC sections remain at 16-byte boundaries;
total PAC length remains a multiple of 2048. Thus the effective maximum under
148,000 bytes is 147,456 bytes. Expanded runtime model storage is **not reduced**
by the compressed-size saving.

Experimental PAC: `0401-PSP-precision-experimental.pac`, SHA-256
`8a42bdead5369be91231aaef63127954652121ed970bf741318d891b24ebecd1`.
The standalone file and checksum are under `downloads/`; the separate
`0401-PSP-precision-experiment.zip` contains the PAC, OBJ/PNG/YOBJ preview,
both QA runs, structural checks and a detailed import README.

## Validation and limitations

**CONFIRMED:** Full before/after source comparison used 24,000 samples per
direction, 320-pixel identical-camera geometry renders, all 14 established
analytical poses and unchanged tolerances. Overall bidirectional surface p95
error changed from 0.6499584% to 0.6505098% of reference height. Posterior/pelvis
surface error after rounding remains approximately 0.001% of height.
No new QA flag identities were introduced. Existing review findings remain:
arm/thigh/shin/wrist material edges, rest jaw and recession/depth findings in
neck/torso/shoulders/hands/feet, plus shoulder/elbow pose findings. Before had
19 review flags; after has 18. A coordinate-derived component flag disappeared;
this is not claimed as an anatomical repair.

**CONFIRMED:** Additional textured before/after panels in
`downloads/0401-precision-comparisons/` use identical cameras, lighting and
converted GIMs. Foreground mean absolute RGB differences were 0.0367–0.0451
on a 0–255 scale across the five views; fewer than 0.068% of foreground pixels
differed by over eight levels. These are measurements, not an acceptance limit.
This CPU shader normalizes interpolated normals and cannot prove equivalence
with real PSP lighting. The images are not Noesis screenshots.

**CONFIRMED:** Separate verified native-topology correspondence tests compared
every vertex in rest plus all 14 analytical poses and all 16 ocular probes.
Weights, ordered topology, rendering records and held ocular motion remain
exact. This index correspondence is valid because this experiment explicitly
preserves and independently verifies all native vertex/draw indices; it does
not assume correspondence with the original PS2 topology.

**INFERRED:** The bounded differences are unlikely to be visible in ordinary
gameplay. Offline preview and analytical LBS tests support a trial, not proof
of real PSP shading or controller behavior.

**UNKNOWN:** Real SVR 2011 animation appearance, load stability and memory safety
for this specific candidate remain untested. General suitability for other
sources is also unproven. A size fit must not be presented as completion of all
visual QA, or as a fix for unrelated memory corruption.

## Reproduce and diagnose

Use the developer runtime requirements in `requirements-desktop.txt`, Blender
4.3.2, the source PAC and the locally owned compatible PSP base:

```python
from pathlib import Path
from desktop.core import Request, run_job
run_job(Request('0401.pac', 'Kurt-Angle-Ring.PAC'), Path('0401-trial'),
        lambda percent, message: print(percent, message, flush=True))
```

The experiment lives in `desktop/precision.py`; `desktop/core.py` invokes it
only when all existing fits fail. `ps2psp_converter.py` traces the separate
attribute-precision stage in QA. `desktop/budget.py` persists `size-fit.json`
incrementally, including failed jobs. Inspect `precision.json`,
`precision-validation.json`, `ocular-qa.json`, `qa/report.html` and `result.json`.
None of these steps writes to the source or base file.

Synthetic conformance fixtures exercise bounds, collapse rejection, exact ocular
coordinate selection, immutable weights/render state and failed-budget reporting:

```text
python -m unittest tests.test_portable_budget tests.test_portable_precision -v
python -m unittest discover -s tests
```

For gameplay, inject the experimental PAC into a copy of your SVR 2011 PSP slot
using the already-tested PAC Editor/ARC-update workflow. Test entrance completion,
standing, walking, crouching, grapples, facial motion and victory sequences in
PPSSPP. Keep the prior accepted replacement for immediate rollback. Compare the
preview YOBJ with the decompressed section 2 of the injected PAC before blaming
rendering discrepancies on archive size.

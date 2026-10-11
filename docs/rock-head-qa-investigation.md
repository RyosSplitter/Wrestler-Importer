# Rock scalp corruption: open investigation

Follow-up: the exact failing upload has now been supplied and compared. See
[the isolated scalp-layout control](rock-scalp-layout-control.md). The initial
input-identity uncertainty below is preserved as investigation history.

The user reported crown-like scalp spikes and gaps around the forehead/temples
in SVR 2011 PSP with **both** texture options. This is a gameplay failure. The
experimental changes here improve the separate QA stage; they do not claim to
fix that failure. No converter, texture allocator, rig, packaging code or
accepted PAC was changed. Main and the shipped Windows application remain
unchanged. Work is on `experiment/rock-head-qa`.

## Evidence and confidence

| Classification | Finding |
| --- | --- |
| CONFIRMED — user gameplay report | Both current and adaptive app outputs show the scalp problem. The screenshots show spikes and gaps; the actual exported PAC has not yet been supplied for this investigation. |
| CONFIRMED — implementation/binary inspection | Adaptive allocation leaves every decoded YOBJ payload unchanged. The stored main YOBJ in the repository's current/adaptive Rock A/B pair is identical. |
| CONFIRMED — QA implementation | Previous clay renders rasterized both windings and used absolute normal illumination. Reversing all triangles on a synthetic skull produced identical old render pixels. |
| CONFIRMED — QA implementation | The old front face ROI excluded the rear scalp. Synthetic eye tests verified donor replay on selected ocular records; they did not certify the full posed head or simulate game rendering. |
| CONFIRMED — reproduction measurements | The stored Rock A/B candidate has a smooth scalp under culled and unculled head comparisons. Maximum cranial vertex-to-reference-surface error is 0.079269% of complete reference height. Worst culled reference coverage loss is 0.227151% at 160 pixels. Neither reproduces the large gameplay spikes. |
| CONFIRMED — stage comparison metric | Two nearby head triangles have opposed reference normals after decimation, absent in the prepared stage. Their centers are approximately (-0.306, 8.762, 1.533) and (0.300, 8.762, 1.534) in canonical coordinates, on the face rather than the crown. Nearest-surface normal opposition alone is not proof that a triangle needs flipping. |
| CONFIRMED — native subset audit | 84 supported uppercase `.PAC` inputs contain 2,050 skinned meshes with palettes of 3–8 slots, and three rigid 1-slot meshes with flag `0x11ff`. The subset deliberately excludes unsupported files and differently cased extensions; it is not the complete 110-PAC texture census. |
| CONFIRMED — binary inspection | The reproduced Rock's mesh 0 uses one float weight, `atama`, flag `0x17ff`, stride 40, and 131 vertices; all upper-scalp records above canonical y=9 have weight 1 on `atama`. Native structural auditing accepts this layout. |
| INFERRED | A shared geometry/weight/native-runtime stage is a stronger suspect than adaptive texture selection, given the paired gameplay failures and unchanged YOBJ payloads. |
| INFERRED | A single-slot **skinned** layout deserves compatibility review because it departs from the checked native convention. It is not a proven SVR minimum or the established cause of this defect. |
| UNKNOWN | Whether the exact user-produced PAC matches the reproduction, whether the spikes are present in its decoded geometry, and which actual SVR controller/draw/loader behavior causes the corruption. |

Do not replace the skull with a donor skull, move scalp vertices, impose a
three-bone minimum, or flip the two faces on the strength of these findings.
Those changes would conceal or confound an unresolved cause.

## Reproduction inputs

These are the developer reproduction, **not a verified hash of the user's
failing app output**:

- Original source `0000.pac`:
  `d1d5ca744b5a793743851c142bf273554c81076ae3b8231834364559e048a973`.
- Current-method Rock PAC:
  `ae56c7e0f18f230a865790a5f7bb18796003c354c65fa1f1be744e1c4581a16e`.
- Adaptive Rock PAC:
  `a36d20b854f7e51843345179c8eabf8c9bcebd8d55926fd67d97387bcd8d9eab`.

The source's internal name is `hogan`; the original container metadata was not
renamed. Source positions are compared after one proper uniform bone-landmark
alignment. There is no independent fit or nonuniform scale of the candidate.

## QA changes

`model_qa/head.py` is a read-only, reusable diagnostic. The ordinary QA pipeline
now invokes its checks as well, without changing conversion output:

- Full-head region in addition to the existing facial regions.
- Cranial ancestry selection at bind time, so posed vertices escaping the
  original bounding box remain tested.
- Maximum vertex-to-triangle-surface distance alongside existing area-weighted
  percentile metrics. No source vertex-index correspondence is assumed.
- Reference-normal opposition diagnostics and matching front/rear/side/
  three-quarter clay renders with no culling and with each winding convention.
- Entire cranial support checked under existing ocular probes, every available
  eyebrow controller about each axis, and head/neck/jaw probes. Source-derived
  weights and candidate weights use the same PSP rig. PSP-only controls are
  sensitivity probes, not equivalent HCTP animation semantics.
- Review warning for 1/2-slot skinned palettes. This is an observed-convention
  warning, **not structural rejection or a hard technical limit**.

Maximum-distance threshold (0.4% of full height) and culled reference-coverage
loss threshold (2%) are **provisional**, not calibrated gameplay acceptance
criteria. Both cull conventions are reported because the complete SVR material
culling semantics remain unknown. Clay renders do not simulate texture alpha,
the runtime loader, GPU vertex interpretation, or actual game animation clips.
Opposed-nearby faces can be legitimate folds/inner shells; the flags require
review. Repeated pose flags can concern the same faces, not independent defects.

## Tests and artifacts

Seven new synthetic tests cover unchanged skulls, a spike outside reference bounds,
inverted faces hidden by two-sided renders, a controller-weight defect appearing
only when posed, the advisory native-layout warning, invalid inputs, and stage
attribution that distinguishes unrelated findings in the same region. All
242 repository tests passed. Game-derived fixtures are not required by these
new tests.

The standalone head report and native audit metadata are in
`downloads/rock-head-qa/`. Comparison PNGs are **CPU clay renders**, not Noesis
or PPSSPP captures. The full comparison report and test evidence are included
in the downloadable study bundle when generated.

The full Rock rerun used 24,000 samples in each surface direction, all 14 existing
body/jaw poses and 37 whole-head/controller probes. Structure/pointers/alignment/
indices/palettes/normalized weights passed and the PAC stayed 147,456 bytes.
There are 43 review flags, many repeats of the same opposed-face finding across
poses. None of those probes reproduces the screenshot's crown spikes. Inputs
remained unchanged. Stage attribution was recomputed from the saved measurements
after tightening finding-kind matching; geometric measurements and renders were
not changed.

Reproduce using user-owned inputs and fresh output folders:

```sh
python -m model_qa.head --source 0000.pac --candidate Rock-output.pac \
  --stage prepared=prepared.json --stage reduced=reduced.json \
  --output new-head-report --resolution 160
python -m model_qa compare --source 0000.pac --converted Rock-output.pac \
  --stage selective-weight-transfer=prepared.json \
  --stage guarded-decimation=reduced.json \
  --samples 24000 --resolution 160 --output new-full-report
python -m tools.qa_native_palette_inventory native-root new-native-palettes.json
python -m unittest discover -s tests
```

The native inventory's root layout is `native-root/<folder>/<filename>.PAC`.
Source PACs and generated converter intermediates are supplied separately; they
are not embedded in these synthetic tests.

## Required next evidence

Get the exact app-generated PAC used in the screenshots, its original source,
and preferably the job's `qa/report.json`, `size-fit.json`, and preview YOBJ.
Hash and independently decode that PAC before attributing the failure to a
particular stage. If the decoded scalp is smooth, capture a failing PPSSPP
frame's head draw, vertex type/stride, bone matrices and index buffer, and compare
the live transformed scalp with the stored records. That distinguishes loader/
GPU interpretation from actual clip-driven skinning. Preserve the successful
textures and use an isolated, one-variable compatibility experiment once the
evidence identifies the suspect. Offline QA review does not replace this
gameplay test.

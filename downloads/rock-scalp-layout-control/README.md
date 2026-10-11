# Exact Rock upload: isolated scalp layout control

This is a **runtime compatibility experiment**, not a confirmed cure or a
production converter rule. Work is on `experiment/rock-single-slot-skinning`.
No branch was merged into main and no accepted PAC or texture pipeline changed.

## What the exact upload establishes

**CONFIRMED — binary comparison:** the user's `the rock 2.pac` is 147,456 bytes,
SHA-256 `2228eabd964bf0584a8c89909b997baeba3c84929ab46fdd28d074b1879b1406`.
Its three YOBJ sections (2, 26, 27), skeleton, section 8, and effective head
weights are byte-identical to the developer reproduction in the initial
[head investigation](rock-head-qa-investigation.md). Section 9 differs in
texture data. The exact upload resolves the earlier input-identity uncertainty.

**CONFIRMED — decoded geometry and viewer checks:** its stored scalp is smooth.
The source comparison, offline probes and Noesis rest preview do not reproduce
the gameplay crown/spikes. A rest OBJ cannot test native skinning or the game
loader. The user reports the issue with both texture modes.

**INFERRED:** the visible discrepancy therefore arises during game rendering,
animation or runtime interpretation rather than being large spikes already
present in the stored rest geometry. The precise operation remains **UNKNOWN**.

## Hypothesis and one-variable test

**CONFIRMED — audit:** only mesh 0 has a one-slot skinned palette. It includes
the upper scalp, 131 vertices, and effective weight 1 on `atama`. The checked
native sample subset uses 3–8 slots for skinned meshes; its one-slot examples
are rigid and have a different vertex format.

**INFERRED:** SVR may handle a one-slot skinned vertex buffer differently from
the generic PSP GE interpretation used by our reader. This supports an isolated
test, not a claim that three slots are a hard loader minimum. The general QA
warning remains advisory until gameplay supplies compatibility evidence.

The candidate pads **only mesh 0** with two zero-weight slots:

| Field | Uploaded PAC | Control PAC |
| --- | --- | --- |
| Zero-based palette | `[4]` (`atama`) | `[4,3,2]` (`atama,kubi,mune`) |
| Stored one-based palette | `[5]` | `[5,4,3]` |
| Vertex weight values | `[1.0]` | `[1.0,0.0,0.0]` |
| GE vertex flag | `0x17ff` | `0x97ff` |
| Vertex stride | 40 bytes | 48 bytes |
| Mesh 0 vertices | 131 | 131 |
| Main meshes / vertices / triangles | 43 / 2,331 / 2,725 | 43 / 2,331 / 2,725 |
| All-model meshes / vertices / triangles | 45 / 2,473 / 2,853 | 45 / 2,473 / 2,853 |
| Textures | 19 | 19 |
| Decoded main YOBJ | 187,888 bytes | 188,944 bytes |
| Stored main section | 113,049 bytes | 113,135 bytes |
| Complete aligned PAC | 147,456 bytes | 147,456 bytes |

**CONFIRMED — independent serialization/semantic verification:** ordered
positions, normals, UVs, colors, all nonzero per-bone weight bits, oriented
triangles, draw records, materials, skeleton, culling bounds and model metadata
remain identical. Every unselected mesh's vertex bytes/palette/stride/flag
remain exact. Sections 8, 9, 26 and 27 remain identical in **both stored and
decoded bytes**, including the user's exact GIM textures and elbow-pad models.
Only weight-layout metadata, added zeros, required layout offsets/relocations,
size fields, alignment and compressed main-section bytes change. The existing
writer, compressor and PAC packaging functions are reused without edits.

Decoded model storage increases 1,056 bytes. The file cap passes, but no hard
game-heap envelope or actual runtime interpretation has been established for
this candidate (**UNKNOWN** pending PPSSPP testing).

## Validation

**CONFIRMED — executed checks:** native pointer/offset/alignment/relocation,
allocation, index ranges, palette bounds, normalized finite weights, material/
texture-depth consistency and 148,000-byte PAC cap passed.

All 14 analytical body/jaw poses and 37 cranial/controller probes have a maximum
before/after vertex component difference of **exactly zero**. A fresh full QA
run used 24,000 surface samples per direction and 160-pixel paired renders. Its
complete rest metrics, body-pose metrics and head-probe metrics equal the prior
reproduction report exactly. Applicability to the uploaded baseline is proven
by the identical three YOBJ payloads; clay metrics do not depend on its changed
texture pixels. There are 42 remaining review flags, many repeats of the
existing opposed-face finding across poses. Only the one-slot convention warning
is eliminated. This is not a visual-fix claim. All 246 repository tests passed,
including four new synthetic native round-trip/padding tests.

The bundle contains fresh QA, an exact-change report, applicability proof and
test evidence. Full game-derived geometric NPZ intermediates are omitted from
publication. Input PACs remain read-only and are identified by hashes.

The OBJ was opened in the supplied Noesis64 with orientation, culling and
shading toggles applied once. Actual Noesis front/three-quarter screenshots are
included separately from the CPU front/rear/side preview images and QA clay
renders. OBJ has no bones and Noesis may split groups by material: its reported
89 preview meshes are not the native model's 45 meshes and are not a loader
limit. The preview includes both elbow-pad models.

## Reproduce

```sh
python -m experiments.skin_palette_padding --input "the rock 2.pac" \
  --output fresh-slot-control --mesh 0 --slots 3
python -m model_qa compare --source 0000.pac \
  --converted fresh-slot-control/Rock-scalp-three-slot-CONTROL.pac \
  --stage "uploaded-before=the rock 2.pac" --samples 24000 --resolution 160 \
  --output fresh-slot-control-qa
python -m unittest discover -s tests
```

The helper refuses existing output folders, unsupported/rigid layouts, invalid
slot counts, unrelated data changes and oversized PACs. It does not reduce
geometry or textures to fit. It is not called by the production converter.

## Download and gameplay decision

Candidate: `Rock-scalp-three-slot-CONTROL.pac`

SHA-256:
`b23c97770203e517eb26f64c61aad88cf9661e157957bf49979e705264107fbf`

Use the same SVR 2011 costume slot and proven injection/ARC-update workflow as
the failing PAC, on a separate ISO copy. Launch a fresh match so it loads the
new PAC rather than an already-loaded model. Compare the same entrance, standing
views, match animations and victory sequence that exposed the spikes. Keep the
uploaded PAC as the A/B baseline. For Noesis, load `preview/Rock-scalp-control.obj`
beside `preview.mtl` and the PNGs, then apply the usual viewer toggles once.

If this control fixes the scalp, investigate the loader's one-slot path and
choose/calibrate a general format rule with more samples. If it does not,
preserve both controls and capture the failing frame's PSP GE vertex type,
stride, vertex/index buffers and live head matrix for comparison. A gameplay
outcome alone would support the layout hypothesis but would not fully decode
the loader's internals. No automatic main-branch promotion is authorized here.

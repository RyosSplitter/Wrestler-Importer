# PSP blood-layer experiment

This experiment is separate from the v0.25.6 converter. Run it over a frozen
converted PSP PAC; it never invokes conversion, decimation, texture optimization
or a new weight transfer. Accepted PACs and the production app remain unchanged.

## Native evidence

**CONFIRMED:** Native Kurt, Slaughter, Rock and Jericho ring PACs contain separate
draw records referencing `blood` and `blood_b`. Their ordinary body materials
are separate. In these references, section 8 contains `blood1`, `blood2` and
`blood_b1`. Retaining that table alone does not create a surface that can draw it.
See `downloads/psp-blood-overlay/native-reference-analysis.json`.

| Reference | Blood triangles | Blood draw records | Observed material control |
|---|---:|---:|---|
| Kurt 2007 base | 145 | 8 | 0x115, T4 |
| Slaughter PSP ring | 129 | 6 across 5 meshes | 0x117, T8 |
| Rock 2011 | 132 | 7 across 6 meshes | 0x115, T4 |
| Jericho native PSP | 92 | 6 across 5 meshes | 0x117, T8 |

**CONFIRMED:** These words also occur on alpha/cutout materials. They are not a
unique blood-enable bit. This experiment identifies blood by the observed native
texture references and copies complete records. **UNKNOWN:** The individual bit
semantics and the game-side stage/texture lookup mechanism.

Relevant existing structures, all little-endian:

| Structure / offset | Size | Role |
|---|---:|---|
| Main PAC section 2 | variable | YOBJ body plus overlay draw buffers |
| Main PAC section 9 | variable | Named body and `blood`/`blood_b` GIM images |
| PAC section 8 | variable | Additional native blood images; retained exactly |
| YOBJ header +24 | 4 | Mesh count; rewritten by existing writer |
| YOBJ header +32 | 4 | Texture-name count |
| Material +22 | 2 | Texture index into YOBJ names |
| Material +24 | 4 | Observed complete render/control word |
| Material +132 | 4 | Strip count |
| Material +136 / +140 | 4 each | Strip array / first-index aliases |
| PSP float-weight vertex | 36 + 4*N | N weights, UV, RGBA, normal, position |

**CONFIRMED:** The existing writer reconstructs buffers and pointer aliases,
POF0 relocation data, descriptor counts and palette-dependent strides. Vertex
and index buffers use 16-byte alignment relative to YOBJ byte 8; PAC sections
align to file byte 16 and the final PAC is padded to 2048 bytes. All are audited
again from the final PAC. See the main format documentation for full structures.

## Fitting and skinning

**CONFIRMED implementation:** The first supported profile requires the converted
body and donor to have byte-identical bind rigs, audited float32 skinning, no
existing blood references, one main model and the Kurt T4 blood contract. Other
rigs, T8 donor profiles and accessory-model dependency arrays are refused rather
than guessed. Only this isolated CLI uses this restriction; the app is unchanged.

The trial projects each ordinary converted skin triangle's center onto the
donor's ordinary body surface, then checks proximity to the native blood patch.
It rejects cutout draws, degenerate faces, opposing normals and distant body
projections. The coverage threshold comes from the measured maximum native
patch/body gap, with a numeric epsilon. A provisional 4%-height body-projection
gate and 0.5 normal-dot gate limit unrelated surfaces. **INFERRED:** These gates
give suitable coverage on the examined models; they are not proven general
anatomical classifiers. Hair, teeth, unusual clothes and other donors need review.

**CONFIRMED:** Selected converted triangles are copied into appended blood
buffers. Every added vertex has verified `(body mesh, body vertex)` provenance.
Its palette and weight values come from that exact converted record; no donor
facial weights, nearest posed weighting, pruning, averaging or welding occur.
Normals are copied from that record. UVs are sampled barycentrically from the
native blood patch at the corresponding donor-surface point. The native white
vertex color, T4 blood GIM bytes/alpha and full non-pointer material state are
preserved. Texture references are appended; existing texture indices stay fixed.

**CONFIRMED measured offsets:** Native Kurt face and chest blood surfaces have
median signed normal separations of -0.0254916 and -0.0198534 model units from
ordinary skin. The added layers use these values along the converted skin
normal. The body is not displaced. **INFERRED:** This avoids coincident rendering
ambiguity while resembling native separation. Negative sign is relative to the
stored PSP normal convention; it must not be assumed to mean inward in another
coordinate convention. `--coincident` supplies an analytical/control variant with
zero separation. **UNKNOWN:** Actual game depth-test/bias interpretation.

## Results and budgets

**CONFIRMED:** The generated Benoit candidate is 135168 bytes, SHA-256
`6f34fdc205d8ad6dc57611ec0291ebcc88c838b468699403947d754c73a83672`.
No existing body texture is resized, re-quantized or changed.

| Metric | Frozen Benoit | Experimental Benoit |
|---|---:|---:|
| PAC bytes | 120832 | 135168 |
| Main meshes | 38 | 50 |
| Vertices | 2040 | 2354 |
| Triangles | 2380 | 2721 |
| Main texture references | 15 | 17 |
| Decoded YOBJ bytes | 168368 | 195328 |
| Modeled padded pixel/CLUT bytes, including retained effects | 34176 | 38400 |

**CONFIRMED:** Existing body positions, UVs, vertex/color/weight bytes, palettes,
flags, ordinary material state and oriented strips remain exact. Body movement
has zero difference in 14 analytical poses and 37 cranial probes. Added layer
motion stays within the measured native normal separation plus float roundoff
in the same probes. Blood-stage image pixels are copied exactly. All stored and
decoded sections outside 2/9 remain exact; only their file offsets may move.

**CONFIRMED:** The analogous RVD trial is 165888 bytes, exceeding the unchanged
148000-byte cap by 17888. Export is withheld. Its existing body/textures are not
reduced to pay for overlays. Its report is retained separately; no oversized
injectable PAC is distributed. Existing 200/220-symbol BPE settings and PAC writer
are reused without packaging changes.

**UNKNOWN:** Actual peak memory allocation and blood-stage activation. The extra
26960 decoded model bytes and 4224 modeled texture bytes have runtime costs even
though this Benoit PAC fits. A 38400-byte texture allocation is an experiment,
not an increase to the app's established Default allowance or a proven heap limit.
Native observations, CPU renders and strict binary validation do not certify
in-game safety. The preview forces the initial blood map visible; it does not
emulate event gating or stage changes. Live Noesis/PPSSPP execution was unavailable
in this environment. OBJ/MTL/PNG and native YOBJ/GIM exports are supplied for Noesis.

## Reproduction and regression tests

```sh
python -m tools.psp_blood_overlay_trial --input OWN_CONVERTED.pac \
  --donor OWN_KURT_BASE.pac --output new-output-directory
python -m unittest tests.test_blood_overlay_trial -v
python -m unittest discover -s tests
```

The eight generated-fixture tests check immutable inputs/body attributes,
native material records, zero-offset attachment, incompatible rigs/missing
effects, changed-but-normalized weights, layer separation, invalid indices,
and oversized export withholding. They contain no original game-derived assets.

Test the released candidate with blood enabled in SVR 2011 PSP. From clean
archives, compare the supplied before-control and experimental PAC in the same
wrestler slot using the usual PAC injection, archive update/rebuild and ISO-save
process. Observe before bleeding, first blood, later blood stages, chest streaks,
jaw/neck movement, entrance, victory and multi-wrestler matches. Look for permanent
pre-injury blood, missing activation, flicker, floating patches and crashes. Keep
the before-control and accepted PAC available for restoration. Production
integration awaits that gameplay evidence and a general size-allocation policy.

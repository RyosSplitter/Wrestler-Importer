# Wii packet position-scale failure and v0.27.1 hotfix

## Failure, evidence and confidence

**CONFIRMED:** In the uploaded `Undertaker - ch103.pac` (507,904 bytes),
costume 00, Standard, Kurt Angle PSP base, the v0.27 reader produces the reported
two large shapes near the shoulders. The `trans` image is a tribal decoration;
104 auxiliary vertex records / 154 triangles have source pelvis/thigh/calf
influences. They are not anatomical hair. Those influences are legitimate.

**CONFIRMED:** The ring main packet stores byte `07` at YOBJ+0x74; its auxiliary
packet stores `08`. The entrance auxiliary also stores `08`. The reader formerly
ignored this field and divided every signed position component by 128. Reading
the auxiliary with divisor 256 puts its surface on the thighs; some vertices
coincide exactly with the original body, and median nearest-body-vertex distance
drops from 21.3954 to 0.1680 source units before rig adaptation. No fitting,
translation, manually chosen displacement, weight averaging or re-rigging is
used to get this result.

**INFERRED, strongly supported:** This byte specifies position fractional bits,
with divisor `2**fraction_bits`. Q7 and Q8 are the only enabled contracts.
Source-runtime execution and the full range of possible encodings remain
**UNKNOWN**. Other values are rejected, never silently interpreted as Q7.

**CONFIRMED:** Of 30 packets in the prior nine-file / 15-costume source census,
29 use Q7 and one uses Q8 (Edge alternate, auxiliary packet 0). Existing Edge
ring uses Q7. The 15 reference costumes pass the new source/IR encoding audit.
The Q7 position calculation is unchanged; the Q8 alternate now receives its
declared scale and still requires its own appearance/runtime review.

## Binary contract supplement

Offsets below are relative to the inner big-endian Wii `YOBJ`, after DUMY+24.
For packet `i`, `h = 0x40 + 64*i`:

| Offset | Size | Meaning / confidence |
|---|---:|---|
| h+0x08 | 2, BE | Position/normal allocation count, CONFIRMED |
| h+0x0c / h+0x0d | 1 each | Observed tags 2/7, full semantics UNKNOWN; h+0x0d is not this scale field |
| h+0x14 | 4, BE | Position/normal buffer pointer, origin +8, CONFIRMED |
| h+0x34 | 1 | Observed 7/8, CONFIRMED; position fractional-bit interpretation INFERRED |
| h+0x35..0x37 | 3 | Opaque metadata, UNKNOWN; preserved |

Position records are still six signed big-endian 16-bit components. Only XYZ
use the per-packet divisor. Normal axes/divisor, UV /1024, source indices, blend
coefficients and palettes do not change. Both headers of the observed two-packet
layout read their own h+0x34 field; the private header views keep the source bytes
untouched. The old documentation's `/128` examples apply to Q7 samples only.

## Why existing QA missed it

**CONFIRMED:** The comparison reference came from the same wrong decoder as
the candidate. Comparing two consistently misdecoded surfaces cannot establish
that the source was interpreted correctly. Also, `trans` was labelled `Hair`
solely from texture-slot naming, which misidentified leg decorations.

`model_qa/wii_source_encoding.py` now independently reads original fixed-point
buffers and the per-packet binary-point field, then checks every exported source
IR position before rig adaptation. Its test recreates the old doubled-Q8 result
and requires a scale-mismatch error. Inspection and app jobs use
`verified_source_bundle`; evidence appears in `wii/source-materials.json` and is
linked from the QA report. Unknown fields/counts/encodings fail clearly.
This audits compliance with the observed contract; it is not source emulation.

Transparent Wii draws are now labelled `Cutout`. They keep the established full
retention policy (the historical reducer profile key is still `Hair`) and their
original anatomical weights. Facial-color masks exclude both Hair and Cutout.
No transparency is deleted, baked opaque or assigned to the head by this fix.

## Controlled Undertaker experiment

**CONFIRMED:** Same source, base, costume 00, Standard settings, source images and
byte-exact final texture table. Before/after comparisons use the *same corrected
source reference*, 6,000 surface samples, 128-pixel comparison renders, all body
poses and head-controller probes. User-facing previews decode the actual PACs.

| Metric | Reproduced v0.27 | Q8 corrected |
|---|---:|---:|
| Native buffers | 63 | 59 |
| Vertex records | 2,924 | 2,903 |
| Triangles | 3,050 | 3,050 |
| PAC bytes | 147,456 | 147,456 |
| Overall p95 distance / reference height | 0.1521203504 | 0.0018262779 |
| Full comparison review flags | 289 | 255 |

The remaining flags are retained; this is not an all-regions quality pass.
Sampled regional scores can fluctuate because surface-area allocation changes.
Independent oriented-triangle comparisons prove that face/eyes, torso, arms,
hands and boots retain exact positions, UVs, normals, colors and effective
weights. Only the cutout page and adjacent leg page have changed triangle
attributes: all 154 cutout faces change position, and 40 existing leg faces
change tessellation/position after corrected source contacts activate the normal
boundary guards; 131 leg faces have changed complete attribute tuples including
normal updates. No total face reduction is added. Better location changes the
existing spatial PSP packing buckets, rather than targeting a mesh count.

Six influence radii (root, koshi, both thighs and calves) are recalculated by the
existing conservative enclosure step. Bone names, parents, axes and local bind
transforms remain byte-exact; it would be inaccurate to call the entire bone
table byte-exact. Native pointers, ranges, alignment, palette indices, weights,
ocular/digit/hand probes and enclosure checks pass. The 152,064-byte ring cap
and independent donor texture allocation envelope remain enforced. Source and
accepted PACs are never overwritten; PAC packaging code is unchanged.

**UNKNOWN until tested:** PPSSPP gameplay/entrance/victory safety and every
animation. Analytical pose tests are not recorded game motion.

## Reproduction and regression coverage

Use the v0.27 job workflow with source format `wwe13-wii`, source entry `00`,
`costume_role='ring'`, `wii_geometry='Standard'`. The separate controlled PAC
pins the prior GIMs so texture allocation cannot obscure the geometry fix.
Fresh app runs may reallocate texture detail using the corrected surface areas;
their reports and previews describe the actual new candidate.

Tests cover exact Q7/Q8 decoding, mixed packet fractions, unchanged normals/UVs/
weights, unsupported fractions, independent source/IR mismatch rejection and
preserved leg weights on cutouts. The Windows procedural fixture now contains
a Q7 body and Q8 leg auxiliary. Frozen end-to-end smoke requires both divisors
in inspection evidence, then performs Blender reduction, packing, full QA,
preview, entrance Save As and cancellation. No supplied game assets ship in
the Windows app. HCTP/JBI paths and the separate UV-layout experiment are unchanged.

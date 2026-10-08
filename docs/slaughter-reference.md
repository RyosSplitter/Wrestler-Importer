# Sgt. Slaughter: HCTP PS2 versus native PSP

Slaughter's supplied PSP port combines selective geometry reduction, revised
mesh/rig organization, smaller indexed textures and **BPE-compressed PAC
sections**. Its arms retain 49.1% of the source material's triangles. The current
1800 beta retained only 14.7% of its arm material. Together with the earlier
[stage isolation](arm-diagnosis.md), this supports protecting the arms and using
compression to recover file space before reducing them further.

This is a read-only comparison of four original files. No PAC was modified or
rebuilt, no replacement 1800 was made, and the beta backend remains unchanged.
HCTP and SVR 2008 are different game versions; some differences can be art or
animation updates rather than requirements of the PSP platform. The files show
the resulting port, not which production tools or reduction algorithm made it.

[Download the reference review bundle](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/Slaughter-PS2-PSP-reference-review.zip)
for extracted YOBJs, static OBJ/MTL/PNG previews, original PSP GIMs, four actual
Noesis screenshots, and detailed inspection/comparison JSON.

## Counts and container sizes

The user identified `5800` as HCTP ring, `5804` as HCTP entrance, and the named
PSP PACs as their SVR PSP counterparts.

| Original PAC | Bytes | KiB | Native vertex records | Decoded preview vertices | Triangles | Meshes | Bones |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HCTP `5800.pac` | 460,288 | 449.5 | 2,020 | 2,203 | 2,996 | 13 | 68 |
| HCTP `5804.pac` | 462,592 | 451.75 | 2,170 | 2,440 | 3,298 | 14 | 66 |
| PSP `Sgt-Slaughter-Ring-.PAC` | 104,448 | 102 | 1,455 | 1,455 | 1,730 | 22 | 83 |
| PSP `Sgt-Slaughter(Hat).PAC`, body YOBJ only | 110,592 | 108 | 1,378 | 1,378 | 1,600 | 17 | 83 |
| PSP hat/glasses YOBJ, section 32 | Included above | Included above | 213 | 213 | 272 | 1 | 83 |

PS2 preview vertices include duplication for UV seams; its native position-record
count is a different measurement. Neither column counts just unique positions.
Triangles are reconstructed from native strips with alternating winding,
excluding triples with repeated indices. PSP mesh counts are YOBJ header counts;
Noesis may split an OBJ further by material and report a higher count.

The ring YOBJ includes **five blood-overlay meshes: 101 vertices and 129
triangles**. Excluding these leaves **17 ordinary body meshes, 1,354 vertices and
1,601 triangles**, or 53.4% of the HCTP ring triangle count. The hat preview
combines its 1,600-triangle body with the separate 272-triangle accessory:
**1,591 vertices and 1,872 triangles**. Repeated 83-bone tables do not mean the
character has 166 bones.

## Compression explains much of the size

All seven sections in the two PSP PACs use a `BPE ` wrapper. The HCTP sections in
this pair are uncompressed. The bounded read-only decoder checks wrapper sizes,
dictionary cycles, block bounds and the exact expanded length. Expanded YOBJ and
texture tables then pass their structural readers.

| PSP PAC | Section | Content | Stored bytes, including BPE wrapper | Expanded payload bytes |
| --- | ---: | --- | ---: | ---: |
| Ring | 2 | Body and blood YOBJ | 66,513 | 129,504 |
| Ring | 8 | Three additional blood textures | 4,008 | 7,072 |
| Ring | 9 | Thirteen named textures | 32,812 | 48,064 |
| Hat | 2 | Body YOBJ | 62,396 | 121,728 |
| Hat | 9 | Eleven body textures | 30,181 | 43,360 |
| Hat | 32 | Hat/glasses YOBJ | 10,877 | 17,352 |
| Hat | 39 | Four accessory textures | 5,981 | 10,192 |

The ring's expanded section payloads total **184,640 bytes (180.3125 KiB)**,
while the original stored PAC is **102 KiB**. The hat's expanded payloads total
192,632 bytes; the stored PAC is 108 KiB. Expanded sums exclude PAC tables and
padding and are not hypothetical rebuilt PAC sizes.

Therefore the user's approximately 148 KiB *stored-file* budget should not be
applied directly to uncompressed model and texture payloads. These files do not
establish an engine-wide limit or memory budget. No BPE writer or newly
compressed conversion has been implemented or tested in PPSSPP here.

The PS2 container also has different ancillary data: ring section 8 is a
standalone RTX3 image, while sections 100/101 are small texture tables in both
HCTP variants. These sections are absent from the PSP pair. Sections must be
interpreted in their game/context rather than copied solely by numeric ID.

## Geometry reduction is selective

These are counts by texture material, not bone-defined body regions or measured
outputs of a known decimation modifier. They are useful starting references,
but are not exact reduction settings to apply to every wrestler.

| Comparable surface | HCTP triangles | PSP ring triangles | Retained |
| --- | ---: | ---: | ---: |
| Face, `sgt_kao` | 882 | 527 | 59.8% |
| Shoulder, `sgt_kata` | 264 | 157 | 59.5% |
| Arm, `sgt_ude` | 228 | 112 | **49.1%** |
| Chest, `sgt_mune` | 142 | 37 | 26.1% |
| Abdomen, `sgt_dou` | 206 | 98 | 47.6% |
| Hands, two `hk_hand*` materials versus `jm_hand` | 532 | 266 | 50.0% |
| Eyes, `sgt_eye` | 48 | 32 | 66.7% |
| Teeth, `sgt_ha` | 20 | 20 | 100% |
| Mouth, `sgt_kuti` | 24 | 31 | 129.2% |
| Entrance hat, `sgt_hat` | 194 | 164 | 84.5% |
| Entrance glasses, three `sgt_gla*` materials | 108 | 108 | 100% |

The hand texture changes name and layout. Pants, belt and thighs also change
material allocation; comparing `sgt_pant` alone would misleadingly report a
triangle increase. The mouth gains triangles. Uniform across-the-board removal
does not describe this port.

The native PSP ring uses 460 strip records and 2,716 indices, with strips up to
86 indices long. HCTP ring uses 569 strips and 4,134 indices, up to 16 long.
Strip packing is another space consideration, although total counts also
reflect different topology. The original PSP uses floating-point weights;
fitting this file did not require quantizing its weights to U16.

## Rig, weights and normals

The ring skeleton changes from **68 to 83 bones**. It shares 66 names, but
**64 shared names change bone index**. HCTP-only `l_mayu`/`r_mayu` are replaced
by a larger set of facial bones; two shared mouth bones have different parents.
Most shared local transforms differ as well. Bone indices and bind transforms
cannot be copied from PS2 and assumed to mean the same thing on PSP.

In the ring's 1,455 stored PSP vertices, 570 have one active weight and 885 have
two. All weights pass the normalization/range checks. Mesh palettes reserve
five to eight slots, but no decoded vertex uses more than two active influences.
The hat body follows the same one/two-influence convention. This is evidence
for a conservative PSP weighting target, not proof that every game requires it.

The separate accessory uses rigid GE flag `0x11ff`, a 36-byte vertex layout with
no per-vertex weight array. Its runtime attachment semantics are not decoded.
It is shown at its stored coordinates without moving it onto the body.

The HCTP reader decodes bone tables and source group/palette associations but
**does not decode exact PS2 per-vertex skinning**. Consequently this analysis
cannot establish whether the original source weight values were preserved,
remapped or repainted. PSP ring and entrance bone tables also differ byte for
byte despite both containing 83 bones.

Subsequently, the separate [Benoit weight study](benoit-weight-trials.md) added
an analysis-only HCTP VIF weight reader and verified structural decoding on both
Slaughter source YOBJs. The results above remain the original read-only
comparison; source-to-PSP weight correspondence is not established here.

Stored normals in all five YOBJs have lengths approximately 1.0. Every decoded
vertex has alpha 255. These observations do not identify the original normal
recalculation algorithm; smooth shading still depends on topology and seams.

## Textures use different budgets

All 19 main HCTP RTX3 textures are PSMT8/256-colour images. The PSP port keeps
its face at 256 colours and uses 16-colour GIMs for most other textures.

| Texture | HCTP dimensions / palette capacity | PSP dimensions / palette capacity |
| --- | --- | --- |
| Face, `sgt_kao` | 128 × 128 / 256 | **64 × 128 / 256** |
| Chest, `sgt_mune` | 64 × 128 / 256 | **64 × 128 / 16** |
| Shoulder, `sgt_kata` | 128 × 256 / 256 | 64 × 128 / 16 |
| Arm, `sgt_ude` | 128 × 128 / 256 | 64 × 64 / 16 |
| Pants, `sgt_pant` | 128 × 64 / 256 | **128 × 128 / 16** |
| Hands | Two 64 × 64 / 256 images | `jm_hand`, 64 × 32 / 16 |
| Hat | 128 × 64 / 256 | 128 × 64 / 16 |
| Mouth | 8 × 8 / 256 | 8 × 8 / 16, padded GIM rows |

Preserving dimensions for the chest and increasing the pants image area show
that a blanket 64-pixel limit is not the native port's strategy. UV/material
layout changes must accompany texture replacements. Palette capacities here
are format sizes, not necessarily the number of distinct used colours.

Blood textures retain alpha values from 0 to 255; ordinary stored PSP body and
accessory images are opaque. Preserve alpha per texture/material when converting
hair, masks or effects; making every image opaque would destroy valid overlays.

Both PSP body YOBJs reference `sgt_ris`, but no named `sgt_ris` texture is present
in the supplied PSP sections. Its preview material is plain, with no fabricated
replacement. It might be supplied elsewhere by the game; that is unverified.
Texture-name matching for `sgt_EYE`/`sgt_eye` is case insensitive in the previews.

## Preview and validation details

- [HCTP ring Noesis screenshot](../downloads/slaughter-hctp-ring-noesis.png)
- [PSP ring Noesis screenshot](../downloads/slaughter-psp-ring-noesis.png)
- [HCTP entrance Noesis screenshot](../downloads/slaughter-hctp-entrance-noesis.png)
- [PSP hat Noesis screenshot](../downloads/slaughter-psp-hat-noesis.png)

Each capture uses Noesis64 4.466 with fresh default settings, then one click each
on orientation, face cull and shading, in that order. The viewer automatically
fits the model. These are actual viewer captures, not rendered illustrations.
The OBJs are exported by the read-only inspector with native strip winding,
rather than YOBJ File Tool's previously observed inconsistent strip winding.
Stored coordinates and UVs are retained; coordinate axes are converted for OBJ
display. No alignment, reshape, simplification or texture enhancement is applied.

PSP ring blood-overlay meshes are excluded from the ordinary-body screenshot.
PSP hat includes its accessory. OBJ previews omit weights, vertex colours,
stored normals and native PSP shader state; Noesis generates preview normals.
They establish static appearance, not animation or in-game shading correctness.

All four input hashes remain unchanged. All seven PSP sections were redecoded
and compared exactly with their saved expanded payloads. Triangle indices,
finite geometry, PSP weights and 69 main-table texture images were checked.
The PSP mouth's small padded layout and CP932 Japanese internal model name
required analysis-only reader handling; these are not new beta capabilities.

The next conversion change should combine tested BPE writing with geometry
budgets that protect arms, shoulders, joints and facial details, followed by
surface/silhouette checks. Keep destination PSP rig records and material
conventions explicit, and budget texture dimensions/colour depth separately.
Then compare each new export against these references and test it in PPSSPP.

# Texture decoding, GIM and rendering

## RTX3 host image / PS2 TEX0

| RTX3 offset | Bytes | Field | Status |
|---:|---:|---|---|
| 0 | 4 | `RTX3` | CONFIRMED E08 |
| 4 | 4 | u32 total file length−8 | CONFIRMED E08 |
| 8 | 8 | u64 GS TEX0 register | CONFIRMED E08 |
| 16–35 | 20 | opaque | UNKNOWN E08 |
| 36 | 4 | u32 pixel payload byte count | CONFIRMED E08 |
| 40 | 4 | u32 pixel pointer, relative to byte 8 | CONFIRMED E08 |
| 44–63 | 20 | opaque | UNKNOWN E08 |
| pointer+8 | variable | host image pixels; palette follows indexed pixels | CONFIRMED E08 |

**CONFIRMED [E08]:** Minimum header is 64 bytes. TEX0 fields used by the decoder
are PSM bits 20..25, TW 26..29, TH 30..33, CPSM 51..54, CSM 55 and CSA 56..60.
Width=`1<<TW`, height=`1<<TH`; the expanded reader rejects dimensions over 4096.
Validate complete payload length before allocating or decoding.

| PSM / CPSM | Implemented interpretation | Evidence scope / status |
|---|---|---|
| PSM 19 / PSMT8 | byte palette indices | CONFIRMED real samples + synthetic E08 |
| PSM 20 / PSMT4 | low nibble then high nibble | CONFIRMED original 1800 + synthetic E08 |
| PSM 0 / PSMCT32 | linear RGBA8 | CONFIRMED synthetic implementation E08 |
| PSM 1 / PSMCT24 | RGB in 3-byte or padded 4-byte words | CONFIRMED synthetic implementation E08 |
| PSM 2,10 / PSMCT16,16S | little-endian RGB5A1 words | CONFIRMED synthetic implementation E08 |
| CPSM 0 | 32-bit RGBA palette | CONFIRMED samples + synthetic E08 |
| CPSM 2,10 | RGB5A1 palette | CONFIRMED synthetic implementation E08 |
| other PSM/CPSM | reject with diagnostics | UNKNOWN format coverage E08 |

**CONFIRMED [E08]:** A 256-entry CSM1 palette (CSM=0) reorders logical entry i
from stored index `(i & ~24) | ((i & 8)<<1) | ((i & 16)>>1)`. Compact 16-entry
palettes remain in their compact order. For a full 256-entry PSMT4 palette,
select CSA*16 through CSA*16+15 after reordering; a T8 nonzero CSA is unsupported.
The implementation accepts CSM2 without this swap for the tested synthetic host
layout. **UNKNOWN:** This is not proof of every real CSM2 upload layout.

**CONFIRMED [E08]:** PS2 32-bit alpha expands as `min(a*255//128,255)`.
RGB5A1 channels expand using `(c<<3)|(c>>2)`; bit15 selects alpha 0/255.
24-bit RGB is opaque. The observed RTX3 host pixels are linear; applying an
additional GS VRAM swizzle to these arrays corrupts them. Other storage layouts
remain unsupported rather than silently guessed.

**CONFIRMED [E08]:** The initial tools/stable reader supports only T8/32-bit
CSM1 and is still intentionally frozen. `app.ps2_textures.read_rtx3` is the
expanded decoder. `read_source` selects model-referenced names, prefers section
9 for duplicates and emits name/section/PSM/CPSM/CSM/CSA/dimension diagnostics
before Blender. Original 1800 has eight T4 images among nineteen; that explains
why the older beta reader failed on it.
**UNKNOWN:** General TIM2/.tm2 and DDS decoding, originally discussed as possible
inputs, is not implemented by the RTX3 reader and must not be advertised as such.

## Written GIM subset

**CONFIRMED [E08]:** The writer emits the 16-byte `MIG.00.1PSP` signature,
root block at 16 (type2), picture block at32 (type3), image block at48 (type4),
image data at128, and a palette block afterward (type5). This describes the
written subset, not every GIM used by native games.

| Block-header offset | Bytes | Meaning | Status |
|---:|---:|---|---|
| 0 | 2 | u16 type | CONFIRMED E08 |
| 2 | 2 | u16 header value16 | CONFIRMED E08 |
| 4 | 4 | u32 block size | CONFIRMED E08 |
| 8 | 4 | written next-link: size for image/palette, 16 for root/picture | CONFIRMED written contract / INFERRED link meaning E08 |
| 12 | 4 | written value16 | CONFIRMED written contract / UNKNOWN complete semantics E08 |

**CONFIRMED [E08]:** Image and palette blocks each contain a 16-byte block
header plus a 64-byte information allocation. Known written information fields
are below; offsets are relative to that information allocation.

| Info offset | Bytes | Written meaning/value | Status |
|---:|---:|---|---|
| 0 | 4 | header value48 | CONFIRMED contract E08 |
| 4 | 2 | format4=T4,5=T8,3=RGBA8888 palette | CONFIRMED E08 |
| 6 | 2 | order1 swizzled image,0 linear palette | CONFIRMED E08 |
| 8,10 | 2 each | width,height | CONFIRMED E08 |
| 12 | 2 | bits per pixel4/8/32 | CONFIRMED E08 |
| 14 | 2 | pitch alignment16 | CONFIRMED written contract E08 |
| 16 | 2 | vertical alignment8 image,1 palette | CONFIRMED written contract E08 |
| 18 | 2 | value2, remaining semantics unresolved | UNKNOWN E08 |
| 24 | 4 | index-array offset48 | CONFIRMED written contract E08 |
| 28 | 4 | data offset64 | CONFIRMED written contract E08 |
| 32 | 4 | end offset64+payload size | CONFIRMED written contract E08 |
| 40,42 | 2 each | level type1 image/2 palette, level count1 | CONFIRMED written contract E08 |
| 44,46 | 2 each | frame type3,count1 | CONFIRMED written contract E08 |
| 48 | 4 | frame offset64 | CONFIRMED written contract E08 |
| other bytes | variable | writer zeros; broader meaning unresolved | UNKNOWN E08 |

**CONFIRMED [E08]:** For byte row width B, swizzle address is
`((y//8)*(B//16)+x//16)*128+(y%8)*16+x%16`.
T8 uses B=width, requires width multiple16 and height multiple8.
T4 first packs adjacent pixels `even | (odd<<4)` and then uses B=width/2,
requiring width multiple32 and height multiple8. Unsizzling uses the inverse
lookup, not the PS2 CLUT permutation. Palette colors are linear RGBA8:
256 entries for T8,16 for T4; do not expand PS2 alpha a second time.

**CONFIRMED [E08]:** Written T8 length=`1232+width*height`; T4
length=`272+width*height/2`. These include palette/block overhead, so halving
pixel data does not halve complete file size. Halving both dimensions quarters
pixels; to roughly halve them, lower one axis, respecting block alignment.
Native Slaughter includes a differently padded 8×8 mouth texture; these writer
restrictions are not universal native texture limits.

## Budgeting and alpha

**CONFIRMED [E08/E11]:** Budgeted opaque textures use RGBA Lanczos reduction,
FastOctree quantization to16/256 colors, no dithering and endpoint alpha snapping
(≥252→255,≤3→0). Common trial caps are64/T4 with128/T8 face detail. These choices
are lossy; preserve original decoded RGBA, dimensions and hashes separately.
The half-texture stage lowers resolution and retains the existing skeleton,
geometry and weight pipeline. A budget pass must report actual GIM byte totals.

**CONFIRMED [E18/E20]:** Latest Jericho cutout textures retain original T8 indices
and the decoded RGBA palette without resizing, quantization or alpha snapping.
Accepted corrective PACs preserve stored sections8/9 byte-for-byte. This keeps
hair/mask transparency independent of the opaque-body vertex-alpha rule.
**INFERRED:** For new cutouts, either preserve the exact supported indexed source
or explicitly verify alpha coverage against a high-quality source reference;
do not apply an indiscriminate opaque-image policy to all materials.

## Material state and separate alpha sources

| Observed PSP use | Control word | Status |
|---|---|---|
| ordinary T4 body material | 0x5 | CONFIRMED observed Kurt profile E08/E12 |
| ordinary T8 body material | 0x7 | CONFIRMED observed Kurt profile E08/E12 |
| blood/overlay T4 or T8 | 0x115 / 0x117 | CONFIRMED observed profile E12 |
| source-cutout T8 trial material | 0x117 | CONFIRMED accepted Jericho E18/E20 |
| bit-level interpretation of 0x110 | alpha/overlay-related behavior | INFERRED E12/E18 |
| complete GE/material state semantics | not decoded | UNKNOWN E06/E12 |

**CONFIRMED [E12]:** Copying the first base material indiscriminately selected
blood-overlay state for ordinary face/body draws. Select appropriate ordinary
base rendering templates and match color depth; preserve other opaque state.
Do not assume changing one word fully converts all native material types.

**CONFIRMED [E13]:** HCTP corner alpha can be zero/partial despite opaque image
pixels. The working opacity fix sets ordinary-body **vertex** alpha to255,
preserving RGB and independently retaining texture/palette alpha. User gameplay
confirmed disappearance was fixed. Neither vertex-alpha255 nor opaque Noesis
appearance proves the underlying texture cutout is correct; inspect both.

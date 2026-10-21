# WWE 13 Wii `ch145.pac`: source feasibility study

**CONFIRMED:** This is a read-only, separate study. Existing converters, PSP
packaging, accepted assets and app behavior are unchanged. Source files and
decoded game textures/models remain private owner artifacts, not repository
fixtures. The numerical inventory is [here](wwe13-wii-ch145/inventory.json).

## What the supplied sample establishes

**CONFIRMED:** Input is 585,728 bytes, SHA-256
`feeea42460893cf577b3aa2ffadb239462538be18e822e33d051e096445df542`.
It has an `EPK8` signature. Two aligned PACH containers at `0x4000` and `0x48000`
each have nine independently bounded BPE-compressed sections. All 18 top-level
sections decompress through the existing byte-pair codec with declared lengths
verified. These are not the Xbox sample's EPAC/ZLIB wrappers.

**INFERRED:** This is Shawn Michaels, based on the decoded face, attire and
Heartbreak Kid logos. The two variants appear ring and entrance respectively.
**UNKNOWN:** Exact runtime costume-role selection. WWE 13/Wii provenance is
provided by the user; the filename alone does not authenticate game/platform.

**CONFIRMED:** Each variant has a recognized `body` model (section 2) and `trans`
model (section 10000). The body has 88 bones, and trans has 110, including 22
additional `kami_*` bones. All bone names are unique within each table, parents
are in range, hierarchies are acyclic and transforms finite. The 88 common
body/trans bones have identical name-matched world bind matrices in each variant.
**INFERRED:** The trans payload represents alpha hair/accessories, supported by
its texture slots, decoded hair image and additional bone names. **UNKNOWN:** Its
vertex influences, draw order, material behavior and source spring animation.

## Measured comparison

| Observed property | Supplied Wii `ch145` | Previous Xbox 360 `ch104` |
|---|---:|---:|
| Complete uploaded archive bytes | 585,728 | 9,289,728 |
| First main-model expanded section bytes | 120,656 | 734,612 |
| First main-model bones | 88 | 109 |
| Main color atlas | 512×512 | 2048×1024 |
| Main triangles | UNKNOWN | 13,514 provisional strip triangles |
| Geometry reader ready | No | Sample-specific reader exists |

**CONFIRMED:** These are different wrestler/attire samples. Their file-size and
bone-count differences are not a controlled same-character platform comparison.
Expanded byte counts also reflect different vertex/storage formats and must not
be translated into polygon-count estimates.

**INFERRED:** Wii is a promising size-budget starting point: its main atlas has
one eighth as many texels, its model section is compact, it has separate alpha
maps, and many Biped/facial bone names overlap our existing mapping research.
Lower source resolution can require less reduction but also sets a lower detail
ceiling. **UNKNOWN:** Whether it ultimately needs less geometry decimation, how
large its float-weight PSP serialization becomes, and actual PSP animation and
runtime-memory compatibility. The ready Xbox reader remains easier to use today;
Wii needs a different geometry/skinning reader before conversion can be evaluated.

## Archive layout

**CONFIRMED:** PACH uses the following little-endian records in this sample:

| Relative offset | Bytes | Meaning |
|---|---:|---|
| `+0` | 4 | ASCII `PACH` |
| `+4` | 4 | Section count, u32 |
| `+8+12*i` | 4 | Section ID |
| `+12+12*i` | 4 | Offset relative to payload origin |
| `+16+12*i` | 4 | Stored section bytes |
| `+8+12*count` | variable | Payload origin |

**CONFIRMED:** Each identified section starts on a four-byte boundary. Stored
sizes can be odd; do not copy the Xbox inspector's size-multiple-of-four rule.
Nonoverlap and exact BPE length/output checks are required. The first section set
is `2,9,40,60,61,80,100,110,10000`. Section 100 contains a nested PACH, which is
preserved as data; this study does not claim to inventory every nested resource.
**UNKNOWN:** General EPK8 directory field semantics. Roots are discovered at
sector-aligned signatures and validated independently, not parsed by a universal
EPK8 directory implementation. The preliminary directory contains EMD labels
`00014502` and `00014504`; units/role meanings are not generalized.

## Wii model header

**CONFIRMED:** Recognized model sections begin with a 24-byte DUMY prefix:
`DUMY`, bytes `00 00 00 10`, then 16 zero bytes. The YOBJ starts at section `+24`.
Numbers below are big-endian, relative to that YOBJ, with observed table pointers
addressed as stored value plus eight. This is a different header from PSP/HCTP
YOBJ and Xbox JBOY; swapping endian settings on the old reader is insufficient.

| YOBJ offset | Bytes | Observed meaning / status |
|---|---:|---|
| `+0` | 4 | `YOBJ` |
| `+4` | 4 | Declared body end minus eight |
| `+8` | 4 | Version `0x00070001` |
| `+12` | 4 | Header size `0x40` |
| `+16` | 4 | Bone count |
| `+20` | 4 | Bone-table relative pointer |
| `+24` | 4 | INFERRED material-entry count |
| `+28` | 4 | INFERRED material-entry table pointer |
| `+32` | 4 | Texture-name slot count |
| `+36` | 4 | Texture-name table pointer |
| `+40,+44` | 8 | UNKNOWN reserved/other fields |
| `+48` | 4 | Region before `GCTC` marker; marker at stored value +16 |
| `+52,+56` | 8 | UNKNOWN other table/count fields |
| `+60` | 4 | Observed name pointer to `body`/`trans` |

**CONFIRMED:** The tables at `+32/+36` are 16-byte name slots, including repeated
names. First body has 13 slots and six presumed materials; first trans has nine
slots and three presumed materials. Those numbers are **not mesh counts**.
Only four actual texture assets are in the first texture section.

**CONFIRMED:** Bone records are 80 bytes. Known fields: name16 at `+0`, float3
local translation at `+16`, float3 local Euler rotation at `+32`, signed parent at
`+48`. Hierarchy validation and source bind-matrix comparison run successfully.
**UNKNOWN:** Wii geometry-packet organization, vertex/index/mesh counts, corner
attributes, palette numbering and skinning-weight storage. A GCTC marker and
compact packet region are observed, but their instructions are not decoded.
No model OBJ, PSP YOBJ or playable PAC is produced by this inspector.

## Decoded texture evidence

**CONFIRMED:** Section 9 uses the existing little-endian named texture-table
reader, with `.tpl` payloads. Nintendo TPL internals are big-endian. Each has
signature `0x0020AF30`, one image, and image/palette pointers checked against
the actual payload. The following images decode to recognizable source atlases:

| First variant asset | Dimensions | Format | Palette | Pixel bytes |
|---|---:|---|---|---:|
| `color` | 512×512 | CMPR, 4 bits/texel | None | 131,072 |
| `trans` | 128×256 | C8 | 256 RGB5A3 entries | 32,768 |
| `blood` | 64×64 | C4 | 16 RGB5A3 entries | 2,048 |
| `blood_clt0` | 64×64 | C4 | 16 RGB5A3 entries | 2,048 |

**CONFIRMED:** The second variant has color/trans only, with the same dimensions
and formats. Color is opaque; trans contains alpha levels
`0,36,73,109,146,182,219,255`. Blood maps contain transparency too. The decoder
preserves alpha and uses native channel bit replication rather than approximate
linear-floor expansion. These are source textures, not PSP-encoded candidates.

**CONFIRMED:** TPL starts with magic/count/table pointer at `+0/+4/+8`. Each table
entry has image and optional palette header pointers (u32 each). Image header
contains u16 height/width and u32 format/data pointer at `+0/+2/+4/+8`. Palette
header contains u16 entry count and u32 format/data pointer at `+0/+4/+8`.
Some reserved image/palette bytes contain nonzero data and are not assumed to
be meaningful flags. No mipmap behavior is inferred from them.

**CONFIRMED:** C4 uses 8×8 tiles, 32 bytes each, high nibble first. C8 uses 8×4
tiles, 32 bytes each. RGB5A3 palette words select opaque RGB555 or A3RGB444.
CMPR uses 8×8 tiles containing four 4×4 DXT1-style blocks ordered top-left,
top-right, bottom-left, bottom-right, with big-endian RGB565 endpoints and
most-significant-first two-bit row selectors. Edge blocks are bounded/padded
and cropped to logical dimensions. Unsupported texture/CLUT formats fail rather
than producing guessed pixels. No TPL format is directly copied into a PSP PAC.

## Reproduction and next boundary

```sh
local/app-runtime/bin/python -m tools.wwe13_wii_inspect /path/ch145.pac \
  --out local/NEW-wii-study
local/app-runtime/bin/python -m unittest tests.test_wwe13_wii_inspect \
  tests.test_wwe13_inspect tests.test_yukes_bpe
```

**CONFIRMED:** The study produces private decoded section binaries, TPLs, RGBA
PNGs, contact sheet and inventory, while preserving the source file. The focused
run passed 29 tests, including synthetic tile order, CMPR interpolation/alpha,
RGB5A3/channel expansion, indexed bounds, bad offsets, archive extraction and
wrong-model rejection. No new dependency or environment configuration is needed.

**UNKNOWN / next work:** Decode and validate the Wii geometry/skinning packets,
export a faithful source preview, establish polygon counts, then compare the
original weights and poses before attempting PSP adaptation. Neither smaller
archives nor readable bone names establish that this step is already solved.

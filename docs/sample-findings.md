# Initial sample findings

User-identified inputs:

| Input | Role | Bytes | Sections |
| --- | --- | ---: | --- |
| 0900.pac | HCTP PS2 source | 457984 | 2, 8, 9, 100, 101 |
| Kurt-Angle-Ring.PAC | SVR 2007 PSP base | 180224 | 2, 8, 9 |

SHA-256:

```text
0900.pac: 05d264911fde503a0f5d07b634611de2c666b30845c711d4943da8fbdfc21552
Kurt-Angle-Ring.PAC: bf935a51fe30bfd2df929f8eb9e50be5d793426ea05125ca9411ce21b19ead80
```

## Observed layout

Both samples start with `PAC ` followed by a little-endian u32 section count.
Each eight-byte table record consists of a little-endian u16 ID, u24 relative
offset, and u24 byte length. Offsets are relative to `8 + 8 * section_count`.
Every declared range fits in its input, and no sections overlap. Trailing bytes
remain outside the last section (188 source bytes; 1112 target bytes).

Section 2 begins with YOBJ in both inputs. Its PAC length is larger than the
YOBJ length field. Retain the complete section until the extra data is understood.
No inference about skeleton compatibility follows from the shared magic.

Named texture tables have a 16-byte header and 32-byte entries: 16 name bytes,
four extension bytes, u32 size, u32 section-relative offset, and four opaque bytes.
Observed header words are count, 0x100, 0, 16. The opaque entry bytes differ
between samples and must not be discarded during future repacking.

The PSP base has 3 GIM entries in section 8 and 14 GIM entries in section 9.
All 17 begin with `MIG.00.1PSP`. The HCTP source has one standalone RTX3 payload
in section 8, 16 TXC entries in section 9, and one TXC entry in each of sections
100 and 101. Named TXC payloads begin with `RTX3`, rather than TIM2 or DDS.
Do not assume the proposed TM2/DDS conversion route covers this source.

## Uploaded references and PSP geometry reader

| Model | Meshes | Bones | Vertices | Nondegenerate strip triangles |
| --- | ---: | ---: | ---: | ---: |
| Base.yobj | 1 | 113 | 8 | 6 |
| Full Body.yobj | 31 | 113 | 1194 | 1318 |
| Kurt PSP model | 29 | 79 | 1356 | 1488 |
| HCTP model | 11 | 71 | 1722 source / 2016 with UV splits | 2836 |

Base and Full Body have identical bone names, ordering, parents, and bone-table
bytes. The reference is not a replacement for Kurt's skeleton: it contains 34
additional bones, 78 shared bones have different indices, and four shared bones
have different parents (`l_sune`, `l_te`, `r_sune`, `r_te`). Keep the real target
skeleton; any reference weights will require mapping by name and accounting for
hierarchy differences.

The YOBJ reader uses pointers relative to byte 8. Shared header fields provide
mesh, bone, and texture counts and table pointers. Bone records are 80 bytes,
with a 16-byte name, local position, rotation, parent index, and stored global
position. Parent bounds and hierarchy cycles are checked. The stored global
positions in the reference files are zero; they are not usable alignment
landmarks without composing the local transforms.

PSP mesh records are 64 bytes. The observed vertex flags specify float weights,
UVs, byte colors, float normals, and float positions. Weight slots are mapped
through each mesh's bone palette. Materials reference 16-bit triangle strips;
the reader retains those strips and alternates winding when producing triangles.
OBJ output preserves raw model axes and UVs. HCTP mesh fields differ; its geometry
is deliberately rejected by the PSP decoder.

All decoded PSP vertex weight sums are within 0.001 of 1. **Mesh palette references
are one-based on disk; bone-table and parent indices are zero-based.** The earlier
reader incorrectly treated palette references as array indices. A bend test
exposed the error (a left toe appeared weighted to the right thigh). Correcting
the reader fixed that mapping. Kurt's stored reference 79 is valid and maps to
bone index 78, `r_tsumasaki`; it is not a defect in the user's file. Native palette
bytes are retained separately from normalized array indices, and export adds
one back. Unit tests enforce this distinction.

The supplied Windows mesh editor was inspected as a PyInstaller archive with
Python 3.13 bytecode; its readers helped identify the layout. The executable was
not run as a Windows process, and none of its implementation was added to this
repository. The native reader has no dependency on it. The conversion bridge
now executes a selected set of inspected reader/writer/export functions from
that exact hash-pinned executable under CPython 3.13, with no GUI or top-level
module execution. The supplied PAC editor contains a Python 2.7
Windows distribution and `unrrbpe.exe`; GUI execution is not verified here.

The uploaded cleanup script clears vertex groups from selected meshes. The UV
script applies `v = 1 - v` and uses Blender 2.79's active-object API. Neither
performs body sectioning, automatic alignment, or weight transfer. They were
read rather than run against the user's assets.

Validation: twenty-seven unit tests pass, covering container extraction, malformed
ranges, unsupported layouts, triangle winding, bone cycles, palette diagnostics,
and overwrite prevention. Blender 4.3.2 imported the Base preview with exact
counts. The Full Body OBJ import retained all 1318 triangles, but omitted two
objects and seven vertices used only by degenerate/no drawable faces. Exact
mesh and vertex preservation needs a structured importer rather than OBJ.
Structured JSON imports into Blender preserve all mesh, vertex, and triangle
counts for Base, Full Body, Kurt, and the HCTP source. HCTP geometry was also
rendered for visual inspection. Blender rig and pose checks now also run, as
described in [conversion status](conversion-status.md). Native Windows and
PPSSPP validation remain pending.

## Experimental HCTP source decoder

The source's internal name is `RVD1p_0100`. Its mesh headers point to 32-byte
groups containing vertex counts, bone references, position-array pointers, and
normal-array pointers. Positions and normals are float4 vectors. The groups'
counts sum to the mesh vertex counts in all eleven sections.

HCTP material records are 208 bytes, with texture indices at byte 40 and draw
table count/pointer fields at bytes 196/200. All 536 observed draw records have
primitive/attribute values (3, 3). They reference 32-byte corners containing
float UVQ, a source position index, and float RGBA. These observations support a
separate source geometry decoder; the PSP vertex reader is not reused for PS2.

The decoder reconstructs triangle strips and splits vertices when a UV or color
seam requires it. Repeated original position indices are treated as degenerate
triangles, even when the UV split creates distinct output indices. All source
positions, normals, indices, and UVs pass the implemented structural checks.
The rendered source resembles a complete wrestler in a T-pose. Raw YOBJ axes
are retained in exported data; the preview rotates negative Y upward for display.

Source skinning is not decoded or copied. Geometry/UV correctness still needs
in-game comparison. The pipeline uses PSP reference weights instead. RTX3 pixels
are now decoded: the observed PSMT8 host pixel arrays are linear, and the CSM1
CLUT order swaps indices 8/16 within 32-entry blocks. PS2 alpha values are mapped
from the 0..128 scale to 0..255. All fifteen active model textures convert to
PNG and swizzled PSP indexed8 GIM, retaining resolution and the 256-color palette.
Each GIM round trip reproduces the converted pixels and palette exactly. Other
PSM, palette, mipmap, and GIM formats are rejected rather than guessed.

## Next format work

Test the experimental repacked PAC in PPSSPP. Use the outcome to establish game
mesh/memory limits, texture orientation, and actual animation quality before
expanding profiles or building the Windows interface. A known PS2 importer or
`yukes.bms` can still provide an independent source-format comparison.

`Tools.zip` and `blender-2.79-windows32.zip` exceeded the cloud file-transfer
limit of 32 MiB and were not downloaded or inspected. The separately uploaded
scripts, references, mesh editor, and PAC editor were successfully received.
The current cloud has Blender 4.3.2, not the tutorial's Blender 2.79.

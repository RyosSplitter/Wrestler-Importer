# Binary structures and serialization contracts

**CONFIRMED [E02–E07]:** Unless explicitly called out, integer and IEEE-754
float fields below are **little endian**. Offsets in tables are bytes, relative
to the named structure. `u24` is three bytes, not a padded 32-bit word. Pointer
origins differ between PAC, texture tables and YOBJ. Never share a generic
"add 8" rule across these formats.

## PAC container

**CONFIRMED [E02]:** The observed wrestler PAC uses this layout:

```text
0              8                      P = 8 + 8*N
+--------------+----------------------+--------------------------+
| PAC header   | N section rows       | payloads + padding       |
+--------------+----------------------+--------------------------+
row.offset is relative to P; physical section start = P + row.offset
```

| Offset | Bytes | Type / meaning | Status |
|---:|---:|---|---|
| 0 | 4 | ASCII `PAC ` | CONFIRMED E02 |
| 4 | 4 | u32 section count N | CONFIRMED E02 |
| 8+8i | 2 | u16 section ID | CONFIRMED E02 |
| 10+8i | 3 | u24 offset relative to P | CONFIRMED E02 |
| 13+8i | 3 | u24 stored section size | CONFIRMED E02 |
| P onward | variable | raw or BPE-wrapped section contents | CONFIRMED E02/E03 |

**CONFIRMED [E02]:** Require the complete table, positive section lengths,
sections at/after P, ranges inside the file and no overlapping section ranges.
The inspector reports unfamiliar payloads instead of inventing their types.
In studied PSP bases section 2 is the main model, section 9 a named texture
container and section 8 a separate texture container. HCTP section 8 can instead
be a standalone RTX3 image. Identify contents as well as IDs.

**UNKNOWN [E02]:** IDs are not universal semantic tags across all PACs. Other
HCTP tables, including 100/101 in samples, cannot simply be copied into the PSP
base under an assumption of equivalent game meaning.

**CONFIRMED [E02]:** `replace_sections` preserves section IDs, table order and
unreplaced **stored payload bytes**. It places payload starts at absolute
16-byte-aligned PAC addresses and zero-pads the final PAC to 2,048 bytes. It
rewrites offset/size entries and padding; it does not preserve old section
addresses. Offsets/sizes must fit 24 bits. This is the unchanged packaging
process used by accepted trials.

### Named texture container

| Offset | Bytes | Meaning | Status |
|---:|---:|---|---|
| 0 | 4 | u32 texture count | CONFIRMED E02 |
| 4 | 4 | observed/written marker 0x100 | CONFIRMED E02 |
| 8 | 4 | written zero; semantic meaning unresolved | UNKNOWN E02 |
| 12 | 4 | u32 table address, normally 16, relative to container start | CONFIRMED E02 |
| row+0 | 16 | NUL-padded texture name | CONFIRMED E02 |
| row+16 | 4 | extension, e.g. `gim\0` | CONFIRMED E02 |
| row+20 | 4 | u32 payload size | CONFIRMED E02 |
| row+24 | 4 | u32 payload address relative to container start | CONFIRMED E02 |
| row+28 | 4 | written zero; semantic meaning unresolved | UNKNOWN E02 |

**CONFIRMED [E02]:** Rows are 32 bytes. Validate payloads against the end of the
row table and section length. The writer sorts names case-insensitively;
YOBJ's texture list keeps its own index order. Material indices refer to that
YOBJ list, not automatically the texture table's row number.
**UNKNOWN:** Whether row sorting is an engine requirement is not established.

## BPE section compression

| Offset | Bytes | Meaning | Status |
|---:|---:|---|---|
| 0 | 4 | `BPE ` | CONFIRMED E03 |
| 4 | 4 | version 0x100 | CONFIRMED E03 |
| 8 | 4 | compressed payload length, excludes 16-byte wrapper | CONFIRMED E03 |
| 12 | 4 | expanded byte length | CONFIRMED E03 |
| 16 | variable | sequence of dictionary/token blocks | CONFIRMED E03 |

**CONFIRMED [E03]:** Block decoding algorithm:

1. Reset 256 entries: `left[i]=i`, `right[i]=0`, dictionary index 0.
2. Read control byte c. If c≤127, read c+1 entries. If c>127, skip c−127
   identity entries, then read **one** entry unless index has reached 256.
3. An entry reads `left[index]`; if it differs from index, also read
   `right[index]`. Identity entries decode to their literal byte. Other entries
   recursively concatenate their two decoded symbols.
4. Once all 256 entries are covered, read **u16 little-endian token count**,
   then that many token bytes; expand each through this block's dictionary.
5. Continue until exact payload EOF. Require expanded total to equal the wrapper
   length. Reject cycles, dictionary overflow, truncation, zero token blocks,
   output overflow and unreasonable allocation (current limit 32 MiB).

**CONFIRMED [E03]:** Current compression builds blocks of at most 4,000 input
bytes, stopping at 200 distinct symbols, then substitutes frequent adjacent
pairs with unused high symbols. A pair needs count≥3 and net token reduction≥3.
These are deterministic **compressor choices**, not decoder-format limits.
A literal-only valid encoder is sufficient for correctness, though a real
compressed encoder is needed to meet the accepted size budgets.

**CONFIRMED [E03]:** BPE does not reduce expanded YOBJ size or vertex-buffer
memory. A small stored PAC is not evidence that runtime memory corruption is
impossible. Native PSP samples contain BPE around model and texture containers.

## YOBJ common header, bones and names

**CONFIRMED [E04]:** Every YOBJ pointer below stores `absolute_address - 8`.
The primary header occupies 72 bytes. `E = u32(file+4)+8` is the end of the
pre-POF0 model allocation; PSP POF0 begins at E.

| Offset | Bytes | Meaning | Status |
|---:|---:|---|---|
| 0 | 4 | `YOBJ` | CONFIRMED E04 |
| 4 | 4 | u32 E−8 | CONFIRMED E04 |
| 8 | 4 | opaque | UNKNOWN E04 |
| 12 | 4 | PSP second E−8; strict auditor requires equality | CONFIRMED E04 |
| 16,20 | 4 each | opaque | UNKNOWN E04 |
| 24 | 4 | u32 native mesh count | CONFIRMED E04 |
| 28 | 4 | u32 bone count | CONFIRMED E04 |
| 32 | 4 | u32 texture-name count | CONFIRMED E04 |
| 36 | 4 | mesh-header array pointer | CONFIRMED E04 |
| 40 | 4 | bone-table pointer | CONFIRMED E04 |
| 44 | 4 | texture-name array pointer | CONFIRMED E04 |
| 48 | 4 | model descriptor pointer | CONFIRMED E04 |
| 52–71 | 20 | mostly opaque; native accessory may relocate word +60 | UNKNOWN E04 |

**CONFIRMED [E04]:** Texture names are 16-byte NUL-padded records. The native
PSP model descriptor is 32 bytes: name at +0 (16 bytes), opaque +16..23,
u32 mesh count at +24 and opaque +28..31. Its mesh count must match the header.
Some supplied non-native reference tools export a name-only descriptor; the
auditor allows that only explicitly for inspection, not relaxed trial output.

| Bone offset | Bytes | Meaning | Status |
|---:|---:|---|---|
| 0 | 16 | name, NUL terminated; strict reader uses CP932 | CONFIRMED E04 |
| 16 | 16 | float4 local XYZ plus W | CONFIRMED E04 |
| 32 | 12 | float3 stored rotation | CONFIRMED E04 |
| 44 | 4 | opaque | UNKNOWN E04 |
| 48 | 4 | i32 parent: −1 root, otherwise zero-based table index | CONFIRMED E04 |
| 52 | 12 | opaque | UNKNOWN E04 |
| 64 | 12 | float3 stored global position | CONFIRMED E04 |
| 76 | 4 | opaque | UNKNOWN E04 |

**CONFIRMED [E04/E09]:** Bone records have stride 80. Validate names,
finite decoded transforms, parent ranges and acyclic hierarchy. The
implementation constructs `Mworld = Mparent * T(localXYZ) * Rz * Ry * Rx`.
**INFERRED [E09]:** The stored angles behave as radians under the supported
sample interpretation. Exact native animation/controller semantics are not
fully reverse-engineered; the matrix formula alone does not certify them.

## HCTP PS2 mesh layout

| Mesh offset | Bytes | Meaning | Status |
|---:|---:|---|---|
| 0 | 4 | u32 position-group count | CONFIRMED E05 |
| 4 | 4 | u32 material count | CONFIRMED E05 |
| 8 | 4 | group-array pointer | CONFIRMED E05 |
| 12 | 4 | material-array pointer | CONFIRMED E05 |
| 16–27 | 12 | opaque | UNKNOWN E05 |
| 28 | 4 | VIF weight-stream pointer | CONFIRMED E05 |
| 32 | 4 | observed packet count 2*position_count+2 | CONFIRMED E05 |
| 36 | 4 | weight-stream length in 16-byte qwords | CONFIRMED E05 |
| 40 | 4 | native position count | CONFIRMED E05 |
| 44–63 | 20 | not fully interpreted by source reader | UNKNOWN E05 |

**CONFIRMED [E05]:** Headers are 64 bytes. The supported group is 32 bytes:
u32 position count +0, bone count +4 (1..4), position pointer +8, normal pointer
+12, four u32 stored palette slots +16. Used slots are **one-based bone IDs**.
Unused slots are not interpreted as bones. Group positions concatenate in group
order; their total must equal mesh position count. Positions and normals are
separate float4 arrays, stride 16. Position W≈1; normal W is not used.

| HCTP material/primitive/corner field | Bytes | Meaning | Status |
|---|---:|---|---|
| Material +40 | 4 | u32 zero-based texture ID | CONFIRMED E05 |
| Material +196 | 4 | u32 strip count | CONFIRMED E05 |
| Material +200 | 4 | strip-array pointer | CONFIRMED E05 |
| Other material bytes (stride 208) | variable | opaque PS2 rendering data | UNKNOWN E05 |
| Primitive +0,+4 | 4 each | observed `(3,3)` primitive/attribute words | CONFIRMED E05 |
| Primitive +8 | 4 | u32 corner count | CONFIRMED E05 |
| Primitive +12 | 4 | corner-array pointer; primitive stride 16 | CONFIRMED E05 |
| Corner +0 | 12 | float3 U,V,Q; Q≈1 | CONFIRMED E05 |
| Corner +12 | 4 | u32 source position index within this mesh | CONFIRMED E05 |
| Corner +16 | 16 | float4 RGBA, supported range 0..1 | CONFIRMED E05 |

**CONFIRMED [E05]:** Corner stride is 32. Split vertices by
`(source_position_index, UV, color)` while retaining source index for weights.
One position may produce multiple UV/color records. Triangle strips use
`(i,i+1,i+2)` at even i and `(i,i+2,i+1)` at odd i. Suppress triangles repeating
**source position indices**, even when UV splitting assigned distinct output IDs.
Native position counts, UV-split records and unique spatial points are different
quantities. A count report must state which it measures.

### HCTP weights / VIF

**CONFIRMED [E05]:** Each supported packet has 16 bytes of header: three zero
u32s and a command at +12, followed by `count` float4 weight rows. Command:

```text
31            24 23           16 15         10 9             0
+---------------+---------------+-------------+---------------+
| 0x6c V4-32    | count (0=256)  | reject bits | VU destination|
+---------------+---------------+-------------+---------------+
first source vertex = destination - 0x280
```

**CONFIRMED [E05]:** The decoder rejects command low control bits masked by
0xfc00. The weight address base is fixed **0x280**, not derived from this mesh's
vertex count. Current decoder coverage is ≤160 source positions per mesh, a
supported-layout restriction, not a proven universal game limit. One-bone
groups are implicit weight 1; multi-bone groups require exactly covered explicit
rows. Weights occupy the group's ordered slots, not global bone indices. Unused
float4 slots must be zero; weights finite, 0..1, sum within 1e−5. Reject overlaps,
missing coverage and out-of-bounds packets. UV-split records copy their native
source position's weights.
**UNKNOWN:** The complete VU microprogram, other VIF commands and larger layouts
are not implemented or proved compatible.

## Native PSP mesh and weighted vertices

| PSP mesh offset | Bytes | Meaning | Status |
|---:|---:|---|---|
| 0 | 4 | opaque donor part metadata | UNKNOWN E06 |
| 4 | 4 | material count | CONFIRMED E06 |
| 8 | 4 | palette-header pointer | CONFIRMED E06 |
| 12 | 4 | material-array pointer | CONFIRMED E06 |
| 16–23 | 8 | opaque metadata | UNKNOWN E06 |
| 24 | 4 | pointer to four-byte vertex-pointer cell | CONFIRMED E06 |
| 28 | 4 | GE vertex-format flag | CONFIRMED E06 |
| 32–39 | 8 | opaque metadata | UNKNOWN E06 |
| 40 | 4 | vertex-record count | CONFIRMED E06 |
| 44 | 4 | opaque metadata | UNKNOWN E06 |
| 48 | 16 | float4 center XYZ / radius, preserved or enclosed | CONFIRMED E06 |

**CONFIRMED [E06]:** PSP mesh headers are 64 bytes, but +28 has a different
meaning from HCTP. The palette allocation is `16+4*K` bytes:
vertex count +0, K +4, vertex-data pointer +8, opaque word +12,
K one-based u32 bone IDs +16. The separately pointed vertex cell and palette+8
must point to **the same** vertex buffer. Palette entries must be unique and in
range. Vertex weight slot j corresponds to palette[j], not bone j globally.

**CONFIRMED [E06]:** For weighted layouts, clear 0x1c000 from the flag to obtain
the base. `K=((flag>>14)&7)+1`, supported 1..8, and K must equal palette length.

| Base flag | Per-slot encoding | Normalization denominator | Status |
|---|---|---:|---|
| 0x17ff | float32 | 1 | CONFIRMED E06 |
| 0x13ff | u8 fixed point | **128**, not 255 | CONFIRMED E06 |
| 0x15ff | u16 fixed point | **32768**, not 65535 | CONFIRMED E06 |
| exact 0x11ff | rigid/no vertex weight block | external attachment unresolved | CONFIRMED layout / UNKNOWN attachment E06 |

**CONFIRMED [E06]:** Let `W=align_up(K*slot_width,4)`. The weighted stride is
`W+36`, with fields:

```text
+0         weights K*slot_width, then padding to W
+W         float2 UV                  8 bytes
+W+8       RGBA8                      4 bytes
+W+12      float3 normal             12 bytes
+W+24      float3 model-space position 12 bytes
```

**CONFIRMED [E06]:** Rigid stride is 36. Finite weighted values must lie in
0..1.0001 and sum within 0.001 under the strict auditor. Integer quantization
uses largest remainders so the integer sum equals the format denominator;
normalizing to all-ones would be wrong. The successful latest artifacts use
float32 weights. Four strongest active influences is a conversion policy;
eight slots is the encoded palette capacity, not a two-influence law.

### PSP materials and indices

| Material offset | Bytes | Meaning | Status |
|---:|---:|---|---|
| 0–21 | 22 | opaque native rendering state | UNKNOWN E06 |
| 22 | 2 | u16 zero-based YOBJ texture index | CONFIRMED E06 |
| 24 | 4 | rendering/depth control word; see texture book | CONFIRMED values / UNKNOWN full semantics E08 |
| 28–131 | 104 | opaque native rendering state | UNKNOWN E06 |
| 132 | 4 | strip count | CONFIRMED E06 |
| 136 | 4 | strip-header-array pointer | CONFIRMED E06 |
| 140 | 4 | first-index-buffer pointer alias | CONFIRMED E06 |

**CONFIRMED [E06]:** Material stride is 144. Each strip header has opaque +0..7,
u32 count at +8 and index-buffer pointer at +12 (stride 16). The tested primitive
prefix is `03 00 00 00 00 00 00 00`. Indices are u16 LE and **local to this mesh's
vertex buffer**. Require each `<vertex_count`; preserve strip parity and exclude
repeated-index triangles from triangle counts. Raw index totals include degenerate
connectors. Material+140 must alias the first strip's index allocation. Empty
material alias behavior is unknown and the controlled writer refuses it.

## POF0 relocation and alignment

**CONFIRMED [E07]:** POF0 is not part of E: at file offset E, write ASCII POF0,
u32 LE payload byte length, then relocation data including final zero padding.
That size must end at exact file EOF. Relocations identify **addresses of pointer
fields**, not addresses of the referenced buffers. Start address cursor at 8.
Each encoded unsigned delta represents `(next_field_address−cursor)/4`:

| Top two bits | Width | Encoding | Status |
|---|---:|---|---|
| 01 | 1 byte | lower 6 bits | CONFIRMED E07 |
| 10 | 2 bytes | big-endian lower 14 bits | CONFIRMED E07 |
| 11 | 4 bytes | big-endian lower 30 bits | CONFIRMED E07 |
| 00 | zero byte only | end/padding; all remaining bytes must be zero | CONFIRMED E07 |

**CONFIRMED [E07]:** Require positive deltas, valid four-byte pointer fields
strictly inside E and exact agreement between parsed pointer-field locations
and relocation locations. Distinct pointer fields can target the same allocation.
Do not remove aliases merely because two pointer values are identical.

**CONFIRMED [E06/E07]:** The selected writer aligns allocations **relative to
YOBJ byte 8**, i.e. `(address−8)%16==0`, while PAC payload starts use
`address%16==0`. Index data are two-byte values but their allocated buffer starts
follow that relative 16-byte convention. Pointer targets must be at least
four-byte aligned. Final YOBJ EOF is 16-byte aligned by enlarging POF0 padding,
without changing the pre-POF0 end. Native audit enforces bounded/disjoint spans;
exactly identical aliases are allowed, partial overlap is rejected.

## Writing a compatible model without the editor

**CONFIRMED [E06]:** `tools.psp_mesh_merge.write_model` is a repository-native
serializer for audited float-weight skinned models. Its algorithm copies opaque
header/mesh/material/strip bytes, allocates arrays, remaps palette slots, writes
local indices and pointer aliases, copies the PSP bone table and texture names,
updates both mesh counts and E fields, then regenerates POF0 and audits output.
It rejects unknown relocated header +60, unsupported layouts and unknown empty
material semantics rather than manufacturing meanings.

**INFERRED [E06]:** A new implementation can implement the same layout independently
using native PSP donor templates for opaque state. The synthetic fixture proves
field/offset contracts, not that a zero-filled material template works in-game.
**UNKNOWN:** Building all rendering/controller metadata from scratch without a
native donor remains unsupported; preserve a known-working PSP template.

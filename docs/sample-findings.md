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

## Next format work

Inspect the supplied extraction/import scripts to establish YOBJ mesh, bone,
weight, and RTX3 pixel layouts. Then decode the source and base into a shared
mesh representation and verify the decoded models against the existing tools.
Only after that, implement alignment, PSP body sectioning, weight transfer,
texture conversion, and repacking while preserving unrelated base sections.

`Tools.zip` exceeded the cloud file-transfer limit of 32 MiB and was not
downloaded or inspected. Request smaller archives containing scripts/plugins
and reference assets. The current cloud has Blender 4.3.2, not the tutorial's
Blender 2.79; plugin compatibility is unverified. No Windows execution or PPSSPP
validation has occurred.

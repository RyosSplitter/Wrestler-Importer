# PS2 texture decoding in beta 0.1.1

The user's HCTP `1800.pac` fails in beta 0.1 because eight of its 19 model
textures are PSMT4 RTX3 images with compact 16-entry RGBA32 palettes. The old
reader only accepts PSMT8 with a 256-entry RGBA32 CSM1 palette. This is a decoder
limitation, not a bad editor selection or an archive injection failure.

`app/ps2_textures.py` expands source decoding without changing the 13 pinned
opacity-fix backend modules. The working RVD case still calls the original
PSMT8 reader, texture budget, GIM writer, model preparation and PAC packer.

## Supported RTX3 layouts

| Source format | Stored pixels | Palette |
| --- | --- | --- |
| PSMT4 | Linear packed indices, low nibble first | Compact 16 entries or a full 256-entry table with CLUT-bank selection |
| PSMT8 | Linear byte indices | 256 entries |
| PSMCT16 / PSMCT16S | Linear RGB5A1 words | None |
| PSMCT24 | Linear packed RGB bytes or RGB in 32-bit upload words | None; fourth byte is padding |
| PSMCT32 | Linear RGBA bytes | None |

Indexed palettes support RGBA32 and RGB5A1 (PSMCT16/16S). Full CSM1 palettes
swap CLUT address bits 3 and 4; CSM2 host palettes retain linear order. Compact
16-color palettes retain their stored index order. RGBA32 PS2 alpha 0–128 maps
to 0–255; RGB5A1 uses its one-bit alpha, and RGB24 is opaque. No extra GS VRAM
unswizzle is applied to linear RTX3 upload images.

Coverage is for these validated host layouts, not all PS2 texture containers.
TIM2, compressed texture payloads, raw GS VRAM dumps, higher-byte indexed modes,
and unrecognized palette/layout variants remain unsupported. Errors now include
the source texture name, PAC section, PSM, CPSM, CSM, CSA and dimensions, before
Blender processing. Unknown layouts are not interpreted as another format.

The PSP output remains indexed4 GIM with the original lossy resize/quantization
and alpha endpoint handling. Decoding preserves source alpha; budgeting can
change intermediate alpha and fine cutout detail, as in the accepted profile.
Each emitted GIM is decoded again and compared with its converted pixels and
palette. PNG previews use those same converted RGBA values.

## Size fitting

The app first tries the accepted ratio-0.3/64px settings. It measures the
actual aligned, 2048-byte-padded PAC in memory. If oversized, it tests a 32px
texture budget before lowering the same seam-protected collapse ratio. It
keeps float weights, individual triangle strips, the original PSP skeleton,
material rules and alpha policy. The completion message and `size-fit.json`
identify changes; no archive over 147456 bytes is published. Geometry retries
are limited to four and cannot go below ratio 0.1. This can sacrifice detail.

`1800.pac` produces:

| Settings | Fully padded PAC | Source triangles after reduction |
| --- | ---: | ---: |
| Ratio 0.3, 64px | 167936 bytes (164 KiB) | 969 |
| Ratio 0.3, 32px | 149504 bytes (146 KiB) | 969 |
| Ratio 0.27, 32px | 147456 bytes (144 KiB) | 916 |

The final model has 44 PSP mesh chunks, 79 preserved PSP bones and 19 textures.
PAC SHA-256:
`340b1221ede95ed4bc5051661a35643c078274518cb56160285da275dc40c93f`.
`preview/prepared.yobj` matches the PAC model payload exactly. Source alpha,
pixel nibble order and palette behavior are checked by texture tests; source
bone tables, native vertex attributes and triangle winding are checked during
the worker conversion. The RVD sample remains at its original settings and
matches the accepted PAC SHA-256 byte for byte.

Sixty unit tests cover the existing pipeline and expanded decoding/size fitting.
Real PAC checks exercise RVD's PSMT8 textures and the eight compact PSMT4 textures
in `1800`; RGB5A1, direct color and alternate palette addressing use synthetic
format fixtures. Cloud conversion checks do not establish in-game rendering.
The `1800` export still needs the user's PPSSPP test.

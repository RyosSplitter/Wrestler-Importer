# WWE SVR PSP PAC / YOBJ preview — experimental 0.1.0

Copy **fmt_wwe_psp_yobj.py** into your complete Noesis installation's
`plugins/python` folder, then restart Noesis. Double-click a PSP wrestler PAC
or YOBJ. This is a standalone plugin: no Blender, NumPy, OBJ extraction,
RROEexporter, unrrbpe.exe or converter installation is required.

For the first test, move the old **PS2 plugin outside `plugins/python`**. Its
checkers claim any YOBJ/BPE signature and some PSP PACs, which can make Noesis
choose its incomplete PSP fallback instead of this plugin. Keep the original
file as a backup. To retain both plugins later, add the following two lines at
**the beginning of each** original `wwePs2YobjCheckType(data)` and
`wwePs2PacCheckType(data)` function, with the same indentation as its body:

```python
from fmt_wwe_psp_yobj import check_type as is_psp
if is_psp(data): return 0
```

That makes the original handler decline formats the PSP reader recognizes.
Do not install two copies of the new PSP plugin. Noesis must already include its
standard Python runtime and `inc_noesis.py`; those proprietary/runtime files
are not distributed here.

## Files and textures

* **PAC:** Reads its TOC and BPE entries in memory. Embedded GIM textures are
  used automatically, with costume table 9 taking precedence over effect tables.
  No sibling files or manual extraction are needed for a normal costume PAC.
* **YOBJ/BPE model:** Geometry loads directly. Place matching, named GIM or PNG
  textures beside it; a YOBJ alone does not contain its image pixels. DDS is
  also accepted through Noesis's built-in texture handler. Missing maps are
  logged and remain untextured; another version's images are not substituted.
* All YOBJ sections in a costume PAC are included as named preview meshes,
  using their stored rest coordinates. Accessory/alternate models can overlap.
  The importer option `-pspmainonly` shows only main section 2. External game
  attachment rules, removal/throw behavior and variant switching are not emulated.
* UVs, normals, vertex colors and texture alpha come directly from the file.
  Indexed4/8 GIMs decode narrow padded/swizzled rows and RGBA8888 CLUTs. Alpha
  samples are not made opaque. Cutout textures use a 0.5 preview alpha test;
  Noesis lighting/blending is not a reproduction of every PSP render flag.
* Coordinates use the proper rotation `(x,z,-y)` also used by this repository's
  native OBJ preview. No scaling, vertex movement, V flip, smoothing or arbitrary
  triangle reversal occurs. Degenerate strip triangles are omitted, with parity
  preserved across the complete original strip.
* Use Noesis's orientation/culling/shading controls to adjust the view, as in
  the existing review workflow. The viewer state can persist between files.

## Scope and limits

This previews verified WWE SVR **PSP** costume layouts, including converted
models. It deliberately rejects PS2 YOBJ layouts. It is not a CH.PAC/DPK8 archive
browser, PAC editor, converter, PSP exporter or animation emulator. Weights and
bone palettes are read/validated but no Noesis skeleton or game animation is
built. Bone count in the Noesis preview is therefore zero; that does not mean
bones were removed from the source file. The plugin never writes to the PAC.

Supported GE layouts: rigid `0x11FF`; float weights based on `0x17FF`; u8/128
weights based on `0x13FF`; u16/32768 weights based on `0x15FF`, one to eight slots,
with four-byte weight padding followed by float UV, RGBA8, float normal and float
position. Stride is `36 + align4(slot_count * weight_width)`, not a guessed 36.
Mesh records are 64 bytes, materials 144 bytes, strip headers 16 bytes and
indices little-endian u16. YOBJ pointers are relative to byte 8. PAC records are
u16 section + u24 relative offset + u24 size; origin is the end of the TOC.
Unexpected layouts are rejected rather than guessed or repaired.

## Evidence and testing status

**CONFIRMED decoder tests:** Eight generated tests cover compressed PAC/YOBJ,
multiple YOBJs, native strip winding, attributes, float/u8/u16/rigid formats,
rectangular/narrow GIM pixels and alpha, invalid pointers/indices/palettes and a
Noesis callback mock. The mock checks actual position/UV/color/index buffers and
embedded texture attachment. It is not an execution of Noesis's native callback.

**CONFIRMED native corpus comparison:** 116 supplied PSP PAC files decoded.
All model positions, normals, UVs, colors, weights, strides, palettes and material
triangles match the separate repository auditor. All embedded indexed GIM pixels
match its independent NumPy decoder. Some native files have an inconsistent
secondary model-descriptor count; for those comparisons only, a temporary copy
of that count was normalized to allow the stricter oracle to read the same raw
geometry. Source files were never modified. No such repair occurs in the plugin.

**PENDING real Noesis verification:** The available local Noesis binaries lack
its Python plugin runtime and do not register Python importers. The complete
uploaded archive exceeds the 32 MiB file-transfer cap. Downloading the official
full 4.466 runtime from richwhitehouse.com was blocked by the cloud allowlist;
a domain addition was saved to the environment draft for user review. Thus no
working PAC/YOBJ screenshot from this plugin is claimed yet. Treat this download
as an experimental candidate until tested in a complete Noesis installation.

Run repository checks with:

```
python -m unittest tests.test_noesis_psp_plugin
```

The decoder is self-contained and can also be imported without Noesis for binary
conformance tests. The accompanying report lists file hashes and comparison
results. It includes no original game PACs, Noesis binaries or Noesis SDK files.

# WWE SVR PSP PAC / YOBJ preview — experimental 0.1.1

Copy **fmt_00_wwe_psp_yobj.py** into your complete Noesis installation's
`plugins/python` folder, then restart Noesis. Double-click a PSP wrestler PAC
or YOBJ. This is a standalone plugin: no Blender, NumPy, OBJ extraction,
RROEexporter, unrrbpe.exe or converter installation is required.

Remove the previous **fmt_wwe_psp_yobj.py** from `plugins/python` if installed.
Keep the **00** prefix on the new filename: in the tested Noesis 4.466 installation,
this registers the PSP handler before **fmt_wwe_ps2_yobj.py**. Both can then stay
installed. The PSP type checker validates the PSP layout and declines HCTP files,
which continue to the PS2 handler. Do not install duplicate PSP handlers.

**Confirmed failure:** With the old unprefixed filenames, the PS2 checker claimed
a native PSP Kurt PAC first. Noesis selected its PS2 fallback and displayed white,
exploded geometry with no textures. Moving the PS2 plugin out fixed loading;
installing the prefixed PSP filename also fixed it with both plugins present.
If another plugin still claims the file first, temporarily move that handler
outside `plugins/python` and restart. Keep a backup rather than deleting it.

Noesis must already include its
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
  triangle reversal occurs in the decoder. Degenerate strip triangles are omitted,
  with parity preserved across the complete original strip. The renderer uses
  `RPGOPT_TRIWINDBACKWARD=1` to adapt Noesis's front-face convention; this prevents
  culling from displaying the inside of the head. File geometry is not changed.
* The importer applies `setPreviewOption("setAngOfs", "0 90 0")` for an upright
  starting view (rear in the tested installation). You no longer need to press
  the orientation toggle each time. F3 changes orientation, F4 controls face
  culling, and F5 controls shading. This does not simulate three keypresses.
  Automatic culling/shading settings are not exposed by the documented preview
  API we found, so those remain manual. Persisted viewer settings can affect the
  result; blindly toggling them on every load would alternate their state.

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

**CONFIRMED actual Noesis verification:** The user's `plugins.zip` supplied the
missing Python runtime. Noesis64 4.466 runs with that runtime under Wine 11 in the
cloud environment. Native Kurt PSP PAC, converted Jericho PAC, a standalone
Jericho YOBJ with named GIM siblings, and native multi-model Rock PAC were tested.
The PS2 HCTP Jericho PAC still selects the PS2 handler with both installed. Actual
viewer screenshots and input hashes accompany the download. This is native
Noesis execution under Wine, not a clean Windows test or an animation test.

**Confirmed rendering adaptation:** For Kurt, 1,486 nondegenerate triangles agreed
with stored normals and two disagreed; all 2,665 tested Jericho triangles agreed.
In actual Noesis, adapting front-face winding removed the inside-out face/braid
appearance under the tested culling state. The decoder's index buffers and all
source files remain unchanged. Alpha, skeleton/animation semantics and material
flags retain the scope limits above; game-equivalent rendering is not claimed.

Run repository checks with:

```
python -m unittest tests.test_noesis_psp_plugin
```

The decoder is self-contained and can also be imported without Noesis for binary
conformance tests. The accompanying report lists file hashes and comparison
results. It includes no original game PACs, Noesis binaries or Noesis SDK files.

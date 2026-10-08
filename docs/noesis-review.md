# Model review workflow

The user specifies this review process for every finished conversion version.
Use the YOBJ from that version's PAC and its corresponding converted PNGs;
do not combine geometry and textures from different versions.

1. Open **YOBJ File Tool v2.0** (`YOBJ_Tool_GUI.exe`).
2. Select **PSP** in the file-type dropdown.
3. Open the finished `prepared.yobj`.
4. Select **Export all as one OBJ**. Place the OBJ and its material file in
   the same directory as that version's named PNG textures.
5. Open **Noesis 4.466** and double-click the exported OBJ.
6. From the initial viewer state, click **orientation toggle** once,
   **face cull toggle** once, and **shading toggle** once, in that order.
7. Capture an actual Noesis screenshot. For comparisons, retain a consistent
   camera/view and note any changes to the camera after these toggles.

For controlled comparisons, restart Noesis from default viewer settings for
each model before applying these three toggles. Opening another model resets
orientation, but other viewer settings can persist. Do not assume one click
per load produces the same culling/shading state across a reused instance.

Keep the OBJ's material texture paths relative to this directory. This tool
writes `.gim` references into the MTL, so include the matching GIMs as well as
PNGs. Check that the referenced images exist and Noesis displays them. Record which PAC,
YOBJ and texture set the screenshot depicts, plus the output PAC size. A
Noesis OBJ preview checks static appearance; animation/skinning and in-game
material behavior still require the PSP YOBJ/PAC and PPSSPP.

The preview tool is separate from **yobj_mesh_editor_PSP_GUI.exe**, which the
beta uses to write PSP YOBJ files. Do not replace the mesh editor selection in
the beta with `YOBJ_Tool_GUI.exe`.

## Verified cloud review

The separately supplied Noesis executables and `noex64.zip` provide a working
Noesis64 4.466 installation. Actual textured model screenshots were captured
under Wine 11.0 with software OpenGL, Xvfb and Openbox. Disabling Xvfb's MIT-SHM
extension avoids Mesa shared-memory errors. Keep the initial window height;
horizontal maximization works, but vertical resizing clips the rendered image
in this runtime. Startup instructions are saved in the cloud configuration
draft; third-party runtimes and tools remain local and are not redistributed.

The YOBJ File Tool Windows executable is 32-bit and fails under this runtime's
WoW64 mode. Its original embedded Python 2.7 GUI bytecode and exporter modules
run under native CPython 2.7.18 with a local compatibility harness. The harness
adapts the file dialog option to native Tk; it does not replace the exporter.
PSP selection, YOBJ loading and **Export all as one OBJ** were completed through
that original GUI. This is not execution of the Windows EXE.

## 1800 export comparison

A subsequent [stage comparison with additional HCTP samples](arm-diagnosis.md)
localizes the static arm damage to reduction, before sectioning or weight
transfer. That comparison uses fresh viewer defaults for every screenshot.

The reviewed PAC is the unchanged beta 0.1.1 `1800` candidate: 147456 bytes
(144 KiB), SHA-256
`340b1221ede95ed4bc5051661a35643c078274518cb56160285da275dc40c93f`.
The review YOBJ matches its PAC model section exactly. The original tool's OBJ
contains all 1327 vertices and 916 triangles, with matching positions and UVs
after its documented coordinate conversion. Its MTL references 17 textures;
all 19 model textures are included in both PNG and GIM form.

However, the original tool's **Export all as one OBJ** path does not alternate
triangle-strip winding correctly. It reverses 317 of these 916 native triangles.
This can affect face culling and generated normals. The review bundle preserves
the unmodified `prepared.obj`, MTL and screenshot. A separately labeled
`native-winding-preview.obj` restores the triangle order from the native YOBJ
without changing vertex positions, UVs, materials or the PAC. Its screenshot
is included for comparison. Arm gaps remain visible in the static previews;
the winding correction does not establish that the conversion's appearance
is fixed. Further alignment/geometry investigation and PPSSPP testing remain.

[Original tool export screenshot](../downloads/1800-noesis-original-tool-export.png)
and [native-winding diagnostic screenshot](../downloads/1800-noesis-native-winding-preview.png)
are actual Noesis captures. Both use the requested orientation, face-cull and
shading toggles once after loading, with no camera adjustment.

[Download the complete review bundle](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/1800-HCTP-to-PSP-Noesis-review.zip)
for the unchanged test PAC, exact YOBJ, both OBJs, MTL, named PNG/GIM textures,
screenshots and validation report. A static OBJ has no PSP skinning or animation;
this preview is not an in-game test.

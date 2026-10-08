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

Keep the OBJ's material texture paths relative to this directory. Check that
the referenced PNGs exist and that Noesis displays them. Record which PAC,
YOBJ and texture set the screenshot depicts, plus the output PAC size. A
Noesis OBJ preview checks static appearance; animation/skinning and in-game
material behavior still require the PSP YOBJ/PAC and PPSSPP.

The preview tool is separate from **yobj_mesh_editor_PSP_GUI.exe**, which the
beta uses to write PSP YOBJ files. Do not replace the mesh editor selection in
the beta with `YOBJ_Tool_GUI.exe`.

## Environment status

The provided YOBJ File Tool archive has been extracted locally. Its executable
is 32-bit Windows and ships Python 2.7. This Linux cloud environment has no Wine
runtime installed. GUI execution has not been established.

The uploaded `noesisv4466.zip` exceeds the upload-to-executor tool's 32 MiB
transfer limit and could not be downloaded. A smaller ZIP or multiple separate
ZIPs containing Noesis's executables, required DLLs and plugin folders is needed
to test this workflow. No actual Noesis screenshot has been captured yet.

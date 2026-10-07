# Wrestler Importer

Goal: turn a PS2 wrestler PAC from SYM, JBI, HCTP, or PS2 SVR into a PSP SVR
wrestler PAC using a target PSP base skeleton and body layout. The intended app
runs on Windows; exports will be tested in PPSSPP.

## Current capability

The first component is a read-only PAC container inspector and extractor.
It is tested against the provided HCTP `0900.pac` and SVR 2007 PSP
`Kurt-Angle-Ring.PAC`. It extracts exact model sections and named texture
payloads, validates table bounds, and reports SHA-256 checksums.

The YOBJ reader also decodes skeleton tables in all four supplied models and
PSP geometry in the reference files and Kurt's PAC. It can export geometry-only
OBJ previews and JSON containing the original bone palettes and vertex weights.
It reports out-of-table bone references without silently changing them.

An experimental HCTP reader now decodes the supplied source's positions, normals,
UVs, and triangles. It preserves UV seams and source vertex indices, and exports
the same mesh representation for later alignment work.

The first experimental conversion now aligns the supplied HCTP model, assigns
body sections, transfers reference weights onto the unchanged PSP base skeleton,
converts RTX3 textures to indexed8 GIM, serializes YOBJ/DAE, and repacks a copy of
the PSP PAC. Native model serialization is independently checked, and repeated
PAC repacking produces identical bytes. Section starts and the final model
relocation chunk are padded to 16-byte boundaries.

**PPSSPP compatibility remains unverified.** This is a backend prototype for the
supplied HCTP -> SVR 2007 PSP pair, not the finished Windows drag-and-drop app.
Other games and packet variants remain unsupported. Source skeletons are not
retargeted; the real PSP base's bone records are preserved byte for byte.

## Convert the initial sample

Requires CPython 3.13, NumPy/Pillow, the supplied PSP mesh editor executable,
the PS2 source PAC, the PSP base PAC, and `Full Body.yobj`. The bridge only accepts
the inspected executable's SHA-256. It calls selected serialization functions
without running the Windows GUI or executable's top-level code. That third-party
implementation is not included in this repository.

From the repository directory on Windows:

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 tools/convert_hctp.py "C:\models\0900.pac" "C:\models\Kurt-Angle-Ring.PAC" "C:\models\Full Body.yobj" --editor "C:\tools\yobj_mesh_editor_PSP_GUI.exe" --output "local\rvd-test"
py -3.13 -m unittest discover -s tests -v
```

The output directory must be new. The output contains the experimental PAC,
decoded PNG/GIM textures, prepared JSON, native YOBJ/DAE, logs, and a conversion
report. Original files are opened for reading only. The DAE follows the supplied
editor's coordinate and UV conventions; prepared JSON stores Blender UVs, and
the native YOBJ export restores native top-origin V.

In this Linux cloud, the tested equivalent is `python3 tools/convert_hctp.py ...
--editor-python /usr/bin/python3.13`. The main pipeline runs on Python 3.12 while
the serialization bridge uses 3.13. Native Windows execution is not yet tested.

Optional Blender 4.3 review (not Blender 2.79):

```powershell
blender --background --python-exit-code 1 --python tools/blender_validate.py -- local/rvd-test/prepared.json local/rvd-test/review local/rvd-test/textures
```

This saves a review rig with packed textures, three pose previews, and deformation
diagnostics. Colored-section previews are available by omitting the texture path.
The Blender review rig is not the native PSP skeleton export.

See [conversion status and test instructions](docs/conversion-status.md).

The initial [PPSSPP test bundle](downloads/README.md) is available to download
from this repository.

## Run

The inspection readers alone require Python 3.10+ with no external packages.
From the repository directory:

```powershell
py -3 tools/pac_inspect.py "C:\models\0900.pac"
py -3 tools/pac_inspect.py "C:\models\Kurt-Angle-Ring.PAC" --extract "local\kurt-extracted"
py -3 -m unittest discover -s tests -v
```

Read a YOBJ skeleton, compare it with the target, or export PSP geometry:

```powershell
py -3 tools/yobj_read.py "C:\models\Base.yobj" --compare "C:\models\Kurt-Angle-Ring.PAC"
py -3 tools/yobj_read.py "C:\models\Kurt-Angle-Ring.PAC" --psp-geometry --json "local\kurt.json" --obj "local\kurt.obj"
py -3 tools/hctp_read.py "C:\models\0900.pac" --json "local\hctp.json" --obj "local\hctp.obj"
```

Create `local/` first if using these paths. Outputs must not already exist.
OBJ previews preserve raw coordinates, UVs, and normals; they have no armature
or texture images. JSON retains bone hierarchy, local transforms, mesh palettes,
weights, material indices, and triangle strips for later conversion work.
`--psp-geometry` explicitly selects the observed PSP vertex layout and rejects
the source PS2 layout. Skeleton comparison measures names, indices, and parents;
it does not prove transform or animation compatibility.

On Linux use `python3` instead of `py -3`. The extraction directory must not
already exist. Extraction writes numbered files rather than trusting embedded
texture names as paths. Original PACs are opened for reading only.

Model sections retain all their bytes, including data following the YOBJ size
field; they are saved as `.bin` until model-boundary semantics are verified.
Texture entries retain their native GIM or TXC bytes in the inspection command.
The conversion pipeline performs image conversion separately. `report.json`
maps extracted files to the original offsets and names.

See [sample findings](docs/sample-findings.md) for the first format observations.
Keep local game assets and third-party binaries under ignored `local/` or
outside the checkout.

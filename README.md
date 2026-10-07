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

It does **not** yet transfer weights, convert images, repack modified PACs, or
produce playable exports. HCTP source skin weights and other games' container
variants remain unverified.

## Run

Requires Python 3.10+ with no external packages. From the repository directory:

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
Texture entries retain their native GIM or TXC bytes. No image conversion is
performed. `report.json` maps extracted files to the original offsets and names.

See [sample findings](docs/sample-findings.md) for the first format observations.
Keep local game assets and third-party binaries under ignored `local/` or
outside the checkout.

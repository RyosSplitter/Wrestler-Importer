# Wrestler Importer

Goal: turn a PS2 wrestler PAC from SYM, JBI, HCTP, or PS2 SVR into a PSP SVR
wrestler PAC using a target PSP base skeleton and body layout. The intended app
runs on Windows; exports will be tested in PPSSPP.

## Current capability

The first component is a read-only PAC container inspector and extractor.
It is tested against the provided HCTP `0900.pac` and SVR 2007 PSP
`Kurt-Angle-Ring.PAC`. It extracts exact model sections and named texture
payloads, validates table bounds, and reports SHA-256 checksums.

It does **not** yet decode meshes, transfer weights, convert images, repack
modified PACs, or produce playable exports. Other games' container variants
remain unverified.

## Run

Requires Python 3.10+ with no external packages. From the repository directory:

```powershell
py -3 tools/pac_inspect.py "C:\models\0900.pac"
py -3 tools/pac_inspect.py "C:\models\Kurt-Angle-Ring.PAC" --extract "local\kurt-extracted"
py -3 -m unittest discover -s tests -v
```

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

# PSP bone-weight regional decimation

The preceding facial-detail build improves the face in the user's SVR 2011 test,
but sacrifices too much body detail. The new `--regions` profile transfers weights
to the unchanged PSP skeleton before reducing geometry. Bone ancestry defines
Head (neck and facial bones), Torso, Arms (including hands), and Legs. Each face
belongs to the region with the greatest summed PSP weight at its three corners.

Blender's weighted collapse modifier preserves 80% of head faces, 50% of torso
faces and 35% of arm/leg faces. Shared boundary positions and the eye, teeth and
inner-mouth surfaces are protected. The pipeline evaluates each modifier before
applying it and enforces a minimum retained face count; integer rounding and
paired collapses can retain an extra face. Transferred bone groups are interpolated
through the modifier and packed into PSP palettes of at most eight bones.

The supplied HCTP RVD conversion retains:

| Region | Source faces | Exported faces | Retained |
| --- | ---: | ---: | ---: |
| Head | 899 | 721 | 80.2% |
| Torso | 415 | 209 | 50.4% |
| Arms | 1075 | 377 | 35.1% |
| Legs | 447 | 157 | 35.1% |

All 64 eye triangles, 16 tooth triangles and 33 inner-mouth triangles survive.
The final model has 1464 triangles, versus 830 in the preceding detail candidate,
and 1336 vertices in 38 palette chunks. Chunk bounding spheres are recalculated.
Area-weighted smooth normals are rebuilt across UV/region seams; inner facial
surfaces have separate smoothing groups. Those normals are written into the
native YOBJ and used by the Blender review rig.

The face remains 128x64 with 256 colors. The torso now uses a 64x64, 256-color
texture to reduce color banding. Other opaque textures retain their size budgets.
Cutout textures bypass resizing and quantization: decoded alpha and RGB remain
pixel-exact in `bn_ha`, `bn_ha2` and `rvd_eye`. Named hair/mask textures also use
this preservation path. Opaque hair in this sample retains its opaque alpha.
Ordinary body vertex alpha remains 255, the previously tested opacity correction.

## Storage and validation

The smaller PAC is **143360 bytes (140 KiB)**, including 2048-byte archive padding,
8 KiB below the preceding 148 KiB regional build. The regional size guard now
refuses exports above 144 KiB, leaving at least 4 KiB below the previous cap.
The geometry, weights, smooth normals, UVs, colors, material states and texture
payloads decode identically to the 148 KiB build. Disconnected triangle strips
are joined using repeated indices that create zero-area bridges, with winding
parity preserved. This reduces strip records from 491 to 63. Joined strips
respect the PSP GE's 65535-index draw-count limit. Palette packing limits duplicate vertex
storage. PSP GE U16 weights replace float weight storage, with four influences
per vertex and exactly normalized sums. Positions, normals and UVs remain floats.
Fixed-point weight decoding follows PPSSPP's
[Step_WeightsU16Skin and vertex-layout code](https://github.com/hrydgard/ppsspp/blob/master/GPU/Common/VertexDecoderCommon.cpp):
little-endian U16 weights divided by 32768, padded to four bytes before float UVs.
The largest weight rounding error is 0.0000217. Decimation interpolation and
four-influence/palette limits discard up to 10.1% of a vertex's weight mass after
the initial full-model transfer; both stages are reported separately.

Native serialization checks weights, coordinates, normals, colors, UVs, oriented
triangles, material depth and the original PSP bone table. The PAC contains the
exact `preview/prepared.yobj` bytes. Texture payloads match the named preview GIMs.
Three Blender poses have finite positions and zero separation at duplicate
seams. The 44 unit tests cover classification, seam normals, integer weight
alignment, normalized rounding, mask alpha, joined-strip winding/parity and
draw-count limits, and previous format/repacking checks.

This candidate needs an SVR 2011 PPSSPP test, particularly its U16 vertex format
and appearance during animation. The checks exercise file structure and a Blender
review rig; they do not execute the game's model loader or animation engine.

## Download and reproduce

[Download the smaller regional PAC and matching preview bundle](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-region-small-test-bundle.zip).
Inject `RVD-HCTP-to-PSP-region-small-test.pac` using the same working archive workflow.
`preview` contains the exact native model and named PNG/GIM textures. If an older
Noesis plugin only supports float weights, use `preview-float/prepared.yobj` or
the DAE. The float preview has identical decoded attributes and textures, but
different weight encoding and larger file size; it is for viewing.

```powershell
py -3.13 tools/convert_hctp.py "C:\models\0900.pac" "C:\models\Kurt-Angle-Ring.PAC" "C:\models\Full Body.yobj" --editor "C:\tools\yobj_mesh_editor_PSP_GUI.exe" --regions --blender "C:\tools\Blender 4.3\blender.exe" --output "local\rvd-regions"
```

The supplied HCTP source, SVR 2007 PSP Kurt base and reference YOBJ remain the
supported sample pair. Windows execution and other source-game profiles still
need development/testing. Outputs go to a new directory; originals are preserved.

PAC SHA-256:

```text
0ea14a9f0544db22dd0829d1700f2f52716b38c3bdb672a32830cc772c3a98be
```

# PSP material-state and texture-table correction

Update: the user now reports that the converted wrestler loads, enters, and
appears in a match without crashes in SVR 2011 PSP, but has see-through skin
and missing surfaces. The current [opacity-corrected candidate](opacity-correction.md)
keeps this build's structure and changes only native vertex alpha. The ARC
control test below is retained as prior investigation guidance, not a required
next step after successful loading.

The user reports that the compact 144 KiB RVD candidate still does not work.
Auditing the converter found that seven ordinary body/face materials inherited
the Kurt base's blood-overlay control word, `0x115`, instead of regular `0x5`
state. The affected textures are `bn_dou` and `bn_kao2`. The exporter selected
the first material of the nearest target mesh; eight meshes in the base are
blood-effect surfaces rather than ordinary body surfaces.

This is a concrete converter defect. It is not yet a confirmed explanation of
the game failure: PPSSPP execution is unavailable in this environment, and
Noesis geometry display does not validate game material state.

The exporter now chooses a complete regular base material matching the converted
GIM's color depth, preferring the target part when possible. In the supplied
Kurt sample, regular indexed4 textures use control `0x5`, regular indexed8 use
`0x7`, and the named `blood`/`blood_b` indexed4 effects use `0x115`. These are
observed profile conventions; the whole control word has not been decoded.
Unsupported templates fail explicitly. Repacking independently checks material
controls against color depths read from the actual GIM bytes rather than trusting
manifest metadata.

The main texture tables in both original PAC samples are sorted by name,
ignoring case, independently of their YOBJ texture arrays. Our table used model
index order. Repacking now follows the originals' table convention while keeping
each name paired with its image and preserving all model texture indices. The
game's texture lookup implementation is unavailable, so the effect of this
ordering difference on the failure is not confirmed.

The corrected compact YOBJ differs from the previous compact YOBJ in exactly
14 bytes: the seven control words change from `0x115` to `0x5`. All remaining
YOBJ bytes, all individual texture bytes, the DAE, section 8, and the PAC section
offsets/sizes are identical. The main texture table and its image payloads are
now ordered by name.
It remains 147456 bytes (144 KiB), with 45 mesh chunks, 1211 vertices, 877
triangles, 79 base bones, and 15 main textures. It does not add blood-overlay
gameplay support.

Checks completed:

- 35 unit tests pass, including regression checks for overlay-template selection,
  material/color-depth mismatches, and sorted texture names retaining the correct
  image payloads.
- A fresh complete compact conversion passes independent serialization and
  native GIM checks; the previous compact candidate fails the new material guard.
- All 795 decoded relocation fields and their pointer targets are within the
  native model, with no duplicate fields.
- The bundled preview YOBJ and every named GIM exactly match the PAC payloads.
  Pose review files are retained from the previous compact build because all
  geometry, bones, weights, UVs, and textures are byte-identical.

The supplied SVR 2007 PSP Kurt base remains the selected base for the user's
SVR 2011 PSP test. The user confirms PSP SVR PAC interchangeability; another
2011 base PAC is not required for this investigation. No Windows editor or
PPSSPP/ISO test was performed here.

Download [the corrected test bundle](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-material-fix-test-bundle.zip).
Use `RVD-HCTP-to-PSP-material-fix-test.pac` from that ZIP. Open
`preview/prepared.yobj` beside its named PNG/GIM textures in Noesis.

## Separate ARC/injection behavior from conversion

The user suspects the ARC update and has not tested the unconverted Kurt PAC
through the same workflow. The ZIP includes `control/Original-Kurt-Angle-Ring.PAC`,
byte-identical to the uploaded file, without conversion or repacking. It is
180224 bytes (176 KiB); it is a baseline, not the reduced RVD build.

Test that control from a clean game archive using the same slot and injection,
ARC update, and ISO save workflow. If it works, test the corrected RVD PAC from
another clean archive. If the control also fails, investigate the saved archive,
ARC, and injection path before drawing conclusions about the conversion.
That result alone would not prove that the ARC is wrong; different file size and
the selected base are also variables. No actual CH.PAC/ARC or PPSSPP log was
provided for inspection, so archive corruption has not been established.
The exact failure stage and PPSSPP error/log text would help narrow it down.

Corrected PAC SHA-256:

```text
4912f8b20fe8f57e14280ed948b6de7fadb3096d59da0dcedec04c81bc462087
```

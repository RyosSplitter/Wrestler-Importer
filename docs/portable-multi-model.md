# Independent HCTP accessory models → PSP model set

Evidence date: 2026-10-10. Isolated branch: `experiment/multi-yobj-accessories`.
This supersedes the main-only **output** limitation documented in
`portable-primary-model-fix.md`; its main-model reader remains valid.

## Downloaded Windows release verification

**CONFIRMED:** Release `portable-preview-13-62abe01676035e3559385bf3a80fdfbc2e8f8435`
was built from commit `62abe01676035e3559385bf3a80fdfbc2e8f8435`. Hosted Windows
CI passed 191 tests, frozen main/accessory conversions, and the independent
body geometry/bone/material regression comparison. The downloaded ZIP is
556,556,884 bytes, SHA-256
`b95834aecbce25c4ac170d2d6dab56bd734b4e7d0b50e51f323c72d506a2753c`.
All 7,084 manifest file hashes and archive paths were verified. Critical bundled
converter source files match the build commit; no PAC/YOBJ/GIM assets are bundled.
Machine-readable evidence is in `portable-multi-model-release.json`.
**UNKNOWN:** Gameplay behavior, including pad removal/throw events. The hosted
build is not a clean user Windows installation or PPSSPP gameplay test.

## What failed and what the supplied files show

**CONFIRMED — binary inspection:** `0000.pac` SHA-256
`d1d5ca744b5a793743851c142bf273554c81076ae3b8231834364559e048a973`
is 542,976 bytes. Its independent YOBJs are:

| Source section | Internal label | Meshes | Decoded UV/color-split vertices | Triangles | Bones | Texture array |
|---|---|---:|---:|---:|---:|---|
| 2 | `hogan` | 13 | 2308 | 3077 | 71 | 18 body/face names |
| 6 | `l_pat` | 1 | 71 | 64 | 15 | `pat` |
| 7 | `l_pat01` | 1 | 71 | 64 | 15 | `pat` |

**CONFIRMED:** File/model names do not identify roles reliably. Section 6's
positive weights are on `l_ninoude`, `l_ninoude_x`, `l_kote`, `l_kote_x`;
section 7's are on the corresponding right-arm bones. Their meshes surround
the left/right elbows. The costume table has 19 textures, including `pat`.

**CONFIRMED:** The uploaded `The Rock.pac` is 133,120 bytes, SHA-256
`7e452bb6290e69aecc0302222e4453c6391a33d659b6ac39b1821e8c28a53bba`.
It contains only sections 2, 8 and 9. There is one YOBJ (43 meshes, 2331
vertices, 2725 triangles, 79 bones), and only the 18 main texture names.
Both pad models and `pat` are missing.

**CONFIRMED — code trace:** The maintained readers' `select_model_section`
correctly selects the main wrestler. `HctpAdapter.read` and `read_source`
previously returned only that model's geometry and referenced textures.
`desktop.core.run_job` wrote replacements only for sections 2 and 9 into the
Kurt donor. Selecting section 2 fixed input acceptance but did not implement
accessory conversion. It was a documented limitation, not a compression error.

**CONFIRMED:** Native 2011 `Rock.PAC` is 153,600 bytes, SHA-256
`30825f27cc19cbb5e4339e4244aaf650c34b1a30183a8b7567d326c7aaffd165`.

| PSP section | Meaning observed in this reference | Decoded bytes | Meshes | Vertices | Triangles |
|---|---|---:|---:|---:|---:|
| 2 | `The Rock_1500` main YOBJ | 125656 | 28 | 1372 | 1725 |
| 26 | `L_elb` left pad YOBJ | 8776 | 1 | 23 | 26 |
| 27 | `R_elb` right pad YOBJ | 8776 | 1 | 23 | 26 |
| 8 | Other native data, preserved from selected donor | 7072 | — | — | — |
| 9 | Shared GIM table | 50992 | — | — | — |
| 100 | Nested PAC with two `JUDE` payloads | 139312 | — | — | — |

**CONFIRMED:** Native pads have the main rig's complete 83-name bone table
and identical local bind records. Each draw uses four float32 weight slots
(`0xd7ff`, base format `0x17ff`), stride 52, u16 strip indices, and material
control 5 referencing `ro_elb` (texture-array index 19). Stored palettes are
one-based. The left palette is 65,64,63,62; the right is 43,42,41,40.
Both independent native YOBJs declare the main 22-entry texture-name array;
duplicate blood names account for some array entries. Only `ro_elb` is drawn
by the pads. The shared archive table has 18 unique names.

**CONFIRMED:** Native main/pad local bone records match in bytes 0–63 and
76–79 of each 80-byte record. Bytes 64–75 differ: inactive pad bones contain
zero, and active arm bones have pad-specific values. This sparse pattern also
appears in the HCTP pads. **INFERRED:** These values are per-model global
geometry metadata; their exact game runtime interpretation is not established.

**UNKNOWN:** The nested `JUDE` section's exact relationship to pad removal,
throwing, events and animation. Do not transplant PS2 sections 100/101 (they
are texture tables in this source), nor copy the native Rock's animation data
into an unrelated donor. Actual pad event semantics require PPSSPP testing.

## Explicit supported contract

**CONFIRMED — implementation:** `desktop/accessories.py` enumerates the model
set separately from the existing main-model readers. Only the experimentally
observed mappings 6→26 and 7→27 are supported. They additionally require:

* Positive weight support only on the indicated side's four arm controllers,
  including the elbow controller; valid decoded nonempty geometry.
* Influencing bones and all ancestors match the main HCTP rig by name, parent
  name and local transforms within 0.00002 absolute float tolerance.
* Every influencing bone maps directly by name to the selected PSP rig, and a
  compatible regular float-weight arm draw template exists in that donor.

**INFERRED:** These section mappings generalize to other HCTP elbow-pad
costumes satisfying the same contracts. They are not a universal YOBJ mapping.
**CONFIRMED:** Unknown extra YOBJs, wrong-side rigs, duplicate IDs, malformed
models, unavailable textures and unmatched accessory models already in a PSP
donor are rejected. The implementation never silently discards them, guesses
roles from size/name, copies raw PS2 YOBJs, or bakes accessories into the body.
The native Rock supplied here is a structural reference; it lacks an ordinary
indexed8 material template and is still unsupported as this app's donor.
The conversion below uses the existing user-supplied SVR 2007 Kurt donor.

## Conversion and packaging

**CONFIRMED:** Main conversion retains its prior stages. All accessory positions
receive exactly the same recorded uniform scale/proper rotation/translation as
the main model; there is no second independent alignment. No accessory
decimation, nearest-donor weight transfer, influence pruning or geometry merge
occurs. UV/color records and all oriented source triangles survive native
serialization. Normals are normalized and stored as float32, as in the main
pipeline. Independent bone indices are remapped by controller name, with their
weights unchanged apart from the native float32 representation.

**CONFIRMED:** Each pad uses the chosen PSP main rig's local bind records.
Sparse stored-global fields are generated from the aligned source pad's active
bone values, with zero for unused bones. This preserves the observed sparse
pattern without inventing offsets or manual reshaping. **INFERRED:** This is
compatible with native per-model global semantics; analytical LBS does not
consume these metadata floats, so it cannot establish their runtime meaning.

**CONFIRMED:** The texture decoder resolves the union of model dependencies.
The main YOBJ and both pads declare the same 19-name array, matching the
shared-array pattern in the native Rock. `pat` is appended at index 18; pad
materials use that index. Existing body indices remain unchanged. The shared
PAC table contains 19 converted GIMs.
`pat` uses the existing texture policy: source 64×32 PSMT4 → 32×32 indexed4
GIM, 784 bytes. Source cutout RGBA follows the existing exact-alpha policy;
this particular pad texture is opaque. No additional resizing of body textures
was needed. All 18 body GIMs are byte-identical to a separate current-runtime
main-only texture conversion, confirming that accessory dependencies did not
alter body texture processing. Against the uploaded older app output, ten GIMs
are byte-identical, five have only palette/index changes with identical decoded
RGBA, and three have decoded pixel differences: `rc_hiza` 2/1024 pixels (maximum
channel delta 170), `rc_pan2` 1/1024 (46), `rock_eye_y` 20/512 (3). **UNKNOWN:**
The exact cause of those older-output quantization differences; host/library
or build differences are plausible but not proven. This is reported for review,
not described as a pixel-identical texture baseline. No texture-conversion
algorithm was changed by this feature.

**CONFIRMED:** `pac_repack.rewrite_sections` permits explicit noncolliding
additions. Existing IDs stay in order with exact unrelated payloads; additions
are appended by ID. The original replacement-only API still rejects missing
replacement IDs. The writer performs no role inference.

| Outer PAC field | Offset / size | Encoding and meaning |
|---|---|---|
| Magic | 0 / 4 | `PAC ` |
| Count | 4 / 4 | u32 LE |
| Entry ID | 8+8i / 2 | u16 LE |
| Entry offset | 10+8i / 3 | u24 LE, relative to end of entry table |
| Stored size | 13+8i / 3 | u24 LE |
| Section payload | computed / stored size | BPE-wrapped YOBJ/GIM table as applicable |

**CONFIRMED:** Section file addresses are 16-aligned; complete output is
2048-aligned. Native YOBJ pointers use byte-8 origin, vertex/index allocations
align to that origin by 16, and POF0 relocation/pointer sets are independently
audited. The complete model set contributes to the existing 148000-byte
budget; accessories are never dropped to force a fit. Source and accepted PACs
remain untouched. See the format manual for complete YOBJ/texture structures.

## Validation and reproduction

**CONFIRMED:** Native auditing now visits every YOBJ, checking ranges, allocations,
offsets, palettes, weights, indices, relocation sets, alignment and material/GIM
bit depth. The shared table must match the union of declared model texture
names. Expected accessory roles, independent attributes, oriented triangles,
and all local bind bytes are checked. Eighteen analytical poses per pad include
standing, walking, bending, crouching, shoulders and elbow flexes. These prove
serialization/replay consistency, not real game animation behavior.

**CONFIRMED:** The combined `preview/output.obj` contains the body and both pads;
it remaps texture IDs for viewing only. Independent `section-26/27.yobj` and
`.obj` files are also provided. The three preview YOBJ payloads are extracted
and compared exactly against the corresponding final PAC payloads. Textured
PNG views are offline CPU renders, not Noesis screenshots or PSP GPU captures.

**CONFIRMED:** The new uploaded-source trial is 143360 bytes, SHA-256
`ae56c7e0f18f230a865790a5f7bb18796003c354c65fa1f1be744e1c4581a16e`.
It has three YOBJs, 45 meshes, 2473 vertex records, 2853 triangles and 19
unique textures. Each pad retains 71 vertices and 64 triangles. Section 8 is
unchanged from the selected Kurt donor. Every main vertex-buffer byte, mesh
header, bone-table byte, material and strip record matches the uploaded
`The Rock.pac`. The main YOBJ's texture-name metadata gains the `pat` entry;
its descriptor address, declared sizes and relocation placement are rebuilt
accordingly. Its geometry, UVs, weights, normals and body material indices do
not change.

**CONFIRMED:** Tests in `tests/test_portable_accessories.py` generate independent
synthetic models and cover role/texture closure, wrong-side/unknown/duplicate
roles, bind differences, exact attributes and pose replay, missing textures,
corrupt accessory indices, exact unrelated data, preview remapping and explicit
section addition contracts. `tools.portable_fixture.create_with_accessories`
generates independent left/right quads for frozen Windows end-to-end CI.
No uploaded game assets are added to the application runtime.

To reproduce with Python 3.13 and the existing Blender runtime:

```python
from pathlib import Path
from desktop.core import Request, run_job
run_job(Request('0000.pac', 'Kurt-Angle-Ring.PAC'), Path('new-job'))
```

Inspect `model-set-input.json`, `accessory-qa.json`, `size-fit.json`, the main
`qa/report.html`, combined previews and `result.json`. Run `python -m tools.ci_tests`.
The main QA's five existing review findings remain; no main geometry change is
hidden by alignment or tolerances. **UNKNOWN:** In-game pad events, actual game
skinning behavior and runtime memory safety until SVR 2011 testing. Test normal
entrance, gameplay, victory, elbow flexes and the People's Elbow pad removal/
throw with a backed-up ISO and the user's working rebuild/ARC-update workflow.

## Shared texture namespace refinement

**CONFIRMED:** The first trial used a separate one-name pad texture array and
material index 0. Before gameplay acceptance, comparison of the native Rock's
three YOBJs showed that the pad model and body share identical name arrays and
indices. The final candidate mirrors that arrangement. The first candidate's
SHA-256 was aadc99d153735cdb9ee4fbbecac4c1250cdd12666d0046cc0de03902499e044c;
it remains in Git history as an unaccepted experiment, not a validated baseline.
**INFERRED:** Matching the reference avoids reliance on undocumented per-pad
texture-pool behavior. **UNKNOWN:** Whether the previous local-array variant
would have bound its texture correctly in-game; it was not tested.

**CONFIRMED:** The provided SVR 2008 Sgt-Slaughter(Hat).PAC has a main section-2
YOBJ with 16 texture-name entries, a section-9 texture table with 11 unique
names, a hat section-32 YOBJ with 5 entries and a separate section-39 texture
table with its 4 unique names. That is a different namespace/section contract
from the Rock pads, which share section 9. Do not generalize elbow-pad mapping
or shared-array validation to hats without a separate profile.

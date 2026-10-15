# PSP Model Creator 0.1 — standalone experimental application

This is a separate prepared-pair prototype for the supplied **Kenny Dykstra** and
**Brian Kendrick** native PSP models. It does not modify or replace the converter,
the PSP Model Suite, or their accepted outputs. It is not yet a universal creator
or a library of thirty interchangeable bodies.

## Windows use

1. Extract the complete portable ZIP and run `PSP-Model-Creator.exe` inside it.
   Keep `_internal` beside the executable. Python, Blender and Noesis do not need
   to be installed separately.
2. **New project**: select your original `Kenny-Dykstra.PAC` as source 1 and
   `Brian-Kenderick(Ring).PAC` as source 2. Choose a parent directory. The app
   creates a new private project with immutable SHA-256-pinned input snapshots.
3. Choose **Head, Torso, Arms and Legs** independently. The whole assembled
   selection previews automatically after a short debounce, before PAC building.
   Change camera, pose, or **Green body preview** to examine it with or without
   textures. Uncheck Green to see the original textures. Previewing an oversized
   combination is permitted; previewing is not export approval.
4. **Assemble and validate** makes a separate build directory. The actual native
   PAC is read back before export. **Save choices** retains previous recipes in
   project history. Changing choices cannot export an older validated PAC.
5. **Save PAC as** creates a new file. **Export preview folder** exports the PAC,
   native YOBJ, OBJ/MTL, texture PNGs, five matching renders, checksums and QA JSON.
   OBJ is a rest-geometry preview, not a rig-preserving interchange format.
6. **Export editable textures** creates a self-contained folder. Edit its named
   PNGs in Photoshop/GIMP without changing dimensions, alpha capacity, OBJ, UVs,
   material files or raw native files. **Pack edited folder** imports those PNG
   changes into a new PAC, enforcing the existing native texture contracts and
   actual file budget. Palette quantization and failures are reported.
7. Use your established injection workflow on a **copy** of the game archive/ISO.
   Inject the new wrestler PAC into the intended slot, rebuild/update its enclosing
   PAC/ARC metadata as required by your tool, then test the copied ISO in PPSSPP.
   Check standing, entrance, walking, grappling, crouching, victory, facial motion,
   eyes, blood and multiple matches before accepting a result.

The app does not inject an ISO or update its ARC for you. Input PACs and previous
builds are not overwritten. Failed jobs report the full traceback path in the
error dialog; it is `psp-model-creator-last-error.txt` in the Windows temp folder.
Save `qa.json` with any reported defect. Builds and their preview folders remain
in the private project's `builds` directory.

## Evidence and scope

Technical findings use **CONFIRMED**, **INFERRED**, and **UNKNOWN** to distinguish
measured behavior from interpretation. Confirmation here identifies its test
scope; it does not claim game-runtime validation.

**CONFIRMED — supplied binary analysis:**

| Input | PAC bytes | Main-model vertices / triangles | Meshes | Named bones |
|---|---:|---:|---:|---:|
| Kenny Dykstra | 108,544 | 1,394 / 1,771 | 24 | 83 |
| Brian Kendrick | 135,168 | 1,343 / 1,746 | 21 | 83 |

Both main models use the observed float32-weight PSP vertex layout. Their named
bone sets and parent hierarchies match; the stored **bone order differs**.
Body local bind transforms match within the recorded numerical tolerance. Their
`atama` facial subtrees contain 26 bones and have different local bind positions.
Copying numerical bone IDs or using one complete donor facial rig for both heads
would therefore be unsafe. These facts are checked at import, not inferred from
the filenames.

**CONFIRMED — container inspection:** Kenny contains sections 2, 8 and 9. Brian
also contains section 100, whose decoded payload begins with `PAC `.
**UNKNOWN:** the complete runtime role of Brian's nested section 100. Mixed
assemblies use **source 1's container** and copy its non-model/non-texture payloads
byte exactly. They assemble the main model, not the second source's auxiliary
PACs. Complete original inputs remain in the private project. Choosing all four
parts from the same source returns that source's original PAC byte exactly,
including its auxiliary sections and existing section alignment.

**CONFIRMED — creator implementation and readback tests:**

- No geometry decimation, texture resizing, palette reduction or automatic
  re-rigging is performed. Source PNG appearance is retained through byte-exact
  GIM copying. Texture-name collisions are resolved deterministically and material
  texture indices are remapped; native material state stays attached to its source.
- Mixed models use the torso's bone order, mapped by name. Selected head records
  provide the complete native facial bind subtree. Parents are remapped by name;
  body/limb bind records come from the selected region's native rig.
- Four explicit planes in native coordinates prepare this pair: neck Y=-6.8,
  waist Y=-1.3, upper arms X=±3.15. These are **prepared-pair parameters**, not
  claimed anatomical constants for all wrestlers. Native negative Y points up.
- Source triangles are clipped to selected regions. New intersections interpolate
  UVs, color, normals and named-bone weights. Distinct source records retain an
  identity signature; position-only welding and weight averaging are not used.
- Only joints joining different sources are stitched. The torso provides the
  reference cross-section. A union of angular samples splits both attachment
  chains to reduce mismatched edge chords. Shared attachment positions and named
  weights match; texture coordinates remain local to each part.
- All original interior vertex positions, normals, UVs, colors and nonzero named
  weights are independently checked against their source records. Interpolated
  records are separately serialized and read back. Oriented triangle multisets
  are checked against the pre-serialization assembly.
- Original palette entries are retained where the eight-slot capacity permits.
  The existing exact single-slot compatibility adapter pads any remaining
  one-slot float-weight draw to three slots with **zero additional weights**.
- Adjacent splits from the same original source buffer can be losslessly rejoined
  only through the existing conservative merge planner/verifier. Material order,
  unknown rendering metadata, UVs, effective weights and winding are checked.
  There is no arbitrary target mesh count.
- Hair remains with its head, including cutout textures. Blood/effect decorations
  are retained in the PAC. Ordinary previews and the preview OBJ hide blood
  overlays so they do not look permanently activated. Native YOBJ retains them.

**INFERRED — attachment handling:** some neck-cut records lie inside the selected
outer radial contour, consistent with overlapping/internal source triangles.
The prototype does **not** prove that every such record is hidden or invalid.
Projection is restricted to a local 0.45-native-unit corridor; other cut records
are retained and explicitly listed as ambiguous in `review_findings`.
The upper displacement guard is a prototype bound, not an established universal
visual tolerance. These findings require side/rear/neck visual inspection.

**UNKNOWN:** completeness of the prepared contour for every pose, every visual
seam in-game, undocumented facial controller semantics and game heap/culling
behavior. The prototype must not present a finite pose or coincident endpoint
test as proof of a watertight or game-compatible surface.

## Native format behavior reused

Read the existing `docs/hctp-psp` documents and `REIMPLEMENTATION_GUIDE.txt` for
the broader PAC/YOBJ/GIM layout. The creator reuses their audited implementations.

| Record | Relevant offsets / interpretation | Evidence |
|---|---|---|
| YOBJ pointer origin | Offsets relative to byte 8, little endian | CONFIRMED by existing native reader/writer tests |
| Native bone | 80 bytes; name 0..15; local XYZW at 16; rotation XYZ at 32; signed parent at 48 | CONFIRMED by native decode/hierarchy and posed comparisons |
| Bone record at 64 | Four floats consistent with culling center XYZ / radius | INFERRED; conservative union retained, never treated as another bone ID |
| Native mesh | 64-byte header, palette, float-weight interleaved vertices | CONFIRMED by strict native audits |
| Material | 144 bytes, texture uint16 at 22, control uint32 at 24; strip records at 132..143 | CONFIRMED by existing audits and creator roundtrip |
| Primitive | uint16 indices, checked per buffer; preserved oriented triangle strips | CONFIRMED by independent triangle readback |
| Header word 60 | Both supplied main YOBJs relocate a zero-valued word, aliasing byte 8 | CONFIRMED by these two files; nonzero values are rejected |
| Texture | Native indexed4/indexed8, RGBA CLUT, existing swizzled layout | CONFIRMED by decode/byte copying; no new GIM format is introduced |
| Mixed PAC | Existing repacker: section starts aligned to 16 and final file to 2048 | CONFIRMED by rebuilt bytes; native unchanged originals can use other section spacing |

The original general-purpose writer deliberately rejects an unknown header-60
relocation. The creator removes this one verified zero alias only from the
temporary writer input and restores it explicitly in the output POF0. It does
not weaken the converter writer's policy or accept a guessed nonzero pointer.

The fields interpreted as mesh spheres are recomputed to enclose the assembled
buffer. Bone center/radius records conservatively enclose both source records.
**UNKNOWN:** whether this inferred union alone establishes all game-side culling
behavior. It requires PPSSPP testing; local bind transforms are kept separately.

## QA and actual pair study

The configured **148,000-byte** export cap is enforced on the serialized PAC;
2048-byte file alignment makes 147,456 the largest compliant aligned file.
This is the project's validated conversion target, not a generic PSP hardware
maximum. Original and combined decoded GIM/pixel/CLUT allocation is reported.
**UNKNOWN:** the game's full runtime-memory envelope for every mixed assembly.
No texture or geometry is silently reduced to force a fit.

`qa.json` contains source SHA-256 hashes, exact choices, output hash/bytes,
source-part/material provenance, every attachment change, ambiguous neck records,
lossless merge groups, byte/pointer/index/weight/palette audits, texture allocation
and pose comparisons. The native YOBJ placed beside the OBJ is compared byte for
byte with section 2 decompressed from the final PAC.

Ten analytical probes cover rest, standing, walk, bend, crouch, shoulders, neck,
jaw, eyes and eyelids. They check finite motion, common attachment displacement,
and untouched source-record motion against the corresponding original native
rig. A 0.03-native-unit interior pose guard is explicitly a prototype guard;
the actual measured deltas are reported. These are analytical LBS probes, **not
captured SVR animation clips**. Native controller semantics remain unconfirmed.

The private study is reproducible with:

```sh
python -m tools.creator_pair_trial --first Kenny-Dykstra.PAC --second "Brian-Kenderick(Ring).PAC" --output NEW_STUDY_FOLDER
```

It tries all sixteen combinations, saves five rest views and four posed views
for each exported candidate, creates a contact sheet and records withheld exports.
Only geometry-free numerical evidence is committed as
`docs/creator-pair-results.json`; private PACs, textures and source-derived renders
are not bundled in the app or committed.

The code in that results file uses Head/Torso/Arms/Legs order: **0 = Kenny,
1 = Brian**. Fifteen combinations fit with native textures. `0100` (Brian torso
with Kenny head/arms/legs) is withheld at **149,504 bytes**. It can still be
previewed. This is an explicit initial limitation, not a successful export.

## Development, tests and distribution

```sh
python -m pip install -r requirements-desktop.txt
python -m unittest tests.test_model_creator -v
python psp_model_creator.py
python psp_model_creator.py --smoke-test PATH_TO_NEW_REPORT.json
# Windows x64 only:
python -m tools.build_creator
```

The self-check uses entirely original block-humanoid fixtures generated by
`model_creator/fixtures.py`. It checks live selection previews before export,
actual Tk controls, background assembly, native export, posed views and a
byte-exact editable-texture-folder roundtrip. The creator tests additionally
cover tampered/moved snapshots, duplicate destinations, hierarchy/bind mismatch,
source interior attributes, facial parent mapping, palette capacity, UV/weight
interpolation, seam samples, invalid selections and actual budget enforcement.
The full repository suite had **402 passing tests** during development.

The isolated `windows-creator.yml` workflow builds with Python 3.13/PyInstaller
and runs the frozen self-check with the development Python directory removed
from PATH. This establishes hosted Windows-runner behavior, **not** a clean
personal Windows installation or PPSSPP runtime success.

The portable includes dependency notices/licenses, Python/Tcl/Tk notices,
application source and original synthetic tests. It bundles no Blender, Noesis,
third-party modding executables, user PACs or game-derived templates. Existing
NumPy/SciPy/Trimesh/Rtree dependencies support reused analysis/preview code.
It does not rewrite the Blender-based production conversion pipeline.

Future work: remove remaining ambiguous neck joins through explicit topology
profiles, validate the pair in-game, offer opt-in texture budget fitting for the
one withheld combination, generalize verified attachment profiles, then integrate
the proven creator module into the suite. None of those steps should be reported
as already complete by this first standalone preview.

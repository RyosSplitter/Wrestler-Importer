# PSP Model Creator 0.2 — prepared native library

The Windows app includes the 31 native PSP PACs supplied in `Models for Codex.zip`,
plus their prepared catalog and front/rear preview images. They are immediately
available in the Head, Torso, Arms and Legs selectors. No initial PAC import,
Blender, Noesis or separate Python installation is required. Content rights remain
with the respective owners; the supplied model library is included at the
repository owner's explicit request. It is model content, not just a list of names.

## Use

1. Extract the **complete** Windows ZIP. Run `PSP-Model-Creator.exe`. Keep both
   `_internal` and `creator_library` beside the executable.
2. The prepared library opens automatically. Pick a donor for each part. The
   preview updates before export. Use the dropdown arrow and scroll or type a
   donor's initial letters to navigate the list. **Preview whole head donor**
   selects that donor for all four parts. **Selection details** shows native
   vertex/triangle/mesh/bone counts, original PAC sizes and input hashes.
3. Examine textured and green previews, all five camera views and ten analytical
   poses. **Assemble and validate** creates an independent job and a native PAC
   only when its checks pass. **Save PAC as** saves a new file. A rejected or
   oversized mix does not overwrite the last build or any source.
4. **Save choices** snapshots the selected originals and recipe into a new folder.
   **Open project** restores that independent project even if the library moved.
   The original two-source **New project** workflow remains available separately.
5. **Export preview folder** includes the native YOBJ, OBJ/MTL, texture PNGs,
   five renders, QA report and checksum. OBJ is for preview, not rig-preserving
   reimport. **Export editable textures** creates a PNG-editable folder for
   Photoshop/GIMP. Keep original texture dimensions and native model files;
   **Pack edited folder** imports supported PNG changes into a new PAC.
6. Use your established PAC/ARC injection workflow on a copied ISO. Update/rebuild
   the enclosing archive metadata and test in SVR 2011 PSP/PPSSPP. Check entrances,
   standing, movement, crouching, grapples, facial motion, eyes, blood and victory.

Library jobs live under `%LOCALAPPDATA%\PSP Model Creator\jobs`. Each job has
immutable source snapshots, `project.json`, and, after successful validation, a
`build` directory containing PAC, preview and QA files. Full error diagnostics
are in `%TEMP%\psp-model-creator-last-error.txt`.

## What changed and why

- **CONFIRMED:** Every library original is copied byte-for-byte and SHA-256 pinned
  in `creator_library/catalog.json`. Catalog entries include native geometry counts,
  bone counts, descriptor groups and original file size. Preparation happens at
  build time with `model_creator.library.prepare`; users do not need to import
  their collection before using it.
- **CONFIRMED:** Six supplied YOBJs use two named 32-byte descriptor records.
  Header word 52 counts records; pointer 48 is relative to byte 8; each record's
  word 24 counts its contiguous meshes. The creator adapter verifies array bounds,
  count sums, no overlap with other allocations and the observed record pattern
  `[1,0,mesh_count,0]`, then uses the existing native auditor for the other buffers.
  Mixed output preserves the selected head's separate hair group. It does not
  flatten that group or merge buffers across descriptor boundaries.
- **INFERRED:** Unreferenced, dword-sized FF runs of at most 20 bytes immediately
  before native palette/material/vertex-pointer allocations are allocation fill.
  Previously the pair-only importer accepted at most 16 bytes. The creator checks
  pointer targets and ownership before accepting them; arbitrary nonzero data is
  still rejected. Rewritten layouts use zero fill.
- **CONFIRMED:** Whole-model selections retain the original YOBJ, GIMs and PAC
  bytes. Mixed builds do not decimate, optimize textures, reshape interiors or
  average incompatible source skinning records. Only planar cut intersections,
  attachment contour vertices and necessary edge splits are changed.
- **CONFIRMED:** Multi-donor assembly maps native bone palettes by verified names.
  Common body binds must match within 1e-5. The selected head supplies its native
  facial subtree. Extra controllers are selected by actual influence on chosen
  geometry, not assumed to be hair because of their names. Conflicting required
  extra binds are rejected. Each untouched interior record is checked against its
  original geometry, attributes and named nonzero weights and compared under ten
  analytical poses; the existing 0.03-native-unit pose tolerance is retained.
- **CONFIRMED:** The torso donor supplies the mixed output container. Non-model,
  non-texture stored sections of that donor remain byte-exact. The final PAC is
  decompressed and its native YOBJ compared to the preview YOBJ. Native indices,
  buffers, offsets, relocations, palettes, weight sums and alignment are audited.
- **CONFIRMED:** Texture-edit export/pack can explicitly opt into this same
  array-aware reader. Its default reader and the production converter are unchanged.
- **UNKNOWN:** Native descriptor semantics beyond the observed contiguous grouping,
  all game facial-controller semantics and the safe runtime heap ceiling for an
  arbitrary new assembly. Structural checks and synthetic poses do not prove
  compatibility with every real game animation.

## Guarded combinations and limits

All 31 originals can be previewed. The current mixed-export envelope remains
**148,000 bytes**, measured after real PAC serialization; nine larger native
originals are available for preview, not silently certified for this export target.
No geometry or texture reduction is applied to force a creator mix to fit.

28 supplied rigs share the tested common body bind. Jeff Hardy and Matt Hardy have
an offset neck bind; JBL Suit has different leg/foot binds. Whole-model preview
works, but mixes with incompatible body binds are withheld. This release does not
retarget them or claim all 31^4 combinations are interchangeable.

The current attachment algorithm retains the first creator's planar cuts at neck
Y=-6.8, waist Y=-1.3 and arms X=+/-3.15. The torso supplies shared contours.
Internal or ambiguous intersections outside the existing 0.45-unit outer contour
corridor remain untouched and are listed in `qa.json`; they require visual review.
Clothing, unusual body shapes and mixed hairstyles can expose these limitations.
The native/pose checks do not certify those retained internal intersections as
invisible. This remains an experimental creator.

Only the main model and its selected-head descriptor groups are assembled.
Auxiliary nested PACs from non-torso donors are preserved in project snapshots,
but are **not** transferred into the new container. Torso auxiliary sections stay
unchanged and may need game-specific review. Their memory is not free budget.

Accepted converter/suite outputs and the previous creator release are preserved.
The opt-in library path is separate from the legacy prepared Kenny/Brian path.

## Reproduce validation

```sh
python -m unittest tests.test_model_creator tests.test_creator_library -v
python -m tools.creator_library_check --output NEW_REPORT_FOLDER
python psp_model_creator.py --smoke-test NEW_REPORT_FOLDER/smoke.json
```

The library check covers all 31 originals, all 465 pair body-bind comparisons,
each of four donor parts against Batista (124 trials), and eight serialized PAC
recipes covering all six multi-descriptor heads, additional weighted controllers
and a four-donor assembly. It records withheld combinations and oversized PACs,
rather than weakening checks to make them pass. It is not exhaustive four-way
coverage or an in-game test. See `docs/creator-library-validation-02.json` for the
actual results when available.

The frozen Windows self-check additionally opens the packaged library, loads all
31 native models, previews a Christian/CM Punk selection without an import,
builds its PAC with two descriptors and roundtrips its editable textures exactly.
It retains the original synthetic pair checks, stale-selection export guard and
on-screen export-button checks. CI checks a hosted Windows runner; a clean user
machine and real PPSSPP tests remain separate validation steps.

## Recorded development results

- 31/31 originals loaded, audited and posed; source hashes remained unchanged.
- 379/465 pair body-bind comparisons matched. This is a body-bind precheck, not
  approval of every attachment or facial combination.
- 108/124 single-part trials against Batista passed native and ten-pose checks.
  Twelve were withheld for the known Hardy/JBL bind differences; three torso
  mixes exceeded the existing jaw-pose tolerance; Cena's neck contour was not
  star-shaped under the current seam algorithm. No tolerance was loosened.
- Six of eight actual PAC recipes fit and passed readback/native/pose checks.
  Joey Mercury head/Batista body was 149,504 bytes and the four-donor recipe
  was 161,792, so both were withheld. Original textures and geometry were not
  reduced to force them into 148,000 bytes.
- The GUI Christian-body/CM-Punk-head experiment produced a 129,024-byte PAC,
  retained both descriptor groups, and its unedited texture project roundtripped
  to exactly the same PAC bytes.
- 410 automated repository tests passed. Hosted Linux GUI checks at 1280x900 and
  1024x768 and the frozen Windows runner results are recorded separately; none
  substitute for gameplay validation of newly mixed models.

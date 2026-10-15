# Model Editor: export → edit PNGs → pack a PAC

## User workflow

1. Choose your PAC library folder in **PSP Model Editor** and select a PAC.
2. Click **Export folder...** and choose a parent directory. The app creates a
   new `<PAC-name>-edit` directory, adding a numbered suffix when needed.
3. Open the named PNGs under `textures/` in Photoshop, GIMP or another image
   editor. Save as PNG with the same filenames and dimensions. `textures.csv`
   identifies the native names, palette capacities and read-only resources.
4. Click **Pack folder...**, select the exported directory containing
   `project.json`, then choose a new `.pac` filename. The destination defaults
   to the PAC library. Existing files cannot be overwritten.
5. The output appears in the library and is loaded in the preview. Inspect its
   appearance and test in PPSSPP. A `.pac.report.json` beside the output records
   changes and any palette quantization. **Quality Assurance → Last packing
   report** opens the latest report.

The folder is self-contained; the external source PAC is not needed after
export. PSD/XCF working files can live beside the PNGs, but only the listed PNGs
are imported. ZIP preview export remains a developer API, not the primary editor
workflow. This feature adds actual texture editing/rebuilding, not geometry editing.

## Folder contract

**CONFIRMED implementation and tests:** `desktop/edit_folder.py` implements
`psp-model-suite.edit-folder/1`, independent of conversion algorithms.

| Item | Role |
|---|---|
| `project.json` | Version, original checksum/filename and documented budget policy |
| `original.pac` | Authoritative snapshot; SHA-256 checked before rebuilding |
| `manifest.json`, `textures.csv` | Reference inventory and friendly texture mapping |
| `textures/NNNN-native_name.png` | External texture edit input; deterministic sanitized filenames |
| `textures/texture_NNNN.bin` | Original encoded texture reference; must remain unchanged |
| `models/model_NNNN/model.yobj` | Original decoded native model; never rebuilt from OBJ |
| `models/model_NNNN/model.obj`, `preview.mtl` | Preview geometry/UV/material references; edits are rejected |
| Model audit JSON and five view PNGs | Reference diagnostics, not import inputs |

**CONFIRMED:** The packer regenerates its inventory from `original.pac`. It does
not trust JSON-supplied offsets, counts, palette capacities, mappings or an edited
budget field. It compares YOBJ, OBJ and MTL against this independently regenerated
reference. Line-ending differences in MTL are allowed; semantic edits and additional
OBJ/YOBJ/MTL files are rejected. Missing inputs, changed raw GIM bytes, a changed
snapshot, unsupported native geometry or symlinks stop packing. No geometry edits
are silently ignored. Unknown source sections stay preserved verbatim.

## Texture encoding and preservation

**CONFIRMED implementation/tests:** Newly edited images retain the native texture's
dimensions, 4-/8-bit index depth, 16-/256-entry RGBA CLUT capacity, headers, swizzling,
row padding and serialized allocation. Existing verified narrow/padded layouts
are patched in place rather than requiring a newly whitelisted dimension/format.
There is no resizing, material-depth conversion, geometric simplification or
adaptive reallocation in this editor path.

Unchanged decoded PNG pixels reuse their original encoded GIM bytes. Saving the
same pixels with different PNG compression/metadata does not re-encode the native
texture. If every texture is unchanged, the original PAC is emitted byte for byte,
including its compression, padding, unclassified data and existing conventions.

For an edited image with no more RGBA colors than its palette capacity, mapping
is exact. Otherwise three deterministic Pillow RGB quantizers are compared using
alpha-weighted squared RGB error. Quantization is separated into exact alpha-level
groups; output alpha must equal every input alpha sample. Too many alpha levels
for the native palette produces a clear rejection, rather than thresholding or
averaging away transparency. The report gives the quantizer and RGB RMSE so loss
is visible. Manual art still must fit the original PSP color capacity.

**CONFIRMED scope:** Main costume section 9 is editable, except named `blood`,
`blood_b` and `bandage` resources. Non-main texture tables and unsupported textures
are read-only. Blood/effect palette stages have controller relationships that must
not be destroyed by generic reindexing. This does not claim every undocumented
controller convention has been identified.

## PAC construction and constraints

**CONFIRMED implementation/tests:** Texture tables are patched at existing entry
allocations, preserving original entry order, names, offsets, headers, extension
fields and padding. A changed table retains its original uncompressed/compressed
storage class. Compressed tables use the existing BPE implementation and its
already-used 200/220 symbol settings; decompression must equal the intended table.
The unchanged `replace_sections` writer updates PAC offsets and alignment.

Every original model and unrelated stored section must have the exact original
stored checksum and decoded bytes. All models are audited using the native reader
before use; final model bytes remain identical. Index ranges, bone palettes,
weights, skeletons, UVs, material/render records and auxiliary model payloads are
therefore preserved, not reserialized. Changed-table decoding, section order,
container bounds, 16-byte section starts and 2048-byte final alignment are checked.
Nonzero unclassified gap/trailer bytes block a changed repack instead of being
discarded. No-edit exact copies retain the original file's conventions.

**CONFIRMED budget policy:** Converted models use the existing 148000-byte
envelope. A larger existing native PAC may retain up to its original file size;
the editor does not shrink an accepted native file to the converter's budget.
In all cases encoded GIM sizes and decoded texture allocation cannot increase.
The final serialized PAC is measured; an oversized output is withheld, with no
automatic reduction of resolution, geometry or other textures. This policy is
not a universal SVR engine limit.

PNG bytes are snapshotted and checked again before publishing, so a concurrent
image save stops packing. Output is staged and fsynced in its destination directory,
checksum verified, then published without replacing an existing file (exclusive
Windows rename / POSIX link). Closing the app cannot expose a partially written
named PAC. An interrupted job can leave a hidden temporary file or an orphan
report; original PACs and edit inputs remain unchanged.

**INFERRED:** Keeping exact model bytes and identical texture allocation should
avoid geometry/skinning and allocation regressions from editing. **UNKNOWN:**
Gameplay behavior of arbitrary new art, undocumented palette controllers and
format variants outside the verified reader. Native structural success is not
gameplay acceptance; new edited PACs require PPSSPP testing.

## Reproduction and evidence

```sh
python -m unittest tests.test_edit_folder -v
python ps2psp_converter.py --suite-smoke-test local/edit-folder-smoke.json
```

**CONFIRMED local tests:** exact portable no-edit round trips; changed compressed
texture tables with three models and opaque data; T4/T8, rectangular and padded
images; fixed palette capacity and exact alpha; insufficient alpha capacity;
size, model, material, raw-texture and snapshot edit rejection; protected blood
resources; concurrent PNG saves; actual final-size enforcement; and existing-file
protection. The GUI smoke performs real folder export, an unedited frozen-worker
pack, a PNG edit, another worker pack, library refresh and output preview.

Private native/converted samples for Kurt, Benoit, Lance, Jericho and Rock also
passed exact unedited round trips and controlled one-texture edits. Rock retained
all three model sections. These are preservation/encoding experiments, not new
in-game acceptance. The public evidence in `downloads/model-suite-edit-folders/`
contains metrics and generated-fixture GUI captures, not game PACs/textures.

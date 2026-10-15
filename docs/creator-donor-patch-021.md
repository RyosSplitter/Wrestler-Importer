# PSP Model Creator 0.2.1 — add-donors drop-in patch

## Install over 0.2

1. Close PSP Model Creator.
2. Keep a backup copy of your current `PSP-Model-Creator.exe`.
3. Extract the patch ZIP **into the existing app directory**, beside `_internal`
   and `creator_library`. Replace `PSP-Model-Creator.exe` when prompted.
4. Run the app and click **Add donors…**. Select one or several native PSP PACs.
   Added donors appear in all four selectors. No Python, Blender, reinstall or
   future app rebuild is needed to add more donors.

Keep your existing `_internal` runtime and `creator_library` folder. This patch
contains no replacement catalog or bundled donor PACs, so it does not reset the
31 prepared models or your added donors. It is for Windows x64 Creator **0.2**,
not the separate PS2 converter. It does not add support for new binary formats.
The old executable can still read the extended catalog if you roll back.

## Import behavior

- The original PAC is read and strictly checked by the current creator's native
  reader: model descriptors, allocations, relocations, vertex/index buffers,
  palettes, weights, float skin layout and GIM texture references must be supported.
  PS2 PACs and unrecognized/damaged layouts are rejected with an explanation.
- A valid donor is copied byte-for-byte into `creator_library/pacs` under its
  SHA-256 identity. Front/rear previews and model statistics are generated locally.
  Your source PAC is never edited; its original location is not needed afterward.
- Duplicate contents are skipped, even under a different filename. Different PACs
  with the same filename retain separate stored identities and numbered selectors.
- Valid files in a mixed batch are added; invalid files are individually reported.
  The import summary includes counts for added, existing and rejected donors.
- A catalog backup is made in `creator_library/backups` before each successful
  batch. The catalog is atomically replaced after the new objects are written.
  An OS-owned lock prevents concurrent imports from losing another batch's updates;
  the lock is released automatically if the process exits. A failed catalog commit
  leaves the previous catalog and existing donor PACs intact.
- The existing model order and source hashes remain unchanged. Current part
  selections are preserved on library refresh. Nothing is uploaded automatically.
- Import diagnostics are in `%TEMP%\psp-model-creator-donor-import.json`.
  The app folder must be writable; extract the portable app into your own folder
  if it is installed in a protected location such as Program Files.

Registration is not a compatibility certificate. Larger original native PACs may
be previewed, but mixed exports still enforce the **148,000-byte** budget and
existing body-bind, seam, controller, source-attribute and analytical-pose checks.
Donors with incompatible rigs can be registered and inspected while unsafe mixes
are withheld. No geometry or textures are reduced or retargeted during import.
New assemblies still require in-game PPSSPP testing.

## Reproduce tests

```sh
python -m unittest tests.test_creator_donor_import tests.test_creator_library tests.test_model_creator -v
python psp_model_creator.py --smoke-test NEW_FOLDER/report.json
```

The Windows patch test overlays only the new executable onto the **released 0.2
ZIP**, preserving that release's original runtime and 31-model library. Its frozen
GUI test selects files through the Add donors button, adds a synthetic native
model, rejects an invalid file, skips a duplicate, reloads the library after the
input was removed, then previews and exports a mixed model. It also repeats the
original pair, library, hair-descriptor and texture-edit roundtrip checks.

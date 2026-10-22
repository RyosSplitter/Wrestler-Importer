# PSP Model Suite v0.28.3

Adds **Protect clothing seams** under the Wii geometry settings. Enable it to
retain extra source UV contacts on arms, torso and legs during reduction. It can
straighten wristband, trunks and knee-pad borders. For Billy Gunn, combine it
with **Geometry: Preserve Hands**. The setting is optional and starts unchecked;
existing conversions retain their previous behavior until it is enabled.

Additional seam geometry can leave less room for texture detail or fail a pose
check on some models. The existing ring/entrance limits and deformation gates
still apply. Failed hand checks now name the failed probes and suggest a geometry
profile; with seam protection enabled, the error also offers disabling it for
comparison. The conversion timer learns separate timing histories for seam-on
and seam-off runs. See [Wii clothing seam protection](wwe13-wii-clothing-seams.md).

The verified overlay updates **v0.28.2 to v0.28.3**. Close the app and copy the
overlay's `PSP-Model-Suite` contents into your existing app folder, replacing
files. Use the complete ZIP for older versions or new installations.

## Previous v0.28.2 Road Dogg support

Adds WWE ’13 Wii Road Dogg (`ch312.pac`) source support. His body and transparent
model each contain three geometry packets; the first two omit vertex-color
indices. The decoder now reads those position/UV pairs and all three packet
headers, retaining every packet's geometry, UVs, weights and Q7/Q8 position scale.
Missing vertex colors use neutral white, consistent with the converter's existing
source-tint policy. Unknown counts, attribute combinations and invalid indices
remain rejected. The independent source-encoding audit checks all six packets.

Choose **WWE ’13 (Wii) — Experimental**, costume **00**, then select ring or
entrance and your PSP base as usual. This expands source decoding; the existing
rig mapping, geometry profiles, texture allocation and output limits still apply.
Review the final preview and test the converted model in PPSSPP.

The verified overlay updates **v0.28.1 to v0.28.2**. Close the app and copy the
overlay's `PSP-Model-Suite` contents into the existing app folder, replacing files.
Use the complete ZIP for a new installation. Retexture and the conversion timer
remain available.

## Previous v0.28.1 countdown

The converter now shows elapsed time and an **estimated remaining** countdown.
It learns stage durations from successful conversions on this computer, grouped
by source platform, texture mode, output role and geometry profile. New profiles
use a provisional progress-rate estimate after startup. Counts adjust at stage
changes; a slow stage shows "updating" instead of a misleading zero. Completion,
failure and cancellation stop the clock. Only successful runs train the local
`conversion-timings.json` history; no filenames or model data are stored there.
The estimate is approximate and may increase as work progresses. This update
does not change conversion algorithms or PAC output.

The verified overlay for this release updates v0.28.0 to v0.28.1. Close the app
and copy the overlay's `PSP-Model-Suite` folder contents into the existing app
folder, replacing files. Use the complete ZIP for a new installation.

## Previous v0.28.0 editor milestone

Adds an [offline Retexture editor](offline-retexture-editor.md) as a node under
each model in Model Editor, with a toolbar shortcut and a Retexture tab. Paint,
protect/recolor regions, layer imported logos, warp/mirror them, consult reference
pictures and watch the encoded model preview update during strokes. Save layered
`.pspret` projects or export a new PAC after exact model/alpha/allocation and
serialized-size checks. No online service, AI model or new dependency is needed.
The converter's existing geometry and texture paths are unchanged.

If the release includes a verified overlay, it updates v0.27.1 to v0.28.0.
Close the app and copy its `PSP-Model-Suite` contents into your current app folder,
replacing files. Keep the existing runtime/libraries/sources/licenses alongside
the executable. Retexture still needs supported native PSP PACs supplied by you.

## Previous v0.27.1 hotfix

Hotfix: [per-packet Q7/Q8 decoding](wwe13-wii-packet-scale-hotfix.md) corrects
Undertaker's oversized floating thigh decorations and adds an independent
source-encoding QA gate. If present in the release, the verified small overlay is for v0.27.0 users;
close the app and extract it over the existing folder as its instructions describe.

Adds [experimental WWE ’13 Wii conversion](wwe13-wii-app-preview.md): explicit
costume and ring/entrance selection, tested geometry profiles, source-nearest
hair alpha, guarded measured T4/T8 textures, full comparison reports and final
PAC previews. Wii exposes Default textures only in this preview. Existing
HCTP/JBI modes and the editor/validator remain available. Known Wii appearance
issues are documented rather than presented as solved; test every model in
PPSSPP. Main and accepted PAC baselines remain unchanged.

## Previous v0.26.0 milestone

The converter now offers the observed JBI PAC/TIM2 family, including archive
costume selection and supported independent elbow pads. See
[JBI usage and integration](jbi-app-integration.md). HCTP conversion stays on its
established path. SYM remains unavailable pending confirmed source evidence.

## Foundation history

# PSP Model Suite — foundation preview

This is the first suite milestone on `feature/psp-model-suite`. It extends the
classic Windows interface around the established v0.25.6 HCTP converter. It does
not implement the entire roadmap or integrate the separate blood experiment.
Accepted PAC baselines and main remain preserved.

## Available workflows

| Module | This milestone |
|---|---|
| Converter | Existing HCTP workflow, texture modes, PSP base preference, QA and Save As |
| PSP Model Editor | PAC library, native inspection, editable folder export, PNG texture editing/repacking, five rest views, exact unchanged PAC copy |
| Textures | Shared native texture browser, dimensions, encoded cost, palette/used-color counts, transparency preview; conversion settings remain in Converter |
| Retexture | Offline layers, selections/protection, paint/recolor, logo transforms, UV guides, live encoded preview, editable projects and texture-only PAC export |
| Quality Assurance | Textures / Model / Full PSP-base compatibility validation, verified repair copies, conversion reports |
| Model Creator | Explicit development roadmap; assembly/export and asset libraries are not implemented |

SYM/PS2 SVR/PS3-X360 SVR/WK conversion, PS1 texture styling,
UV editing, OBJ reimport and creator assembly remain planned. Unsupported formats
are not passed to the HCTP parser as if they were supported.

## Windows use

Extract the entire portable ZIP and launch `PSP-Model-Suite.exe`. Keep its
`_internal`, `runtime`, `sources` and `licenses` directories together. The same
bundled Blender/runtime remains in this preview; the suite shell does not shrink
that dependency. This is a Windows 10/11 x64 build with Windows 7-style controls,
not a Windows 7 operating-system compatibility claim. No game assets are bundled.

The Converter tab retains the Convert button above its preview and the current
Default/Legacy/ATO/Priority Selection/Downgrade/Maximum Downgrade policies. The
remembered PSP base uses the existing settings directory. Switching tabs does not
reset a conversion, its base, or texture choices. Conversion still runs in its
existing isolated process. `--converter-only` opens the standalone converter UI.

In **PSP Model Editor**, click **Choose folder...** to list PAC files inside the
app. Single-click a file or use the arrow keys to load it; double-click or Enter
reloads the selection. Scroll through the list, filter filenames, or use Refresh
after adding/removing files. `.pac` matching is case-insensitive, filenames sort
naturally (Model2 before Model10), and only the selected folder's direct files are
listed. The last folder is remembered alongside the existing PSP-base preference;
starting the app restores the list without automatically loading a model. Empty
and missing folders are reported explicitly. Individual PAC opening still works.

Selection is debounced while moving quickly. If a model is already being inspected,
the latest requested PAC loads next; intermediate results cannot replace the final
selection. The previous workspace remains available until its successor loads
successfully. Filtering and switching tabs preserve the loaded workspace.

Open your own native PSP PAC. Select each model or expand
its mesh rows, then choose front/rear/left/right/three-quarter views. The **Textures**
tab shows the same workspace's images, with transparency on a checkerboard and
no upscaling. Stage/blood palettes in additional named tables are listed too.
Previews are actual offline CPU renders of decoded rest geometry, not Noesis or
PPSSPP captures. Unsupported or ambiguous resources are reported, not replaced
by invented pixels.

Use **Export folder...** to create a self-contained editable directory. Edit its
named PNGs in Photoshop/GIMP, then use **Pack folder...** to produce a new PAC in
the library. Read the [folder-editing contract and limitations](portable-edit-folders.md).
Use **Quality Assurance → Validate PAC...** to check an existing PSP PAC and write a separate verified repair copy where supported. Choose a working PSP base and Textures, Model or Full compatibility validation. HCTP anatomical comparison stays separate. Read the [validator scope](portable-pac-validator.md).

Texture dimensions/palette capacity remain fixed; native geometry reimport is
not supported. Edited PACs are previewed automatically and still require testing.

**Save unchanged copy** writes the captured PAC byte for byte to a new filename.
It is a validated exact-copy round trip, not a PAC rebuild or model edit. Existing
destinations and the original input are protected from overwrite. The developer
preview-ZIP API creates a new ZIP containing each original decoded YOBJ, its structural
audit, OBJ/MTL, numeric texture filenames, PNGs and views. OBJ has no armature,
weights or PSP draw metadata. It is not the authoritative project representation.

## Workspace contract and boundaries

New modules are separate from converter algorithms:

- `desktop/suite.py`: navigation and shared native workspace UI.
- `desktop/pac_browser.py`: folder listing/filtering, remembered directory and debounced file selection; never decodes PACs.
- `desktop/workspace.py`: inspection, snapshot verification, exact-copy and preview export.
- `desktop/gui.py`: hosts the existing converter page and shuts down both job types.
- `ps2psp_converter.py --suite-inspect SOURCE JOB_DIRECTORY`: isolated inspector.
- `tools/suite_smoke.py`: actual GUI/frozen-worker functional checks.

Local jobs are under the existing app data directory, `suite/jobs/<id>/`. Each has
`inspection.log`, `result.json`, optional `error.log`, and `workspace/manifest.json`.
The schema is `psp-model-suite.workspace/1`:

| Item | Purpose |
|---|---|
| `original.pac` | Exact immutable snapshot; SHA-256 checked before copies/exports |
| `manifest.json` | Original path/hash/size, section inventory, models, textures, findings and explicit inspection scope |
| `models/model_NNNN/model.yobj` | Original decompressed YOBJ; never reconstructed from OBJ |
| `models/model_NNNN/audit.json` | Existing strict pointer/index/palette/weight audit |
| `models/model_NNNN/model.obj`, `preview.mtl` | Rest-geometry exchange preview, material IDs retained |
| `textures/texture_NNNN.bin`, `.png` | Original encoded texture bytes and decoded preview; embedded names remain metadata |

Duplicate or ambiguous resources stay separate. Matching uses the native observed
case-insensitive spelling convention, preferring texture section 9, with no
guessing when multiple matches remain. Native model/mesh boundaries and all
source skinning records remain untouched. Unknown section bytes remain in the
original snapshot. An unsupported YOBJ layout retains its bytes and error;
it is not certified or rewritten.

Native inspection calls the existing strict converter export-profile validator
as an additional check. Native PACs can exceed the configured 148000-byte
conversion budget or use conventions outside that profile; such files are still
inspectable. A profile finding is not by itself proof of game corruption. The
148000-byte cap remains unchanged in conversion. Native inspection does not run
source comparison, anatomical QA, analytical poses or gameplay; the conversion
QA report and [standalone PAC validator](portable-pac-validator.md) provide those checks separately.

Failed inspections retain the previous loaded workspace. Closing the application
cancels a conversion through its existing mechanism and terminates read-only
inspection. It never overwrites accepted PACs or saves partial inspection as a
successful manifest. Editable texture folders retain verified native provenance; see the folder-editing contract. The standalone validator preserves a separate original snapshot and only publishes independently validated repair copies.

## Reproduce and validate

Use the established desktop requirements and runtime; no new dependency is added.

```sh
python ps2psp_converter.py
python ps2psp_converter.py --converter-only
python -m unittest tests.test_suite_workspace -v
python -m unittest tests.test_pac_browser -v
python -m tools.ci_tests
python ps2psp_converter.py --suite-smoke-test local/suite-smoke.json
python ps2psp_converter.py --smoke-test local/converter-smoke.json
```

GUI checks need a graphical display. The smoke creates synthetic multi-model
fixtures, starts the real isolated inspector, navigates every module and view,
verifies texture display, exact PAC copying, preview export, preserved converter
choices and minimum window layout, and captures actual application screenshots.
No game fixtures are bundled in that smoke.

On Windows, build with `python -m tools.build_portable --suite`. The separate
`windows-suite.yml` workflow tests and packages the frozen suite without changing
the established converter release workflow. The initial Linux validation and
Windows run results are recorded in `downloads/model-suite-foundation/`.

Texture-folder editing/repacking is now available. UV/geometry editing is the
next milestone, with explicit topology and skinning mapping.

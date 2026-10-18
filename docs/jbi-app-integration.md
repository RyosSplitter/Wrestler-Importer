# PSP Model Suite v0.26.0: JBI conversion

[Windows x64 download](https://github.com/RyosSplitter/Wrestler-Importer/releases/download/suite-jbi-7-35371bd8cf8c7f2639fd9ae709839fb334c28a83/PSP-Model-Suite-v0.26.0-Windows-x64.zip)
 · [Verified release and test evidence](../downloads/jbi-app-integration/README.md).

Implementation, byte/file and executed-test observations below are
**CONFIRMED** for build `35371bd8cf8c7f2639fd9ae709839fb334c28a83`.
General anatomical/controller equivalence is **INFERRED**; untested game
semantics and true runtime limits remain **UNKNOWN**, as described below.

The JBI path integrates the arm/hand and independent elbow-pad experiment
accepted by the user. The HCTP preparation, reduction and texture defaults stay
on their previous path. SYM remains disabled: the original uploaded archive
was corrected by its owner to JBI. See `jbi-provenance-correction.json`.

## Using the app

1. In Converter, select **SmackDown! Just Bring It (PS2)** and open an original
   JBI costume PAC or the observed JBI `CH.PAC` archive. Dropping a supported
   DPAC wrapper selects the JBI reader automatically; this is format routing,
   not a binary title identifier.
2. An archive displays an **Archive costume** selector. Choose its four-digit
   hexadecimal entry ID. The file remains read-only; the output is one selected
   costume's PSP PAC, not a rebuilt JBI archive. IDs are not assumed to be
   decimal roster numbers or reliable wrestler names.
3. Choose your own compatible PSP base once, as before. It must supply ordinary
   indexed4 and indexed8 float-weight rendering templates and the required
   skeleton/controller family. No game-derived base is bundled.
4. Use Default to reproduce the validated JBI texture allocator. Convert,
   inspect the actual final PSP preview and QA report, then Save PAC As.
   Keep the accepted PAC available for rollback and test each new model in
   SVR 2011 PSP. Opening a model in the app is not game validation.

The classic interface, Convert button above the preview, editor/library,
editable folders and scoped PAC validator remain available. HCTP files still
use HCTP's source selector and established conversion behavior.

## Separate source and conversion contracts

`desktop/adapters/jbi.py` uses `tools/jbi_source.py`. It does not alias the HCTP
adapter. The format reader reuses the proven bounded packet decoder and the
DPAC/TIM2 primitives in historically named `sym_*` research modules.

Supported source structure is the observed single-EMD DPAC directory with
bounded cumulative entry allocations, or an extracted classic PAC. The main
YOBJ is section 2 and its TIM2 atlas is section 1. Supported auxiliary YOBJs
are the individually verified left/right arm accessories in sections 6/7.
They require the main model's local rig/atlas and unilateral arm support;
the PSP output retains independent sections 26/27 with a shared texture array.
Unknown auxiliary YOBJs stop conversion rather than being silently omitted.

Inputs are limited to 32 MiB. Corrupt offsets, duplicate IDs, unknown texture
layouts and unsupported VIF packets fail explicitly. In particular, the
original corpus's entry 0069 packet variant remains unsupported. One-bone
props in source section 5 are not converted by this update. Recognition of
the archive is not a guarantee that every costume or controller is supported.

`desktop.core.Request` now carries `source_entry` and `texture_review_entry`.
Both default to empty for backward-compatible HCTP jobs. A manual texture
review is bound to both the source SHA-256 and selected JBI entry; switching
costumes clears priorities and regenerates source texture previews. An invalid
entry never falls back silently to the first costume.

`desktop.core.run_job` dispatches JBI jobs to `desktop/jbi_job.py` before HCTP
orchestration. The app calls the same `tools.jbi_trial.run` engine as the
accepted experiment, with generic archive selection, optional accessories,
progress/cancellation callbacks and laboratory comparison renders disabled.
The native writer and `desktop.accessories.package_models` are unchanged.
The JBI path does not invoke Blender or HCTP decimation.

## Geometry, weights and QA

The existing JBI engine keeps the source geometry/material topology and UV
appearance through lossless UV-island atlas adaptation. Local arm/hand
reference-pose conversion accounts for the PSP elbow/wrist origins and thumb
rest frames. Digit-constrained transfer prevents one source finger receiving
another finger's controller. Parent-side arm support, including clavicles,
is retained at joint transitions. The established ocular/jaw guard stays in
place. This is a general contract/region rule, not a Rock-name or hash patch.

Full details, failed weights-only controls, source/native thumb stress evidence
and limitations are in `jbi-rock-arm-accessory-trial.md`. Source joint order,
blended hand boundaries, influence limits and coincident rest seams are checked;
unsupported cases are rejected rather than averaged, welded or reshaped by an
arbitrary displacement. The PSP skeleton remains the selected native skeleton.

The app runs independent index, palette, weight, relocation, pointer, alignment,
model-set, GIM/material and actual PAC-size checks. Body, ocular, accessory,
independent-digit, wrist/grip and thumb-web analytical tests run before export.
The OBJ/MTL/PNG and textured views are generated from the actual final PAC.
These CPU previews are not Noesis/PPSSPP screenshots or captured animation clips.

The report distinguishes review findings from structural failures; the inherited
two-slot leg palette is not described as a proven illegal format. Source helper
animation semantics, all game poses, pad events, runtime memory and long-match
stability still require model-specific game testing.

## Texture options

JBI Default retains the accepted measured allocator: source-bounded atlas
candidates, cranial/cutout safeguards, immutable native material depth, actual
compressed PAC measurement and the selected PSP base's conservative pixel/CLUT
envelope. The configured in-match target remains 148,000 bytes. This envelope
is a policy derived from observed native data, not a proven hardware heap limit.

Optional ATO, Priority Selection, Downgrade and Maximum Downgrade reuse the app's
existing texture-only modules over the validated JBI Default PAC. They must
preserve every decoded non-texture section, including all YOBJs, skeletons,
weights, UVs and accessories. Retained effect data can use the existing lossless
BPE storage optimization without changing decoded bytes. The final PAC is
validated again and previews are regenerated from its actual textures.

Priority Selection accepts at most three atlas charts; reductions and budget
decisions are reported. Downgrade reduces Default output by the requested
steps, preserving the existing 64-pixel long-axis floor and aspect ratio;
already smaller maps stay smaller. Maximum Downgrade remains an explicit
texture-only last resort. Legacy is HCTP-only and is hidden for JBI, rather
than pretending that a previous JBI Legacy path existed.

## Reproduce and validate

```sh
python ps2psp_converter.py --inspect CH.pac inspection.json jbi 0000
python ps2psp_converter.py --worker job/request.json
python -m unittest tests.test_jbi_adapter tests.test_jbi_rig
```

Example request (use real absolute paths):

```json
{"source":"CH.pac","base":"OWN-PSP-BASE.pac","source_format":"jbi",
 "source_entry":"0000","texture_mode":"Default"}
```

Inspection returns a read-only entry catalogue and source-chart previews. The
worker emits its normal progress events, success/failure JSON, diagnostics,
final PAC, QA and preview folders. Cancellation removes incomplete models using
the established isolated-worker cleanup. Save As retains hash verification,
protected-input checks, backups and atomic export.

The Windows workflow builds the full suite, tests source switching and the
existing converter/Blender runtime, then exercises frozen JBI archive selection,
all five supported texture modes, independent accessories, exact non-texture
preservation, Save As and cancellation. Procedural JBI-format geometry and
TIM2 checkerboards are generated on a development-only user-supplied PSP rig;
no original JBI archive or wrestler mesh/texture is placed in the app. These
fixtures demonstrate packaged behavior, not original-game compatibility.

The user's original archive and accepted Rock PAC remain separate local
regression controls. The app's Default is compared against that accepted PAC;
platform floating-point differences must be distinguished from changed geometry
or rigging. Previously accepted HCTP/JBI PACs are preserved, and experiments are
not silently merged into main by publishing this preview build.

The pinned local app worker reproduced the accepted Rock PAC byte-for-byte at
133,120 bytes. The downloaded Windows ZIP passed all 7,215 manifest hash checks,
and the hosted frozen GUI/worker checks passed all five applicable texture modes,
archive switching, accessory retention, Save As and cancellation. The existing
converter/runtime and suite functional checks also passed. These results remain
distinct from original-game testing and clean-user-PC validation.

# Creator Blender editing: architecture audit and first integration

## Architecture reviewed

The Creator already assembles native PSP records in `model_creator/core.py`, previews the decoded model through `desktop.preview`, and retains independent builds. `model_creator/native.py` understands library descriptors. Morph Studio (`model_creator/morph/`) has an in-place position/normal/bounds patcher, contact/face checks and analytical poses. The UV editor (`model_creator/uv/`) has a UV-only patcher and reversible recipes. `desktop/blender_runtime.py` locates and validates the existing Blender 4.3.2 runtime. Texture quantization, GIM contracts, BPE compression and PAC rebuilding are already available in the desktop/tools modules.

A preview OBJ is insufficient for editing: it omits native-record identity, full rig bindings and the return contract. Reimporting arbitrary Blender topology would require new vertex allocation, draw-palette fitting, material mapping and deformation review. The first integration therefore uses an explicit native-record handoff, leaving the converter and its adapters unchanged.

## Implemented workflow

The existing Creator window now has a **Blender** tab:

1. Assemble and validate the current parts, morph and UV choices.
2. Choose Blender 4.3.2 (the same runtime setting as Morph Studio).
3. **Edit assembled model in Blender...** creates a new session folder and opens `model.blend`.
4. Edit mesh positions, the original **PSP UV** layer, or existing image textures. Save the `.blend`; save/pack painted images as well.
5. **Import saved Blender file...** validates a separate native build, refreshes the Creator preview and enables the existing PAC/preview/report exports.
6. **Undo Blender import** restores the preceding build. Every build/session remains on disk.

The session includes an immutable baseline PAC snapshot, PNGs, a packed textured `.blend`, and fingerprinted job/scene contracts. Existing assembled morph and UV edits are already baked into that baseline. The session is tied to the exact current PAC; stale or modified contracts are rejected. A saved-as `.blend` outside the session folder can be imported by selecting its original `session.json` when prompted.

The bridge is isolated in `model_creator/blender_edit/`: `bridge.py` handles host-side contracts/native validation and publishing, `worker.py` handles Blender scene creation/readback, and `ui.py` handles the Creator tab. The build script already collects Creator submodules and includes the entire Creator folder as worker data, so no second app or bundled Blender distribution is introduced.

## Preservation and validation

- One Blender object per native draw mesh; native point IDs, face order and material slots are explicit.
- Texture UV V and coordinate axes are converted reversibly. Native → Blender is `(x,z,-y)` with unit scale1.
- Bone names/parents and displayed rest transforms are validated. Bone bindings and weights are never re-exported from Blender: the original native data is retained and Blender modifications to them are rejected.
- Normal fields rotate with local geometric surface changes, preserving native shading under uniform scaling instead of recomputing each palette boundary independently. No-op and UV-only edits preserve original normals.
- Host-side byte whitelists permit positions, normals, conservative mesh radii, and UV float pairs only. Indices, palettes, bones, native material state and unknown data remain exact.
- New/folded/collapsed faces, opened verified shared contacts, nonfinite data and unsafe native records are rejected. Existing analytical checks run under both supported pose conventions.
- Texture dimensions and palette depth stay at the native baseline. Existing quantization/GIM packing is reused; edited alpha must remain exact after encoding. Visually unchanged textures retain their original bytes, including irrelevant RGB under zero alpha.
- PAC compression/readback and the current PSP file-size budget are mandatory. No automatic mesh reduction is introduced by a Blender import.
- Readback runs with embedded Blender autoexecution disabled. Input hashes are checked before publishing. Output is staged on the destination filesystem and renamed into a new build folder only after validation and preview generation complete. A failure/cancellation preserves the active result.

## First-version limits

Only native float-weight skinned meshes are supported. Vertex count/order, faces, IDs, skin groups/weights, rig, material assignments and shader graphs must remain intact. UV corners belonging to one native vertex must stay together; splitting them requires a topology-changing export and is rejected. Extra mesh objects/modifiers and unapplied object transforms or shape keys are rejected. Apply intended shape changes to the base mesh and return the rig to rest before import.

The Blender rig is a **bind-position display**, not a reproduction of PSP bone-axis/animation behavior. Blender lighting/material appearance is an approximation; the Creator shows the actual decoded native export. Large edits still require in-game review.

Blender imports are separate final build branches, not new Morph/UV recipes. Creator previews use the imported result directly, preventing older recipes from being applied twice. While that build is active, further shape/UV editing uses a fresh Blender session; reassembling returns to Creator choices and starts a fresh build. Save choices preserves those original choices, not a replayable arbitrary Blender deformation. The imported PAC, QA and editable session are independently preserved.

Blender 4.3.2 is the currently validated runtime. A Windows executable/installer has not been rebuilt or published by this change.

## Follow-on phases

1. Persist imported deltas as a project layer so Creator Morph Studio/UV controls can compose with Blender edits after import.
2. Add reliable shared-record selection helpers and clearer body-region collections for sculpting across native draw boundaries.
3. Add opt-in topology-changing import with material provenance, palette fitting and independent deformation QA. Arbitrary weight/rig editing remains a separate scope.
4. Broaden Blender-version compatibility after testing the same contracts against each runtime.

## Validation performed

Procedural asset-free tests cover exact no-op PAC preservation, shape/UV/painted-texture round trips in real Blender4.3.2, stale baselines, budget failure, rejected record-ID/modifier/rig/material/shader/UV-split/weight edits, invalid/collapsed geometry and failure atomicity. The real Tk smoke test exercises the new buttons through session creation/import, preview switching, PAC readiness and Undo. Existing Creator, morph, UV, library, waist and0.3 regression suites pass.

A private read-only round trip using the accepted Eddie97 Wii-based PSP PAC also returns the **identical151,552-byte PAC**; proof and UI capture are under `local/creator-blender-validation/`. These are not game-runtime tests. No source game assets are included in test fixtures or committed feature data.

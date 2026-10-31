# PSP Model Creator 0.5.0 — integrated UV editor

Open a prepared donor or Creator project, use **Morph Studio** to reshape a compatible whole donor, then choose **UV Editor** in the same window. A texture canvas appears beside the existing live 3D preview. UV editing also works on native mixed-part assemblies and does not require Blender; body morph validation still uses the existing Suite Blender 4.3.2 runtime.

## Fit a texture

1. Pick the active texture. **Load texture PNG** accepts a replacement with exactly the original dimensions and alpha. The editor quantizes to the existing PSP indexed palette and shows those actual encoded colors in both views. It reports color error; no model download or online service is involved.
2. Choose **Face / head**, **Torso**, **Arms**, **Legs**, or **All**. These are approximate filters using skinning influences and anatomical fallback. **Isolate region in 3D** hides faces outside the active texture and region for review; it does not remove them from export.
3. Click an island to select it. Shift-click adds/removes an island. Drag empty canvas space to box-select UV records. **Select region** selects all visible records; **Clear** clears the selection.
4. Select **Move**, **Scale**, or **Rotate** and drag. Move follows the pointer, scale uses horizontal drag, and rotate uses horizontal drag at half a degree per pixel. Numeric Apply controls offer UV offsets, separate X/Y scale factors, and degrees. Transform pivots use the selected records' center. V increases downward, matching the native sampler. UV coordinates outside 0–1 retain texture repeating.
5. Wheel over the texture to zoom, middle-drag to pan, or use **Fit**. Scroll the left toolbox to reach lower controls on smaller screens. **Mirror U/V** reflects UV placement about its selection center; it does not mirror the mesh or automatically pair left/right anatomy.
6. **Undo**, **Redo**, **Reset selected**, and **Reset all UVs and textures** keep editing reversible. One mouse drag is one undo step; Escape cancels a drag. **Compare original UVs / texture** changes only the displayed layer. Morph Studio's original comparison independently controls body shape.
7. Use **Assemble and validate**, then **Save PAC as**. Changing a UV or texture after building blocks stale export until validation runs again. The existing size warnings, texture-only fitting option, preview-folder export, and PAC packing workflow still apply.

Save choices stores both morph and UV layers in the project, including imported indexed texture data. Source PACs remain immutable. Projects with UV edits use schema 3 so older Creator versions reject them rather than silently lose UV adjustments. Resetting both edit layers with texture downgrade off restores a whole donor's original PAC byte for byte.

## Distortion and limitations

**Show UV area distortion** compares each triangle's UV area to its current 3D surface area, relative to that texture's median density. Red indicates lower density/stretch, blue higher density, green similar density; purple marks collapsed or flipped UVs relative to the original. This measures area density, not every kind of angular distortion. Different density in deliberately separate atlas regions may be intentional.

Islands connect complete continuous surface/UV edges, including native palette-split aliases. Overlapping coordinates alone do not join unrelated surfaces. Native records shared with neighbouring regions/materials move together: the canvas warns when a selection affects records outside the filter. Editing a mirrored/shared UV layout may affect both sides. Independent unmirroring, seam creation, topology splitting, automatic bilateral pairing, facial landmark alignment and automatic unwrapping are later phases.

The editor is modular in `model_creator/uv/`. UV export patches only native UV float pairs; byte-difference whitelists and native readback verify positions, normals, skinning, indices, bone data, material state and allocation sizes remain intact. A combined export validates body morphs first and applies the UV layer second. Blood overlays and auxiliary PAC payloads stay in export, although the normal 3D preview hides blood as before. Analytical checks still need in-game PPSSPP review.

## Install the Creator patch

Close Creator and merge **all** ZIP contents into its existing folder, including `_internal`. The patch contains the executable, required Python worker data and source/docs; it keeps the existing native donor library and runtime binaries. It supports Creator 0.2 through 0.4.0. Select the Suite's existing `runtime/blender/blender.exe` for morph export if it has not already been configured. The full Windows ZIP is also available for a separate fresh installation.

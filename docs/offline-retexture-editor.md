# Offline Retexture node — v0.28.0

The Model Editor has a **Retexture...** child node under each inspected model
and a matching toolbar button. Both open the suite's Retexture workspace with
that PAC/model selected. The separate Textures inspector and external
Export folder / Pack folder workflow remain available.

This is a manual offline texture editor. It has no network client, image model,
API key, generative service, or additional Python dependency. Reference photos
are displayed for the artist to consult; they are not automatically converted
into attire. Only supported native PSP PAC/YOBJ/indexed-GIM layouts are editable;
convert HCTP/JBI/Wii input through the existing converter first.

## Workflow

1. Browse your PAC folder in Model Editor. Select the model's Retexture node,
   or open a native PSP PAC directly in Retexture.
2. Choose a texture thumbnail. The canvas and layer list are specific to this
   image. **Show usage** highlights its model surfaces by dimming other maps.
3. Add reference pictures. Choose among them beneath the model preview. Up to
   twelve are stored with the project, reduced to at most 1024 pixels per axis
   for display/storage. This does not resize model textures.
4. Use **Picker**, **Similar color**, or **Select rectangle** to isolate clothing.
   Selection affects brush/recolor; **Protect** paints a persistent red mask that
   blocks every layer, including imported logos. **Unprotect** removes that mask.
   **Clear protection**, **Select all**, and **Invert** are undoable.
5. **Recolor** makes a new layer using the chosen hue/saturation while scaling
   original brightness around the selected area's median. Folds/shadows remain,
   though very black fabric may require brush/artwork refinement.
6. Import a transparent PNG logo/pattern (JPEG/BMP/WebP also open). Drag it with
   **Move layer**. Use rotate, smaller/larger, mirror/flip, and opacity controls.
   **Warp corners** drags the closest cyan corner; a convex perspective warp is
   supported. Invalid/crossing corners retain the last valid placement.
7. **Brush** adds raster paint. **Erase** removes paint from the top paint/recolor
   layer; it does not erase imported artwork or the original. Delete/hide an
   imported layer to remove it. Layer order is bottom-to-top compositing; the
   list shows topmost first. The original is immutable.
8. UV guides draw the current model's triangle edges over the actual texture
   coordinates. They do not change UVs. Mirrored/shared UVs necessarily repeat
   artwork on every surface using those texels. Zoom the canvas; use its scroll
   bars (or middle-button drag) to pan.
9. Rotate the model by dragging its preview or using named views; the slider
   zooms. **Encoded preview** defaults on and shows the actual indexed texture
   representation. Turn it off to compare the editable full-color draft.
10. **Check size** builds the actual serialized candidate, including original
    compression conventions, headers, padding and sector alignment. If it is
    too large, lower **Edited colors**, simplify artwork, or remove unnecessary
    layers. Lower colors is a cap for newly allocated artwork colors, not a new
    GIM palette format. Native T4 stays T4 and T8 stays T8.
11. **Export PAC** repeats native preservation, allocation and size checks and
    saves to a new filename with a `.report.json` sidecar. It never overwrites an
    original/existing PAC. Test edited appearance under actual PPSSPP lighting.
12. **Save project** stores a self-contained `.pspret` ZIP containing the PAC
    snapshot, editable layers/transforms, selections, protection and references.
    Reopen it without the old source file. Save revisions under new filenames;
    existing projects are preserved. **Export texture PNG** exports the draft
    composite for optional work in GIMP/Photoshop; it is not a PAC by itself.

## Live preview implementation

`desktop/retexture_ui.py` throttles preview requests at 100 ms rather than
debouncing them until the end of a stroke. A single background rendering worker
uses immutable texture snapshots and the original audited model. New edits
coalesce into the next request instead of building an unbounded job queue.
Rendering uses a 480-pixel surface cache. The last completed frame from the same document can be shown while a newer revision
is rendering; results belonging to a replaced document are discarded. Tk widgets
and PhotoImages are updated only on the UI thread.

`desktop/retexture_preview.py` caches visible texture addresses, interpolated
vertex colors and lighting for each model/camera. Color-only edits then resample
the edited textures without rerasterizing triangles. This is valid because
dimensions, UVs, geometry and alpha are immutable. New views/orbit angles rebuild
the cache. The cache rejects altered alpha/dimensions. Tests compare cached output
pixel-for-pixel with the full renderer, including actual hair-cutout views in
private acceptance checks. A local 3,242-triangle Shawn test improved from four
to thirteen completed encoded-preview frames during a three-second active stroke;
this is one machine's observation, not a promised rate on every computer.

This is interactive CPU feedback, not a claim of 60 FPS or PSP shader emulation.
Update rate depends on model complexity and the user's computer. The renderer
uses the existing neutral light and decoded GIM palette. Export-size checks run
separately from the live render because full PAC compression need not happen on
every mouse movement.

`desktop/preview.py` accepts optional RGBA textures, selected-texture highlighting,
a fixed-framing yaw angle and an optional surface-capture buffer. Existing callers pass none of these: their render
path, camera and default shading are unchanged. The renderer does not serialize
the display model or modify positions/normals/UVs/weights.

## Preservation and palette rules

`desktop/retexture.py` owns the document and builds candidates separately from
the converter. The original PAC bytes are immutable. Model sections are audited
on load and compared byte-for-byte, including their stored compression streams,
on every build. Non-texture sections, model order, material controls, UVs,
geometry, skinning and skeletons are preserved. No mesh rebuild occurs.

Only supported main-table textures in section 9 are editable. Effect/blood maps
and other tables remain read-only. Original alpha is locked for every pixel;
imported art alpha controls blending, not the model's final coverage. Texture
width/height, bit depth, native GIM headers/padding and encoded allocation are
retained, so texture runtime allocation does not grow.

Encoding first pins all original palette entries used by texels outside the
edit. It allocates remaining slots to newly quantized artwork in separate alpha
groups. Changed pixels use the new colors or compatible pinned source colors.
Every untouched decoded texel and every alpha value is verified after encoding.
The existing `edit_folder.replace_gim_pixels` writer patches only pixel/CLUT
bytes. No edit yields exact original GIM/PAC bytes.

A full 16-color palette shared by skin/clothing can leave no new color slots.
In that case the draft can differ substantially from its encoded result; this
is reported as actual RGB RMSE, pinned slots, and available new slots. The
encoded preview is essential. Expanding bit depth/material controls or splitting
atlases is outside this milestone. Recoloring a larger appropriate clothing
region can free slots, but do not select skin merely to obtain more capacity.

The export allowance follows the existing native editor policy:
`max(152064, original_native_PAC_bytes)`. The larger existing size is not a
universal loader limit. Converted ring models normally use 152064. Candidates
over this allowance are withheld with explicit advice, never silently resized.
Texture allocation is constant; BPE stored bytes can grow when art complexity
increases. Unknown nonzero PAC gaps/trailers stop repacking instead of being
discarded. Publishing uses complete-file verification and exclusive creation.

## Project integrity and limits

Projects are bounded ZIP/JSON/PNG data, not pickle or executable scripts. Assets
are addressed inside the archive without filesystem extraction. Stored checksums
detect accidental changes; they are not signatures/authenticity guarantees.
Source inventory is rebuilt from the snapshot, not trusted JSON offsets. Masks,
layer dimensions, transforms, opacity, read-only maps and source hash are checked
when reopening. Limits include 32 MiB source PAC, 4 megapixels per imported
image, 64 layers per texture, twelve references, 128 MiB uncompressed archive,
and bounded undo history (20 steps/64 MiB, retaining the newest state).

Reference pictures and artwork must be supplied by users. No game-derived PAC,
texture library, attire photographs or generated Shawn textures ship in the app.

## Verification

Run `python -m unittest tests.test_retexture -v` for procedural fixtures covering
selection/protection, painting/erasing, shading, layers/warps, alpha, pinned
palette behavior, undo, project portability/integrity, oversize refusal,
unchanged native sections and pose replay. The legacy GIM renderer must match
the new RGBA path exactly when displaying identical colors.

`PSP-Model-Suite.exe --retexture-smoke-test REPORT.json` exercises the real editor
tree node, pointer strokes, live frames *before mouse release*, layers,
transforms, project save/reopen, encoded preview, actual size check and export.
The Windows build runs it alongside existing suite/converter/JBI/Wii tests.
It uses generated conformance models, not game assets. A screenshot and JSON
result are released with the build. Analytical pose equality proves texture
editing did not alter geometry; actual attire appearance still needs game review.

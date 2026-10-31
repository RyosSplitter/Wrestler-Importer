# PSP Model Creator 0.4.0 — Model Morph Studio

Morph Studio is a new sidebar tab in the existing Creator window. It uses the
same model preview, pose controls and checked PAC export workflow.

1. Choose a supported whole native donor on **Body parts** (use **Whole donor**).
2. Open **Morph Studio**. If necessary choose `blender.exe` inside your installed
   PSP Model Suite's `runtime/blender` folder. Blender **4.3.2** is the verified
   runtime; Creator does not download or bundle another Blender installation.
3. Adjust shoulder width, chest width/depth, waist width, upper-arm thickness,
   thigh thickness and calf thickness. Controls are bounded and symmetrical.
   Use Undo/Redo, Reset all and Compare original. Scroll the sidebar on small screens.
4. Save choices to retain the portable recipe. **Assemble and validate** runs the
   Blender shape keys, checks native readback and both analytical pose conventions.
   Save PAC As exports the separate validated result. Changing a control requires
   another validation before export.

The first release handles body silhouette/girth on a supported whole donor.
Mixed-part morphs, limb length, height, face sculpting and donors with auxiliary
sections are later phases. Their existing Creator operations remain available.
Some test/unknown donors lack useful anatomical anchors and cannot be morphed.
Bone positions, assignments, weights, topology, UVs and material state are retained.
Vertex positions/normals and mesh culling radii may change. Body adjustments use
smooth spatial fields; independently indexed UV/palette corners are not welded.

The preview evaluates the same fields against an immutable baseline after a
short debounce. A fresh Blender process is used for validation/export, not every
slider movement. Blender builds relative shape keys with stable native-record
IDs. Its result must agree with the numerical preview within 0.0002% of model
height. Export checks reject inverted/collapsed faces and openings in verified
equal-weight contact groups. Original distinct skinning branches are retained.
Undo/Redo is session history; saved projects store the baseline fingerprint and
control values. Reset all returns to an exact original PAC when texture downgrade
is off. Source changes select another baseline; in-session edits to previous
selections are retained in their own cached documents.

Nonzero morph recipes use Creator project schema 2. New Creator reads schema 1
as zero morph; older executables reject schema 2 instead of silently dropping
edits. Original source snapshots and saved recipe history remain intact.

No geometry decimation is applied. Recompression can change PAC size even with
identical topology. The established 152,064-byte target, optional texture-only
fitting and oversized-export warning remain. Other native sections, including
textures, remain exact unless maximum texture downgrade is explicitly enabled.
Bone/controller/culling semantics and gameplay still need PPSSPP review; passing
analytical tests is not game certification. Geometry sliders do not repaint skin.

## Install

Close Creator. Copy **all contents** of the 0.4.0 Creator Patch into the existing
Creator folder, including its `_internal/model_creator` worker sources. Keep the
existing runtime libraries and `creator_library`. This patch requires the previous
complete Creator app. For a new installation use the full Windows x64 ZIP.
Blender is shared with the Suite by executable selection; its files are not
replaced by this patch. Existing non-morph workflows do not require Blender.

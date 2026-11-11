# PSP Model Creator 0.6.0 — Blender editing

The **Blender** tab opens an assembled model in your existing Blender4.3.2 runtime with textures, UVs, a bind-position rig and skin weights. Shape, UV and existing-texture edits can return as a separately validated Creator build, with refreshed preview, the normal PAC exports and **Undo Blender import**. Earlier builds and originals remain untouched.

Assemble your parts/morph/UV choices, choose **Edit assembled model in Blender...**, save the `.blend` and save/pack painted images, then choose **Import saved Blender file...**. Keep vertex count/order, faces, native IDs, bone/rest data, skin weights, material assignments and shader bindings intact. Unsupported changes are rejected. Apply intended object transforms/shape keys to the base mesh and return the rig to rest before importing. The displayed rig does not reproduce native PSP animation axes.

The first version edits native float-weight skinned models. UV corners belonging to one native record must stay together. New vertices, new materials, rig/weight edits and extra modifiers are unsupported. Imports enforce native readback, contact/collapse/pose checks, original texture dimensions/depth, alpha preservation and the PAC size budget. Reassembling starts from Creator choices; arbitrary Blender edits are preserved as separate builds rather than replayed as project recipes. See **BLENDER.md** for the architecture and detailed limits. In-game testing remains necessary.

## Choose a package

- **Full Windows x64 ZIP:** extract into a new folder and run `PSP-Model-Creator/PSP-Model-Creator.exe`. Includes the existing prepared library and Python support files.
- **Creator Patch ZIP:** close Creator, back up its folder, and merge **all** patch contents into your existing Creator0.2–0.5.0 folder, including `_internal`. Do not copy just the executable. The patch preserves your existing library/catalog and runtime binaries.

Blender is **not bundled**. Select the installed Suite's `runtime/blender/blender.exe` in the new tab, or the same validated Blender4.3.2 runtime already used by Morph Studio. Compare the downloaded ZIP's SHA256 with its adjacent `.sha256` file before extraction.

This release retains Model Morph Studio, the integrated UV editor, prepared donor selection, native assembly, saved morph/UV projects and existing experimental PAC QA. Analytical checks do not certify actual PSP game animation or slot compatibility.

# PSP Model Creator 0.3.1 — waistband torso cutoff

The default torso/legs split now sits at the top of the lower-body attire,
near the skin-to-waistband transition. Previously it ran through the upper
trunks/tights. This is a shared horizontal cut, so different costumes can need
an adjustment rather than all using an identical waistband height.

Under **Body parts**, move **Torso cutoff** toward **Higher** or **Lower** and
watch the selection preview update. **Show cut line (rest pose)** displays a cyan
guide on the model. Use the front, rear and side views to align it with the
waistband. **Reset** restores the new default. The guide is only a preview aid;
it is never painted onto the textures or included in exported model data.

The torso and legs use exactly the same selected cut plane. The contour stitcher,
native rig/controller selection, source-interior preservation and both analytical
pose checks also use that plane. Changing the cutoff invalidates an older build
for export: click **Assemble and validate** again. Existing size and seam checks
remain in force. No torso scaling, donor texture repainting or automatic geometry
reduction is introduced.

**Save choices** stores the cut height with source snapshots. New projects and
the prepared library start at the new waistband default. Older saved projects
without a cut-height field retain the original cut for reproducibility; click
**Reset** to adopt the new placement and save the choices again. A whole-donor
assembly remains byte-for-byte original at every slider setting.

Close the creator before installing the **0.3.1 Creator Patch** into the existing
creator folder. It replaces the executable and supplies updated source/docs;
keep `_internal` and `creator_library`, including any added donors. The patch is
checked on the previously released 0.2 runtime/library. For a new installation,
extract the complete Windows ZIP. This updates the separate PSP Model Creator;
the converter and its batch queue are unchanged.

The prepared library and optional Maximum texture downgrade remain available.
Structural, seam and rig/pose failures still block export. The current in-ring
size target is 152,064 bytes; oversized creator exports retain their explicit
warning. Mixed models still need visual and PPSSPP review.

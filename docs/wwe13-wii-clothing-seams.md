# Wii clothing seam protection

In v0.28.3, choose **WWE ’13 (Wii) — Experimental**, then enable **Protect
clothing seams** below Geometry. Combine it with any existing geometry profile.
For Billy Gunn (`ch313`, costume 00), use **Preserve Hands** and ring output.
The control starts unchecked. HCTP/JBI conversions keep their existing paths.

The reducer retains extra original contact points with distinct material/UV
corners in the **Arms, Torso and Legs** regions. This is the clothing-only scope
from the Billy seam study, replacing its private wrapper with normal worker/CLI
plumbing. It does not weld source records, paint new artwork, introduce new UV
atlas layouts, or add extra UV locks inside Head, Hands, Eyes or Mouth. Existing
shared-joint/skin-domain guards still apply everywhere. Normals at shared
contacts can change when adjacent region topology changes.

The Billy study straightens wristbands and trunks and removes large knee-pad
wedges stretching up the thighs. It retains the previous hand/head positions,
UVs, weights and topology before packing. Its 151,552-byte ring PAC passes native
pose/eye checks and all four hand probes. Source-fidelity comparison still has
review findings, including broad right-hand/shoulder ROIs in elbow flex; native
gate success is not full animation or appearance approval. Some pixelation
remains. Closest-surface texture metrics can be ambiguous at overlapping layers.

Extra geometry uses PAC space and may change the allocator's texture palette or
resolution choices. Ring output remains limited to 152,064 bytes and Wii entrance
output to 180,000 bytes. Pose, memory, source-encoding and actual-size checks are
mandatory. No automatic fallback disables the option or relaxes a failed gate.
If a source fails, try the suggested geometry profile or uncheck seam protection
and compare. Review the final preview and test the result in PPSSPP.

The request, QA HTML, result JSON and Blender reduction report record whether
protection was selected and the exact three-region scope. Conversion timing
history distinguishes this setting. Leaving it off retains existing geometry
behavior and timing keys. Tests use procedural geometry, with private
user-supplied PAC checks kept out of the distributable.

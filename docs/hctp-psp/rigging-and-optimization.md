# Alignment, weights and controlled optimization

## Coordinate and rest-pose contract

**CONFIRMED [E09]:** Align using one similarity transform
`p_target=s*R*p_source+t`, s positive and R a proper rotation. Kabsch/SVD
fits shared rest-bone landmarks and rejects degenerate/collinear fits. QA
requires at least six available landmarks from the twelve-name set:
`koshi, atama, l_te, r_te, l_ashi, r_ashi, l_kote, r_kote, l_sune,
r_sune, l_sakotsu, r_sakotsu`. Record residuals, scale, rotation and translation.
Rotate/normalize normals without translation. Never use per-axis scale to hide
an anatomical defect.

**CONFIRMED [E09/E15]:** Supported native axes have negative Y toward the head
and negative Z toward the front. QA rotates to `(x,-y,-z)` so Y is up and Z
forward; exported inspection OBJ uses `(x,z,-y)`. These are proper rotations.
Noesis orientation toggles affect the viewer, not the binary asset. An earlier
front/back labeling error is explicitly recorded in the failure history.

**CONFIRMED [E01/E09]:** The output copies the PSP donor skeleton. It does not
retarget HCTP animation files. The source rest geometry is aligned onto that rig.
Legacy Blender-facing preparation flips V once (`1-v`) and records
`uv_v_flipped=True`; serialization flips back. Hybrid native stages retain native
UVs with `uv_v_flipped=False`. Images are not also blindly flipped. Stage metadata
must make coordinate and UV conventions explicit.

## Source bone mapping and five evaluated approaches

**CONFIRMED [E10]:** HCTP group palettes/weights are decoded before UV splits
are mapped to target bones. Same-name mapping is by identity, not table index.
For source-only bones, the ancestor method walks upward to the nearest shared
named ancestor and sums redirected mass. Missing weight mass is an error, not
silently dropped. Supported source-only hair chains map to the head ancestor;
independent source hair physics is not reproduced.

| Method | Mechanism / result | Status |
|---|---|---|
| 1. Direct names | retains same-name support; missing support leaves incomplete mapping in the diagnostic trial | CONFIRMED E10; unsuitable as universal export |
| 2. Ancestor redistribution | redirects missing source support to nearest shared ancestor | CONFIRMED E10 |
| 3. Hybrid | source-derived body, continuous nearest-donor cranial blend in initial trial | CONFIRMED E10/E17 |
| 4. Nearest PSP donor | closest ordinary surface triangle, barycentric donor weights | CONFIRMED E10 |
| 5. Blender heat bind | automatic geometric binding; poorer trial deformation | CONFIRMED recorded trial E10; universal superiority UNKNOWN |

**CONFIRMED [E10/E17]:** Donor transfer queries closest triangles, not just nearest
vertices; it interpolates weights barycentrically, excludes known blood overlays,
normalizes and prunes to the strongest four influences. Seam position caching
keeps coincident records consistent. The old hybrid is
`W=(1-f)*Wmapped+f*Wdonor`, where f is the source mass in the `atama` subtree.
For f=1 it discards all original facial-controller distribution. This explains
why static geometry can be exact yet the animated jaw acquires neck/body motion.

**CONFIRMED [E14/E18]:** Same-name bones do not guarantee equivalent bind frames,
parents or controller semantics. Slaughter comparisons found 68→83 bones and
64 changed indices among66 shared names, plus two mouth-parent changes.
Jericho eye/lid pivots differ by about0.40/0.47 model units and local frame
rotation by approximately(-90°,90°,0). Palette validity alone cannot detect
that semantic mismatch.

## Successful selective facial policy

**CONFIRMED [E17/E18]:** The jaw fix preserves original mapped cranial support
instead of substituting unrelated nearest-donor neck/body weights. Its replay
keeps the already reduced geometry unchanged, using verified source positions
or same-material closest triangles when topology differs. It changed637 weight
records and18 palettes, preserving all positions/UVs/colors/normals/indices.
Jaw-opening and neck-turn QA improved and the user confirmed the jaw fix.

**CONFIRMED [E18]:** Whole-cranial preservation also increased eye-controller
mass from18.52% to88.27%, and head mass fell69.20%→11.73% over81 PSP eye records.
The selective correction restores the earlier **serialized PSP** ocular weights
only where mapped source support includes `l_eye,r_eye,l_mabuta,r_mabuta`.
Of99 selected records,84 change:66 eye and18 lid/surrounding records. Every other
record retains the jaw-fixed weights. Four palettes change; all remain≤8.
Two PSP versions have explicitly verified geometry/topology correspondence before
native-record copying. This is not an assumption that source indices survive
conversion, nor proof that a fresh donor query reproduces this frozen result.

**INFERRED [E18]:** Future transfer should classify facial controller compatibility
individually, preserving source jaw/chin data while retaining proven PSP ocular
behavior for incompatible controllers. The specific four-controller rule is
supported by Jericho, not yet by all HCTP facial rigs. Generalize only with paired
controller and gameplay evidence. Do not revert all facial weights to solve an
ocular-only problem.

## Decimation, normals and preservation

**CONFIRMED [E11/E16/E20]:** Region classification uses target-rig weights:
head roots `kubi/atama`, arms `l/r_sakotsu`, legs `l/r_momo`, otherwise torso.
Face ownership follows greatest summed region support. Historical first profile
retained Head80%,Torso50%,limbs35%; later hybrid profile retained Head80%,
Torso65%,Arms80%,Legs65%. These are explicit **retention ratios**:0.30 retains30%
(removes70%), whereas "remove30%" means retain70%.

**CONFIRMED [E11]:** Blender collapse simplification welds coincident positions
inside each entry, carries corner UV/color layers and weights, protects shared
positions across entries and uses region-membership-weighted Decimate with
triangulation. `vertex_group_factor=1000` protects seam membership. It enforces
a ceil(face_count*ratio) floor, compensating when paired collapses reduce further
than requested. The factor is not a posterior volume constraint. Output normals
are recalculated using area-weighted faces and matching smoothing ownership;
hard accessory boundaries must not be blindly smoothed together.

**CONFIRMED [E11]:** Create every Blender mesh attribute layer **before** retaining
RNA layer references; creation can invalidate previously held references.
Reacquire them and assert input UVs. Persist UVs on loops/corners, not merely a
welded point. Regenerate native records after corner seams, with explicit normals
and materials. The current output keys round UVs to six decimals and colors to
8-bit integers; these are implementation choices and must be included in loss
reports, not called bit-perfect source preservation.

**CONFIRMED [E16]:** Whole-region face counts and seam endpoints failed to preserve
Lance's rear volume: rear trunks lost23/55 faces, back torso37/110. Replacement
triangles flattened the interior even while boundary vertices survived. The
successful guard freezes source posterior materials `l-pan2/l-se1` before collapse,
without paying for those faces by reducing unrelated regions more. It restores
source faces and verified anchors, not an outward butt displacement. An initial
full patch altered an upper neck seam and was rejected; final replay retains that
unrelated superior boundary while restoring the lower original surface.

**CONFIRMED [E20]:** Jericho's whole-arm region contained multiple materials;
shared-entry seam protection did not protect its internal `y2j_hiji` pad boundary.
Three source anchors moved0.423525,0.317730,0.007060 units and the upper corner
acquired2.421% shoulder influence. Successful preservation retains the original
pad54 records/73 triangles and restores three skin aliases and their source UVs,
normals/weights; original upper weight is5% `r_ninoude`,95% `r_ninoude_x`.
Eye/jaw data stay exact. That successful correction is now a QA regression case.

**INFERRED [E16/E20/E21]:** For a general pipeline, preserve sensitive anatomy and
material/accessory boundaries before collapse; reject local volume/depth or
edge-drift regressions. Prefer protected source surfaces over post-hoc inflation.
Use QA-driven protected selections and evidence-backed profiles; material names
alone are not transferable across every wrestler. If a budget cannot retain
those features, report that conflict rather than silently compromising them.

## Palette packing, strips and mesh fragmentation

**CONFIRMED [E06/E11/E19]:** Assign triangles to verified ordinary donor parts,
then split into chunks whose triangle bone unions fit≤8 slots. Duplicate vertices
when required by palette/part/UV/color ownership; retain all semantic attributes.
Local 16-bit indices impose a representable buffer range; current conservative
writer caps chunk vertices at65535. Remap weights by bone identity and regenerate
stride/flag when palette size changes. A vertex's four active influences do not
imply its entire draw can use four bones.

**CONFIRMED [E19]:** Lance's57 native draw buffers produced82 Noesis meshes.
Material grouping and palette splits explain why Noesis's count is different.
The lossless merge trial reduced native57→52 yet Noesis still reported82.
Expanded bytes increased196256→202256 because palette unions increased vertex
stride, while stored PAC remained139264. Thirty-one is not a required mesh cap.

**CONFIRMED [E19]:** A merge is allowed only for adjacent chunks with verified
same-part provenance, matching opaque mesh/palette metadata, same supported
float-weight layout and representable union palette/buffer. Material and strip
records stay individually ordered; remap all local indices and palette slots,
retain each per-bone nonzero float32 weight bit pattern and enlarge the bounding
sphere conservatively. `compatible` returns a list of rejection reasons—an empty
list means compatible. Different rendering state cannot be discarded to lower
counts. Do not assume merging automatically improves runtime memory use.

**UNKNOWN [E19/E22]:** Fragmentation's exact role in intermittent crashes or arena
corruption was not established. Lossless merge validation proved semantic
preservation for the tested structures, not that the runtime symptom was cured.

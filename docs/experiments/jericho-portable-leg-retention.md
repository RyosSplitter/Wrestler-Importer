# Jericho portable leg-retention trial

This tests the inward boot/shin notch in the portable preview's 0600 conversion.
It does not replace the accepted in-game Jericho baseline or change the desktop
converter's release/profile. Keep this branch isolated until PPSSPP testing.

**CONFIRMED:** aligned HCTP/prepared geometry matches at float32 precision. The
notch appears in guarded decimation, before PSP serialization. Holding textures
and cameras identical reproduces the defect in geometry alone. The source material
boundaries protect unequal amounts of the two shins: `y2j_sune` has 34 free
left-side and 18 free right-side faces, while all 14 `y2j_su_r` right-side faces
are protected. Original total shin counts are equal (73 each). The same regional
retention ratio does not impose equal spatial protection on each side.

**CONFIRMED:** changing only the experimental Legs ratio from .65 to 1.0 retains
108/108 free leg triangles instead of 90/108. Head and Arms reductions remain
unchanged. Native face signatures show changes only in `y2j_knee` (112 → 116)
and `y2j_sune` (118 → 132). Their normals are recalculated by the existing reducer.
All other oriented triangle signatures, positions, UVs, vertex colors, weights
and normals match the previous native model. This retains reference geometry;
there is no manual displacement, rerigging or texture change.

**INFERRED:** Blender collapse minimizes geometric cost under vertex constraints,
rather than anatomical volume or local silhouette error. The unprotected shin
patch can collapse inward even when most leg triangles and material boundaries
survive. Uneven protected patches explain why one boot is affected more.
This isolates the decimation stage; it does not establish a Blender bug.

**CONFIRMED:** meshes stay 47; vertices 2635 → 2645; triangles 2667 → 2685.
Both PACs are 147456 bytes. The same 220-symbol lossless BPE setting fits the
restored geometry. Bone-table bytes and every non-model PAC section, including
textures, are identical. Pointers, offsets, allocations, index bounds, palettes,
weights, rendering controls and final alignment/size pass native audits.

**CONFIRMED:** the complete QA run uses exactly the previous thresholds, 24000
samples per direction, 320-pixel comparisons, 14 analytical poses and 16 ocular
probes. The foot warning clears: its distance p95/height falls from
0.0004127899104 to 1.521471852e-8; side-view absolute depth p95/height falls from
0.1279753162 to 6.535261518e-9. No previously passing region adds a flag.
The existing left-hand review finding remains. Two existing degenerate triangles
elsewhere remain unchanged; this localized trial does not remove them. Small
sample-statistic changes on untouched regions reflect changed total surface
sampling; exact native signatures establish unchanged geometry.

**UNKNOWN:** behavior in actual SVR 2011 animation clips. Analytical poses do not
prove gameplay. Texture downsampling remains visible: original vs PSP textures on
identical geometry establish a separate blockiness issue. This trial preserves
the previous texture data to isolate the geometry change.

## Reproduce

Use the original HCTP 0600 PAC and the same user-owned PSP base as the previous
portable trial. Clone `desktop/profiles/hctp-v1.json` to a local experimental
profile; change only `ratios.Legs` to 1.0. Set `desktop.core.PROFILE` to that local
profile in an experiment-only invocation and call `desktop.core.run_job` with
a `Request` and a fresh output directory. Verify `reduced.json` records Legs
retention 1.0, rather than a later budget fallback, before accepting the result.

This trial reused the previous job's `prepared.json` and texture-cap-32 GIMs,
invoking `desktop/geometry_worker.py` with the cloned profile, then the existing
`pack`, `serialize`, `compress(max_distinct=220)`, `replace_sections`,
`validate_pac` and `ocular_checks` functions. Packaging code was unchanged.
Run `python -m model_qa compare` with the original PAC, candidate PAC, previous
report's `thresholds` saved as the profile, both intermediate stages, 24000 samples
and resolution 320. The companion JSON and ZIP contain hashes and reports.

## Test

Back up your current PAC/ISO and inject `Jericho-SVR2011-PSP-leg-retention-TEST.pac`
using your established PAC Editor/ARC-update workflow. Check entrances, walking,
knee bending, crouching, facial motion and victory animations in PPSSPP. Retain
the accepted version until this candidate passes those checks.

The review ZIP contains the exact PAC, embedded YOBJ, Noesis-previewable OBJ/MTL/PNG
export, textured views, five fixed-camera source/before/after leg comparisons,
full before/after QA JSON, and the after HTML report/renders. These images are CPU
preview/QA renders, rather than Noesis or game captures. No proprietary tools are
included; this separate test bundle is excluded from the portable application.

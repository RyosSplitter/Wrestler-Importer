# 0101 source skinning identity — experimental test

The source already contained 15 coincident locations with different bone influences.
Position-only welding/cache lookup incorrectly combined or rejected those records.
This candidate preserves their topology and weights instead of averaging them.

| Version | Vertex records | Triangles | Native buffers / intermediate meshes | PAC bytes |
|---|---:|---:|---:|---:|
| Original HCTP | 4,096 | 4,974 | 23 | 669,696 |
| Pinned old minimum-profile reducer | 3,253 | 3,488 | 26 | No valid PAC: packing aborted |
| Corrected experimental PSP | 3,264 | 3,675 | 41 | 145,408 |

Configured budget: 148,000 bytes; headroom: 2,592 bytes.
41 native vertex buffers become 88 Noesis material draw groups. These counts
measure different structures, and neither is an arbitrary count target.

PAC: `0101-PSP-source-skinning-identity-TEST.pac`
SHA-256: `ac79307a694234dabb43e43266e22c64eea52d7607d4f841d66f5443cb81d21f`

Validation: all 33 records and 80 protected faces survive native decoding;
zero added contact motion/gap error over seven analytical poses. Seven-pose
regional nonregression passes at 24,000 samples per direction. Full existing
QA has 14 body/facial poses plus head/eye stress checks. Native structure,
ocular, precision and source-record checks pass. 312 automated tests pass.

The full report still has 47 review warnings, including ordinary limb/material
seams, open-surface topology and provisional controller/layout questions.
This is not an all-clear or an in-game validation result. Noesis may show boot/
knee cutout/seam irregularities; those remain review items rather than being
silently smoothed or assigned averaged weights. PPSSPP testing remains required.

Budget: existing Default texture generation, existing 32-cap fallback and .35
free-limb ratios. Sensitive source contact surfaces are preserved. Only normal
precision is reduced for compression (maximum 0.183586 degrees); geometry
positions, UVs and weights are unchanged by that fitting step. The existing
single-slot compatibility stage adds zero weights to two meshes. Donor bone
bytes and stored opaque PAC section 8 remain exact. Packaging code is unchanged.

The ZIP contains the following files.

## Review

- `ALL-15-LOCATIONS.md`: every location and source record IDs.
- `all-15-source-native-records.json`: original, prepared and native weights,
  positions, UVs, materials, palettes, stride and flags for every record.
- `contacts/report.html`: 120 source / failed-old / corrected comparisons.
  These are CPU clay renders and analytical PSP-rig poses, not Noesis/game captures.
- `regional-nonregression.json`: regional before/after p95 errors and tolerances.
- `qa/report.html`: full static, pose, multiview and stage-trace QA, with warnings.
- `audit/`: native binary validation, mesh/submesh and weight CSVs.
- `preview/output.yobj`: exact decoded section 2 of the supplied PAC.
- `preview/output.obj` + `preview.mtl` + `texture_*.png`: Noesis-ready static export.
- `preview/Noesis-native-rear.png`: actual Noesis 4.466 capture opening this PAC.
  Noesis static plugin reports zero bones because it does not expose an animation
  rig; the PAC retains the verified 79-bone PSP donor skeleton.
- `textures-32/`: selected GIM/PNG files and texture manifest.
- `controls/`: reproducible source/prepared and pinned old reducer controls.
- `size-fit.json`, `precision-validation.json`, `skin-compatibility.json`:
  actual budgets, precision and existing skin-layout checks.

Open the OBJ with its MTL/PNG siblings together; use F3/F4/F5 as needed for the
orientation/culling/shading view. Direct PAC viewing needs the repository's
`plugins/noesis/fmt_00_wwe_psp_yobj.py` (load it before conflicting PS2 PAC plugins).
Noesis meshes/materials are preview draw groups, not hardware limits.

## Import test

1. Back up the original ISO and destination wrestler PAC. Use a separate test ISO.
2. Inject the supplied whole PAC into the intended wrestler slot in SVR 2011's
   CH.PAC using your established PAC Editor workflow.
3. Rebuild/update the archive and save the ISO as you did for successful trials.
   Do not inject `output.yobj` as if it were a whole PAC.
4. Start a fresh game session in PPSSPP and check standing, walking, bent knees,
   crouching, toe/boot motion, facial motion, entrance, match and victory.
5. Report any new seams, contact separation, distortion or crashes. The analytical
   tests cannot determine whether original HCTP controllers have identical
   semantics in every real PSP animation.

This candidate is isolated on `experiment/source-skinning-identity`. Main,
accepted baselines and the released Windows app are unchanged.
See `docs/source-skinning-identity.md` for root causes and reproduction commands.

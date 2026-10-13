# RVD 0400 — singlet-detail texture allocation test

Inject **RVD-0400-Singlet-Detail-TEST.pac** for the improved version.
`RVD-Priority-control-TEST.pac` inside the review ZIP is the lower-detail comparison
control. Both were built from the uploaded original 0400 and existing PSP Kurt
base. Neither has been tested in-game by this experiment.

The improved PAC is **147,456 bytes**, within the configured 148,000-byte cap.
SHA-256: `76c42c211151aca43fc883deeea1eb29983b0c149942ae185ff8d1d73eff1476`.

| Texture | Priority control | Improved candidate |
|---|---|---|
| Front `rvd_mae` | 32×16 / 16-color slots | 128×64 / 16-color slots |
| Back `rvd_usir` | 64×16 / 16-color slots | 128×32 / 16-color slots |

Only those two GIMs change relative to this control. The other 17 textures,
all stored and decoded non-texture sections, and the complete model/rig are
byte-identical. Compared with Default, the control already includes earlier
Priority donor decisions; the "two changes" guarantee is relative to the control.

The modeled padded pixel/CLUT allocation rises from 26,432 to 31,808 bytes.
The explicit experimental envelope is 34,176 bytes, the lowest modeled native
allocation in the 110-PAC census. This observation supports a trial; it is not
proof of the game's actual heap ceiling, loader semantics or runtime safety.
The production app still uses its existing memory policy.

Structural checks pass: pointers, relocations, sizes, allocation bounds, vertex/
index ranges and alignment, palettes/weights, GIM and material controls. Fourteen
analytical body/facial poses plus 37 head/eye probes show exactly zero comparative
motion changes. 316 repository tests pass. All cutout textures stay byte-identical.

The inherited baseline QA has 43 human-review flags; this texture-only change
neither repairs nor waives them. Baseline diagnostic QA used 6,000 surface samples
and 128-pixel comparisons. Comparison texture/model renders use 512 pixels.
Static and analytical results do not certify gameplay compatibility.

## Preview and reports

- `texture-comparison.png`: original / existing Priority / improved singlet maps.
- `model-front-comparison.png`, `model-back-comparison.png`: identical cameras,
  geometry and lighting, existing versus improved. Offline CPU renders.
- `preview/Noesis-native-rear.png`: actual Noesis 4.466 opening the improved PAC.
- `preview/output.yobj`: exact decoded model section from the supplied PAC.
- `preview/output.obj`, `preview.mtl`, named PNG/GIM siblings: standalone preview.
  Keep the folder together. Direct PAC preview works with the repository's PSP
  Noesis plugin; it reports zero bones because it provides static rendering only.
- `report.html` / `report.json`: configurations, source quality ceilings, alpha,
  metrics, actual allocations, structural audit, model preservation and pose proof.
- `diagnosis-ato`, `diagnosis-priority`: reproduced current-policy results.
- `general-optimizer`: the unchanged allocator independently chooses the same
  singlet detail with an explicit 34,176-byte limit. It also alters two hand maps,
  so its PAC is intentionally not the cleaner two-texture test being distributed.
- `baseline-qa`: inherited geometry/pose report and all review flags.
- `DEVELOPMENT-NOTES.md`: root cause, uncertainty and reproduction commands.
- `SHA256-MANIFEST.json`: checksums for every bundle file.

## PPSSPP test

1. Back up the destination wrestler PAC and ISO; use a separate test ISO.
2. Inject the improved whole PAC into your intended SVR 2011 PSP wrestler slot
   using the PAC Editor workflow that worked for your previous trials.
3. Update/rebuild the archive and save the ISO. The YOBJ is a preview, not the
   whole PAC to inject.
4. Start a fresh session. Compare front/back singlet readability, then test a
   complete entrance, a match with several opponents/arenas, and victory motion.
   Repeat matches to look for intermittent crashes or unrelated geometry issues.
5. Report visual results and any crashes. PPSSPP logs/debugger output would help
   distinguish allocation problems from archive/injection or existing rig issues.

Main, accepted baselines and the released Windows app remain unchanged. This is
an isolated experiment on `experiment/rvd-texture-budget`; the policy should be
integrated only after gameplay validation and further reference-model testing.

Jericho tights priority reallocation, v0.25.5 experimental

Use Jericho-PSP-Tights-Priority-Reallocation-TEST.pac for the controlled texture-only test. Its YOBJ is exact against your uploaded 0600-PSP-experimental.pac. Final size 147456 bytes. Only y2j_mata and y2j_face GIMs changed. Tights: 32x8 -> 128x64 (T4/16 colors); face donor: 128x64 -> 64x64 (T8), with 31 -> 256 used colors. The face reclaims 4096 pixel bytes. Some face metrics improve and others worsen: inspect texture-comparison.png and textures/report.html. No full source fidelity or in-game safety claim.

Back up the uploaded PAC and your ISO/CH.PAC/ARC. Inject into the same intended slot using your previously successful SVR2011 workflow, repair CH alignment/rebuild and update ARC, save as a separate ISO. Check face/tights during entrance, gameplay, crouching and victory animations, and watch for unrelated ring geometry corruption.

CPU before/after renders are offline previews, not game/Noesis screenshots. Preview/output.yobj was extracted from the exact delivered PAC. Open preview/output.obj in Noesis with preview.mtl and all PNGs alongside it; use your normal orientation/culling/shading toggles.

Verification includes exact non-texture stored/decoded payloads, native validation, deterministic repeat, app-worker source-derived QA completion and local UI smoke. QA findings are preserved rather than relabeled passes. The generated fixtures test allocator logic without game assets. Main and accepted baselines remain unchanged.

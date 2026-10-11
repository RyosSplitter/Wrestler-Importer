Maximum Downgrade controlled trial, v0.25.4

Use only Black-Biker-Shorts-PSP-Maximum-Downgrade-EXPERIMENTAL.pac as the game candidate.
Back up your existing ISO/CH.PAC and ARC before injection. Replace the intended EMD wrestler PAC slot, rebuild CH.PAC to repair alignment, then update its ARC using your established working workflow. Save a separate ISO and test in SVR 2011 PSP/PPSSPP. Check entrances, normal matches, crouching/bending, victory motions, repeated loads and unrelated ring geometry.

The accepted baseline PACs were not overwritten. This trial is 147456 bytes. Texture fitting changes only section9; all YOBJ/model and other stored/decoded data remain exact against the existing converter's validated intermediate. The preexisting bounded-precision geometry fallback was required by this source and remains separate from texture fitting. Review verification.json and texture-report/report.html. CPU previews are offline renders, not Noesis or in-game screenshots.

Preview: output.obj + preview.mtl + all texture PNGs belong together in preview/. Open the OBJ in Noesis and use your usual orientation/culling/shading toggles. output.yobj is extracted from the delivered PAC.

Full QA: qa/report.html. Static, pose, head, and review results are numerically identical before/after texture fitting;47 existing human-review findings remain. This is not a new all-regions-pass claim. Verification.json records exact comparisons. Geometry counts:51 meshes,2875 vertices,2576 triangles before and after.

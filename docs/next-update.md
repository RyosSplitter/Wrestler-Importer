# Next update notes

## Rock scalp: single-slot skinned buffers — implemented in v0.25.1

User-requested follow-up: accommodate the scalp compatibility issue in the next
update, including QA coverage for head shape and unusual skinned-buffer layouts.

- **CONFIRMED:** The failing uploaded Rock PAC has intact stored scalp geometry.
  The isolated three-slot control preserves effective weights, geometry, textures
  and all unrelated PAC sections. Structural checks and analytical pose tests
  pass; its PAC size remains 147,456 bytes.
- **INFERRED:** A one-slot float-weight skinned buffer may be interpreted
  differently by the SVR 2011 loader. The native reference subset supports
  reviewing this layout, but does not establish a mandatory three-slot minimum.
- **CONFIRMED (user report):** After requesting the update, the user reported
  that the Rock model looked good. This supports the isolated compatibility
  adaptation. Exhaustive animation/crash validation remains unrecorded.

Tracking record: these integration requirements informed the isolated update.
See [implementation and validation](portable-scalp-compatibility.md). Broader
runtime testing and any main-branch promotion remain separate decisions.

Requirements:

1. Record the control's PPSSPP result against the original failing PAC, including
   entrance, standing, match and victory animations.
2. If supported, generalize the tested zero-weight slot padding as compatibility
   handling for affected layouts; calibrate against additional native and
   converted samples rather than hard-coding a Rock-specific rule.
3. Keep the full-head, culling and analytical pose QA checks. Report unusual
   layouts as review findings until evidence supports a stronger requirement.
4. Verify unchanged positions, normals, UVs, effective nonzero weights, textures
   and unrelated sections; validate offsets, palettes, alignment, PAC size and
   the increased decoded vertex-buffer allocation.
5. Preserve accepted PACs and the working texture pipeline. Keep experiments
   separate from main until gameplay validation and an integration decision.

Evidence, hashes, reproduction commands and control downloads:
[Rock scalp layout control](rock-scalp-layout-control.md).

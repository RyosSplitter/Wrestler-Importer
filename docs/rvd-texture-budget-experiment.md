# RVD singlet allocation experiment — 0400

This isolated experiment is on `experiment/rvd-texture-budget`. Production texture
generation, app settings, accepted assets and main are unchanged. Runtime results
must precede promotion of any new texture-memory policy.

## Evidence and failure

**CONFIRMED:** The uploaded HCTP `0400.pac` is 497,920 bytes, SHA-256
`4ac1ee9637cdf3d9d84669ef1ae63ab53a71b89cedb399f0da13e846e9854a1a`.
Its `rvd_mae` front texture is 256×128 and `rvd_usir` back texture is 256×64.
Both decode as indexed8 RTX3 with 256-entry 32-bit palettes, with clear artwork.
The existing Kurt PSP donor hash is
`bf935a51fe30bfd2df929f8eb9e50be5d793426ea05125ca9411ce21b19ead80`.

**CONFIRMED:** Current Default uses 32×8/T4 for both maps in the fitting pass.
ATO keeps 32×8/T4. Priority Selection with both maps selected reaches only
32×16/T4 front and 64×16/T4 back. Their 143,360-byte PACs have a whole padded
block of remaining storage, but exhaust the 26,432-byte modeled pixel/CLUT
allowance derived from Default. That includes 6,336 bytes in retained texture
tables, and 20,096 in the main costume table. Face/hair/eyes consume 16,384 of
the costume allocation. These quantities exclude GIM headers and count actual
padded/swizzled pixel planes and fixed palettes.

**CONFIRMED:** Under the existing legal candidates and cranial/alpha safeguards,
the minimum allocation for everything except the two selected maps is 25,536
bytes. Only 896 remain for both singlet maps. Even a 64×32 front plus minimum
32×8 back would require 26,816 total, 384 over policy. This explains the stalled
priority result independently of the greedy allocator. It does not prove that
every possible format or different safeguard set must have the same minimum.

**CONFIRMED:** The native census of 110 uploaded PSP PACs/2,008 GIMs in
`docs/texture-quality-v025-native-summary.json` reports modeled pixel/CLUT
allocations from 34,176 to 87,872 bytes. The experiment explicitly uses **34,176**
as an initial reference envelope instead of the aggressive Default result.
Native observations support trying this allocation; they are not an engine heap
measurement or proof that arbitrary converted geometry/texture combinations work.

## Controlled candidate

**CONFIRMED:** `experiments/texture_budget_trial.py` rebuilds only texture table 9
over a frozen, validated PSP PAC. Names/resolutions are explicit user selections,
not character hash/name patches. It decodes the source again, uses the existing
source-bounded native candidate encoder, keeps the material bit depth, and
measures both existing BPE variants through the unchanged aligned PAC writer.
Invalid or oversized candidates get a report but no injectable PAC.

| Property | Existing Priority control | Fixed detail trial |
|---|---:|---:|
| Front `rvd_mae` | 32×16 / 16 slots | 128×64 / 16 slots |
| Back `rvd_usir` | 64×16 / 16 slots | 128×32 / 16 slots |
| PAC bytes | 143,360 | 147,456 |
| Modeled pixels/CLUT, including retained tables | 26,432 | 31,808 |
| Front occupied-area luminance SSIM | 0.470583 | 0.871192 |
| Back occupied-area luminance SSIM | 0.701258 | 0.904553 |
| Front fine-feature loss (lower is better) | 0.601526 | 0.063111 |
| Back fine-feature loss (lower is better) | 0.286611 | 0.054637 |

**CONFIRMED:** Allocation increases by 5,376 bytes, below the explicit experimental
34,176-byte allowance. Final size is 544 below the configured 148,000 cap; there
is no additional 2,048-byte archive block available. Compression variant 200
stores table 9 in 20,644 bytes versus 20,692 for variant 220; both produce a
147,456-byte PAC. Table padding/compression must be measured rather than estimated.

**CONFIRMED:** Only two GIMs change relative to the Priority control. All 17 other
GIM payloads and all non-table-9 stored/decoded section bytes are identical.
The model YOBJ, geometry, normals, UVs, materials, skeleton, weight records,
bone palettes, indices, draw metadata and animation inputs remain byte-identical.
The native structural audit checks internal pointers/allocations, relocations,
index/vertex bounds and alignment, palettes/weights, GIM structures and material
controls. The preview YOBJ is the exact decoded PAC section 2.

**CONFIRMED:** Fourteen analytical body/facial poses and 37 cranial/ocular probes
have exactly zero comparative motion changes. The frozen model inherits the
Default conversion's QA report with 43 review warnings; texture changes do not
resolve or waive those geometry/controller/material-boundary concerns. Baseline
QA used 6,000 samples and 128-pixel renders for diagnosis, not a new high-density
anatomical acceptance certification. Texture renders use 512 pixels with identical
cameras/lighting. Actual Noesis 4.466 directly opens the published native PAC.

**CONFIRMED:** The diagnostic Default, ATO and Priority results were reproduced
from the same uploaded source and donor. Comparing the fixed candidate to
Default includes the earlier Priority donor decisions; "only two changed" refers
specifically to the supplied Priority control. Neither control was previously
validated in-game by this experiment.

## General optimizer control

**CONFIRMED:** Calling the unchanged general `optimize_pac` with both manual
selections, `rebalance_priorities=True` and `max_pixel_bytes=34176` independently
selects the same front/back resolutions at 147,456 PAC bytes and 32,064 modeled
allocation. The singlet GIM bytes match the fixed trial. Two unselected hand maps
also differ, so this alternate result is documented rather than used as the
cleaner two-texture gameplay candidate. No character-specific allocation formula
is needed to recover the singlet detail.

**INFERRED:** An independently calibrated pixel/CLUT profile can avoid trapping
the optimizer inside a poor Default allocation. This one model supports the
direction, not a universal policy. Manual priority also needs a meaningful-detail
acceptance/reporting rule for other models; the existing score alone is not a
guarantee of legible artwork.

**UNKNOWN:** Actual runtime heap/VRAM behavior, allocation lifetime during
entrances/victories, fragmentation, auxiliary effects and every animation state.
Static renders, the census and byte-identical rigs cannot certify runtime safety.
The candidate needs actual SVR 2011 PPSSPP testing before any app policy changes.

## Reproduction and tests

**CONFIRMED:** The published ZIP includes the Priority control PAC, improved PAC,
PNG/GIM/OBJ/MTL/YOBJ preview, same-camera front/back comparisons, actual Noesis
rear capture, native/pose/quality report, baseline QA and general-optimizer
reports, diagnostics, input hashes and SHA-256 manifest. It omits the original
source/donor PAC and third-party executables.

Obtain your own original input, then run:

```sh
python -m experiments.texture_budget_trial 0400.pac \
    RVD-Priority-control-TEST.pac new-output \
    --texture rvd_mae=128x64 --texture rvd_usir=128x32 \
    --experimental-pixel-limit 34176
python -m unittest tests.test_texture_budget_trial
python -m unittest discover -s tests
```

**CONFIRMED:** The source decoder/candidate encoder is shared with the converter.
The new generated tests cover frozen native model/poses, preview material mapping,
source ceiling and separate file/allocation failures without game assets. All
316 repository tests pass. Output directories and input assets are never
overwritten. Existing app Default/ATO/Priority behavior is not modified here.

**CONFIRMED:** Published candidate SHA-256:
`76c42c211151aca43fc883deeea1eb29983b0c149942ae185ff8d1d73eff1476`.

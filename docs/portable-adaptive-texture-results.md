# v0.25 experimental adaptive texture results

Date: 2026-10-10. Branch: `experiment/content-aware-textures`; runtime revision:
`7492d7ed674b34a3f05147dbac1206b2f606692f`. Main and accepted PACs are unchanged.
See [implementation and scoring](portable-adaptive-textures.md) and the
[native texture census](texture-quality-v025.md). Evidence labels apply to each
paragraph/table: CONFIRMED means measured implementation/binary/test evidence;
INFERRED means a proposed visual-quality policy; UNKNOWN means untested behavior.

## Deliverables and A/B procedure

**CONFIRMED:** The checkbox **Adaptive Texture Optimization (Experimental)** is
OFF on every launch. OFF uses the existing generator and size-fitting behavior.
ON preserves that exact baseline and runs a separate frozen-payload texture stage.
It does not request extra decimation or change any YOBJ byte. Convert the same
source/base once with OFF and once with ON; keep the same other options. Save both
under different names. Each adaptive job retains its own baseline and detailed
HTML/JSON report, candidate list, rejected upgrades and review flags.

* [Tested Windows build](https://github.com/RyosSplitter/Wrestler-Importer/releases/tag/portable-preview-17-7492d7ed674b34a3f05147dbac1206b2f606692f)
* [Five-model A/B bundle](../downloads/PS2PSP-v0.25-adaptive-texture-AB-bundle.zip)
* [Rock adaptive PAC](../downloads/Rock-v0.25-content-aware-adaptive-EXPERIMENTAL.pac)
* [Rock full comparison](../downloads/content-aware-textures/Rock-front-left-comparison.png)
* [Rock face comparison](../downloads/content-aware-textures/Rock-front-left-face-comparison.png)
* [Machine-readable summary](../downloads/content-aware-textures/summary.json)
* [Every Rock texture configuration and metric](../downloads/content-aware-textures/Rock-texture-comparison.csv)

The bundle contains both PACs for each case, separate Noesis-compatible
OBJ/MTL/PNG/YOBJ previews, individual texture comparisons, five matching camera
views and enlarged face panels, hashes and reproduction instructions. Renders
are the existing CPU renderer, **not Noesis or PPSSPP screenshots**. Enlargement
of illustration panels does not upscale any serialized texture. Original game
PACs and a redistributable PSP donor are not included.

## Frozen-geometry trials

**CONFIRMED:** All five candidates pass native structure/pointer/alignment,
vertex/index/palette/weight checks and the 148,000-byte file cap. All decoded
non-costume sections are identical; all stored YOBJ/model/material sections are
also identical. Only costume textures and lossless storage of retained GIM tables
change. Pointer relocation and padding follow the existing packer. The baseline
pixel/CLUT envelope is never exceeded.

| Source | Current bytes | Adaptive bytes | Mean texture SSIM, current → adaptive | Importance-weighted combined loss, current → adaptive |
|---|---:|---:|---:|---:|
| Rock `0000` | 143,360 | 147,456 | .8043 → .9032 | 7.7405 → 5.0521 |
| Lance `1800` | 137,216 | 135,168 | .8677 → .9210 | 4.9611 → 3.4787 |
| Jericho `0600` | 147,456 | 147,456 | .8138 → .8633 | 7.9208 → 6.5818 |
| Benoit `0900` | 120,832 | 118,784 | .8431 → .8862 | 5.7347 → 4.9208 |
| `0401` budget regression | 147,456 | 145,408 | .7893 → .8059 | 10.6164 → 10.2849 |

**CONFIRMED / interpretation INFERRED:** SSIM is the arithmetic mean of the
occupied-area per-texture luminance comparisons, not a whole-render score.
Combined loss additionally measures RGB, oriented gradients, fine features and
high-frequency residuals; lower is better. Different models have different
importance totals, so compare paired results, not absolute loss between wrestlers.
These scores differ from the previous research metric definition. Aggregate
improvement does not mean every map improves every metric. Review flags disclose
individual regressions and severe reductions. These baselines are the current
converter outputs, not a claim that they equal every older human-accepted PAC.

## Rock allocation and visible tradeoffs

**CONFIRMED:** The source hash is
`d1d5ca744b5a793743851c142bf273554c81076ae3b8231834364559e048a973`.
The current output hash is
`ae56c7e0f18f230a865790a5f7bb18796003c354c65fa1f1be744e1c4581a16e`;
the final adaptive output hash is
`a36d20b854f7e51843345179c8eabf8c9bcebd8d55926fd67d97387bcd8d9eab`.
The full end-to-end run reproduced that exact current output hash.

| Map | Source | Current | Adaptive | Measured result |
|---|---|---|---|---|
| Face | 256×256, 256 used colors | 128×64, 20 used colors/T8 | 64×64, 256 used colors/T8 | SSIM .851 → .911; fine-edge recall regresses and requires review |
| Tattoo shoulder | 128×128 | 64×32/T4 | 64×64/T4 | SSIM .647 → .826; detail covers 54.39% of occupied area |
| Front trunks | 128×64, 16 used colors | 32×32/T4 | 128×64/T4 | Decoded source RGBA exact; SSIM 1.0 |
| Rear trunks | 128×64 | 32×32/T4 | 64×32/T4 | SSIM .628 → .800 |
| Torso | 128×128 | 64×32/T4, 11 used colors | Exact incumbent retained | Larger alternatives lose to budget/footprint constraints |
| Thighs | 128×128 | 64×32/T4 | Exact incumbent retained | Prevents an earlier unnecessary quality loss |
| Eyes | 32×32 | 32×16/T4 | 32×32/T4 | SSIM .899 → .925 |
| Constant mouth map | 8×8, one color | Upscaled 32×8/T4 | Source 8×8/T4 | Same visible color, legal padded rows, no upscaling |

**CONFIRMED:** T4 remains T4, and T8 remains T8. Changing material controls to
upgrade a T4 tattoo/torso to T8 would violate this experiment's immutable-material
contract. Fixed physical CLUT slots are distinguished from useful colors. No
texture exceeds the source dimensions or actual useful color ceiling. The face
trades resolution for color information; it is not universally sharper.

**CONFIRMED:** Rock measured 601 actual rebuilt PAC combinations. Its stored model
sections total 124,477 bytes; with the PAC header, non-texture allocation is
124,525 bytes. The effective aligned cap is 147,456, giving 22,931 nominal bytes
for all stored textures and texture-related alignment. Retained section 8 takes
4,010 bytes after lossless BPE storage instead of 7,072, so costume table 9 has
18,921 available bytes before remaining alignment. It uses 18,164; alignment and
tail padding use 757. Total stored textures are 22,174 bytes. The final file has
544 bytes below the configured 148,000 cap but no additional aligned block.

**CONFIRMED:** Decoded costume table size stays 26,464 bytes. Total padded pixel
and CLUT data stays **28,224 bytes**, including retained effects. More varied
colors can increase compressed size without increasing decoded allocation. This
data envelope is a conservative guard, **not a measured game memory limit**.

## Validation and failure history

**CONFIRMED:** The final local suite has 235 passing tests, including 31 adaptive
tests. Cases cover dimensions/colors, actual source usage, blank/tiny/wide detail,
monochrome patterns, gradients, rectangular/narrow images, cutout/near-opaque alpha,
UV occupancy, rejected layouts, bad GIM pointers, deterministic scoring,
serialized-budget recovery/exhaustion, independent pixel budget and exact payload
preservation. Fixtures are synthetic, not game-derived test assets.

**CONFIRMED:** Windows workflow
[38083936955](https://github.com/RyosSplitter/Wrestler-Importer/actions/runs/38083936955)
passed its then-current 232-test suite, frozen GUI/runtime smoke, three unchanged
legacy conversion/QA jobs including multi-YOBJ accessories, and the adaptive frozen
worker with exact model verification. Later source changes add three host tests
and documentation only; shipped runtime revision is unchanged. This is hosted
Windows validation, not a fresh user PC or actual game run.

**CONFIRMED:** Rock also completed the full 24,000-sample comparison suite with
standing, both walk poses, bend, crouch, shoulders, neck/head, four jaw poses and
both elbow poses; ocular checks passed. Existing human-review findings were
retained rather than hidden. The full QA run used an intermediate adaptive
texture selection; the published selection has exactly the same stored YOBJ
payloads. The bundle supplies an explicit hash/equality proof; geometry/pose
measurements are applicable, while final texture appearance uses the final renders.

**CONFIRMED failures and resolutions:**

* A forced independent edge-recall floor rejected a better-colored Rock face.
  Palette-band edges can distort that metric. Sensitive-region guards now combine
  sampling, useful colors, SSIM and combined loss; individual detail loss is reported.
* Rejecting every anisotropic legacy layout discarded useful existing torso/thigh
  representations. Source-bounded, alpha-safe exact incumbents are now eligible.
  New candidates remain proportional; unchanged unobserved layouts are flagged.
* Native T8 32×16 was not observed, but the established Benoit cutout already uses
  that layout. Its exact incumbent is retained without generating new unsupported
  layouts, and cutout dimensions/alpha remain exact.
* Reserving colors for every near-opaque alpha stratum damaged Jericho lip color.
  A measured joint near-opaque RGBA option maps alpha back to source levels. True
  cutouts never use that lossy option; alpha errors remain visible in reports.
* The initial Windows legacy hash test assumed Linux byte identity. Actual pinned
  Pillow platforms produce different legacy bytes. Same-platform old/new output
  remains identical; both observed hashes are now recorded, without changing the
  legacy generator. Cross-platform identity is not claimed.

## Reproduction and pending game tests

**CONFIRMED:** From a pinned Python 3.13 environment with the repository requirements:

```
python -m unittest discover -s tests -v
python -m desktop.texture_optimizer --source 0000.pac --baseline current.pac --output rock-ab
python -m experiments.content_aware_texture_validation --case Rock rock-ab --output review-bundle
```

The assembly helper accepts the CLI's output directory directly. The bundle
records each source hash and the measured dependencies. For full UI/worker reproduction, use your own
HCTP source and PSP donor, and retain the ordinary converter's geometry/profile
settings; do not substitute source formats or silently merge experimental branches.

**INFERRED recommendation:** Keep the checkbox OFF by default until PPSSPP trials
confirm the paired candidates. The deterministic greedy allocator measures real
compressed costs and diminishing returns but is not a global optimum and can miss
paired swaps. Individual perceptual heuristics need visual tuning. Presets and a
material-depth-changing optimizer are separate future decisions, not added here.

**UNKNOWN:** Native corpus layouts do not prove acceptance of every new combined
candidate; actual peak loader/heap/VRAM limits are unmeasured. Test entrance,
multi-wrestler matches, facial animation, victory, blood/cutouts and independent
elbow-pad removal. Compare tattoos, logos, skin bands and eyes in motion. No
candidate in this bundle is certified as in-game validated.

# v0.25 content-aware adaptive textures (isolated experiment)

The checkbox **Adaptive Texture Optimization (Experimental)** defaults OFF on
every launch. OFF runs the established texture generator and size fitting
unchanged. ON first builds that same baseline, retains it as
`work/current-texture-method.pac`, then runs a separate texture-only stage.
No changes have been merged into main. Actual SVR 2011 gameplay is unverified.

## Scope and contracts

**CONFIRMED:** `desktop/core.py::textures` is unchanged; a captured deterministic
fixture and an independent execution of its previous revision produce identical
GIM bytes. Geometry fitting, selective weights, precision fallback, native model
construction and QA are the same for both modes. The experimental stage cannot
invoke extra decimation or alter any YOBJ byte. Every stored model/material
section and every unrelated section payload is compared byte-for-byte.
Existing aligned PAC repacking relocates container pointers when sizes change.

**CONFIRMED:** The 110-PAC / 2,008-GIM native census supports indexed4 and
indexed8 images with linear RGBA8888 CLUTs and 16-byte × 8-row swizzling. The
experimental candidate whitelist is the **observed dimension AND bit-depth
combination**, not generic PSP hardware capability. T4 has 22 observed dimension
pairs (8×8 to 256×256). T8 has 11: 32×8, 32×32, 32×64, 32×128, 64×16, 64×32,
64×64, 64×128, 128×32, 128×64, 128×128. This conservatively excludes unobserved
T8 256×256 and T8 16×16 layouts without calling them hard hardware restrictions.
See [the native budget research](texture-quality-v025.md) for binary tables.

**CONFIRMED:** Narrow images receive padded byte rows, not upscaled dimensions.
An 8×8 T4 GIM has 128 pixel bytes plus a 64-byte CLUT and 208 bytes of headers.
The original reader/writer remain unchanged; optional decoder arguments are
supplied only for the adaptive validation, table construction and preview path.

**CONFIRMED:** A palette-depth change in this converter's rendering contract
requires changing a YOBJ material control. This task requires immutable materials,
so incompatible T4/T8 candidates are reported and rejected. For an existing T8
material, both 16-useful-color and up-to-256-useful-color candidates use its fixed
256-slot CLUT. For a T4 material, only its 16-slot format is eligible. Unused CLUT
slots are storage overhead, not extra useful color capacity. This restriction
deliberately differs from earlier research that allowed control-field edits.

## Modular analyzer and scoring

`desktop/texture_optimizer/analysis.py` uses NumPy, Pillow and SciPy already
present in the app. There is no AI model, network service or new dependency.

**CONFIRMED implementation / INFERRED perceptual policy:**

* Occupied area weights alpha and a rasterized union of decoded material UV
  triangles. UV masks are used only for finite coordinates within [0,1]; wrapping
  or empty masks fall back to alpha occupancy. Opaque blank padding is not guessed
  to be unused. This avoids treating an arbitrary skin/background color as waste.
* Luminance Sobel gradients and Gaussian high-frequency residuals measure detail.
  Detail coverage is the occupied-area fraction above edge/residual thresholds.
  Invisible/unused boundaries are excluded from original feature aggregation.
* Reduction sensitivity is an actual Lanczos half-resolution probe compared with
  the original. Texture importance is not inferred from source dimensions alone.
* Optional model coverage is the texture's fraction of total decoded triangle
  area across body/accessories. It is **not** camera visibility, overdraw, draw
  frequency or authoritative UV occupancy in animation.

The default importance formula is:

```
I = (.6 + 1.6*detail + .8*coverage + 1.2*half_resolution_loss) * area_factor
area_factor = .75 + .5*sqrt(min(surface_fraction*20, 4))
area_factor = 1 when model coverage is unavailable
```

Candidate source-sized reconstructions use Lanczos and occupied-area weighting.
The combined loss is:

```
L = .22*RGB_RMSE/255 + .15*(1-SSIM)
  + .30*min(oriented_gradient_error,2)/2
  + .23*fine_feature_loss + .10*min(high_frequency_error,2)/2
```

The gradient term compares direction and magnitude, rather than only global
SSIM. Fine-feature recall compares source high-contrast edges with candidate
edges in a small neighborhood. This measure can over-credit false palette-band
edges: real Rock testing showed a hard independent edge-recall cutoff rejecting
a face with better color, SSIM and combined error. Consequently sensitive-region
guards use combined error, SSIM, sampling and useful-color floors; individual
detail regressions are reported for visual review. The formula is adjustable in
the analyzer and explicitly remains a heuristic, not a trained perceptual model.

## Candidates and source ceilings

**CONFIRMED:** Width/height never exceed source width/height. Newly generated
dimension reductions are proportional and within the native whitelist.
Rectangular images remain rectangular. A baseline image is additionally retained
as an explicitly labeled incumbent if it already obeys source dimensions/colors,
the native layout and alpha safeguards. Such an incumbent can have anisotropic
sampling; normalized UVs and its pixels are left intact. An optimizer should not
discard a good legal existing representation just because its pixel aspect differs
from source. Upscaled legacy maps and alpha-flattened maps are not eligible.
No new aspect stretching, sharpening, super-resolution or geometry/UV compensation
is performed. Every incumbent's sampling-aspect status is reported.

The useful color ceiling is actual visible source RGBA usage, plus one canonical
fully transparent entry where required—not the declared PS2 palette capacity.
Each candidate's quantizer requests at most that ceiling and the applicable
CLUT capacity. Even Lanczos-generated intermediate colors are quantized within
this bound. Fully transparent hidden RGB is discarded; alpha and visible pixels
are what matter. Exact full-size source representation is recognized where legal.

Opaque candidates evaluate deterministic median-cut, maximum-coverage and octree
quantization without dithering, choosing by combined loss. Exact palettes bypass
quantization. Sensitivity and candidate metrics are measured on decoded GIMs.

**CONFIRMED alpha handling:** Cutout images (any alpha below 128) retain original
dimensions and every alpha sample; RGB can be palette-quantized independently,
with colors partitioned by alpha level. A format with too few slots for exact
cutout alpha levels is rejected. Near-opaque images may reduce resolution using
nearest alpha sampling. If many alpha levels compete for a fixed CLUT, they are
quantized to representative **source alpha levels**, all >=128, while reserving
RGB entries per level. A joint near-opaque RGBA alternative is also measured,
snapping its palette alpha to source levels; rare alpha strata otherwise consume
slots needed for visible lip colors. This is a disclosed lossy policy, not exact source-alpha
preservation; alpha MAE and review flags are reported. Cutout boundaries never
pass through that lossy policy. Hair/mask filename guesses are unnecessary.

Minimal cranial safeguards use verified PSP bone support, not wrestler IDs or
texture names: minimum sampling axis is the existing/source minimum, useful color
floor is existing/source actual usage, and candidate combined loss/SSIM cannot
regress beyond recorded tolerances. These are experimental quality policies, not
loader limits. No fixed face/body output size or universal non-face color rule
is introduced.

An unchanged existing GIM layout may be absent from the 2011 census (Benoit's
exact 32×16 T8 cutout is an example). It can remain as a ceiling-compliant
incumbent because this introduces no new layout or pixels; the absence of a
native observation is not proof that the already-established writer is invalid.
Such retention is explicitly flagged for gameplay confirmation. Newly generated
candidates still use only the observed layout whitelist.

## Actual PAC budget allocator

**CONFIRMED:** The current target remains 148,000 bytes, permitting at most
147,456 after 2,048-byte padding. The non-texture allocation is the real stored
sections plus the actual 8+8*N PAC header. Alignment and tail padding are reported
separately. Every trial rebuild uses existing PAC/table/BPE functions; no new
container grammar or model compressor is introduced.

The allocator starts with the cheapest safe GIM for each required texture. It
then evaluates improving alternatives and measures:

```
upgrade value = I * (old L - new L) / max(actual additional PAC bytes, 1)
```

Each evaluation rebuilds and compresses the actual named texture table, trying
the existing 200/220-symbol dictionary variants, aligns sections, pads the PAC,
and measures final file bytes. A second constraint bounds padded pixel+CLUT data
by the existing baseline footprint, including retained effect tables. That
envelope is conservative; it is not a measured SVR heap/VRAM maximum.

Free/improving upgrades are taken first; otherwise measured marginal value per
byte chooses among feasible upgrades. Every candidate texture has a representation
before upgrades begin. If serialized minima unexpectedly exceed the budget,
the recovery pass chooses actual resource savings with the least weighted loss
per recovered byte. It fails explicitly when no legal recovery exists. This is
deterministic greedy allocation, **not exhaustive/global-optimum search**; it can
miss beneficial paired swaps. All improving single-texture upgrades are checked.

**CONFIRMED:** The optional stage also checks already-retained named GIM tables
for lossless BPE storage savings. It never regenerates those images. The decoded
table must compare exactly, unknown tables are untouched, and effects' data
footprints remain included. The prior Rock research demonstrated this storage
factor saving 3,062 bytes without changing blood pixels or model data. Actual
gameplay of a newly combined candidate still needs testing.

## Reports, failures and reproduction

Each successful job links `adaptive-textures/report.html` from the ordinary QA
report. `report.json` includes source dimensions/actual colors/source formats,
occupied/detail coverage, sensitivity, surface/UV coverage, importance, every
candidate/rejection, final configuration, used colors, encoded/padded costs,
metrics, allocation decisions, measured byte budgets, retained-table savings,
hashes and unchanged-payload proofs. Extremely reduced or individually regressing
textures receive explicit human-review flags. Failures retain
`failure-report.json`; no oversized candidate is saved as a successful export.

Texture-only reproduction from your own original HCTP and converted PAC:

```
python -m desktop.texture_optimizer --source 0000.pac --baseline current.pac --output rock-ab
```

This produces current/adaptive PACs, Noesis-compatible OBJ/MTL/PNG/YOBJ exports,
five matching view panels, individual texture comparisons and allocation reports.
The matching model renders use the existing CPU renderer, identical geometry,
cameras and lighting. They are **not PPSSPP or Noesis captures**.

For an end-to-end job, add `"adaptive_textures": true` to the existing worker
request and run `python ps2psp_converter.py --worker path/to/request.json`.
Omitting the property means OFF. Save As revalidates adaptive padded layouts with
the experimental reader; accepted inputs and baselines are never overwritten.

## Remaining validation

**UNKNOWN:** Actual runtime peak texture allocations, cache behavior, game-loader
limits, and new candidate appearance in SVR 2011. Native observations and pointer
validation do not prove gameplay compatibility. Test entrance, match, facial
motion, victory, blood and independent elbow-pad removal/throw behavior. Inspect
tattoos, small lettering, skin gradients, face/eyes, hair and masks in motion.

Tests cover ceilings, source used colors, transparent/near-opaque maps, narrow
padding, rectangular dimensions, monochrome detail, smooth gradients, tiny versus
wide detail coverage, UV masks, deterministic scoring, legal candidates, real
serialized budgets, compression inversion, independent pixel budget, legacy
reference bytes and unchanged non-texture payloads. Windows CI also verifies the
checkbox default and the frozen adaptive worker. Host tests do not replace that
packaged Windows check or PPSSPP validation.

**CONFIRMED platform finding:** The captured legacy reference texture hashes differ
between the pinned Linux and Windows Pillow runtime builds. Tests freeze both
observed platform hashes, and the previous/new legacy function was independently
compared on the same Linux runtime. Determinism means repeatable on the same
pinned runtime; cross-platform byte identity of native image processing is not
claimed. The initial Windows test incorrectly assumed the Linux hash and failed;
the generator itself was unchanged.

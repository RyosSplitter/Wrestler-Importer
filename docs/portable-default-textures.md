# v0.25.6 — content-aware Default textures

The tested RVD singlet allocation approach is now the Default texture stage.
The app automatically identifies dominant fine-detail losses; manual texture
selection is optional. **Legacy** retains the previous Default texture generator
and budget path. ATO retains the earlier adaptive comparison path. Accepted PAC
assets and main are preserved; this update is built on
`feature/default-texture-quality`.

## Evidence and scope

**CONFIRMED:** The user reported that the fixed RVD singlet trial came out great
after in-game testing. That trial stored front/back textures at 128×64/128×32,
kept their existing 16-color material contracts, used 31,808 modeled pixel/CLUT
bytes and produced a 147,456-byte PAC. The source/rig/model were unchanged by
the texture upgrade. See [the controlled trial](rvd-texture-budget-experiment.md).

**CONFIRMED:** The native corpus contains 110 PACs and 2,008 GIM records, with a
minimum modeled padded pixel/CLUT allocation of 34,176 bytes. Default now uses
`max(34176, legacy_actual_allocation)`, including retained texture tables. This
separates source texture allocation from the already degraded Legacy output
instead of treating that output as a hard universal memory ceiling. An existing
larger allocation is retained; this policy does not force it downward.

**UNKNOWN:** Actual SVR memory heap bounds, allocation lifetimes, fragmentation
and compatibility of every converted wrestler. Native observations and RVD's
specific result do not certify every model at the full reference allowance.
The 148,000-byte padded PAC cap remains enforced separately; its largest
2,048-aligned result is 147,456 bytes.

## Automatic attention and allocation

**CONFIRMED implementation:** `desktop/default_textures.py` inspects actual
source RGBA, the frozen native model's UV/surface coverage and the Legacy GIMs.
It reuses the existing offline NumPy/SciPy analyzer and source-bounded native
candidate encoder. No model name, filename, hash, image label or trained AI
selects important maps.

For each map:

```
attention = content_importance * occupied_detail_coverage * measured_fine_feature_loss
```

**CONFIRMED implementation:** Eligibility requires attention >=0.05, coverage
>0.05, fine-feature loss >0.1 and cranial surface fraction <=0.5. Head textures
already receive existing cranial safeguards. Up to three eligible maps with
scores at least half the highest eligible score receive the established 8×
priority multiplier. Original decoded source pixels fund upgrades; the system
does not try to invent detail from the reduced images. Unselected maps may fund
improvements through reported donor exchanges. With no dominant losses, the
ordinary content-aware allocator is used. Every proposed combination is
serialized through the actual aligned PAC/compression writer.

**INFERRED:** The score and thresholds are tunable perception heuristics, not
proof of semantic recognition or a global optimum. A small logo can require
manual attention even if it fails the automatic coverage threshold. **Priority
Selection** remains available and uses the same independent reference budget.
Prioritized maps with remaining fine-feature loss above 0.25 are explicitly
flagged for review; this threshold is provisional, not a guarantee of legibility.

**CONFIRMED:** On RVD, this rule automatically selects `rvd_usir` and `rvd_mae`
and produces the same 128×32/128×64 singlet GIM bytes as the successful trial.
The general result also improves two hand maps and uses 32,064 allocation bytes;
it is not byte-identical to the earlier two-map PAC. The source-derived geometry
and effective animation inputs remain exact. The complete app worker outputs
147,456 bytes with no manual selection.

## Preservation and modes

**CONFIRMED implementation:** Default runs after the existing geometry fitting
and single-slot compatibility stages. Its budget includes their actual overhead.
The texture stage cannot invoke decimation or change a YOBJ, UV, weight, skeleton,
material depth or draw record. Retained texture tables may be losslessly
compressed using the already tested storage factor; their decoded bytes are
verified. All non-texture model payloads remain exact.

**CONFIRMED:** Native-observed T4/T8 dimension/format pairs and existing legal
incumbents constrain candidates. Output width/height and useful colors stay
within the source ceilings. Existing material bit depth remains fixed; requesting
fidelity does not silently convert a T4 material to T8. Cutout and cranial guards
remain. Palette capacity and used colors are separately reported.

**CONFIRMED discovered regression:** Lance's `kutu3` source is 16×32, whereas its
old output was 32×16. The donor filter incorrectly rejected a source-correct
16×32 candidate because its height/allocation exceeded that invalid incumbent.
Strict source-ceiling mode now rebuilds such seeds and permits source-correct
axis/allocation repair before the existing measured-budget recovery. It never
retains an upscaled/color-over-capacity incumbent merely to seed the new Default.
The generated regression reproduces an unselected narrow map next to a selected
map; unsupported cases still report errors instead of waiving source limits.
Legacy and the historical opt-in optimizer defaults remain unchanged.

| UI mode | v0.25.6 behavior |
|---|---|
| Default | Independent native-reference allowance and automatic content priorities |
| Legacy | Previous Default fixed reductions and allocation fitting |
| ATO | Earlier experimental adaptive allocator with Legacy allocation envelope |
| Priority Selection | Up to three manual priorities with the new reference allowance |
| Downgrade | Selected 1/2/3 reductions of new Default output; old floors/palette rules retained |
| Maximum Downgrade | Existing texture-only rescue over the Legacy geometry/texture fitting baseline |

**CONFIRMED:** The UI still starts at Default and shows automatic priorities and
remaining significant detail losses after conversion. `default-textures/report.html`
contains source/current/final images, candidate costs, loss metrics, allocation
decisions and review flags. The QA report links it. `legacy-texture-method.pac`
preserves the same job's frozen comparison before the quality stage. Save As
validates with the extended native GIM reader when new Default is used.

## Reference validation

**CONFIRMED local results:** Over independently preserved native model baselines,
all six cases pass final structure, source ceilings, actual PAC and allocation
checks, byte-exact model/non-texture preservation and analytical motion replay.
No accepted baseline is overwritten. The reference-only driver reruns textures,
not geometry; full existing anatomical review findings remain relevant.

| Case | Before PAC | New Default PAC | Modeled pixels/CLUT | Automatic priorities |
|---|---:|---:|---:|---|
| RVD full app job | 147456 | 147456 | 32064 | Front/back singlet |
| Lance accepted posterior control | 145408 | 145408 | 28736 | boots |
| Jericho accepted eye/jaw/elbow control | 145408 | 143360 | 33472 | y2j_mata |
| Benoit comparison control | 120832 | 120832 | 34176 | bn_asir, bn_asil, bn_kutu |
| Rock scalp control | 147456 | 147456 | 26048 | rc_hiza, rc_kat_l, rc_kutu2 |
| 0401 larger model control | 147456 | 145408 | 34176 | rvd_kosi, rvd_body |

**CONFIRMED:** New generated tests cover routing, deterministic/name-independent
attention, blank/low-coverage/head exclusions, the three-map limit, separate
budget enforcement, source-ceiling seed repair and unchanged model payloads.
Existing ATO/priority/alpha/native/geometry tests still run. Windows workflow
additionally exercises frozen Default, Legacy, manual priorities, ATO, Downgrade,
Maximum Downgrade, GUI/source preview and multi-YOBJ conversions.

**UNKNOWN:** In-game outcomes of these generalized outputs beyond the previously
reported fixed RVD candidate. Automated tests and source comparisons do not
certify runtime safety or universal visual equivalence. Inspect previews,
reports, selected/donor tradeoffs and actual PPSSPP gameplay.

Reproduce a frozen-model comparison with your own source and baseline:

```sh
python -m experiments.default_texture_quality SOURCE.pac BASELINE.pac new-folder
python -m unittest tests.test_default_textures
python -m unittest discover -s tests
```

**CONFIRMED:** New source is included in the portable distribution; no game assets
or new heavy AI/runtime dependencies are introduced.

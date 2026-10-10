# Standalone bpy investigation

Evidence date: 2026-10-10. Isolated branch: `experiment/bpy-runtime-investigation`.
Production reference: `feature/portable-ps2psp` at
`e7c3f403236eae492e7cdda7b2ca096640d94800`.

Labels apply to each technical assertion: **CONFIRMED** means measured or
demonstrated in this experiment; **INFERRED** means supported but not proved for
every input/platform; **UNKNOWN** means not yet established.

The published bundle's [complete file inventory](standalone-bpy-file-inventory.md)
lists every file's purpose, compressed/extracted size, hash and removal assessment.

## Scope and result

**CONFIRMED:** This experiment changes no production reducer, converter, QA,
native writer, PAC compressor/repacker, profiles, requirements, or baseline PAC.
Only an experimental launcher overrides the runtime executable selected inside
its own process. Nothing is merged into main.

**CONFIRMED:** Standalone bpy 4.3.0 and 5.2.2 can run the existing geometry stage
without a Blender executable on Linux. Across seven prepared geometry trials,
both produced byte-identical native PSP YOBJ output to Blender 4.3.2. In the four
trials with existing complete PAC references, unchanged packaging also reproduced
the PAC bytes exactly. This includes the Lance posterior guard and the isolated
Jericho leg-retention candidate.

**CONFIRMED:** The complete frozen Windows prototype passes its synthetic
self-check, GUI/drag-drop startup, two full modified-container conversions,
native/size/ocular checks, static and analytical-pose QA, and native output
comparison against official Blender 4.3.2 on the same Windows runner.

**UNKNOWN:** Clean Windows 10/11 compatibility and PPSSPP behavior of this runtime
prototype await the user's self-check/game testing. Hosted Windows CI is separate
evidence, not a pristine Windows installation.

## Actual Blender dependency

**CONFIRMED:** The packaged converter uses
[`desktop/geometry_worker.py`](../desktop/geometry_worker.py), which calls
[`tools/blender_reduce.py`](../tools/blender_reduce.py). Weight transfer, native
serialization, PAC construction, GIM conversion, QA measurements and CPU preview
rendering do not require Blender. Blender is the guarded geometry reducer, not
the converter's skeleton retargeter or game-format exporter.

| Operation | Existing implementation | Standalone result | Evidence |
|---|---|---|---|
| Reset scene | `bpy.ops.wm.read_factory_settings(use_empty=True)` | Works | CONFIRMED, all trials |
| Construct mesh/object | `meshes.new`, `objects.new`, `from_pydata`, collection link/active/selection | Works | CONFIRMED |
| Preserve corner attributes | UVMap, CORNER/FLOAT_COLOR RGBA, material slots/index | Works | CONFIRMED, unchanged native UV/color/material records |
| Preserve/interpolate rig weights | Named vertex groups; read evaluated group weights, normalize | Works | CONFIRMED, identical serialized weight records |
| Weighted collapse | DECIMATE, ratio, triangulation, `interior` group, factor 1000 | Works | CONFIRMED |
| Enforce regional floors | Dependency graph, `evaluated_get`, `to_mesh`, loop triangles, clear evaluated mesh, retry | Works | CONFIRMED |
| Apply modifier | `bpy.ops.object.modifier_apply` with active object | Works | CONFIRMED |
| Export normals/geometry | `corner_normals`, vertex coordinates, loop-triangle corners, `mathutils.Vector` float32 representation | Works | CONFIRMED |
| Final smooth normals | `tools.region_mesh.smooth_normals`, area-weighted cross products, position/smoothing-group sharing and normalization | Same existing Python code | CONFIRMED |
| Clean objects | `bpy.data.objects.remove(..., do_unlink=True)` | Works | CONFIRMED |
| Blender review rigs | Older `tools/blender_validate.py` uses armatures/pose evaluation | Outside current portable converter and this feasibility test | CONFIRMED about call scope; UNKNOWN standalone review-rig coverage |

**CONFIRMED:** Protection occurs before collapse: torso/pelvis support,
torso-rich material surfaces, source ocular support, cutouts, material-boundary
rings and absent-controller attachment positions are retained. The complete head
floor includes held faces. Source UV restoration and final normals follow collapse.
These are unchanged conversion rules, not new bpy-specific anatomical patches.

**CONFIRMED:** None of the tested operations uses Blender's UI, GPU renderer,
Cycles rendering, video encoding, DAE/OBJ exporters or interactive extensions.
**INFERRED:** Therefore a headless standalone backend is technically appropriate
for this stage. This does not prove that native rendering DLLs can be removed from
the official wheel; dependency trimming was not validated.

## Python / ABI compatibility

Metadata and actual Windows-wheel hashes are preserved in
[`windows-wheel-audit.json`](../experiments/bpy/evidence/windows-wheel-audit.json).

| Candidate | Python | NumPy requirement | App compatibility | Evidence |
|---|---|---|---|---|
| Existing full Blender 4.3.2 | Private Blender runtime; app CPython 3.13 | App 2.3.5 independent | Existing separate process | CONFIRMED |
| bpy 4.3.0, cp311 | `==3.11.*` | No bound in wheel metadata; tested with 1.26.4 | Needs another compatible interpreter alongside the 3.13 app | CONFIRMED |
| bpy 4.3.2 | No release at the queried PyPI endpoint | Unavailable there | Not tested | CONFIRMED for PyPI; UNKNOWN for all archives/custom builds |
| bpy 5.1.0, cp313 | `==3.13.*` | `>=1.26,<2.0` | Conflicts with pinned app NumPy 2.3.5 | CONFIRMED metadata |
| bpy 5.2.2, cp313 | `==3.13.*` | `>=2.2,<3.0` | Compatible with app Python 3.13 and NumPy 2.3.5 | CONFIRMED metadata and actual trials |

**CONFIRMED:** Linux test builds: bpy 4.3.0 `bcb0488787e6` with CPython 3.11.16;
bpy 5.2.2 LTS `d13f752e3b9c` with CPython 3.13.5. The Windows hosted runner uses
CPython 3.13.15. The native API explicitly checks Python major/minor compatibility
in upstream `bpy_interface.cc`; this is not an `abi3` wheel.

**CONFIRMED:** bpy 5.2.2's build hash matches upstream tag v5.2.2 at
`d13f752e3b9c4f8c261cda552b1021f8bcc0382c`. bpy 4.3.0's tested build hash does
not match tag v4.3.0 (`2b18cad88b138a1b16617c27540858fba59e66f5`).
**UNKNOWN:** Whether the 4.3.0 release source archive corresponds exactly to that
wheel build. A future 4.3.0 distribution must resolve its actual source provenance,
not silently substitute the 4.3.2 or tagged 4.3.0 source archive.

**CONFIRMED:** The 5.2.2 prototype uses one frozen CPython runtime. Geometry still
runs in a fresh child process, through the existing CLI argument contract; the UI
does not import bpy. QA remains a separate child. The reducer executes on the
child's main thread, resets scene state and preserves existing cancellation.
**INFERRED:** This process boundary is preferable to sharing Blender's global
context between GUI threads/jobs. Multiple in-process concurrent jobs were not
tested and are not part of this prototype.

## Geometry and regression evidence

[`linux-native-comparison.json`](../experiments/bpy/evidence/linux-native-comparison.json)
records actual input/output hashes and float32 comparisons.
[`additional-native-comparison.json`](../experiments/bpy/evidence/additional-native-comparison.json)
records the three additional source-model trials.

| Trial | Final meshes | Final vertices | Final triangles | Native YOBJ bytes | Compared output | Evidence |
|---|---:|---:|---:|---:|---|---|
| Lance, portable guarded geometry | 44 | 2,365 | 2,568 | 190,912 | Both bpy versions identical; PAC 137,216 bytes identical | CONFIRMED |
| Jericho, portable geometry | 47 | 2,635 | 2,667 | 211,680 | Both identical; PAC 147,456 bytes identical | CONFIRMED |
| Additional original HCTP 2800 | 46 | 2,108 | 2,373 | 174,864 | Both identical; PAC 147,456 bytes identical | CONFIRMED |
| Jericho, isolated leg-retention candidate | 47 | 2,645 | 2,685 | 212,304 | Both identical; PAC 147,456 bytes identical | CONFIRMED |
| Benoit HCTP | 38 | 2,040 | 2,380 | 168,368 | Both YOBJs identical; no full-PAC budget trial added | CONFIRMED |
| Slaughter HCTP ring | 33 | 2,286 | 2,538 | 179,648 | Both YOBJs identical; no full-PAC budget trial added | CONFIRMED |
| Slaughter HCTP entrance | 35 | 2,536 | 2,779 | 192,944 | Both YOBJs identical; no full-PAC budget trial added | CONFIRMED |

**CONFIRMED:** The first four trials reuse existing prepared geometry, exact
profiles, destination base and converted texture manifests. Additional trials
prepare the user's original HCTP inputs with the unchanged portable preparation
stage and Kurt PSP base, then run all three reducers with the same inputs. They
compare complete native output, not counts alone. Native serialization independently
checks float32 positions/normals/UVs/weights, colors, triangle orientation, palettes,
draw buffers and skeleton preservation. Full PAC comparison uses the same 200/220
symbol BPE settings and existing repacker; original reference PACs remain read-only.

**CONFIRMED:** 5.2.2 gave exact JSON mesh equality in the first four trials.
4.3.0 differed only in Python double normal values, maximum `2.22e-16`; all final
float32 normal records and complete YOBJ/PAC bytes were identical. Exact native
identity is stronger than visual agreement for these tested outputs.

**CONFIRMED:** Lance's previous QA posterior surface distance p95 is
`2.435055693831138e-9` of reference height; rear/side silhouette IoU is 1.0.
Unchanged source geometry, palettes and weights retain the same analytical pose
and render inputs. Existing QA summaries include all 14 body/jaw poses and 16
ocular probes. The leg-retention candidate is included separately so this runtime
test does not silently accept the older Jericho leg notch.

**CONFIRMED:** Some portable reference outputs already have unresolved foot/hand
or other review flags, recorded in
[`reference-qa-summary.json`](../experiments/bpy/evidence/reference-qa-summary.json).
This runtime experiment neither fixes nor worsens those identical native outputs.
It must not be described as establishing that every reference is visually perfect.
The historically game-validated Lance/Jericho PAC hashes remain separately verified
by `python -m tools.verify_documented_baselines`; they are not replaced by these
new generalized portable outputs.

**INFERRED:** Existing static/pose/render results carry over to byte-identical
models. **UNKNOWN:** Compatibility for every HCTP PAC, other Blender versions,
different PSP donors, or actual SVR controller semantics not exercised by the
analytical poses. No new PPSSPP session was performed in this investigation.

## Windows packaging experiment

**CONFIRMED:** `bpy_experiment.py` is the experiment-only entry; it delegates to
the unchanged app and reducer. `experiments/bpy/build_windows.py` freezes the app,
copies the physical wheel's native extension/DLLs and versioned resource tree,
includes declared bpy dependencies, app dependencies, matching Blender source,
converter source and available notices. The prototype keeps a console for logs.

**CONFIRMED:** Early builds imported an empty experimental `bpy` package instead
of Blender. A minimal Linux frozen probe reproduced `bpy.__file__` pointing at the
experiment's `__init__.py`, with no `bpy.app`. The cause was the freezer's entry
package import root. A repository-root launcher avoids that shadowing. Attempts
to force delayed native initialization were abandoned; the final prototype uses
ordinary `import bpy` and checks it exposes `bpy.app`. This was a packaging failure,
not a decimation, PSP-format or model failure.

**CONFIRMED:** Hosted self-checks run with PATH limited to Windows/System32 and
without PYTHONHOME/PYTHONPATH. Generated torus fixtures exercise actual head/arm/leg
decimation, protected torso/ocular faces, corner attributes, normalized weights,
finite unit normals and index bounds. Generated native PSP vectors test format
checks; GUI startup tests Tk, drag/drop and view configuration. No wrestler assets
are in the distribution.

**CONFIRMED:** Hosted full-conversion tests reconstruct existing development-only
Lance/Jericho IR in modified HCTP containers with generated checkerboard textures,
then run the frozen app, native checks, full QA and previews. An official Blender
4.3.2 runtime, checksum verified, independently reduces the same Windows prepared
IR; comparison checks complete serialized YOBJ equality. Development-only PACs
are outside the app ZIP. These are not original-container gameplay tests.

**CONFIRMED:** [Windows run 7](https://github.com/RyosSplitter/Wrestler-Importer/actions/runs/38026427363)
passes all stages at build commit `4e02315d4de457f6f5682b4f5d0e5d2582b144b0`.
[`bpy-windows-results.json`](../experiments/bpy/evidence/bpy-windows-results.json)
records complete native YOBJ equality for both modified fixtures. The Lance
fixture yields 43 meshes / 2,356 vertices / 2,568 triangles / a 126,976-byte PAC;
Jericho yields 47 / 2,647 / 2,667 / 137,216 bytes. These counts are not the original
PAC trial counts in the Linux table: the Windows source containers use reconstructed
IR and generated textures. Each comparison uses the same source/profile/platform
on both backends, avoiding that confound. Both retain two pre-existing review flags;
QA finishing is not synonymous with clearing every review flag.

## Measured size

**CONFIRMED:** Existing full-Blender preview ZIP: **556,352,052 bytes (530.6 MiB)**;
expanded **1,276,311,842 bytes (1,217.2 MiB)**. ZIP SHA-256:
`80823d0f6b57b756d5bf370f5649421b3816bb76ce1d1079632ecf6b569f89c2`.
Its Blender runtime accounts for 415,414,900 compressed bytes (396.2 MiB),
and Blender 4.3.2 source for 74,491,360 compressed bytes (71.0 MiB).

| Windows wheel only | Download bytes | MiB | Expanded bytes | Expanded MiB | Evidence |
|---|---:|---:|---:|---:|---|
| bpy 4.3.0 cp311 | 333,159,335 | 317.7 | 733,451,018 | 699.5 | CONFIRMED, downloaded and PyPI SHA verified |
| bpy 5.2.2 cp313 | 338,211,575 | 322.5 | 669,289,527 | 638.3 | CONFIRMED, downloaded and PyPI SHA verified |

**CONFIRMED:** These wheel figures are not complete application sizes. They omit
CPython, NumPy/SciPy/Pillow/Tk/QA, notices, converter code, source archive, packaging
overhead and any freezer dependency duplication. The 4.3.0 option also needs a
separate compatible interpreter; its complete Windows app was not built.

**CONFIRMED:** 5.2.2 still contains `usd_ms`, `oslexec`, OpenImageDenoise, oneAPI
Cycles kernels, FFmpeg and Embree. Complete native wheel contents were retained;
calling no renderer does not establish that DLL removal is safe.

**CONFIRMED:** The actual complete 5.2.2 Windows prototype ZIP, including native
libraries/resources, frozen Python/app dependencies, source archives and notices,
is **504,665,468 bytes (481.3 MiB)**; expanded **935,280,347 bytes (892.0 MiB)**.
Download savings: **51,686,584 bytes (49.3 MiB / 9.3%)**. Expanded savings:
**341,031,495 bytes (325.2 MiB / 26.7%)**. These are measured archive totals,
not estimates from wheel sizes.

| Actual prototype component | Compressed bytes | MiB | Expanded bytes | Evidence |
|---|---:|---:|---:|---|
| bpy native libraries/resources | 337,536,029 | 321.9 | 668,976,330 | CONFIRMED |
| Frozen app libraries / Python / QA | 56,804,568 | 54.2 | 155,567,525 | CONFIRMED |
| Launcher | 14,460,848 | 13.8 | 14,661,905 | CONFIRMED |
| Blender and converter sources/docs | 94,080,362 | 89.7 | 94,727,192 | CONFIRMED |
| Notices | 244,841 | 0.2 | 689,829 | CONFIRMED |
| Manifest, instructions, self-check command | 231,370 | 0.2 | 657,566 | CONFIRMED |
| ZIP container overhead | 1,307,450 | 1.2 | Not an expanded file | CONFIRMED |

**CONFIRMED:** Actual size evidence is
[`bpy-package-size.json`](../experiments/bpy/evidence/bpy-package-size.json),
with the baseline in
[`full-blender-package-size.json`](../experiments/bpy/evidence/full-blender-package-size.json).
`python -m experiments.bpy.measure ZIP_PATH` independently measures an archive.
The newer, larger source archive and additional dependencies offset part of the
runtime-only saving; using bpy does not turn the app into a small download.

**CONFIRMED:** ZIP SHA-256:
`9f9429748771ec96755dcee27179c54ee5a9c6da9cf071a6ed6549c125c33107`.
[Download the complete self-check prototype](https://github.com/RyosSplitter/Wrestler-Importer/releases/download/bpy-experiment-7-4e02315d4de457f6f5682b4f5d0e5d2582b144b0/PS2PSP-bpy-Experiment-Windows-x64.zip)
and [release/checksum/Windows evidence](https://github.com/RyosSplitter/Wrestler-Importer/releases/tag/bpy-experiment-7-4e02315d4de457f6f5682b4f5d0e5d2582b144b0).

**CONFIRMED:** The published ZIP was downloaded independently: its SHA and
expanded/compressed totals match CI, all **4,792** manifested files match their
hashes, and there are no extra unmanifested files other than the manifest itself.
No PAC/YOBJ/GIM/OBJ/PNG assets occur outside the official bpy resource tree.
Both complete GPL texts are present inside the included source archive. Evidence:
[`release-verification.json`](../experiments/bpy/evidence/release-verification.json)
and [`independent-prototype-size.json`](../experiments/bpy/evidence/independent-prototype-size.json).

## Recommendation

**INFERRED:** Standalone bpy 5.2.2 is a technically practical replacement for
the guarded geometry subprocess on the tested runtimes, with modest download
savings and more substantial installed-size savings. Its Python/NumPy versions
fit the existing app, avoiding a second interpreter. Output equivalence is
demonstrated for the tested cases, not presumed from the API name.

**INFERRED:** It is not yet a production shipping decision: complete the user's
clean Windows self-check, resolve the combined-program licensing/source audit,
and preserve a Blender fallback while broader inputs/hardware are tested. A custom
minimal Blender/bpy build might save more, but **UNKNOWN:** its actual size,
dependency safety and output compatibility. It was not built or measured here.

## Licensing / source distribution

**CONFIRMED:** PyPI wheel metadata identifies bpy as `GPL-3.0`. Blender's upstream
COPYING states it is not available under alternate licenses and references
`doc/license/GPL-license.txt`; the source tree supplies GPL2 and GPL3 texts. Native
third-party notices remain in the copied wheel resource tree and available package
notices are copied separately. Python/Tcl/Tk and app dependency notices are retained.

**CONFIRMED:** GPL distribution entails license/copyright notices and corresponding
source obligations; changing delivery from an executable to a `.pyd` does not
remove them. Consult upstream GPL3 sections 5/6 and GPL2 sections 2/3, together with
each third-party library's actual license. A ZIP hash is not proof of licensing
compliance. Matching official Blender source is fetched over HTTPS and its computed
SHA is recorded; it is not independently checked against a published source hash.

**INFERRED:** Importing GPL bpy into the app creates a closer combined-program
boundary than separately launching Blender. A GPL-compatible project license and
complete corresponding-source plan may be required for distributing that combined
application. Process isolation for geometry does not by itself settle licensing.

**CONFIRMED:** This repository currently has no explicit project LICENSE file;
the experiment does not relicense it or grant redistribution rights to game assets.
**UNKNOWN:** A complete legal audit of every native dependency's corresponding
source/build materials and the appropriate licensing of all combined project code.
Shipping an official Blender source archive plus notices is evidence of an effort
to meet obligations, not a certification that all obligations are fulfilled.

**INFERRED:** Resolve that licensing/source audit before promoting this combined
runtime to a production-distributed app. No production licensing change is made
as part of this feasibility experiment.

## Reproduce and clean-machine self-check

**CONFIRMED:** The experiment scripts are separate and the geometry worker refuses
to overwrite an output. On Windows x64 with a development CPython 3.13 installation:

```powershell
py -3.13 -m venv .bpy-env
.bpy-env\Scripts\python -m pip install -r requirements-desktop.txt bpy==5.2.2
.bpy-env\Scripts\python -m experiments.bpy.run_geometry prepared.json candidate.json profile.json
.bpy-env\Scripts\python -m experiments.bpy.compare comparison-cases.json comparison-report.json
.bpy-env\Scripts\python -m experiments.bpy.build_windows
```

**CONFIRMED:** A comparison case names `label`, `reference` (Blender-reduced JSON),
`candidate` (bpy-reduced JSON), `base` (user PSP PAC), `textures` (converted manifest)
and `yobj` (existing native output). Optional `pac` and `bpe_max_distinct` reproduce
and compare packaging in memory. Inputs are checked for mutation; results contain
hashes/counts/attribute differences. Geometry-only identity does not substitute for
the final native comparison.

**CONFIRMED:** `.github/workflows/windows-bpy-experiment.yml` automates the Windows
build, self-check, frozen conversions, unchanged Blender comparison, archive
measurement and isolated prerelease. It does not modify the production build.

For the user's clean-machine trial: extract the entire prototype ZIP to a writable
folder and double-click `RunSelfCheck.cmd`. Send `SELF-CHECK.json` and
`SELF-CHECK.log`, Windows version, and whether Python/Blender is installed. No
developer software or typed commands are needed. Then optionally test conversions
using your own PSP base. Keep accepted PACs and the production app separately.

**UNKNOWN:** The fresh Windows result until those files and machine context are
returned. Passing hosted PATH isolation does not establish a fresh-machine pass.

## Authoritative references

- [PyPI bpy 5.2.2 metadata](https://pypi.org/pypi/bpy/5.2.2/json)
- [PyPI bpy 4.3.0 metadata](https://pypi.org/pypi/bpy/4.3.0/json)
- [Upstream bpy module initialization / Python compatibility](https://github.com/blender/blender/blob/v5.2.2/source/blender/python/intern/bpy_interface.cc)
- [Upstream COPYING](https://github.com/blender/blender/blob/v5.2.2/COPYING)
- [Upstream GPL2 text](https://github.com/blender/blender/blob/v5.2.2/doc/license/GPL-license.txt)
- [Upstream GPL3 text](https://github.com/blender/blender/blob/v5.2.2/doc/license/GPL3-license.txt)
- [Official source archives](https://download.blender.org/source/)

**CONFIRMED:** Official Blender web documentation was blocked by this cloud's
network policy. The investigation used verified wheel metadata, directly tested
binaries, allowed upstream GitHub source and normal Windows build downloads.
The wheel's own documentation states its system requirements are the same as the
corresponding Blender release; lightweight mesh use does not prove weaker CPU/OS
requirements. **UNKNOWN:** Windows 10/11/hardware breadth beyond the tested runner
and forthcoming user self-check.

# Published Windows bundle: file inventory

Evidence date: 2026-10-10. Branch: `experiment/bpy-runtime-investigation`.
This is a read-only inventory; no application files or production baselines were
removed, rebuilt or changed. **CONFIRMED** denotes measured sizes or directly
inspected project contents, **INFERRED** denotes a library/resource role supported
by its name and upstream organization, and **UNKNOWN** denotes untested dependency
or removal behavior. These labels also appear in the complete CSV.

## What was inventoried

**CONFIRMED:** The actual published
[`PS2PSP-bpy-Experiment-Windows-x64.zip`](https://github.com/RyosSplitter/Wrestler-Importer/releases/download/bpy-experiment-7-4e02315d4de457f6f5682b4f5d0e5d2582b144b0/PS2PSP-bpy-Experiment-Windows-x64.zip),
not a pip wheel or estimate. Build commit:
`4e02315d4de457f6f5682b4f5d0e5d2582b144b0`.

SHA-256:
`9f9429748771ec96755dcee27179c54ee5a9c6da9cf071a6ed6549c125c33107`.

**CONFIRMED:** There are **4,793 files**, **504,665,468 ZIP bytes** and
**935,280,347 logical extracted file bytes**. That is **481.286 MiB downloaded**
and **891.953 MiB extracted**. All sizes below use MiB (1,048,576 bytes); exact
bytes are available in the CSV. Extracted size excludes filesystem allocation,
user exports and logs. ZIP overhead is 1,307,450 bytes (1.247 MiB), separately
accounted rather than incorrectly attributed to individual files.

**CONFIRMED:** Compared with the previously published full-Blender application,
the standalone prototype saves 49.292 MiB in the download and 325.233 MiB after
extraction. The full-Blender application was 530.579 / 1,217.186 MiB respectively.
This report inventories the new standalone bundle; the previous release totals
come from the independently measured archive in the feasibility investigation.

## Complete file-by-file inventory

- [CSV: every file, purpose, size, hash and removal assessment](../experiments/bpy/evidence/inventory/file-inventory.csv)
- [JSON: component totals, largest files, identical-content groups and accounting](../experiments/bpy/evidence/inventory/file-inventory-summary.json)
- [Reproducible standard-library inventory script](../experiments/bpy/inventory.py)
- [Runtime feasibility, output comparisons and licensing investigation](standalone-bpy-investigation.md)

**CONFIRMED:** Every ZIP file has one CSV row and one accounting category. Member
hashes are taken from the published manifest independently verified in the earlier
release audit; this inventory independently rehashes the whole ZIP and the
manifest itself. It does not claim to have repeated every individual file hash.
There are no unresolved file-purpose categories. Library-purpose descriptions
remain **INFERRED** unless directly established by the project source. No row
claims that an untested DLL/resource is safe to delete.

**CONFIRMED:** Files inside `sources/blender-5.2.2.tar.xz` and
`_internal/base_library.zip` are contained within those archives; this inventory
counts their containing files once. Bytecode modules embedded in the launcher
are likewise part of the EXE's size, rather than separate extracted files.

## Component totals

**CONFIRMED:** The following file counts and sizes are measured from ZIP entries.
The per-file CSV describes the roles and evidence for each component.

| Component | Files | Download MiB | Extracted MiB |
|---|---:|---:|---:|
| bpy native dependencies | 60 | 165.90 | 350.12 |
| Blender source archive | 1 | 89.34 | 89.33 |
| bpy Cycles resources | 488 | 64.19 | 69.70 |
| bpy core extension | 1 | 40.61 | 107.47 |
| Geometry and QA math libraries | 167 | 33.21 | 95.47 |
| bpy fonts resources | 24 | 14.67 | 14.67 |
| Launcher | 1 | 13.79 | 13.98 |
| bpy assets resources | 17 | 11.22 | 11.27 |
| bpy additional Python bindings | 399 | 10.36 | 41.07 |
| Image libraries | 7 | 6.40 | 12.80 |
| bpy colormanagement resources | 23 | 4.93 | 20.21 |
| Python interpreter and standard library | 20 | 3.91 | 9.53 |
| bpy scene/shader metadata | 739 | 3.89 | 8.18 |
| bpy studiolights resources | 42 | 3.44 | 3.85 |
| GUI, Tcl/Tk and drag/drop | 998 | 3.16 | 8.83 |
| Cython collection | 330 | 2.66 | 8.85 |
| Python native support libraries | 4 | 2.15 | 5.93 |
| bpy startup, modules and templates | 514 | 1.57 | 6.08 |
| Windows C/C++ runtime support | 49 | 1.38 | 3.36 |
| bpy bundled add-ons | 309 | 1.02 | 5.06 |
| Other collected Python dependencies | 68 | 0.85 | 2.29 |
| Converter source and documentation | 142 | 0.38 | 1.01 |
| Python distribution metadata | 65 | 0.27 | 0.77 |
| License notices | 103 | 0.23 | 0.66 |
| Readme, self-check and manifest | 3 | 0.22 | 0.63 |
| Converter, QA and experiment runtime files | 69 | 0.19 | 0.54 |
| bpy icons resources | 149 | 0.09 | 0.29 |
| bpy other resources | 1 | 0.00 | 0.00 |
| ZIP headers/directory entries | — | 1.25 | — |
| **Total** | **4,793** | **481.29** | **891.95** |

**CONFIRMED:** All `bpy` categories together account for **321.892 MiB compressed**
and **637.967 MiB extracted**. The source archive is separate, so it is not
counted again in that runtime total.

## What the application components do

**CONFIRMED:** `PS2PSP-bpy-Experiment.exe` contains the frozen Python entry point
and application modules, launches the GUI, and dispatches isolated geometry and
QA worker processes. `_internal/python313.dll` supplies the interpreter;
`base_library.zip`, Python extensions and Windows C/C++ libraries support it.
The EXE is not a self-contained replacement for the adjacent `_internal` folder.

**CONFIRMED:** `_internal/desktop/core.py` orchestrates conversion;
`geometry_worker.py` invokes the existing guarded reducer; `native.py` adapts the
result to the audited PSP writer; `preview.py` creates textured CPU previews;
`storage.py` manages preferences and reviewed exports; `gui.py` supplies the
interface. `desktop/profiles/hctp-v1.json` is the generalized conversion policy.

**CONFIRMED:** `_internal/tools/` contains readers for PAC/YOBJ/HCTP, original
weight decoding and transfer, Blender reduction, anatomical protection, normals,
palette packing, texture/GIM conversion, triangle strip construction, native
auditing and PAC compression/repacking. It also includes older research and
packaging helpers because the prototype builder collects the entire package.
Their presence does not mean historical wrestler-specific patches run on every
conversion. The CSV retains their own module descriptions so these can be
distinguished rather than silently removed.

**CONFIRMED:** `_internal/model_qa/` implements anatomical reference regions,
surface/depth/curvature metrics, material-seam checks, ocular-controller probes,
deterministic comparison renders and the separate QA CLI. NumPy, SciPy, Trimesh
and Rtree support geometric analysis; Pillow supports textures and previews;
Tcl/Tk and tkinterdnd2 support the GUI and drag/drop.

**CONFIRMED:** `_internal/bpy/__init__.pyd` provides the compiled Blender engine
used for guarded decimation and corner-attribute extraction. Blender scripts and
resources accompany it. The official wheel also carries rendering, media,
scene-interchange and shader libraries. The current conversion stage does not
explicitly run Cycles, video encoding or Blender's interactive UI.
**UNKNOWN:** Which of those optional-feature libraries/resources can be removed
without breaking import, initialization or a transitive native dependency.

**CONFIRMED:** `sources/` contains development/source copies rather than files
loaded from that path by conversion. `licenses/` contains legal notices and
provenance. `RunSelfCheck.cmd` runs the portable procedural test and writes logs;
`README.txt` explains usage; `MANIFEST.json` records hashes and build provenance.

## Largest individual files

**CONFIRMED:** Sizes below are measured. Library roles in the CSV are explicitly
**INFERRED** where based on library identity rather than converter execution.
Paths are relative to `PS2PSP-bpy-Experiment/`.

| File | Download MiB | Extracted MiB | Purpose |
|---|---:|---:|---|
| `sources/blender-5.2.2.tar.xz` | 89.34 | 89.33 | Matching Blender 5.2.2 upstream source; already compressed; not loaded by conversion |
| `_internal/bpy/OpenImageDenoise_core.dll` | 41.57 | 44.77 | Open Image Denoise render denoising core runtime |
| `_internal/bpy/__init__.pyd` | 40.61 | 107.47 | Compiled Blender engine and bpy Python interface; executes geometry operations |
| `_internal/bpy/cycles_kernel_oneapi_aot.dll` | 36.47 | 37.91 | Precompiled Intel oneAPI GPU kernels for Cycles rendering |
| `_internal/bpy/oslexec.dll` | 17.11 | 46.81 | Open Shading Language shader execution runtime |
| `_internal/bpy/usd_ms.dll` | 14.25 | 47.47 | Universal Scene Description scene interchange runtime |
| `PS2PSP-bpy-Experiment.exe` | 13.79 | 13.98 | PyInstaller launcher, embedded app bytecode/PYZ and frozen job/QA dispatch |
| `_internal/bpy/5.2/datafiles/fonts/Noto Sans CJK Regular.woff2` | 10.90 | 10.90 | Blender UI/international font: Noto Sans CJK Regular.woff2 |
| `_internal/bpy/avcodec-62.dll` | 9.92 | 34.45 | FFmpeg media codec/device/filter/container/utility or resampling library: avcodec-62.dll |
| `_internal/bpy/oslcomp.dll` | 9.49 | 24.58 | Open Shading Language compiler |
| `_internal/bpy/embree4.dll` | 8.96 | 25.79 | Intel Embree CPU ray tracing acceleration |
| `_internal/scipy.libs/libscipy_openblas-64eda39e79589aedb16f58e5547eb599.dll` | 6.33 | 19.32 | SciPy native BLAS library: scipy.libs/libscipy_openblas-64eda39e79589aedb16f58e5547eb599.dll |
| `_internal/numpy.libs/libscipy_openblas64_-9e3e5a4229c1ca39f10dc82bba9e2b2b.dll` | 6.20 | 19.46 | NumPy native BLAS/Fortran libraries: numpy.libs/libscipy_openblas64_-9e3e5a4229c1ca39f10dc82bba9e2b2b.dll |
| `_internal/bpy/aom.dll` | 4.14 | 9.46 | Alliance for Open Media AV1 video codec |
| `_internal/PIL/_avif.cp313-win_amd64.pyd` | 4.13 | 7.53 | Pillow image decoding/encoding/color/font support: _avif.cp313-win_amd64.pyd |
| `_internal/bpy/5.2/scripts/addons_core/cycles/lib/kernel_sm_120.cubin.zst` | 3.76 | 3.76 | Cycles GPU/render kernel or integration resource: cycles/lib/kernel_sm_120.cubin.zst |
| `_internal/bpy/5.2/scripts/addons_core/cycles/lib/kernel_sm_50.cubin.zst` | 3.36 | 3.36 | Cycles GPU/render kernel or integration resource: cycles/lib/kernel_sm_50.cubin.zst |
| `_internal/bpy/openimageio.dll` | 3.36 | 8.11 | OpenImageIO image loading/processing runtime |
| `_internal/bpy/5.2/scripts/addons_core/cycles/lib/kernel_sm_60.cubin.zst` | 3.35 | 3.35 | Cycles GPU/render kernel or integration resource: cycles/lib/kernel_sm_60.cubin.zst |
| `_internal/bpy/5.2/scripts/addons_core/cycles/lib/kernel_sm_52.cubin.zst` | 3.34 | 3.34 | Cycles GPU/render kernel or integration resource: cycles/lib/kernel_sm_52.cubin.zst |

## Space-reduction opportunities and limits

**CONFIRMED:** The matching Blender source archive accounts for **89.34 MiB of
download** and **89.33 MiB extracted**. It is not required to execute the app.
**INFERRED:** Separate source delivery is a substantial download-size opportunity.
**UNKNOWN:** Whether a proposed distribution arrangement fully meets all GPL
corresponding-source requirements. The repository's project-license decision and
source completeness review remain unresolved. This audit does not authorize
discarding the source/notices or declare licensing complete.

**CONFIRMED:** Cycles resources are **64.19 / 69.70 MiB**, fonts are
**14.67 / 14.67 MiB**, built-in brush/node assets are **11.22 / 11.27 MiB**, and
studio lighting resources are **3.44 / 3.85 MiB** (download / extracted).
The denoising core alone is **41.57 / 44.77 MiB**, and the Intel Cycles GPU kernel
DLL is **36.47 / 37.91 MiB**; those two DLLs are part of native dependencies,
not the Cycles-resource directory, so the values do not overlap.
**INFERRED:** Optional rendering/resources offer more savings than the converter's
own source files. **UNKNOWN:** How much can actually be removed from the stock
wheel; a custom Blender build may be needed for dependency-coupled features.
Do not sum these numbers as a promised safe removal budget.

**CONFIRMED:** The bundled tkinterdnd2 package includes 56 files for Linux, macOS,
Windows ARM64 and Windows x86, totaling **365,713 compressed bytes** and
**1,186,473 extracted bytes**. Cython collection is **2.66 / 8.85 MiB**.
**INFERRED:** Platform-specific collection and build-only helper pruning are
smaller opportunities. **UNKNOWN:** Startup/import requirements after pruning.

**CONFIRMED:** Manifest-identical content occurs in 432 nonempty duplicate groups.
Beyond one copy per group, repeated content accounts for **1.036 MiB compressed**
and **5.213 MiB extracted**, mostly shared MaterialX schemas, runtime libraries,
source copies and Tcl support. This is an upper accounting bound for retaining
the largest compressed copy of each group, not a measured smaller application.
**UNKNOWN:** Whether duplicates at different lookup paths can be consolidated
without loader/resource changes. Duplicate cleanup is not the main size issue.

**CONFIRMED:** The inventory makes no application removals. Before any pruning is
accepted, repeat native import/dependency checks, clean-Windows self-checks,
complete conversion/QA trials and byte-level output comparisons against the
preserved regression baselines. Licensing/source distribution must also remain
consistent with the selected packaging approach.

## Reproduce and reconcile

**CONFIRMED:** Run from the repository with standard Python; this analysis does
not require installing Blender, bpy, NumPy or the converter dependencies:

```text
python -m experiments.bpy.inventory PATH/PS2PSP-bpy-Experiment-Windows-x64.zip --output PATH/inventory
```

**CONFIRMED:** Output checks reconcile the manifest's path set, CSV file count and
component extracted-size totals. Sum CSV `compressed_bytes` and add JSON
`zip_container_overhead_bytes` to obtain 504,665,468 bytes; sum CSV
`expanded_bytes` to obtain 935,280,347 bytes. The JSON preserves the independently
computed archive hash and explicit measurement caveats.

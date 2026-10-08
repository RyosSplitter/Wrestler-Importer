# Wrestler Importer 0.1 beta

This Windows desktop beta uses the pipeline that produced the uploaded,
working `RVD-HCTP-to-PSP-opacity-fix-test.pac`. The sample export is 147456 bytes
(144 KiB), SHA-256
`c3a89e2171c6d757b1d4ef1b76cd0041d1ca881c8370a3bfbc21f2658d4c2710`.
The app's conversion worker reproduces those exact bytes in the cloud test.

## Start on Windows

1. Download and extract `Wrestler-Importer-beta-0.1.zip` into a writable folder.
2. Install **Python 3.13 for Windows**, including its Python launcher, if needed:
   [Python downloads](https://www.python.org/downloads/windows/).
3. Double-click **Start Wrestler Importer.cmd**. The first launch creates a local
   Python environment and installs the pinned dependencies; later launches open
   the desktop app directly.
4. Open **Tools & base setup**. Select **Blender 4.3.2's blender.exe** and the
   original **yobj_mesh_editor_PSP_GUI.exe** supplied for this project. The beta
   only accepts that inspected editor version. Blender 2.79 is not used by this
   automated pipeline. [Blender 4.3 downloads](https://download.blender.org/release/Blender4.3/).
5. The included PSP Kurt base and Full Body weight reference are preselected.
   Save setup once. You can browse to your own copies or another PSP base.
6. Drag an **HCTP PS2 wrestler PAC** onto the app, select the PSP target game and
   export folder, then click **Convert to PSP**.

The beta remembers tool paths and choices. Conversion runs separately so the
window remains responsive; Cancel stops the worker and its Blender child.
Each successful conversion publishes a new export folder. Original models,
PACs, ISOs and archive files are opened read-only. The app does not inject into
an ISO or update an ARC; use your working injection workflow, then test in PPSSPP.

The beta ZIP includes the user's original reference assets and a `baseline`
folder with the confirmed PAC and matching Noesis files. The third-party mesh
editor and Blender are selected locally rather than redistributed.

## Export and preview

**Open PAC folder** shows the new PAC and conversion report.
**Open Noesis files** shows `preview/prepared.yobj`, DAE and named PNG/GIM textures.
The preview YOBJ is exactly the model payload inside the exported PAC. The app
checks that match before publishing the result.

If conversion fails, **Open logs** shows the worker's log and error details.
Intermediate reduction/editor logs remain in the diagnostic `.partial-*` folder
identified by the error. Failed/cancelled work is not published as a successful
export. An oversized model fails the 144 KiB beta limit; it is not silently
reduced with a different profile.

## Scope of this beta

HCTP is the supported source game. SYM, JBI and PS2 SVR profiles remain future
work. The app uses the selected PSP base's skeleton and archive layout. Target
game selection labels the export/test context; it does not change the conversion
algorithm. SVR 2011 PSP is the user's current test game, with the supplied
SVR 2007 PSP Kurt base.

The backend is pinned to repository revision
`866f9bf65ae06a025160c0f7257944c1fd2111b1`, separately from experimental tools.
The app verifies its source-file hashes before conversion. Its processing is:

- Blender 4.3.2 reduction at ratio 0.3 with shared seams protected.
- Original alignment and reference-weight transfer, up to four influences.
- Original float vertex/weight format and individual triangle strips.
- 64-pixel/4-bit texture budgets, including their original alpha handling.
- PSP body vertex alpha 255, original regular material templates and sorted
  texture archive, with aligned PAC/model sections.

The rejected regional reduction, U16/U8 weights, joined strips and higher-detail
texture profiles are excluded from the beta. The uploaded sample's PAC SHA is
checked when its source/base/reference inputs match. Other HCTP wrestlers and
custom bases need their own PPSSPP tests. Appearance limitations of the working
baseline remain; this beta adds the app workflow around that pipeline.

## Standalone executable builds

The repository's **Build Windows beta** GitHub Actions workflow builds a separate
standalone Windows app using Python 3.13 and PyInstaller. After a successful run,
download the **WrestlerImporterBeta-Windows** artifact, extract the whole folder,
and open `WrestlerImporterBeta.exe`. It includes its Python runtime, so the
executable build does not need a separate Python installation. Blender 4.3.2 and
the supplied mesh editor remain external tools. The workflow checks packaged
window startup, drag-drop resources, reference assets and the pinned backend.

The downloadable `.cmd` package is the runnable source distribution. A standalone
executable should be treated as available only when that Windows build succeeds.

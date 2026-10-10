# v0.25 light desktop interface

[Download the updated Windows build](https://github.com/RyosSplitter/Wrestler-Importer/releases/tag/portable-preview-19-d461d8c7253c5ae92727c4a82b9d1e59824935b2)
or [view its actual Windows capture](../downloads/retro-ui/converter-native-windows.png).

The converter now uses a compact Windows 7-style layout: a light gray background,
small Segoe UI text, standard buttons, simple bordered groups and an inset preview.
Convert and Cancel sit directly above the preview. The smaller header identifies
the app, author and experimental version. Source, PSP base and options remain on
the left; Save, QA and Open folder sit below the preview; progress, status and Logs
remain visible at the bottom. The experimental adaptive option still starts OFF.
The startup window is centered and leaves title-bar/taskbar room on a 1024×768
desktop, while keeping the 940×640 minimum usable layout.

**CONFIRMED implementation:** On Windows, Tk's native `vista` theme supplies the
Windows 7-era themed buttons and focus/disabled states. Other platforms use a
light `clam` fallback. Window title-bar decoration comes from the installed OS.
This is an appearance change; the packaged runtime still targets Windows 10/11
x64, and Windows 7 OS compatibility is not claimed.

**CONFIRMED host checks:** The 235-test suite passed. The existing GUI smoke now
also checks button placement, initial disabled states and the native Windows theme.
Manual screenshots and bounds checks cover 1040×720 and the 940×640 minimum;
all five camera buttons and Zoom remain visible at the minimum size. Twenty-one
event handler methods are unchanged, as are the converter, texture optimizer and
export implementation. The user workflows and output processing are unchanged.
See [layout proof](../downloads/retro-ui/layout-check.json).
An additional [interaction check](../downloads/retro-ui/interaction-check.json)
verified source inspection, remembering the chosen base, OFF→ON→OFF option
changes, all five preview views and both zoom modes using an existing output.

Host screenshots use the Linux light fallback and an existing Rock output:

* [Empty interface](../downloads/retro-ui/converter-retro-empty.png)
* [Existing Rock preview](../downloads/retro-ui/converter-retro-rock.png)
* [Minimum-size interface](../downloads/retro-ui/converter-retro-minimum.png)

The Rock image is an existing offline preview, not a new conversion or a game
capture. The illustrated PSP base path is an example. The original source's
internal model label is `hogan`; the screenshot preserves what inspection returns
rather than changing a source identifier to match the wrestler's display name.

**CONFIRMED Windows validation:** Full workflow 38093772121 passed the 235-test
suite, packaged native-theme/placement checks, three legacy frozen conversion/QA
jobs and the adaptive frozen worker. Its first Windows capture exposed the old
fixed startup size extending underneath the taskbar on the runner's small screen.
The final adjustment caps and centers the startup dimensions; it does not change
any processing callback. UI-only CI changes with identical callback ASTs reuse
that full worker validation while still running tests, building the app and
checking the packaged native GUI. Converter/runtime or callback changes continue
to run the full frozen jobs.
Final workflow [38094840133](https://github.com/RyosSplitter/Wrestler-Importer/actions/runs/38094840133)
passed all 235 tests and the packaged native GUI checks. Its 960×648 Windows
capture shows all controls, including the status bar and Logs, above the taskbar.
See [Windows validation record](../downloads/retro-ui/windows-validation.json).
The [first clipped capture](../downloads/retro-ui/window-fit-before-windows.png)
is retained as a labeled failure reference, not the recommended interface.

The Windows build publishes `PS2PSP-converter-preview.png`, captured from the
packaged app running on Windows, as a separate release asset. Use that image to
inspect the actual native controls. Previous Windows builds and accepted PACs
remain available; this UI change stays on the experimental branch.

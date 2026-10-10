# v0.25 light desktop interface

The converter now uses a compact Windows 7-style layout: a light gray background,
small Segoe UI text, standard buttons, simple bordered groups and an inset preview.
Convert and Cancel sit directly above the preview. The smaller header identifies
the app, author and experimental version. Source, PSP base and options remain on
the left; Save, QA and Open folder sit below the preview; progress, status and Logs
remain visible at the bottom. The experimental adaptive option still starts OFF.

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

Host screenshots use the Linux light fallback and an existing Rock output:

* [Empty interface](../downloads/retro-ui/converter-retro-empty.png)
* [Existing Rock preview](../downloads/retro-ui/converter-retro-rock.png)
* [Minimum-size interface](../downloads/retro-ui/converter-retro-minimum.png)

The Rock image is an existing offline preview, not a new conversion or a game
capture. The illustrated PSP base path is an example. The original source's
internal model label is `hogan`; the screenshot preserves what inspection returns
rather than changing a source identifier to match the wrestler's display name.

The Windows build publishes `PS2PSP-converter-preview.png`, captured from the
packaged app running on Windows, as a separate release asset. Use that image to
inspect the actual native controls. Previous Windows builds and accepted PACs
remain available; this UI change stays on the experimental branch.

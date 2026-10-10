PS2PSP v0.25 light interface preview
==================================

These three screenshots were captured from the actual application on the Linux
host, using its light fallback theme. On Windows the app uses Tk's native vista
control theme; the release's PS2PSP-converter-preview.png is the separate actual
packaged Windows capture. The OS supplies the window title bar. Windows 7 is a
visual reference; the runtime targets Windows 10/11 x64.

converter-retro-empty.png: initial layout, adaptive option OFF.
converter-retro-rock.png: replay of the already-generated Rock preview.
converter-retro-minimum.png: all view buttons visible at minimum 940x640 size.
layout-check.json: bounds proof, smoke results and unchanged event handlers.
interaction-check.json: source inspection, remembered base, option and view checks.
converter-native-windows.png: final actual packaged Windows capture, including
  the visible status bar and Logs on the 1024x768 runner desktop.
windows-validation.json: passing build/release references and validation scope.
window-fit-before-windows.png: earlier failure reference; fixed startup size
  allowed the taskbar to hide the footer. The final build caps/centers the window.

No model processing was performed to make these screenshots. The source's
internal name is hogan; that metadata is unchanged. The base path is illustrative.
Convert/Cancel are above the preview. Conversion/export/QA behavior is unchanged.

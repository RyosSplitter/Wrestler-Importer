# Batch conversion in v0.29.0

In **Converter**, click **Batch…**. Choose a supported source game (HCTP, JBI or
experimental WWE ’13 Wii), a PSP base, and the settings to apply to this batch.
Click **Add models…**, select multiple PACs, then **Start batch**. You can remove
files or clear the queue before starting. Adding the same path twice keeps one
copy. Different files with the same filename remain separate.

JBI archives and Wii containers expand into individual costume entries. Each
entry shows its source filename and costume ID. The Wii output-use setting is
explicit: ring or entrance applies to every costume in the batch. Run separate
batches when costumes need different roles or settings. Wii supports Default
textures and the existing Standard / Preserve Hands / Preserve Arms geometry
profiles with optional clothing seam protection. HCTP/JBI retain their applicable
texture modes. Per-model texture priorities are available in the single converter.

Every model runs in a separate instance of the established conversion worker,
using its own working directory and the existing size, geometry, texture and QA
checks. A bad archive, unsupported accessory, pose-gate failure or worker crash
skips that model and records the reason. Later models continue. Conversion
algorithms and native output budgets are unchanged.

The queue reports progress, a per-model estimated countdown and success/skip
counts. At completion it displays a summary. **Batch report** opens a text list
of every result and error. **Logs** opens the selected model's diagnostics, or the
batch folder for a source rejected before conversion. Timing remains approximate;
only successful observed runs train the existing local history.

Select a **Succeeded** row to see that candidate's final PSP preview, five views,
zoom, size and QA findings. **QA report** opens its individual report. Use
**Save PAC As…** to save the selected model after review; it does not auto-export
unreviewed output. Each costume gets a distinct suggested filename. The existing
Save As hash, native validation and previous-file backup checks still apply, and
no export may overwrite any source from the batch, the PSP base or a batch working
candidate. A failed row clears the preview and cannot be saved.

**Cancel batch** cancels the current model and leaves remaining entries unrun.
Completed candidates stay available for preview and Save As. Closing a running
batch waits for cancellation; closing the app also cancels and waits for its
workers. Starting a new batch or closing its window clears the on-screen review;
working candidates and reports remain in the application's local `batches` folder.
Save the models you want before closing the review window.

Verification includes continuation after a conversion-time unsupported-accessory
failure and malformed input, per-costume archive jobs, distinct success previews
and UI Save As, cancellation with a completed candidate retained, immutable inputs
and protected exports. Windows smoke uses procedural format fixtures; this does
not establish gameplay compatibility of every wrestler. Experimental outputs
still require visual and PPSSPP review.

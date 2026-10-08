# Beta baseline validation

Beta 0.1.1 retains this baseline and adds PS2 RTX3 decoding and size fitting.
See [the format coverage and real 1800 conversion](texture-decoder.md).

The uploaded opacity-fix ZIP contains the same 147456-byte PAC as the repository's
working baseline, SHA-256
`c3a89e2171c6d757b1d4ef1b76cd0041d1ca881c8370a3bfbc21f2658d4c2710`.
The beta pins all 13 original backend source modules from revision
`866f9bf65ae06a025160c0f7257944c1fd2111b1`. `stable_pipeline/profile.json` records
their SHA-256 values, sample identities and the original processing choices.

A fresh conversion with that pinned original CLI reproduces the uploaded PAC
byte for byte. A separate conversion through the beta's actual worker process,
using CPython 3.13, NumPy 2.3.5, Pillow 12.3.0 and Blender 4.3.2, also produces
the exact same PAC. It has 45 chunks, 1211 vertices, 877 triangles, 79 PSP bones
and 15 textures. Both paths preserve the native float weight layout.

The worker invokes the original reducer, preparation, texture conversion,
editor serialization and PAC packing primitives. GUI progress, saved settings,
file selection, cancellation and export-folder publication sit around them.
Publishing follows native serialization checks and an exact PAC/preview payload
comparison. The worker also refuses to publish this sample if its PAC SHA differs
from the uploaded baseline. Inputs are hashed and opened read-only.

The 48 unit tests include the existing format checks and beta tests for a changed
backend, accidentally selecting the source as the base, saved/corrupt settings,
and reporting worker failure without creating an export. A live Tk drag/drop
interface test in the Linux virtual display exercises the setup dialog, source
selection, Convert button, progress polling and opening the preview folder.
That GUI-driven conversion also matches the uploaded PAC byte for byte, with
the UI event loop continuing throughout. Cancel stops both the worker and its
observed Blender child process; source/base/reference/editor hashes remain
unchanged. GUI and native Windows validation results are recorded separately;
Linux tests do not establish Windows or PPSSPP behavior.
The export/preview controls are also checked for visibility at 1040x740 and
940x720, including after the two-line completed-export message.

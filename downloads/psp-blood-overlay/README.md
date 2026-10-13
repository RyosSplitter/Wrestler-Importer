# Experimental PSP blood-layer test

Start with `Benoit/Benoit-PSP-Blood-Overlay-EXPERIMENTAL.pac`.
It is 135168 bytes, under the unchanged 148000-byte budget. This is a separate
test candidate, not an app update. Accepted PACs are untouched.

1. Back up your current wrestler PAC and ISO/archive.
2. Enable blood in SVR 2011 PSP. From a clean archive, inject this candidate into
   the slot you normally use for a converted model, update/rebuild the archive
   through your established editor workflow, save the ISO, and test in PPSSPP.
3. Check normal appearance **before** bleeding starts, then cause bleeding and
   check the first and later blood stages, face/chest streaks, facial animation,
   entrance/victory and multi-wrestler matches.
4. Report whether blood activates, is permanently visible, fails to progress,
   flickers, floats or causes crashes. Use `Benoit-BEFORE-CONTROL.pac` from a fresh
   archive for the corresponding comparison and restore your accepted PAC after
   the test if needed.

The candidate adds blood surfaces using exact corresponding converted-body
weights and native blood textures/render records. It does not change the
existing body geometry, weights, UVs, materials, rig or textures.

`Benoit/preview/blood-overlay.obj` is the Noesis viewing export. Keep its MTL and
PNG files together. Apply your normal orientation/culling/shading toggles. The
native `blood-overlay.yobj` and named GIM files are also included. The complete
viewing export displays blood even without a game injury event; it cannot verify
event gating. `before.obj` displays the unchanged original conversion.

The comparison PNGs are CPU diagnostic renders, not Noesis/PPSSPP screenshots;
they deliberately force the initial blood map visible with identical cameras.
`Benoit/report.json` includes all vertex provenance, pointer/buffer auditing
outcomes, size attempts, 14 body-pose checks and 37 cranial probes. Existing body
motion has zero analytical difference; added-layer separation is bounded by the
measured native skin/overlay separation plus float roundoff.

`RVD-export-withheld.json` records a 165888-byte attempt. It did not fit, so no
RVD experimental PAC is supplied and no geometry or texture downgrade was made.
The added decoded data costs runtime memory; in-budget serialization alone does
not establish game compatibility. Native blood-stage lookup remains unverified.

Eight generated-fixture tests plus the full suite (331 tests) pass. See
`docs/psp-blood-overlay-experiment.md` for classified findings, limitations and
reproduction. Source branch: `experiment/psp-blood-overlays`.

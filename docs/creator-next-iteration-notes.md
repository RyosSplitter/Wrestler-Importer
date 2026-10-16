# Pending creator interaction changes

These user-requested changes are recorded for the next application iteration.
They are not implemented by the isolated facial research branch.

1. Split the current Legs donor selection into **Upper Legs** and **Lower Legs**,
   allowing separate donors above/below the knee. Establish a knee attachment
   boundary from native rig/topology evidence; accommodate knee pads and boots.
   Preview the cut and validate bending, source preservation and attachment closure.
   Existing four-part projects must continue to load (their Legs donor initializes
   both new selections). Do not merely relabel the existing waist-only cutter.
2. Alphabetize every part's donor selector, using a stable underlying donor ID/hash
   rather than the visual list index. Refresh all selectors after Add donors and
   preserve existing selections. Reordering labels must not silently change saved
   recipes, library references or live previews.
3. Develop modular **Head Shell / Facial Insert** separately until its method has
   been demonstrated and reviewed. See `creator-modular-faces.md` for the initial
   analysis, prototype, rejected trials, limitations and reproduction commands.

Any eventual adjustable cut profile must flow consistently through extraction,
stitching, triangulation, original-record classification, rig fitting, saved
recipes and pose QA. Mutating shared `parts.JOINTS` globals from a background job
is not a safe implementation strategy.

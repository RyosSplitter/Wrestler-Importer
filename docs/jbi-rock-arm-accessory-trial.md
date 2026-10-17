# JBI Rock: missing elbow pads and arm/hand binding

Isolated experiment: `experiment/jbi-rock-arms-accessories`, based on
`3167ce0ce1936baaf4ac122cadb3740ddcd66e8a`. Production conversion, native
serialization, PAC packaging and accepted HCTP/PSP files remain unchanged.

**CONFIRMED** means executed binary checks, synthetic pose measurements or
inspected CPU renders. **INFERRED** marks anatomical/controller interpretation.
**UNKNOWN** marks game behavior requiring an actual SVR 2011 test.

[Experimental PAC](../downloads/JBI-Rock-arms-and-elbow-pads-EXPERIMENTAL.pac)
 · [Noesis preview / renders / QA bundle](../downloads/JBI-Rock-arms-and-elbow-pads-test-bundle.zip)
 · [Before/after evidence](jbi-rock-arm-accessory-trial/before-after.json).

PAC SHA-256:
`5d7bf5a090b0c7270baf84da6191e5d78844c3bedb1e6035ec206694c5b38359`.
Bundle SHA-256:
`0cb7781a8699dc82228d7e369cff2cb46aa8433e90d919888c8d7ce8332209ed`.
Two independently executed builds produced byte-identical PACs.

## Provenance correction

**CONFIRMED — owner correction:** The supplied `ch.pac` is from **SmackDown!
Just Bring It**, not Shut Your Mouth. The exact file is 21,286,912 bytes,
SHA-256 `8e64f391179c38632a31a452845fc51c8efa53112b71cdba806136d89097955d`.
The historical `sym_*` modules, reports, branches and first download refer to
this same file. Their names are retained to reproduce the earlier experiment;
they do not prove SYM support. Binary title identification remains **UNKNOWN**.
[Machine-readable correction](jbi-provenance-correction.json).

## Why the pads disappeared

**CONFIRMED:** Costume `0000` contains three independent YOBJs: main section 2,
left accessory section 6 and right accessory section 7. Each accessory has
47 decoded UV/color-split vertices and 68 triangles. Their bounds surround
the corresponding elbow, and positive weights reference only that side's
upper-arm/forearm controls and `_w` helpers. All three models use the same
`rmomo` atlas and identical 124-bone local hierarchy.

**INFERRED:** These objects are the elbow pads. This is supported by geometry,
textures, controller support and the separate native PSP Rock pad references,
rather than section numbers alone. **CONFIRMED:** The previous main-only trial
explicitly omitted both objects. The revised experimental PAC keeps them as
independent sections 26/27, with the main model's full texture namespace and
native local bind records. **UNKNOWN:** Removal/throw/event semantics; unknown
JBI event payloads are not transplanted into the PSP base.

## Why the hands/arms were wrong

**CONFIRMED:** The first trial transfers unknown JBI finger/helper mass using
the nearest ordinary PSP body triangle in globally aligned coordinates.
Of 104 source finger corner records, **78** received influence from a different
finger, including all 24 thumb records. Coincident/nearby donor surfaces are not
an anatomical correspondence. The original source weights are not corrupt.

**CONFIRMED:** JBI's two-joint finger chains run, for example,
`l_te → l_yubi11 → l_yubi10`; PSP's corresponding chain is
`l_te → l_yubi10 → l_yubi11 → l_yubi12`. Same suffixes are not equivalent
hierarchy positions. The PSP thumb also has an additional proximal controller.
**INFERRED:** JBI thumb phalanges correspond to the last two PSP thumb joints;
the ordinary fingers correspond to the first two PSP finger joints. This is
supported by rest transforms and anatomical positions, not animation decoding.

**CONFIRMED:** After the original uniform fit, the left/right wrist origins
miss the selected PSP base by about **0.5813 / 0.5812** model units. The elbow
origins also differ. Keeping the original hand in this global frame while
applying PSP finger rotations creates an excessive thumb-web lever arm.

**CONFIRMED — failed controls:** A hierarchy-only weighting correction removes
wrong-digit coefficients but produces an 8.266× maximum triangle-area ratio
under the bilateral 40° synthetic thumb probe. A donor-query-frame-only
correction also leaves this excessive stretch. Merely translating the wrist
reduces it to about 5.154× and remains inadequate. These controls are retained
locally; their PACs are not the proposed download. They are not promoted to
production rules.

## The new isolated conversion

**CONFIRMED — implementation:** `tools/jbi_rig.py` performs a local anatomical
bind-reference conversion before hand transfer:

1. Pin the previously accepted shoulder surface anchor. Map upper-arm and
   forearm centerline endpoints to the actual PSP elbow and wrist. Preserve
   radial offsets; adapt length along the centerline and transform normals
   with the corresponding inverse transpose.
2. Express hand/finger points relative to their original JBI bone frames and
   reconstruct their local offsets in the matching PSP rest frames. This
   represents the PSP thumb's different rest splay. It is a derived coordinate
   conversion, not a manually chosen outward vertex displacement.
3. Transfer weights from the ordinary PSP hand in the resulting bind
   coordinates. A source finger can sample only its own native digit plus the
   wrist/hand transition. The palm can acquire native metacarpal support.
4. Transfer arm-helper mass from matching native arm surfaces, including the
   clavicle or parent-side arm controller at joint transitions. Excluding the
   clavicle made the shoulder cap follow the upper arm too strongly; that
   intermediate variant was rejected.
5. Fail on unhandled blended hand boundaries, ambiguous digit chains, more
   than four useful influences, wrong-digit support, or newly opened coincident
   rest seams. Do not average source seam weights or weld independent records.

**CONFIRMED:** This intentionally changes local arm/hand bind geometry and
normals. The earlier claim that a weights-only fix could suffice was disproved
by the thumb stress tests. No decimation or topology/material/UV/color edit is
applied. Head, torso and legs retain their prior positions and weights. The
previous ocular/jaw policy is retained. The main native 77-bone PSP skeleton is
byte-identical to the selected Kurt base; the original JBI rig is not inserted.

**INFERRED:** This is a compatible arm/hand reference-pose conversion.
**UNKNOWN:** Full source/controller animation equivalence; actual idle, grips,
weapon holds, elbows, wrist twists and pad events need PPSSPP review.

## Validation and evidence

**CONFIRMED:** The candidate retains all **1,490 main triangles** and both
**68-triangle pads**, totaling **1,626 triangles**. The independent native
offset, relocation, vertex/index alignment, index range, palette, weight,
texture/material and PAC checks run on the actual rebuilt PAC. Its extracted
YOBJs are compared byte-for-byte with the validated native models, and the
Noesis OBJ/PNG preview is generated from those extracted models.

**CONFIRMED:** The main model uses 54 buffers/1,506 stored vertices; each pad
uses one buffer/47 vertices. The combined preview has 56 buffers/1,600 vertices.
Extra vertices/buffers reflect different palette packing, not additional
source triangles. The prior main-only PAC has 50 buffers/1,505 stored vertices.
No arbitrary mesh-count target is imposed.

**CONFIRMED:** All 22 previously accepted main GIMs are byte-identical. One
shared **64×16 indexed4** pad GIM adds **784 serialized bytes / 576 pixel+CLUT
bytes**, reaching the same **54,016-byte** conservative native-base pixel/CLUT
envelope. This is not a proven PSP heap limit. The complete actual PAC is
**133,120 bytes**, below the configured **148,000-byte** target by 14,880 bytes.
The allocator measures actual compressed PACs, including the accessory models.

**CONFIRMED:** Wrong-digit support falls from **78/104 to 0/104**. Ten independent
digit probes check that other source digits do not move, while the selected
digit still moves. Six additional arm/hand stress poses, the existing 15 body
poses and 16 ocular probes run against intended and serialized records.
No new collapsed triangles or opened coincident rest seams were observed.

**CONFIRMED:** The synthetic thumb area maximum is about **1.988×**, compared
with **2.113×** on the original JBI source and **1.743×** on the native donor.
A provisional fail gate is `1.5 * max(source, donor) + 0.25`; it rejects the
8.266× weights-only control. This is a documented review envelope, not a
hardware limit or a universal anatomical tolerance. The old PAC's apparently
small thumb metric was misleading because its thumb ignored the thumb control.
Grip and wrist area distortion also decrease; detailed per-pose minima and
maxima remain in the report instead of claiming every statistic improves.

**CONFIRMED:** One previously observed two-slot leg palette remains a review
finding. It is not a proven illegal format and was present in the user's
working trial. No new two-slot finger draw is required by the final transfer.
Serialization/analytical replay proves data consistency, not game safety.

**CONFIRMED:** The unchanged `desktop.accessories.package_models` creates the
PAC; a second actual packaging call must reproduce the allocator's bytes.
Unrelated base sections and local bind data remain unchanged. The original
accepted PAC and its ZIP remain untouched. No experiment is merged into main,
and desktop JBI/SYM adapters remain disabled.

## Reproduce and inspect

Use the existing research Python environment (NumPy, Pillow, SciPy, Trimesh,
Rtree), the user's original archive and their own compatible PSP base:

```sh
local/sym-runtime/bin/python -m tools.jbi_trial /path/to/ch.pac \
  --base /path/to/OWN-PSP-base.pac --out local/NEW-JBI-trial
local/sym-runtime/bin/python -m unittest tests.test_jbi_rig \
  tests.test_sym_adapter_trials tests.test_portable_accessories
```

The output directory must be new. No raw source archive or PSP base is included
in the test fixtures. `tests/test_jbi_rig.py` uses synthetic skeletons, digit
surfaces, independent controller probes and intentionally conflicting seam
records. The selected relevant regression run passed **153 tests**.

Open `preview/JBI-Rock-with-pads.obj` in Noesis with `preview.mtl` and PNGs in
the same directory. Apply the requested orientation/cull/shading toggles.
Native independent YOBJs are also included. CPU comparison images are explicitly
labeled; they are not Noesis screenshots or actual game animation captures.
Weighting-control comparison panels include restored pads in both halves to
isolate binding effects. Separate accepted-PAC comparisons show the previous
main-only model against the actual final three-model PAC.

Back up the accepted slot, inject the experimental PAC using the same working
SVR 2011 PAC/ARC workflow, update/rebuild the enclosing archive and ISO as
previously tested. Inspect standing, walking, grips, taunts, elbows and wrist
twists; keep the accepted PAC available for rollback. Actual pad-state handling,
all animations, collisions, runtime memory and extended-match stability remain
**UNKNOWN** until tested in-game.

# Portable application architecture and evidence

This supplements the binary specification in `hctp-psp/` and the root
`REIMPLEMENTATION_GUIDE.txt`. Historical accepted PACs remain immutable controls;
new generalized application output is an experiment until tested in PPSSPP.

**CONFIRMED — code and automated tests:** `desktop/` is separate from `app/` and
`stable_pipeline/`. The latter remain the historical beta and pinned backend.
`ps2psp_converter.py` dispatches the interface, inspection worker, conversion
worker and independent QA worker. Workers receive local paths in an isolated job;
they do not upload PACs, invoke external editors or write to either input.

```text
Local HCTP PAC + user's local PSP base PAC
  -> HCTP adapter: PAC / PS2 YOBJ / VIF weights / RTX3 decoding
  -> original weighted corner-preserving intermediate representation
  -> one uniform rest-landmark similarity transform
  -> source body/jaw ancestor map + selective PSP donor ocular weights
  -> protected-source surfaces + regional Blender decimation
  -> original-UV recovery at verified unchanged positions
  -> sparse <=8-bone draw palettes and <=4 active vertex influences
  -> native float-weight PSP writer / GIM textures
  -> existing BPE compressor and PAC section replacement
  -> audit actual decompressed final PAC / ocular replay
  -> separate reference QA, fixed-camera clay pairs, analytical poses
  -> textured CPU renders of actual final YOBJ + actual final GIMs
  -> immutable candidate hash / reviewed, audited atomic Save As
```

## Geometry and skinning rules

**CONFIRMED — unit tests and supplied-model runs:** source positions, normals,
UV/color corner seams and source weights are decoded before reduction. Alignment
uses shared rest-bone landmarks and a proper rotation, translation and **one
uniform scale**. It does not nonuniformly fit the source into the donor's shape.
The PSP base's complete bone byte table is retained. Preparation records the
alignment, redirects and donor distances, and keeps all stages for QA tracing.

**CONFIRMED — historical experiments and current regression tests:** broad donor
replacement of cranial weights caused the Jericho jaw problem; broad source
cranial preservation exposed incompatible eye/eyelid animation behavior. The new
rule maps source body/jaw weights by bone name and nearest shared ancestor, then
uses the legacy ordinary-PSP-surface donor transfer **only where source weights
support `l_eye`, `r_eye`, `l_mabuta` or `r_mabuta`**. A selection that overlaps lower
jaw controller support is rejected for review. It does not revert the entire face.

**INFERRED — generalization:** legacy donor interpolation should provide compatible
ocular behavior on another supported PSP base. The exact historic fix replayed
previously game-tested serialized eye weights on frozen Jericho topology; this app
recomputes donor weights from the user's base. Those are different provenance
claims. Its 16 local/world ocular probes check exact replay relative to the new
donor-control stage and preserve the remaining source-derived jaw weights.
**UNKNOWN:** another base's real facial animation semantics until game testing.

**CONFIRMED — implementation and reference runs:** the geometry worker holds source
triangles supported predominantly by torso bones, whole material surfaces with
substantial torso support, eye/eyelid support, cutouts, shared material-boundary
rings and attachments supported by source-only bones. Held triangles are copied;
there is no buttocks displacement, waist mirroring or hand-authored repair.
Complete torso surfaces preserve shoulders/neck portions that cross bone-region
boundaries. Source-only attachment support protects hair/tails through ancestor
mapping without matching wrestler or texture filenames.

**INFERRED — heuristic:** the 30% torso-supported-material selection threshold is a
conservative way to identify complete anatomical surfaces in the examined assets.
It is not a proved universal HCTP material convention. It can protect more faces
than necessary; the app rejects a candidate that cannot fit while retaining them.

**CONFIRMED — implementation:** initial free-region retention is Head 80%, Torso
65%, Arms 80%, Legs 65%. The head floor counts preserved head faces, following the
established complete-region budgeting approach. Limb-only budget attempts can
reduce free retention to 50%, then 35%, while held surfaces and the complete-head
floor stay intact. QA findings remain visible. These budget attempts do not certify
that lower limb retention is aesthetically acceptable on every character.

**CONFIRMED — observed failure and fix:** Blender's evaluated modifier can meet its
face target while corner remapping later discards duplicate-index triangles.
The new worker reserves additional modifier faces **only in the affected region**
and retries, keeping the final floor strict. `tools.blender_reduce.reduce()` gained
an optional `retention_reserve`; its default is zero, preserving older callers.
Another failure came from six-decimal exported UVs at held/free boundaries, which
duplicated otherwise identical vertices. An exact original UV is restored only at
an unchanged float32 position with a unique nearby material UV match. Different UV
islands are never welded by an arbitrary tolerance.

**CONFIRMED — decoded round trips:** sparse palette packing keeps at most eight
palette entries and four active normalized influences per vertex. Exact serialized
attributes alone may share an index. Coincident corners needed by original faces
remain independent. Normals are recalculated with the established smoothing helper.
Native serialization compares decoded positions, UVs, normals, colors, weights,
palettes and oriented triangle multisets, and verifies the original PSP bone bytes.
The native auditor checks all pointer/size/alignment, allocation and index contracts.
**UNKNOWN:** undocumented game allocation limits beyond observed format constraints.

## Textures, storage and previews

**CONFIRMED — existing expanded decoder tests:** supported RTX3 upload data includes
observed indexed4/8 and direct PS2 color layouts; it is not blindly GS-unswizzled.
Opaque textures use PSP indexed4, with a main cranial map selected by weight support
at indexed8. Other map budgets begin at 64 pixels; the established one-axis
resolution reduction is applied. A 32-pixel attempt precedes lower limb retention.
Alpha below 128 identifies a cutout, following the successful trials. Those RGBA
pixels are retained exactly with an indexed8 palette; more than 256 unique RGBA
colors causes a clear unsupported-exact-preservation error. Ordinary maps use
opaque vertex/material behavior rather than interpreting slight PS2 alpha values
such as 239 as body transparency.

**CONFIRMED — tests:** GIM writer/reader round trips compare pixels and palettes.
Rendering controls use matching ordinary 4/8-bit donor templates, with observed
cutout flags `0x110` where needed. **INFERRED:** the full control-word semantics,
including intermediate alpha/blending behavior; see historical material evidence.

**CONFIRMED — lossless decode comparison:** the existing BPE implementation is
used with its 4000-byte input block cap. A dictionary-density attempt of 220 rather
than the default 200 is tried before further geometry reduction; both model and
texture payloads are independently decompressed and compared byte-for-byte. This
fitted the original Jericho trial while retaining 80% free-arm geometry.
**UNKNOWN:** actual gameplay acceptance of new storage variants; binary validity
alone is not proof of game buffer behavior. PAC packaging code is unchanged.

**CONFIRMED — final-PAC audit:** only section 2 (model) and 9 (textures) are replaced.
Other stored payload hashes, section order and complete skeleton bytes must match
the base. PAC sections align to 16 bytes, YOBJ offsets use the documented byte-8
origin, the final file aligns to 2048 bytes and the strict application limit is
148000 bytes. The largest aligned allowed size is therefore 147456 bytes.

**CONFIRMED — rendering code/tests:** the interface renders the final audited YOBJ
and decoded final GIMs; it never substitutes a source or proxy model. It supplies
five full-body views and enlarged/zoom views using a CPU orthographic depth-buffer
renderer, UV sampling, texture/vertex color, alpha masking and interpolated normals.
**UNKNOWN:** exact PSP lighting, culling/blending and runtime animation appearance;
the preview labels that distinction. QA clay comparisons use the independent
renderer with identical original-derived framing for each pair.

## QA, publication and reproduction

**CONFIRMED — executed runs:** QA compares independent surfaces without assuming
source vertex-index correspondence, uses 24000 samples, 320-pixel comparison renders,
all 14 existing analytical body/jaw poses and ordered transfer/reduction traces.
Source-derived controls isolate rig mapping. Ocular QA adds 16 synthetic controller
probes. Review findings are retained, including known false-positive/ambiguous
open-surface depth and material-boundary cases. See `portable-validation.json` for
the recorded original-container trials and their exact candidate identities.
**UNKNOWN:** PPSSPP behavior of these newly generated generic outputs until tested.

**CONFIRMED — active cancellation test:** a cancelled worker terminates its child,
waits for exit, removes incomplete job geometry/textures and retains diagnostics.
Source/base hashes stay unchanged. UI conversion gates prevent conflicting jobs
inside one instance; independent instances use unique work directories. Save As
rejects input/internal-candidate aliases, rechecks the hash and native structure,
then atomically copies the reviewed candidate. Existing destinations are backed up
by verified SHA-256 before replacement; unexpected destination changes abort saving.

**CONFIRMED — Windows CI evidence:** the portable workflow tests the full suite,
frozen UI and bundled Blender, then the frozen complete pipeline on reconstructed
Lance/Jericho HCTP containers with generated checkerboard textures and no developer
tools on PATH. These are **modified fixture containers**, not original PACs.
The original supplied containers were tested separately in the cloud environment.
**UNKNOWN/unrun:** a pristine Windows 10/11 VM and original-container conversion on
that VM; PATH isolation on a hosted runner does not establish that stronger claim.

The official runtime, source archive, library licenses and source code are included
in the release; game PACs are not. Users select their own base once. Build/runtime
integrity manifests and release SHA-256 sidecars identify each build. Tests use
small original synthetic vectors where possible and historical repository fixtures
only for development. Do not copy those references into an application bundle.

Failed preparation imports, platform newline differences and ~1e-14 BLAS float64
differences were exposed during Windows CI. Imports were made explicit, OBJ output
uses LF on every platform, and historical computed-metric comparisons now allow
only tiny arithmetic tolerance; serialized byte/attribute assertions remain exact.
The initial official-runtime download denied Python's default client; an identified
build-client request succeeded while TLS and checksum verification remained enabled.

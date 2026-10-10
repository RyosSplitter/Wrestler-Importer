# HCTP → PSP developer reference

This book is the standalone specification and development record for Wrestler
Importer. Start here, then read the [from-scratch guide](../../REIMPLEMENTATION_GUIDE.txt).
No previous conversation is required.

## Evidence convention

Every technical statement in this book is qualified either at the start of its
paragraph/list or by its table's **Status** column. A qualification applies to
all statements in that paragraph/list, code block or diagram. Evidence IDs link
to the [evidence ledger](evidence-ledger.md).

- **CONFIRMED**: demonstrated by the cited binary analysis, executable contract,
  test or recorded user gameplay result. Scope matters: a synthetic test confirms
  the implementation contract; it does not prove every game uses that layout.
- **INFERRED**: supported explanation or proposed generalization, without a
  conclusive engine-level observation.
- **UNKNOWN**: unresolved meaning, coverage, limit or causal relationship. Preserve
  the bytes, reject unsupported input, or request evidence rather than guessing.

## Recommended path and scope

**CONFIRMED [E01, E15–E21]:** The latest user-validated outcomes are Lance's
posterior-guard PAC and Jericho's eye/jaw plus elbow-pad PAC. They use the PSP
base skeleton, source-derived body weights, selective facial compatibility,
source-surface preservation, native structural validation and actual-PAC
preview checks. These are the reference outcomes for future work. Failed and
superseded paths are retained for diagnosis, not recommended as new defaults.

**INFERRED [E15–E21]:** The forward workflow should preserve sensitive source
surfaces before collapse, retain mapped source jaw/chin information, use proven
PSP ocular behavior where controller compatibility is not established, and run
anatomical, material-boundary, eye and posed regression QA. Applying those rules
to more wrestlers requires evidence; literal Lance/Jericho texture names are
experimental selectors, not a universal anatomical classification.

**CONFIRMED [E01]:** This documentation does not merge the experiments or change
the converter. The Windows beta still uses its pinned earlier opacity-fix
backend. Reproducing that beta is different from reproducing the latest accepted
models. [Reproduction](pipeline-and-reproduction.md) makes that distinction
explicit and includes both independent experiment branches.

**UNKNOWN [E22]:** Support for every HCTP wrestler, SYM, JBI, PS2 SVR, every PSP
SVR edition, all YOBJ/RTX3 variants and all real facial animations is not
established. The gameplay target tested by the user was SVR 2011 PSP,
ULUS10543; the 79-bone donor used in these conversions was PSP SVR 2007 Kurt.
The project goal is broader than the demonstrated coverage.

## Reading order

1. [Binary formats](binary-formats.md): PAC, BPE, HCTP and PSP YOBJ, POF0.
2. [Textures and rendering](textures-and-rendering.md): RTX3/TEX0, GIM,
   palette/alpha conventions and material controls.
3. [Rigging and optimization](rigging-and-optimization.md): alignment, weights,
   decimation, palettes, safe mesh organization.
4. [Pipeline and reproduction](pipeline-and-reproduction.md): dependencies,
   intermediate representation, scripts, accepted assets and packaging.
5. [QA and validation](qa-and-validation.md): metrics, renders, animation probes,
   stage tracing and acceptance policy.
6. [Failures and discoveries](development-history-and-failures.md): the failed
   assumptions, actual fixes and remaining uncertainty.
7. [Evidence ledger](evidence-ledger.md) and [fixtures/tests](fixtures-and-tests.md).

**CONFIRMED [E23]:** The small conformance fixtures are generated solely from
synthetic triangles, colors and weights. They require no original game PAC or
third-party editor. Published game-derived review bundles are separate historical
evidence and are not a substitute for obtaining source/base assets legitimately.
**UNKNOWN:** Distribution rights for user-provided game assets and third-party
tools are not established by this book; no rights to those assets are granted.

**CONFIRMED [E01/E15/E21]:** Current automated alignment and QA use deterministic
geometric algorithms and explicit profiles; no trained in-app AI guarantees
correct anatomy. Proposed body archetypes, interactive snap/alignment controls
and general automatic refinement are product goals rather than fully implemented
features. The comparison stage remains reusable and separate from conversion.

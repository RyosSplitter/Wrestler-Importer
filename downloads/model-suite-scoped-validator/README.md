# Scoped PSP-base validator evidence

- Real GUI worker smoke: Full no-op, Textures linear-GIM repair, Model single-slot
  repair, required base selector and Textures/Model/Full dropdown with Full default.
- Linux screenshot is the actual classic Tk options dialog, using synthetic
  fixtures. It is not Noesis or PPSSPP footage.
- Four native reference PACs (Benoit, Lance, Jericho, three-model Rock) passed all
  three modes without mutation. Native assets remain private.
- Earlier user-provided `the rock 2.pac` passed Full repair against the native Kurt
  PSP base, with the same zero-weight skinning compatibility correction and exact
  preservation of shape, skeleton, effective weights, UVs, topology and textures.
- Local full suite: **391 tests passed**. All 18 focused compatibility tests passed. Historical
  HCTP anatomical QA remains separate and retains its regression tests.

See [validator contract](../../docs/portable-pac-validator.md). Windows full tests, frozen converter, all three validation workers and the
mode/base dialog checks passed. See windows-release.json for build provenance
and the release asset digest matching its downloaded SHA-256 sidecar. These checks do not
establish in-game compatibility.

[Download the Windows update](https://github.com/RyosSplitter/Wrestler-Importer/releases/tag/suite-foundation-6-3935d556451b1d7b27d5fedf5956e6850a2028b2).

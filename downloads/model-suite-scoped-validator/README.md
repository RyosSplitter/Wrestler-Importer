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
- Local full suite: 390 passed before the last alias-recovery regression test was
  added. All 18 focused compatibility tests passed after that addition. Historical
  HCTP anatomical QA remains separate and retains its regression tests.

See [validator contract](../../docs/portable-pac-validator.md). Windows frozen
build/publication results will be recorded when complete. These checks do not
establish in-game compatibility.

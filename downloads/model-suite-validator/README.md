# Standalone PAC validator evidence

The suite GUI smoke exercises actual Tk tabs and background inspector, packer
and validator workers using synthetic fixtures. The screenshot is the application
on Linux/Xvfb; it is not a Noesis or PPSSPP capture. Native structural summary
contains only counts/statuses from private user-supplied reference PACs; no game
assets are distributed here. Kurt's oversized native reference is reported, not
reduced or rewritten to satisfy the configured conversion budget.

Local full suite: 373 tests passed. All 11 focused validator tests passed.
The GUI smoke also exercised a real single-slot repair through the isolated worker. Windows full-suite, frozen converter, folder editing, standalone validation and
verified repair checks passed in the published build. See windows-release.json
for provenance, step outcomes, exact size and verified release asset checksum.
The large Windows ZIP was built by Actions; its advertised asset digest matches
the downloaded SHA-256 sidecar. It was not downloaded or run on Linux.

See [validator scope and repair policy](../../docs/portable-pac-validator.md).

[Download the Windows update](https://github.com/RyosSplitter/Wrestler-Importer/releases/tag/suite-foundation-5-1f670a80002ab89094dfac63f00bfb1339d0fe5e).

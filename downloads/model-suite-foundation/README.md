# PSP Model Suite foundation evidence

See [the developer/user guide](../../docs/portable-model-suite.md).

- `linux-suite-smoke.json`: real Tk navigation, real isolated inspector, multi-model preview and exact-copy checks.
- `linux-converter-smoke.json`: existing converter controls/runtime checks inside the suite.
- `native-inspection-checks.json`: private local native/converted samples, every model inspected and exact PAC copies verified. No PACs or textures distributed here.
- `converter-preservation.json`: byte/hash evidence that conversion algorithms and texture policies were unchanged from the prior experiment tip.
- `suite-converter-linux.png`: actual Linux application capture; Windows uses native Vista controls.

The first full local regression run passed 348 tests. After native testing exposed upper/lowercase texture-table spelling, a new regression was added; all eight suite workspace tests pass, and Windows CI runs the final complete suite. New Windows build results will be recorded separately. The Model Creator and mutation tools remain planned.

## Published Windows preview

[Download the verified foundation build](https://github.com/RyosSplitter/Wrestler-Importer/releases/tag/suite-foundation-1-fa0a5f22f762a7ae8d4c5233b3807f8493739fd6). The full Windows regression step, frozen converter smoke, frozen suite navigation/worker/previews/exact-copy smoke, packaging and publication all passed. `windows-build.json` records the tested commit, step results, artifact size/checksum and practical limits. `suite-converter-windows.png` and `suite-editor-windows.png` are actual captures with generated conformance data.

The original full local run passed 348 tests; the final eight workspace tests include the added case-insensitive native-name regression. No claim of new in-game validation is made.

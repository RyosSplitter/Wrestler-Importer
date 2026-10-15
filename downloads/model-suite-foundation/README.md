# PSP Model Suite foundation evidence

See [the developer/user guide](../../docs/portable-model-suite.md).

- `linux-suite-smoke.json`: real Tk navigation, real isolated inspector, multi-model preview and exact-copy checks.
- `linux-converter-smoke.json`: existing converter controls/runtime checks inside the suite.
- `native-inspection-checks.json`: private local native/converted samples, every model inspected and exact PAC copies verified. No PACs or textures distributed here.
- `converter-preservation.json`: byte/hash evidence that conversion algorithms and texture policies were unchanged from the prior experiment tip.
- `suite-converter-linux.png`: actual Linux application capture; Windows uses native Vista controls.

The first full local regression run passed 348 tests. After native testing exposed upper/lowercase texture-table spelling, a new regression was added; all eight suite workspace tests pass, and Windows CI runs the final complete suite. New Windows build results will be recorded separately. The Model Creator and mutation tools remain planned.

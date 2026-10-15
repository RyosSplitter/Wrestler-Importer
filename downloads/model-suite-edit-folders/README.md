# Editable export folders and texture PAC rebuilding

See [the workflow and implementation contract](../../docs/portable-edit-folders.md).

Actual Linux GUI checks exported a folder, packed it unchanged through an isolated worker, edited a PNG, repacked again, refreshed the PAC library and previewed the output. Ten focused synthetic tests cover preservation, alpha, palette formats, invalid edits, concurrency, size enforcement and overwrite protection. The first full local regression run passed 360 tests; two additional focused regressions then passed. Windows CI runs the final full suite and packaged worker workflow.

Private Kurt, Benoit, Lance, Jericho and Rock preservation experiments passed; no game PACs/textures are distributed here. `native-preservation-checks.json` records exact no-edit copies and controlled one-map edits, including all three Rock models. `converter-preservation.json` confirms converter algorithms and the established PAC writer were unchanged.

This is texture editing at existing dimensions/palette capacity. Geometry/UV/material import, special effect palette editing, creator assembly and new game adapters remain outside this update. Generated-fixture GUI screenshots show actual decoded PAC results. No edited candidate here has new PPSSPP acceptance.

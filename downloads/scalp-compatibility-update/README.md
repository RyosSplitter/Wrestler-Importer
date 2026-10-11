# v0.25.1 validation evidence

- `tests.log`: 253 development-runtime tests passed.
- `regressions.json`: five existing wrestler samples, both texture modes; native checks, exact preservation and actual sizes.
- `exact-upload-proof.json`: reproduces the user-accepted Rock control SHA-256 exactly from the uploaded PAC.
- `fresh-e2e-qa-proof.json`: fresh Rock conversions; compatibility OFF reproduces the old current-method PAC, and complete static/body/head pose metrics match the updated adaptive output.
- `fresh-rock-layout-report.json`: exact final app-stage layout changes, buffer memory cost, preserved attributes and analytical motion.

Windows packaged checks and the downloadable app are provided by the isolated
[build workflow](https://github.com/RyosSplitter/Wrestler-Importer/actions/runs/38100126132).
See [implementation notes](../../docs/portable-scalp-compatibility.md).
No new gameplay validation is asserted for other wrestlers.

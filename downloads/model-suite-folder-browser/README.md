# Model Editor PAC folder browser

Choose folder in the editor, scroll/select PACs with the mouse or keyboard, filter names and Refresh. The last folder is remembered. Listings include direct child PAC files, case-insensitively, naturally sorted; files are not decoded merely by listing them.

Actual Linux GUI checks verify background inspection, single-click loading, filtering, latest-request selection, retained workspace on a bad PAC, folder preference storage, refresh, previews and exact copies. A separate fresh-process check restored the last directory alongside the existing PSP base without automatically opening a PAC. The eleven focused browser/workspace tests passed. Existing converter GUI smoke passed; protected converter/native workspace modules are byte-identical to the foundation preview.

Windows packaging and functional checks are run by the separate suite workflow; results will be recorded in windows-build.json when complete. Actual texture/geometry editing remains a separate forthcoming stage; this update adds folder navigation to the existing viewer/inspector.

## Windows preview published

[Download the PAC folder-browser update](https://github.com/RyosSplitter/Wrestler-Importer/releases/tag/suite-foundation-2-8ab5474b8a16d93d659ecec91854fff9e56201a7). The full regression step, packaged converter smoke, packaged folder/filter/queue/failure-recovery smoke, preview exports and exact-copy checks all passed. `windows-build.json` records the tested commit, artifact checksum and verification scope.

The Windows image deliberately shows the state after the invalid-PAC recovery test: the error status is expected, and the preceding valid model stays loaded. All models and textures in these GUI captures are generated conformance fixtures.

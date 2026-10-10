# PS2PSP Pac Converter by RyosPrime

Portable Windows 10/11 x64 **experimental preview**. Extract the **entire ZIP**
to a writable folder, then run `PS2PSP-Pac-Converter.exe`. The runtime is large
because it includes the tested Blender runtime, Python, numerical QA libraries,
licenses and Blender's source archive. No Python, Blender, Noesis or PAC Editor
installation is required. Conversion and previews work offline.

1. Select your own PSP SVR base wrestler PAC once. Its local path is remembered.
   The supported base has float-weight vertex buffers and ordinary indexed4/8
   material templates. An incompatible base is rejected with a diagnostic.
2. Select HCTP in the source container selector; drop or browse one PS2 `.pac`.
   Supported modified HCTP containers are accepted using binary contracts, rather
   than original character hashes. JBI, SYM and PS2 SVR remain disabled.
3. Convert. Processing, native validation, reference QA and preview rendering
   run in an isolated job. Cancel removes incomplete geometry and retains logs.
4. Review the **final PSP output**. Use front/rear/sides/three-quarter, Zoom and
   click the preview to enlarge it. Open the QA report for source comparisons,
   analytical poses, heatmaps and material-boundary findings.
5. Save PAC As. The candidate is re-audited and hashed immediately before copying.
   Saving into the source, base or internal candidate is rejected, including
   hard-link aliases. Existing destinations use the Windows Save As overwrite
   confirmation. The previous file is verified and retained under
   `.ps2psp-backups/<SHA-256>.pac` before replacement; a changed destination aborts
   saving. A new conversion never overwrites the inputs or its review candidate.

Inject into SVR 2011 PSP with your tested PAC Editor/ARC-update workflow, save a
copy of the ISO and test entrances, matches, facial motion and victory animations
in PPSSPP. Keep original PAC/ISO backups. An offline preview or native audit cannot
certify game compatibility or rule out runtime memory/animation issues.

Settings and jobs are in `%LOCALAPPDATA%\PS2PSP Pac Converter`. **Logs** opens the
active job; `error.log`, `geometry-*.log` and `qa.log` diagnose failures. Successful
jobs retain the PAC, exact embedded `preview/output.yobj`, textured OBJ/PNG export,
all intermediate geometry, texture manifests, `ocular-qa.json` and the independent
QA HTML/JSON report. Personal PACs stay local and are never uploaded by the app.

Native errors and the **148000-byte** budget block export. Review findings remain
visible and require an explicit experimental-export acknowledgement. Game tests
must establish whether the generalized rules are acceptable. Historical accepted
Lance and Jericho PACs remain unchanged; the preview does not claim byte-identical
reproduction of their wrestler-specific experiments.

## Developer build

On Windows x64, install Python 3.13 for development, then:

```powershell
python -m pip install -r requirements-desktop.txt
python -m unittest discover -s tests -v
python -m tools.build_portable
```

The builder downloads Blender 4.3.2 from its official HTTPS distribution, checks
the Windows ZIP against its published SHA-256, includes the corresponding source
archive and generates a manifest. Run the packaged `--smoke-test OUTPUT.json`
to exercise Tk drag/drop resources and the bundled Blender binary. The separate
`windows-portable.yml` workflow builds and tests this branch, then publishes a
prerelease. It never merges into main. See `portable-distribution.md` for notices
and `docs/hctp-psp/` plus `REIMPLEMENTATION_GUIDE.txt` for format details.

# v0.25.6 Default texture quality reference checks

The new Default automatically selects lost fine-detail maps using source image
analysis, occupied detail coverage and frozen model surface usage. Its independent
pixel/CLUT allowance is max(34176, actual Legacy allocation), with the unchanged
148000-byte whole-PAC cap. Legacy retains the previous texture method; manual
Priority Selection uses the new allowance. ATO remains the earlier comparison.

RVD's full new Default worker outputs 147456 bytes and automatically chooses the
front/back singlet at 128x64/128x32, without user selection. The model matches the
previously gameplay-tested RVD PAC byte-for-byte. The two singlet GIMs match that
trial; two hand maps also differ, so this is not a byte-identical whole PAC.

`reference-results.json` records RVD, Lance, Jericho, Benoit, Rock and 0401 checks,
allocation, source ceilings, configurations, quality metrics and analytical
motion/geometry preservation. Frozen baseline assets were never overwritten.
The RVD front/back sheets compare Legacy and new Default with identical geometry,
cameras and lighting. These are CPU renders, not PPSSPP captures.

The RVD fixed-detail trial has user-reported gameplay success; generalized
outputs still require model-specific in-game testing. Native observations do not
establish a universal runtime heap ceiling. All existing geometry/QA findings
remain reviewable. See docs/portable-default-textures.md for implementation,
reasoning, the narrow-source failure/repair and reproduction.

The app update is built/published through the Windows portable workflow on
feature/default-texture-quality. No original game PACs or third-party tools are
bundled in the application. Accepted baselines and main remain preserved.

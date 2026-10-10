# Development reasoning, failed assumptions and unresolved behavior

**CONFIRMED [E01–E25]:** This record preserves failures as evidence. The
recommended forward path is the latest validated hybrid/source-preservation,
selective facial and accessory workflow with separate QA, not the failed
candidates below. Historical filenames and reports remain unchanged even where
later analysis corrected an explanation.

| Symptom / experiment | Evidence and diagnosis | Resolution / status |
|---|---|---|
| Initial source `0900` mislabeled RVD | internal model/name-derived naming was misleading; later provided/identified Benoit source uses `bn_*` textures | CONFIRMED provenance correction E10; use hashes, not filenames/internal labels |
| HCTP YOBJ fails PSP geometry reader | source separate float4/group/corner/VIF structure differs from PSP interleaved GE layout | CONFIRMED E05/E06; separate readers and source IR |
| 424KiB PAC crashes | large file and CH.PAC screenshot suggested allocation/archive overlap; exact runtime/ARC data absent | CONFIRMED symptom E22; size/ARC causal explanation UNKNOWN; compact candidates plus archive checks |
| PAC Editor alignment warning | early generated allocations did not follow later explicit container/POF0 padding contracts | CONFIRMED alignment changes E02/E07; rebuild absolute16/final2048 and YOBJ POF0 padding; anatomy unrelated |
| Compact model still failed | seven ordinary face/body materials inherited first blood-overlay template | CONFIRMED binary mismatch E12; select regular0x5/0x7 templates; crash causality INFERRED |
| Visible skin missing/see-through |1082/1211 records nonopaque,225 zero; face/body alpha0/152 while images opaque | CONFIRMED E13; ordinary vertex alpha255; user confirmed transparency gone; retain texture cutouts |
| Face better, body/arms uncanny | uniform/aggressive simplification sacrificed local anatomy; beta arm material retained14.7% vs native Slaughter49.1% | CONFIRMED comparisons E11/E14; use source-derived weights, selective retention and compression; exact native studio algorithm UNKNOWN |
| Original1800 exceeds PSP test budget |553728-byte source; unchanged non-model data alone exceeds budget | CONFIRMED E16; abandon impossible identical-container trial; format/texture/donor conversion required |
| Beta1800 texture exception |old reader onlyPSMT8/32-bitCSM1; actual source includes8PSMT4 images | CONFIRMED E08; expanded RTX3 decoder and early detailed diagnostics |
| App's output too large |0.3/64 cap167936;0.3/32 cap149504;0.27/32 cap147456 | CONFIRMED beta fitting E01/E08; distinguish retention from removal, preserve partial logs; this is historical app path |
| HCTP→PSP bone-index copy unsafe |Slaughter shared names have changed indices/parents/transforms | CONFIRMED E14; map identities/ancestors and inspect bind/controller compatibility |
| Direct source-name mapping incomplete |Benoit8missing bones,52affected records,10unweighted diagnostic records | CONFIRMED E10; ancestor redistribution with missing-mass rejection |
| Automatic heat binding poorer |evaluated against four other methods and source/native references | CONFIRMED trial E10; hybrid/body-source mapping chosen; no universal heat-binding verdict |
| UVs/waist small details distorted |Blender attribute creation invalidated held RNA refs; UV assertions exposed corruption | CONFIRMED E11; create layers first/reacquire, preserve corner seams |
| Manual waist/mirror edit improves front but rear caves |later source-reference comparison shows original anchors and weights not preserved; some source weights became roughly42.6%root/56.1%koshi vs82.35%/17.65% | CONFIRMED E15/E16; source-reference positions plus correct weights/aliases, no arbitrary displacement |
| Previous pelvis restoration claimed posterior success incorrectly |negative nativeZ is **front**, not rear; `l-pan1/l-mune2` were front-facing | CONFIRMED erratum E15/E16; preserve history, use verifiedaxes, rear+side depth and source geometry |
| Rear silhouette looks almost identical yet volume caves |99.8088%silhouette overlap but inward-depthp95≈3.3752%height; rear p95≈2.4473%height | CONFIRMED E15; silhouettes alone insufficient; surface/depth stage trace |
| Rear defect first introduced by reduction |rear trunks23/55faces lost, back torso37/110; broadregionalfloor/seam protection lacks localshape guard | CONFIRMED saved-stage E16; freeze actual original rear surfaces beforecollapse; generalcurvature/volumeoptimizer not implemented |
| First protected posterior replay regresses neck |upperboundary pulled retained neck/head; neckp95 .207%→.487%height | CONFIRMED rejected trial E16; retain unrelated superior seam, restore only targetsourcepatch; finalrear/pelvis error float32roundoff |
| Meshes82 vs nativeJericho31 suspected engine limit |Lance57native buffers become82OBJmeshes duepalette/material splitting; merge57→52 leaves82OBJmeshes | CONFIRMED E19; safe metadata/palette-aware merges only; hard31limit UNKNOWN |
| Merge reduces draws but expands buffers |unionpalettes increaseper-recordstride;196256→202256bytes;storedPACunchanged139264 | CONFIRMED E19; measureexpanded andstored costs; runtimeeffect UNKNOWN |
| Intermittent entrance/victory crash and stretched turnbuckles |user observed first trials crashes then three without; innermodel audit alone does not measure renderer allocations/outerarchive | CONFIRMED reported symptoms E22; actualcause UNKNOWN; preserveworkinghash and compare archive/debugger traces |
| Jericho jaw good at rest, bad animated |oldheadblend injects neck/body weights; sourcejaw98.07%cranial,0%neck vs80.67%cranial,10.69%neck | CONFIRMED stage/influence evidence E17; preservemappedsourcecranial weights, unchangedgeometry; userjawfixed |
| Jaw-only fix makes eyes protrude |controllerweightmass increases, bind pivots/localframes differ; palettes and normalization valid | CONFIRMED records/probes E18; unsafe same-namecompatibility INFERRED rootsemantic; selectiveprovenPSPeye weights, preservejaw |
| Eye clip shows protrusion but no controller matrices |10.21seconds, symptomnear6.25s | CONFIRMED reviewed clip E18; exactgameanimationstream UNKNOWN; don't infer matrices from pixels |
| Jericho pointed elbow pad passes wholearmQA |3sharedmaterialanchors collapsedwithin oneArmsentry; sourcepad54/73→52/69 | CONFIRMED E20; protectoriginalpadmaterial/skinanchors; no jaw/eye rollback; useraccepted |
| Small pad defect missed by area percentiles |tinyboundarypeak lostamong broadROI samples | CONFIRMED regression E21; materialboundaryendpoint/midpoint maximum, p95 andposedseam checks |
| QA0.2 still flags other acceptedmodel differences |sixother hand/finger/lowerleg boundary findings remain | CONFIRMED E21; retainreviewfindings, don't relax thresholds to callallgreen |
| Noesis textures absent / wrong PAC shown |OBJ needs adjacentMTL/PNG, exportedmodelidentity mustmatch deliveredPAC | CONFIRMED E25; extractafterpackaging, compareYOBJhash, distinguishviewer vsCPU vsgame renders |

## Lessons carried forward

**CONFIRMED [E16–E21]:** The accepted Lance posterior guard restores original
source anatomy without an inflation heuristic; the accepted Jericho preserves
jaw improvements while selectively restoring safe ocular behavior and source
pad boundaries. Static/posed/native/actual-PAC identity checks accompany those
changes. User gameplay validation supports these particular hashes.

**INFERRED [E16–E21]:** General policies should preserve source shape where
simplification is sensitive, treat facial controller compatibility as selective,
protect internal material boundaries and use both local maxima and regional
metrics. New rules should be tested on paired source/native references, not
fit to a wrestler's texture names or a desired mesh count.

**UNKNOWN [E22]:** Remaining research includes real SVR animation extraction,
all facial-controller semantics, runtime allocation limits, any relationship
between draw fragmentation and arena corruption, rigid accessory attachment,
all opaque rendering fields and wider game/texture/VIF coverage. HCTP support
is promising and tested on specific inputs, not universally complete.

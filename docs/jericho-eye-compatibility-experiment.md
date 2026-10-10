# Jericho eye compatibility: preserve the jaw, restore proven ocular skinning

The prior facial correction kept all mapped HCTP cranial weights. That fixed Jericho's jaw in SVR 2011 PSP, but the user's PPSSPP test showed protruding eyes. This isolated experiment changes only source-eye/eyelid-supported weight records back to the previous PSP hybrid behavior. It retains every other weight record from the jaw-fixed version. It changes no geometry, UV, normal, color, index, skeleton, texture, material or rendering-control bytes.

[Test PAC](../downloads/Jericho-SVR2011-PSP-eye-compatibility-TEST.pac) · [Complete bundle: backups, Noesis preview, QA reports and comparison renders](../downloads/Jericho-SVR2011-PSP-eye-compatibility-TEST-bundle.zip) · [Actual PAC audit summary](../downloads/Jericho-SVR2011-PSP-eye-compatibility-TEST-validation.json) · [Combined facial-pose comparison](../downloads/Jericho-SVR2011-PSP-eye-compatibility-TEST-comparison.png) · [Eye-turn comparison](../downloads/Jericho-SVR2011-PSP-eye-compatibility-TEST-eye-turn-comparison.png).

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Eye-compatibility test PAC | 145408 (142 KiB) | `da7a9fa75b0941e58aba86881472f40129448b22880b5cc4fba478b265961bd9` |
| Corrected YOBJ extracted from that PAC | 194688 | `f4fba01b184ed012fa98038e24f07694b10a09ecd4a69ec984cd20f2d931ea47` |
| Complete bundle | 12888416 | `6420a5af50bcae590db05a1519c98577048e778dc6922a41df056d66b1ab2737` |
| Preserved earlier PSP, jaw broken / eyes apparently normal | 147456 | `1715f8f2768dbe1c8293461dd10c72d383397d660b8c61689365683bbf2f5729` |
| Preserved jaw-fixed PSP, eyes reported protruding | 143360 | `f4f60125520f48285b4d03cd59abc21b980af4eca24124bc5a29423108aa3f1e` |

## Evidence and root cause

The three inputs were the original HCTP `0600.pac`, the earlier `0600-PSP-hybrid-Jericho.pac`, and the experimental `Jericho-SVR2011-PSP-facial-weights-TEST.pac`. The original was aligned with one uniform bone-landmark similarity transform, not a nonuniform fit. The two PSP models have identical geometry attributes and triangle/index sequences, so their native record correspondence is explicitly verified before any weight copying. For original eye geometry, nearest-position correspondence is independently checked after alignment (maximum error about 4.7e-7 model units). Original source vertex indices are not assumed to match PSP indices.

The jaw correction increased average combined `l_eye`/`r_eye` influence on eye records from **18.52% to 88.27%**. Average head (`atama`) influence fell from **69.20% to 11.73%**. These are means over 81 PSP eye vertex records; they are not a percentage of triangles. The original HCTP eye surface has 50 records before PSP duplication and uses about 85.2% combined eye-controller influence.

The names map without missing entries, but the bind transforms are not equivalent:

| Controller | Aligned HCTP vs PSP pivot distance, model units | HCTP local rotation | PSP local rotation |
|---|---:|---|---|
| `l_eye` | 0.40023 | approximately 0, 0, 0 | approximately -90°, +90°, 0 |
| `r_eye` | 0.39959 | approximately 0, 0, 0 | approximately -90°, +90°, 0 |
| `l_mabuta` | 0.46611 | approximately 0, 0, 0 | approximately -90°, +90°, 0 |
| `r_mabuta` | 0.46511 | approximately 0, 0, 0 | approximately -90°, +90°, 0 |

All four are children of `atama` in both rigs. PSP has extra brow/corner controllers (`*_mayu_00/01/02`, `*_meziri`) while HCTP's `l_mayu` and `r_mayu` have no same-name PSP controller and map to the shared head ancestor. The complete raw bind records, world pivots, previous weights, jaw-experiment weights and changed native record IDs are in `trial/experiment.json` inside the bundle.

All eye vertices in the jaw-fixed PAC reference valid palette entries, have finite attributes and normalized weights. The issue is therefore not an out-of-range palette/serialization defect. The excessive eye-controller influence increases sensitivity to motion around incompatible pivots/frames. In an eye rotation probe, the jaw-fixed eye surface moves up to **0.17770 model units** away from the prior PSP eye behavior. A local controller translation probe differs by up to **0.10 units**. The selected candidate reduces both differences to **zero** while leaving non-ocular and jaw motion unchanged.

The uploaded 10.21-second camera/editor clip also shows narrow eye surfaces appearing to poke through adjacent facial skin at about 6.25 seconds. It supports the observed symptom but contains no bone matrices or animation stream. The exact game controller semantics cannot be recovered from pixels. The diagnosed unsafe assumption is that a matching HCTP/PSP controller name makes its source weights safe to preserve. In this trial, the previous PSP eye behavior is the empirical compatibility control; original-rig poses are a separate comparison, not assumed identical animation semantics.

## Exact correction and scope

The selection uses nonzero mapped source eye/eyelid controller support (`l_eye`, `r_eye`, `l_mabuta`, `r_mabuta`) in the reviewed jaw-fixed model. It does not use an arbitrary facial box, manual displacement or broad head rollback. None of the selected records carries a source lower-jaw controller influence.

There are **99 selected records**, of which **84 differ** between the two PSP versions: **66 eye records and 18 eyelid/surrounding seam records**. Fifteen selected records already agree and remain equivalent. Each changed record receives the exact float32 weights of the earlier serialized PSP version, copied by bone identity after verifying frozen geometry/topology. Every unselected weight record retains the jaw-fixed bytes. This retains post-decimation PSP ocular behavior rather than claiming a fresh nearest-donor query would reproduce the same weights on reduced eyelid/seam vertices.

Four palettes were rebuilt without merging or splitting meshes. All palette sizes stay within eight slots. Native counts remain 54 meshes, 2387 vertices, 2413 triangles, 4085 indices, 79 bones, 20 textures and 94 material records. The full per-mesh/submesh/vertex-weight audits are in `audit/`.

`tools/jericho_eye_guard_trial.py` is an opt-in experimental refinement tool. `model_qa/ocular.py` is a separate reusable QA stage. The normal converter and its defaults remain unchanged. The candidate is not yet a general conversion rule: broader compatibility rules need gameplay validation and evidence beyond this paired trial.

## QA and regressions

The complete source-reference QA suite ran at the existing 24000 samples and 320-pixel resolution, with unchanged tolerances: static geometry and all 12 analytical poses have **zero review flags**. Static metrics are exactly identical to the jaw-fixed baseline. Jaw-region p95 distances are unchanged in all 12 poses, including neck-turn, jaw-18 and jaw-25. Whole regional report dictionaries are not asserted identical because comparison render/depth fields include neighboring eye surfaces; the raw reports are retained.

The additional suite has **16 eye-specific probes**: rest, positive/negative world-axis eye rotations, separate left/right local eye turns, left/right lid closure, local controller translations on all three axes, combined eye/lid/neck/jaw motion, and PSP brow motion. It evaluates original HCTP skinning on its own rig and both PSP baselines on their rig. Unsupported original brow controllers are explicitly reported, not fabricated.

The old jaw-fixed model fails **14 of 16 ocular compatibility probes**. The candidate fails **zero**. Its eye motion matches the earlier PSP eye version exactly in every probe; non-ocular and jaw motion match the jaw-fixed version exactly. A whole-face revert is explicitly rejected by the jaw regression test. Invalid source geometry correspondence is also rejected.

**70 tests passed**, including the existing model QA, source weight, hybrid transfer, native mesh, compression, texture and PAC suites plus six new eye regression tests. Synthetic probes are not actual SVR game animation playback. In some original-rig probes, neither PSP version reproduces HCTP motion exactly; the report does not hide this or treat same-name motion as proof of compatibility.

Comparison renders use original-reference framing and identical cameras/lights for four panels: original HCTP, previous PSP, jaw-fixed PSP and selective candidate. They are CPU QA clay renders, not Noesis or in-game screenshots. The bundle contains a textured Noesis OBJ/YOBJ preview extracted from the actual final PAC.

## Packaging and gameplay test

The unchanged `tools.yukes_bpe.compress` and `tools.pac_repack.replace_sections` replace only section 2 of the jaw-fixed experimental PAC. Stored sections 8/9 are byte-identical, including texture alpha. The final decompressed YOBJ exactly matches the QA-reviewed candidate. The actual final PAC passes native pointer/offset/relocation/buffer/index/palette/weight checks, container range/nonoverlap checks, 16-byte section alignment and 2048-byte final alignment. Its **145408 bytes** are below the strict **148000-byte** cap.

1. Back up ISO, CH.PAC, ARC and the current wrestler slot. Inject only `Jericho-SVR2011-PSP-eye-compatibility-TEST.pac` into the intended ring-model entry with PAC Editor v6.7.1 and the established working workflow.
2. Resolve archive space/alignment changes with Rebuild as needed, update ARC against the resulting CH.PAC, verify entry size and no overlap, then save the ISO.
3. Restart PPSSPP fully and begin a fresh match instead of loading an old model save state. Repeat the expression/camera-editor sequence from the clip, then inspect both eyes/lids, brows and jaw in entrances, taunts, neck turns, gameplay and victory.
4. Keep the test independent from other modifications. Both prior PACs are preserved in `backups/` with hashes, and original repository baselines remain untouched.

The branch is `experiment/jericho-eye-compatibility`, based on the prior Jericho experiment. Nothing is merged into main; integration waits for the user's PPSSPP results.

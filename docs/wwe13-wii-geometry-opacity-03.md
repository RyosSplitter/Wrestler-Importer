# WWE ’13 Wii: geometry isolation and hair-opacity trials, round 3

**CONFIRMED — project state:** These are isolated experiments on
`experiment/wwe13-wii-feedback-02`. The application release and WWE ’13 app
integration remain on hold at the user's request until the geometry issues
are resolved. No changes were merged to main, and no production texture,
HCTP/JBI geometry, or PAC packaging algorithm was changed in this round.

**CONFIRMED — provenance:** The user clarified that Edge's complaint is missing
hair strands/gaps. All 14 previously exported nine-source study PACs were
rehash-checked against their original manifests and remain unchanged. In
particular, the accepted Barrett and Bradshaw APA PACs are retained. Full
machine-readable results, original/candidate hashes, counts, and new findings
are in [geometry-opacity-trials-03.json](wwe13-wii-nine-models/geometry-opacity-trials-03.json).
Private game assets are not new repository fixtures.

## Why the first geometry approach was rejected

**CONFIRMED — controlled measurements:** Blanket source UV-contact locks can
improve UV placement while substantially worsening surface geometry. Raising
hand retention to pass native gates did not fix this tradeoff:

| Experiment | Baseline whole-surface p95 / height | Candidate | Decision |
| --- | ---: | ---: | --- |
| Orton, UV locks + complete Hands region | 0.001993 | 0.008984 | Reject |
| Booker, UV locks + complete mixed hand-transition support | 0.004618 | 0.011109 | Reject |
| Bret ring, UV locks + 65% Hands floor | 0.003336 | 0.007316 | Reject |

These are 6,000-sample deterministic bidirectional surface comparisons, not
vertex-index comparisons. The complete rest, 14 analytical body poses, facial
controller probes, material-boundary tests, palettes, indices, weights,
serialization and allocated-offset checks were run. A native-gate pass only
proves the particular structural/serialization tests; it does not prove source
shape fidelity. Some higher hand-floor trials also exceeded the measured PAC
budget and were withheld rather than repackaged with relaxed limits.

**INFERRED — mechanism:** Locking more UV contacts at an unchanged aggregate
face-count floor transfers collapse pressure to the remaining edges. The
observed pelvis/foot regressions show why a lower UV score cannot justify a
global switch. This is supported by the stage reports, not a claim to have
instrumented Blender's internal collapse queue.

**CONFIRMED — mixed wrist classification:** The experimental reducer normally
places a triangle in Hands only when its average hand/finger influence exceeds
0.8. A genuinely mixed forearm/hand transition can therefore use the Arms
floor. An opt-in `--preserve-hand-transitions` probe uses any active hand/finger
support above 1e-7 instead. It does not edit influence values, weld vertices,
or displace points. A procedural Blender fixture demonstrates the difference
and checks the resulting surface under an analytical hand rotation.

**UNKNOWN:** This probe has not established a universally safe new retention
rule or face budget. It remains OFF by default. Its synthetic success does not
outweigh the full-model regressions above.

## Original UV-connected reduction domains

**CONFIRMED — implementation and trials:** The existing reducer can retain
original UV-index-connected islands as independent reduction domains instead
of collecting all islands of an anatomical region/material into one domain.
The new corpus CLI switch `--uv-island-domains` exposes this existing behavior
for reproducible experiments; it defaults OFF. Face floors are then applied
per component, and existing shared-position boundary guards remain active.
No arbitrary target PSP mesh count is imposed.

**CONFIRMED — rejection of a global policy:** This change alone is also not a
safe default. Whole-model trials introduced new facial findings on Orton and
Booker, new posed material-boundary findings on Bret, new shoulder-pose findings
on Billy, and regressions on the accepted controls. Bradshaw APA's control
fails the native pose gate. Bradshaw Acolyte's texture placement also worsens.
Barrett is not replaced merely because one aggregate metric improves. See the
JSON for the retained failures; do not relax the tolerances to pass these trials.

Reproduce the global diagnostic, with original privately supplied assets:

```sh
python -m tools.wwe13_wii_corpus_trial SOURCE.pac --base BASE.PAC \
  --out NEW_EMPTY_DIRECTORY --variant 0 --ratio .45 --hand-floor .5 \
  --costume-role ring --uv-island-domains
```

Booker's original tested hand floor is .75; Orton/Bret use .5. Costume roles
must be explicit; variant numbers are not reliable ring/entrance labels.

## Region-isolated Orton candidate

**CONFIRMED — construction:** To isolate the useful wrist change, an experiment
copies Head, Eyes, Mouth, Hair, Torso, Legs and any Preserved domains literally
from Orton's tested `reduced.json`. Only complete Arms/Hands reduction domains
come from the UV-island trial. The two `charted.json` references are required
to match exactly. No second decimation, normal recomputation, vertex movement,
manual weight correction, or texture allocation is applied to retained domains.

The reproducible assembly procedure is:

1. Read the checked baseline and UV-island trial `reduced.json` files. Require
   identical source `charted.json`, bones and texture bindings.
2. Copy baseline domains outside `{Arms, Hands}` and trial domains inside that
   set, renumbering mesh indices. Recompute record/face totals. Do not infer
   source identity from coincident position alone.
3. Check the original inter-region interface before packing. All 78 baseline
   Orton interface records still have an exactly coincident position on the
   replacement region (maximum measured distance 0). This is a contact check,
   not permission to average distinct weights.
4. Reuse `fit_ocular`, `enclose_influences`, `pack`, `pad_short_prepared`,
   `bounded_precision(..., divisions=65536)`, `serialize` and `adapt_yobj` from
   the unchanged established experimental construction. Preserve the usual
   nonshrinking influence-bound policy and explicit ocular manifest.
5. Extract the baseline GIMs from its actual PAC, not a stale image directory.
   Pass those exact GIMs through existing `texture_table` / `package_models`.
   Re-run `validate_trial`, `pose_qa`, hand reference envelopes and complete QA.
6. Compare decoded native retained triangles using texture ID, cyclic triangle
   orientation and exact position/normal/UV/color/global-bone-weight attributes.
   All 1,716 native triangles identified in retained baseline domains match
   exactly. The diagnostic face-centre association tolerance is 1e-4 model
   units; equality of the resulting corner attributes is exact.

| Orton ring | Baseline | Isolated candidate |
| --- | ---: | ---: |
| PAC bytes | 147,456 | 147,456 |
| Native triangles | 2,983 | 3,007 |
| Native vertex records | 2,856 | 2,861 |
| Native vertex buffers | 55 | 54 |
| Textures | 5 | 5, exact same GIMs |
| Surface p95 / reference height | 0.001993 | 0.001972 |
| Same-page original UV displacement p95, texels | 3.585 | 2.991 |
| Problem wrist-page UV displacement p95, texels | 11.708 | 4.112 |

**CONFIRMED — analytical evidence:** The matching close-ups show the large
misplaced black triangle at the wristband removed. Final native structural and
pose gates pass. Complete comparison QA produces no new `(region, pose, kind)`
findings relative to the tested baseline. All 50 existing review findings are
retained; this is not a claim that the model is free of source-fidelity issues.
The exact candidate is `7709424cf43e6be53c1f2e94d368e0ea7270b2ac6290c2b9250efc6345211130`.
Both wrists are shown because the original left-wrist report did not establish
whether “left” meant anatomical left or screen left.

**UNKNOWN — runtime:** This candidate still needs PPSSPP testing. Analytical
poses do not replay the actual SVR animation clips, collision/culling or heap.
It is eligible for a private trial, not an accepted production replacement.

**CONFIRMED — withheld Booker trial:** Arms/Hands isolation improves pad
appearance but introduces a left-hand rest finding. Keeping baseline Hands and
changing only Arms still raises left-hand regional p95 from 0.001463 to 0.001669
(reference height units), crossing the existing 0.0015 review tolerance. The
pad improvement does not excuse that regression. Both are retained for diagnosis
and withheld from the test download. Booker remains unresolved.

## Edge: spatial opacity loss despite preserved alpha values

**CONFIRMED — binary and image analysis:** The tested Edge Hair region already
has a 1.0 geometry retention ratio. Hair-page post-decimation UV displacement
is approximately 0.00010 source texels. Its page `w13_05` is reduced from a
128×256 source to 32×64. Source alpha *levels* survive nearest resampling, but
spatially thin strands can disappear between retained samples. Similar total
opaque area or a low aggregate alpha error cannot prove strand preservation.

**INFERRED — cause of at least part of the complaint:** Opacity minification
is a supported contributor to missing strands. This does not rule out culling,
layered-surface draw order, source dynamic hair-bone adaptation, or filtering.
The GPU alpha threshold and native rendering-control semantics remain UNKNOWN.

**CONFIRMED — isolated A/B builds:** Both new candidates retain the complete
expanded YOBJ byte-for-byte, including weights, palettes, normals, UVs,
materials and skeleton. Every non-hair GIM is also byte-identical. Only the
hair page changes to the observed legal T8 dimension 64×128. The 128×256 source
is not upscaled; 128×256 T8 itself is outside this experiment's observed-native
whitelist. The file-size cap does not authorize unobserved formats.

- A retains nearest source alpha at the higher resolution.
- B adds actual source RGBA samples for otherwise entirely vanished occupied
  opacity components of at least four source pixels at diagnostic cutoffs
  192, 128 and 64. It does not invent a tint or alpha level. This can enlarge or
  join coverage; it is an explicit experiment, not an automatic repair rule.

| UV-used support at diagnostic alpha 128 | Baseline | A | B |
| --- | ---: | ---: | ---: |
| Hair dimensions | 32×64 | 64×128 | 64×128 |
| Original support recall | 89.78% | 93.67% | 93.73% |
| Thin/edge support recall | 63.27% | 74.08% | 74.33% |
| Entirely lost components ≥4 source pixels | 3 | 3 | 0 |
| PAC bytes | 147,456 | 151,552 | 151,552 |
| Total pixel/CLUT allocation, retained tables included | 42,176 | 48,320 | 48,320 |

The unchanged donor envelope is 54,016 bytes. Complete actual PACs were rebuilt
through the existing packer and independently validated. Non-texture stored
sections are byte-identical. Native body/ocular serialization replay was rerun;
the previous complete geometric/posed QA is inherited only by verified exact
YOBJ identity, retaining the original report and both hashes. It is not
relabeled a new full geometric run or an in-game test.

**CONFIRMED — remaining review:** Both A and B still fail the provisional
spatial opacity review threshold. B's zero lost components does not mean every
fine edge is restored. Compare A first, then B in fresh PPSSPP matches. Do not
promote either based only on the offline images.

Reproduce with a checked baseline work directory containing the original
`result.json`, PAC, `candidate.yobj`, `packed.json`, contracts, source images,
texture report and native manifests:

```sh
python -m tools.wwe13_cutout_trial BASELINE_WORK --base BASE.PAC \
  --out NEW_EMPTY_DIRECTORY --texture w13_05 --width 64 --height 128
# Add --preserve-components for B. No production default changes.
```

**CONFIRMED — exact replay:** The component-support CLI reproduces B's PAC hash
`a30ae2cdde4d606aef8359cf96694b538ec317677eab17c218012d24bff7d258`.
A's supplied PAC hash is
`a793f19d73a76300560dd3a82e7faa3e6ab6295a9acac7747d35c9224fb480b4`.

## Reusable QA addition and remaining work

**CONFIRMED — implementation:** `model_qa.alpha_coverage` is a read-only,
source-UV-mask-aware comparison of actual decoded textures. It reports
precision/recall/IoU, missing and newly opaque pixels, thin-edge support and
entirely lost connected components, plus source-resolution ceiling violations.
The Wii corpus runner writes `qa/opacity-support.json` and includes its review
state in the existing source-fidelity decision. It does not edit textures.

**INFERRED — provisional limits:** Review is requested below 95% support recall,
below 85% thin-edge recall, or for an entirely lost component of at least four
source pixels, at diagnostic cutoffs 64/128/192. These are conservative review
settings, not corpus-calibrated acceptance limits or an emulation of the game
shader. Thin/edge pixels lie within 1.5 source pixels of transparent support.
Unused UV padding is excluded from scoring. Camera visibility is not modeled.

**CONFIRMED — tests:** The complete repository suite passes 596 tests in the
available Linux environment. The nine focused opacity/minification/mixed-wrist
checks also pass, including real background Blender reduction on a procedural
fixture. Tests cover equal-area but displaced opacity loss, unused padding,
fractional alpha, deterministic component rescue using real source samples,
source-resolution ceilings, and posed mixed-influence wrist preservation.
No new native Windows or clean-install run was performed in this round.

**UNKNOWN / unresolved:** Billy and Bret's overall shape/texture placement,
Booker's pad/wrist tradeoff, Bradshaw Acolyte's band placement, remaining
entrance geometry and actual runtime behavior are not declared fixed. The
prior entrance texture-only trials and successful HCTP/JBI paths remain intact.
Comparison images in the private trial bundles are CPU renders of decoded
PACs and adapted source geometry, not Noesis screenshots or game footage.

# SmackDown! Shut Your Mouth → PSP: initial source-format research

Research checkpoint 1; base `55dfbf82d5c25c302238fdec2651dde52e34b543`
(the current Creator/converter development branch). Work is isolated on
`research/sym-format-survey`. Production converter, profiles, native PSP writer,
packaging, creator and accepted model files are unchanged.

**CONFIRMED** means demonstrated by the referenced code/binary controls/tests.
**INFERRED** means a plausible design or related-format lead.
**UNKNOWN** means not demonstrated for an original SYM asset.

## What we can say now

- **CONFIRMED:** SYM is explicitly disabled in `desktop/adapters/__init__.py`.
  Selecting it is not an alias for the HCTP reader. The new research tool does
  not change this. A passing byte-layout probe never enables conversion.
- **CONFIRMED:** no confirmed original SYM PAC/YOBJ has been inspected in this
  checkpoint. The supplied models in the relevant history are identified as
  HCTP or PSP; renaming their files does not supply a SYM test case.
- **INFERRED:** the existing PSP construction, texture optimization, size-fit,
  serialization, structural QA and preview stages are the likely reusable
  backend. The new work should be a source adapter and source-game profile,
  with source-reference and animation QA, rather than a separate PSP writer.
- **UNKNOWN:** whether original SYM costume PACs use the exact HCTP container,
  geometry, VIF weights and texture variants. A related YOBJ family or a visible
  model in Noesis is not enough to confirm skinning or rendering compatibility.

The intended flow is:

```text
Original SYM PAC + provenance
    → read-only inventory / format comparison
    → validated SYM archive/model/texture/skinning decoder
    → common source representation WITH source-record identity and raw metadata
    → uniform alignment / verified pose normalization onto the user's PSP base
    → source-shape-preserving reduction + independently validated weight policy
    → existing PSP builder / texture optimizer / PAC writer
    → original-SYM reference QA + native PSP checks
    → controlled SVR 2011 PPSSPP validation
```

This is a research/integration design, not an implemented SYM conversion path.

## Source and tool evidence

### Supplied Noesis PS2 viewer

**CONFIRMED:** the supplied `fmt_wwe_ps2_yobj (1).py` is 38,613 bytes. Its hash
is pinned in [the evidence manifest](sym-research-evidence.json). It was inspected
as text; it was not imported, executed, or added as a runtime dependency.

**CONFIRMED about the tool, not about SYM bytes:** its description covers HCTP
through later PS2 titles and says bones/rigging are not loaded. A separate
`_sanitize_alpha` comment claims that one SYM skin/face texture had a varying
low fourth channel, possibly gloss/specular data. That function forces a varying
decoded alpha channel opaque when its maximum is below 200; flat channels are
retained and channels reaching 200 are left alone.

**INFERRED:** material-dependent fourth-channel interpretation is an important
SYM research lead. **UNKNOWN:** whether that channel is a gloss mask, actual
transparency, a GS blend operand, or something else for each SYM material.
The comment supplies no independently inspected SYM sample in this checkpoint.
It is not justification for making all SYM textures opaque. Genuine translucent
or cutout resources must remain intact; blood/bandage layers need state-specific
validation. The diagnostic only reports alpha statistics and never edits them.

### Related PS2 importer

Public research reviewed:
[Rumble Roses PS2 YOBJ importer](https://github.com/lynchreborn/Rumble-Roses-YOBJ-Import/tree/3c165db1874d3da75277455a54f8f03e762d4654).

**CONFIRMED about that repository:** its README explicitly says it *may* work
with JBI/SYM/HCTP, but does not fully support their technical aspects/shaders.
The inspected parser uses 64-byte part, 32-byte group, 80-byte bone and 208-byte
material records, plus VIF weight base `0x280`, like this project's HCTP reader.
Its header offsets are relative to a slice beginning at file byte 8, so comparing
them directly to whole-file offsets would produce a false 8-byte discrepancy.

**CONFIRMED about that parser:** it offers experimental four-weight lane
permutations, optional palette mapping, normalization and fallback bindings.
Its comments explicitly distinguish experimental permutations from identity.
**INFERRED:** weight-lane interpretation deserves a controlled test in SYM.
**UNKNOWN:** whether any such permutation applies to SYM. Do not adopt one because
it visually improves one pose. Weight sums can remain exactly 1 under a completely
wrong bone permutation; sums alone do not establish correct deformation.

**CONFIRMED:** upstream is GPL-3.0-or-later. Its code was inspected only, not
executed, copied into the converter, or used to normalize/fill missing weights.
Future code reuse must account for that license. No Blender dependency was added.

### Other public leads, with limits

- [WrestleMINUS](https://github.com/pozzum/WrestleMINUS/tree/905b2ca9442be42cc1df4da1ef9d121f5d022c8b)
  documents Yuke's containers/BPE and YOBJ model libraries. **CONFIRMED about the
  documentation:** its listed container versions chiefly concern much later
  titles. **UNKNOWN:** SYM coverage. It is not a SYM format specification.
- [SmackdownSYM texture project](https://github.com/Bladdee/SmackdownSYM/tree/6a85afe51a45937c4b2d31848044ac7c3943f87a)
  describes PCSX2 texture replacements. **CONFIRMED about the project:** it is an
  upscaling/replacement pack, not a native PAC/skinning decoder. Its replacement
  textures must not be used to infer original source dimensions or color limits.
- **UNKNOWN:** a verified SYM-specific QuickBMS script/decoder contract. The name
  `yukes.bms`, an extractor's output, or a broad family claim is insufficient
  without checking the exact script, archive variant and original asset bytes.

No third-party game models or upscaled textures were downloaded for the study.

## Existing format contracts to test against SYM

The following offsets describe **CONFIRMED HCTP/PSP control interpretations**,
not confirmed SYM fields. Integers are little-endian; observed YOBJ pointers
store address minus 8. This table is a comparison checklist, not a SYM decoder.

| Layer/record | Existing interpretation | SYM status / test needed |
|---|---|---|
| Costume PAC | `PAC `; u32 count at +4; 8-byte entries: u16 ID, u24 table-relative offset, u24 size | **UNKNOWN:** verify archive variant, duplicate IDs, model and accessory roles; inventory every section |
| BPE | `BPE ` wrapper; version 0x100; bounded lossless expansion | **UNKNOWN:** whether/where SYM uses this exact wrapper |
| YOBJ common header | 72-byte header; end = u32(+4)+8; mesh/bone/texture counts +24/+28/+32; pointers +36/+40/+44/+48 | **UNKNOWN:** verify sizes, pointer origin and descriptor variants |
| Bone | 80-byte record; name +0:16; local float4 +16; rotations +32; signed parent +48 | **UNKNOWN:** stride, indexing, names, coordinate system, local axes and controller meaning |
| PS2 mesh | 64 bytes; group/material counts +0/+4; pointers +8/+12; weight pointer +28; packet count +32; qwords +36; source count +40 | **UNKNOWN:** verify every field before decoding |
| PS2 group | 32 bytes; source count +0; palette size +4; position/normal pointers +8/+12; four palette words +16 | **UNKNOWN:** bone base, direct vs indirect palette, implicit groups |
| Position/normal | separate float4 arrays, stride 16; observed position W≈1 | **UNKNOWN:** local/world storage, scale, orientation, W semantics |
| PS2 material | 208 bytes; texture ID candidate +40; strip count/pointer +196/+200 | **UNKNOWN:** shader/GS state, alpha use, wrap, culling and overlays; retain raw bytes |
| Draw packet/corner | 16-byte packet; observed (3,3), count/pointer; 32-byte corner containing UVQ/index/float RGBA | **UNKNOWN:** primitive type, index/strip winding, UV origin, vertex color range |
| HCTP source weights | implicit rigid groups or VIF V4-32; max observed 160 source vertices/mesh; weight VU base 0x280 | **UNKNOWN:** SYM packet commands, destination mapping, four-lane order and influence semantics |
| Texture table | u32 count/0x100/0/16, followed by 32-byte named records | **UNKNOWN:** embedded vs sibling resources, duplicate names, archive roles |
| RTX3 | 64-byte header; TEX0 at +8; PSM/CPSM/CSM/CSA and dimensions; image size/pointer +36/+40 | **UNKNOWN:** SYM variants, pixel layout, swizzle and material-dependent alpha |
| TIM2 | generic format-0 picture header probe only; no new pixel decoder | **UNKNOWN:** actual SYM use, alignment/mips/CLUT/pixel layout |

The probe retains raw candidate mesh/group/material headers even when the
existing weight reader rejects them. This lets the next developer compare
actual differences rather than patching assumptions until a file happens to load.

## Where integration requires explicit work

**CONFIRMED by code audit:** enabling one UI entry is insufficient:

| Location | Current HCTP-specific behavior | Proposed work (**INFERRED**) |
|---|---|---|
| `desktop/adapters/__init__.py` | SYM explicitly unsupported | Add a separate adapter only after verified source fixtures exist |
| `desktop/adapters/hctp.py` | HCTP geometry/weights and source texture readers | Implement independent source decoding; preserve source records and metadata |
| `tools/hctp_read.py`, `tools/hctp_weights.py` | Observed packet/group/corner contracts and fixed VU interpretation | Reuse only the contracts SYM samples actually confirm; reject unfamiliar records |
| `desktop/core.py` | Global HCTP profile selection | Select a source-game profile; do not silently borrow HCTP anatomical/pose assumptions |
| `app/ps2_textures.py` | Main-source dependencies use named `txc`/RTX3; section 9 preference | Validate SYM formats and dependencies; investigate native material alpha before adapting |
| `desktop/accessories.py` | HCTP sections 6/7 mapped to PSP elbow-pad roles 26/27 | Establish actual SYM roles; preserve or explicitly reject other YOBJs |
| `model_qa/geometry.py:read_model` | Source PACs decoded through HCTP loader | Accept validated source adapters / common IR for original-SYM reference QA |
| `desktop/source_reference_qa.py` | HCTP reference loading/labels | Carry source provenance and adapter through QA and reports |
| Weight/identity/reduction stages | Selective HCTP facial handling and stable source records | Verify SYM controllers and source-record identity; preserve distinct coincident skinning |

**INFERRED:** keep the user's PSP base skeleton and rendering templates. A source
bone name or index alone is not proof that its controller has the same bind or
animation meaning as PSP. Map verified body influences; validate jaw, eyes,
eyelids, neck and hair independently before preserving source facial behavior.
Retain source texture dimensions/aspect ratios/useful colors as ceilings and
the established budget/structural checks. Never average source seams or reshape
the anatomy to make a bad mapping look correct.

**CONFIRMED about current policy:** the converter profile uses a 148,000-byte
target. **UNKNOWN:** universal game/runtime limits; a small compressed file does
not establish safe expanded GPU/heap usage. New SYM candidates still require
native readback and repeated in-game testing, including unrelated ring geometry.

## Diagnostic tool and verified controls

Added `tools/sym_research.py`, intentionally separate from application imports:

```bash
python -m tools.sym_research YOUR_SYM_PAC.pac \
  --declared-game sym --output NEW_RESEARCH_REPORT.json
```

**CONFIRMED by tests:** it preserves input bytes and refuses an existing report
path. It records hashes, container sections, all supported nested model/resource
entries, bounded BPE expansion, skeleton/header data, independent HCTP/PSP layout
probes, texture registers and decoded RTX3 alpha statistics. TIM2 is header-only;
unknown layouts (including unparsed DPAC) stay unknown. Signature hits in unknown
payloads are hints, not silently carved models. Node/depth/input/expansion/work/
pixel budgets bound the inspection; incomplete inventories are reported.

`--declared-game sym` records user provenance only. The report always says
`verified_source_game: UNKNOWN` and `conversion_supported: false`. A probe pass
does not certify source weight-lane semantics, pose, rendering or conversion.

**CONFIRMED non-SYM controls** (not substitutes for original SYM samples):

| Control | Source vertices | Triangles | Bones | HCTP weighted contract | Native PSP contract |
|---|---:|---:|---:|---|---|
| Original HCTP Benoit YOBJ, recovered from existing supplied-input review | 1,722 | 2,836 | 71 | pass; 38 weight packets | reject |
| Original HCTP Slaughter ring YOBJ, same provenance | 2,020 | 2,996 | 68 | pass; 46 weight packets | reject |
| Native PSP Batista PAC from prepared library | 1,514 PSP records | 1,497 | 79 | reject | pass |

Exact hashes and archive member names are in
[sym-research-evidence.json](sym-research-evidence.json).
No new game-derived fixture is committed. Existing control files stay unchanged.

**CONFIRMED validation:** 19 new research tests and 33 existing reader/texture/PAC/
portable-converter checks pass (52 total). Coverage includes malformed ranges,
unknown formats, all nested models, duplicate IDs, decompression/work limits,
raw rejected-skinning evidence, transparency preservation, metadata-only TIM2,
determinism, no title misidentification, disabled production SYM and no overwrite.

The relevant suite was run using Python 3.12 and the repository-pinned QA
dependencies in an ignored virtual environment. A missing historical Kurt base
fixture initially prevented one existing facial regression test from running;
it was restored byte-exact from two matching historical beta archives into
ignored `assets/`, then all 52 tests completed successfully. This is source/tool
validation, not a Windows GUI build or game test.

## Samples needed and acceptance gates

Next input: **one untouched original SYM wrestler PAC**, identified by wrestler,
attire, region/build and extraction tool. Prefer a wrestler already represented
in HCTP/PSP (e.g. Jericho, Benoit or RVD), because this helps investigate bone and
material conventions. Their anatomy can differ between games: the ORIGINAL SYM
surface, not a PSP wrestler's shape, remains the geometric reference.

If available, include the same wrestler's entrance variant and original matching
textures if those are external to the PAC. Do not pre-convert the textures or
weld/export the geometry to OBJ before supplying the native asset. No whole ISO
is needed. Subsequent validation should cover several different body/outfit,
hair/alpha and accessory cases instead of overfitting one wrestler.

1. **INFERRED gate:** inventory and fully account for native sections/resources;
   establish actual SYM versioned structures and unknown fields.
2. **INFERRED gate:** decode geometry/UVs/normals/materials and weights with source
   record provenance. Compare original source renders and actual file data; do
   not certify skinning because Noesis displays an unposed mesh.
3. **INFERRED gate:** establish uniform coordinate/pose normalization, bone maps
   and selective facial semantics with controlled posed tests. Reuse the existing
   source-shape, face/head, pelvis, seam, jaw and ocular QA.
4. **INFERRED gate:** build one isolated PSP candidate via the established backend,
   with actual serialized budget, palette/index/offset/alignment/weight checks,
   dependency preservation and a preview decoded from the exact exported PAC.
5. **INFERRED gate:** test entrance, match movement, face/eyes/jaw, victory, blood,
   repeated matches and runtime corruption in SVR 2011 PSP. Preserve all accepted
   baselines. Only then consider enabling the adapter for the validated scope.

**UNKNOWN until these gates pass:** original SYM conversion quality, arbitrary
SYM wrestler coverage, runtime stability and any automatic material-channel fix.

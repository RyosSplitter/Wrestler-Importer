# Lance Storm: controlled mesh-buffer merge trial

Five adjacent, compatible pairs were merged in the accepted **136 KiB half-texture Lance PAC**. Native YOBJ records fall from **57 to 52**. The original baseline remains unchanged. There is no target count of 31, no further decimation, and no new rigging or texture conversion.

Download the [experimental PAC](../downloads/1800-PSP-hybrid-compatible-mesh-merge.pac), [complete preview/audit bundle](../downloads/1800-PSP-hybrid-compatible-mesh-merge-test-bundle.zip), or [machine-readable before/after report](../downloads/1800-PSP-hybrid-compatible-mesh-merge-report.json). Actual Noesis captures: [before](../downloads/1800-PSP-mesh-merge-before-Noesis.png), [after](../downloads/1800-PSP-mesh-merge-after-Noesis.png).

**This does not establish a fix for stretched turnbuckles or intermittent crashes.** The native layout checks pass and the preview is unchanged, but game-side assumptions are undocumented. The expanded YOBJ grows by **6,000 bytes (3.06%)** because a combined palette needs more weight slots per vertex. Stored PAC size remains 136 KiB. This is a mesh-record experiment, not a reduction in expanded memory or primitive submissions.

## Counts and sizes

| Measurement | Before | Experimental after |
|---|---:|---:|
| Native YOBJ mesh records / vertex buffers | 57 | 52 |
| Noesis OBJ preview meshes, actually observed | 82 | 82 |
| Serialized vertices, including existing seam/chunk copies | 2,277 | 2,277 |
| Nondegenerate triangles, same winding and order | 2,276 | 2,276 |
| uint16 indices, including strip degenerates | 3,884 | 3,884 |
| Triangle strips, including no-op strips | 804 | 804 |
| Native material records | 96 | 96 |
| Noesis materials / textures | 19 / 19 | 19 / 19 |
| PSP skeleton bones | 79 | 79 |
| Expanded YOBJ bytes | 196,256 | 202,256 |
| BPE model-section bytes | 119,311 | 119,098 |
| PAC bytes | 139,264 (136 KiB) | 139,264 (136 KiB) |

Before PAC SHA-256: `04ff929f8621a768f7c7d3f0a9c2c6e680a587857ee0532044c8dc64880014b0`.

Experimental PAC SHA-256: `4f97dd464c9cafe119c8a4afecdabdc58c18bd014e20d2d7007f663ce60fd9db`.

## Why the converted model is fragmented

The actual build script, `prepare_reduced.py`, first assigns each triangle to the closest ordinary PSP base body part. Lance occupies 20 target parts. It then packs triangles into per-part bins limited to eight palette bones. Its cost comparison can deliberately create another bin even when an existing bin would fit: extending a palette adds float weight slots to every vertex already in that bin. The result is 57 native chunks, with 3–8 palette bones each. Materials are then grouped by texture within each chunk, producing 96 native material records.

This accounts for much of the fragmentation: there are real bone-palette boundaries, body-part boundaries retained by the conversion, and storage-cost splits. It is not simply one mesh per texture. Some storage-cost splits can be removed while retaining their full palette and attributes. That removal can increase expanded memory, as this trial demonstrates.

Noesis's OBJ count is not the native YOBJ mesh-header count. The same vertices/material partitions imported through an OBJ can yield different preview object counts from the native buffer structure. The actual before and after captures both report 82 meshes, 19 textures and 19 materials. These counts alone cannot diagnose the PSP corruption. Native records really changed from 57 to 52, while all material/strip records were retained.

## Exact merges

All IDs here and in the reports are **zero-based native YOBJ mesh IDs**, not Noesis object IDs. Target parts refer to the original Kurt PSP base used by the existing conversion. Vertex and triangle counts below are the combined original counts; none were removed or deduplicated.

| Original meshes | New mesh | Target part | Vertices | Triangles | Indices | Palette slots | New stride |
|---|---:|---:|---:|---:|---:|---:|---:|
| 26 + 27 | 26 | 8 | 198 | 173 | 323 | 7 | 64 |
| 29 + 30 | 28 | 9 | 95 | 118 | 164 | 7 | 64 |
| 35 + 36 | 33 | 10 | 86 | 65 | 107 | 8 | 68 |
| 40 + 41 | 37 | 12 | 104 | 120 | 196 | 8 | 68 |
| 52 + 53 | 48 | 19 | 201 | 224 | 368 | 8 | 68 |

The source vertices stay in their original global order. Each source material and each strip remains a separate record, in its original order. No strips were concatenated or regenerated. Existing indices receive only the vertex-base offset needed inside the combined buffer. Existing nonzero float32 weight bytes are copied into slots for the same bones; newly introduced slots contain zero. No normalization, pruning or quantization is performed.

The planner considers contiguous compatible partitions without a requested mesh count. Where overlapping compatible pairs achieve the same number of merges, it chooses the lower expanded vertex-buffer cost. Pairs 25+26 and 34+35 are individually compatible alternatives, but merging their respective triples would require 10 and 12 palette bones. Choosing 26+27 and 35+36 avoids 1,784 bytes of additional vertex data compared with those alternatives. Pair 28+29 has a five-bone union but crosses an original target-part boundary, so it remains separate conservatively.

## Which boundaries remain

Confirmed format constraints include eight or fewer weight slots, valid per-palette bone identities, matching GE attribute types, uint16 local indices, matching opaque mesh/palette metadata, and buffers within declared allocations. A palette union above eight cannot be represented by this weighted format without a further split or changing weights. Rigid accessories and weighted body buffers have different formats and are not interchangeable.

Other boundaries are retained as a conservative policy: nonadjacent chunks would change draw ordering; different original body parts might have undocumented engine meaning. Neither is claimed to be an inherent format prohibition. Differing materials, textures, alpha/blend state or primitive metadata stay in separate material/strip records even when the enclosing buffers are combined. Unknown rendering fields are preserved as bytes rather than guessed.

`audit/lance-pair-compatibility.json` evaluates every original pair, with the reasons for retaining each boundary. `report.json` maps **all 57 original meshes** to the 52 output records, including every unmerged mesh.

## Native references and per-mesh inventories

| Reference model section | Native meshes | Vertices | Triangles | Texture names | Material records |
|---|---:|---:|---:|---:|---:|
| Chris Jericho PSP, section 2 | 25 | 1,509 | 1,749 | 17 | 45 |
| Kurt Angle PSP, section 2 | 29 | 1,356 | 1,488 | 14 | 43 |
| Chris Benoit PSP, section 2 | 22 | 1,303 | 1,494 | 15 | 41 |
| Slaughter ring PSP, section 2 | 22 | 1,455 | 1,730 | 20 | 46 |
| Slaughter entrance body PSP, section 2 | 17 | 1,378 | 1,600 | 16 | 40 |
| Slaughter hat accessory, section 32 | 1 | 213 | 272 | 5 | 5 |

Jericho's native PAC also contains an auxiliary section 100, which expands to a nested PAC with JUDE and other non-YOBJ data. It is not counted as wrestler geometry. References were inspected read-only and were not repacked. Slaughter's hat is a rigid `0x11ff` accessory with a 36-byte stride; its attachment semantics are external to per-vertex skin weights. The supplied hat body's unresolved `sgt_ris` texture is not fabricated.

The supplemental uploaded `Base.yobj` has 1 mesh / 8 vertices / 6 triangles; `Full Body.yobj` has 31 / 1,194 / 1,318. Both have inventories in the bundle, but their game provenance is not assumed. Full Body uses a name-only ending without the 32-byte native model descriptor. Its read-only audit explicitly allows that variant; the native PAC rewrite and validation do not.

For **every mesh and material submesh**, the bundle's `audit/` directory contains:

- `LABEL-meshes.csv`: vertices, triangles, indices, material count, GE vertex flag, stride, float/integer weight encoding, active-influence histogram, weight-sum range, bone IDs/names, bounds, opaque mesh state and separation policy.
- `LABEL-submeshes.csv`: owning buffer count and distinct referenced vertices, triangle/index/strip counts, texture ID/name, material control, index format, inherited format/stride/palette, complete non-layout material bytes and per-strip opaque metadata.
- `LABEL-vertex-weights.csv`: each vertex's palette, complete slot weights and nonzero bone-weight pairs.
- `LABEL.json`: the same information plus every index-buffer address/range, all allocation extents, bone hierarchy, raw mesh headers, both material pointers and complete relocation locations.

Lance and the native body references use float32 weights with a 36-byte UV/RGBA8/normal/position suffix. Stride is `36 + 4 × palette slots`. GE flags encode the weight-slot count; `0x17ff` is the shared attribute-format base. Bone IDs stored in palettes are one-based, and reports also provide zero-based IDs. Index entries are uint16. Undecoded rendering properties are supplied in raw hexadecimal form and retained exactly.

## Validation and precisely changed data

Before packing, the original and modified models passed bounds checks for every allocation, every pointer, every local index and palette entry. Bone hierarchies are valid, all values are finite, weights meet the observed normalization tolerance, and both material index-pointer aliases agree. Every POF0 relocation corresponds to a parsed pointer field. Partial allocation overlaps are rejected. The secondary mesh count in the 32-byte model descriptor is validated as well as the main header count.

The source's mesh-first layout order is retained, followed by bones, texture names and the model descriptor. Vertex and index buffers preserve **16-byte alignment relative to the YOBJ pointer origin at byte 8**, rather than changing that convention to absolute file alignment. PAC sections are 16-byte aligned and the PAC ends on a 2,048-byte boundary. The final POF0 chunk is padded to a 16-byte total YOBJ size.

The following changed: the two mesh counts; layout pointers/sizes/padding and relocation locations; merged buffer counts and local indices; merged palette lists and GE weight-slot counts/strides; five merged bounding spheres; compressed section 2; PAC section-table offsets/sizes and zero padding. Merged bounds use the first original center and an upward-rounded radius enclosing every original sphere. Unmerged bounds remain byte-identical. Original opaque mesh fields, palette reserved fields, non-layout model fields and descriptor fields remain identical.

Byte-level semantic comparison proves unchanged position, UV, normal and color suffixes, unchanged **nonzero weight bits for each bone**, unchanged global index/triangle order and winding, unchanged material-state bytes and strip metadata/order. Bone-table bytes, texture-name bytes and model-name bytes are identical. Sections **8 and 9**, including all GIM palettes, alpha and texels, are stored **byte-for-byte unchanged**. `preview/optimized.yobj` equals the final PAC's decompressed model section.

Rest, elbow-flex, arms-up and knees-bent analytical LBS comparisons produce exactly zero difference. These are identical diagnostic poses, not a substitute for native game animations. Actual Noesis captures use the supplied OBJ files with native normals and decoded unchanged GIM pixels; orientation, face-cull and shading toggles were applied once. OBJ cannot encode PSP skinning or complete PSP render state. The common model-render area in the two captures is pixel-identical. **30 focused tests passed**, including deliberately invalid indices, bones, weight sums, pointer aliases, relocations, descriptor counts, and normalized-but-changed weights/render state.

The remaining risk is runtime behavior: this merge changes buffer/palette setup and expanded memory size despite identical decoded semantics. No hypothesis about turnbuckles, draw-count limits or memory safety is declared proven. Test this separately with the same SVR 2011 slot and established CH.PAC/ARC workflow; keep the accepted PAC for comparison.

## Preview and reproduction

Open `preview/optimized.obj` in Noesis beside `preview.mtl` and the 19 PNGs. `preview/before.obj` is the exact baseline comparison exported by the same method. Both native YOBJs and unchanged GIMs are included. All vertex normals are explicit; no smoothing or texture processing is newly applied.

From a repository checkout with Python, NumPy and Pillow installed:

```bash
python -m tools.psp_mesh_merge_trial \
  --input downloads/1800-PSP-hybrid-half-textures.pac \
  --provenance PATH_TO_BUNDLE/provenance.json \
  --output NEW_DIRECTORY
```

The provenance file pins the exact source YOBJ hash and verified original target parts. Optional `--reference label=PATH.pac` arguments reproduce the reference inventories. The reproduction never overwrites an existing output directory. The app's existing conversion pipeline and pinned beta pipeline have not been changed by this experiment.

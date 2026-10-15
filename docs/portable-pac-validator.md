# PAC compatibility validator: Textures, Model, Full

Use **Quality Assurance → Validate PAC...**. Select the PAC to validate and a
**working PSP base PAC**. The base defaults to the remembered validator base or
existing converter base. Select **Textures**, **Model**, or **Full** (default).
Leave **Apply verified repairs to a new copy** checked to make corrections.

The objective is a PAC the app can load and preview using supported PSP
structures. The base supplies format/rendering conventions. Its wrestler shape,
skeleton, weights, textures and arbitrary mesh counts are **not** replacement
assets or anatomical targets. A different valid bone count or mesh count is not
an error. Shapes, rigging, UVs, materials' texture bindings and topology stay intact.

## Modes

| Mode | Selected checks and repairs | Protected bytes |
|---|---|---|
| Textures | Texture tables, indexed GIM layout/lengths, swizzling, alpha and texture bit depth required by existing model materials | Every stored YOBJ/model payload; skeleton, geometry, UVs, weights, rendering records |
| Model | YOBJ pointers/allocations/indices/palettes/attributes, recoverable metadata aliases, material depth settings, base-compatible skinning layout, analytical poses | Every stored texture-table payload; no texture resizing or quantization |
| Full | Both domains; prefers retaining valid texture pixels and correcting model depth settings; requires actual successful app previews after repair | Shape, skeleton, effective weights, topology, UVs, unrelated PAC sections |

Container bounds, unique section IDs, actual PAC size and payload preservation
are always checked. PAC wrapper alignment can be repaired in every mode; it does
not change protected section payloads. **148000 bytes** remains the default
conversion target. This is not a universal native loader limit; native references
can be larger. The base itself is not constrained to the output PAC budget.

A single-domain success does not certify the other domain. For example, Textures
can repair linear GIMs while leaving a broken YOBJ untouched. Its report must say
Model **Skipped**, report app preview as unavailable, and retain the model bytes.
Use Full when the goal is a completely previewable result. A fully alpha-hidden
main model is not falsely certified just because five empty preview files exist;
alpha intent is reported rather than guessed from another wrestler.

## Reference comparison

The PSP base must pass native structural/material/texture checks and produce the
app's actual offline previews. The report records its hash, model sections,
formats, weight-slot conventions, material controls, texture dimensions and
pixel/CLUT allocation. Source bone names are compared diagnostically; missing or
different valid bones do not trigger replacement or weight transfer.

**CONFIRMED:** target output uses the established indexed4/indexed8 swizzled GIM
and RGBA8888 CLUT reader/writer and the native dimensions whitelist from the
supplied corpus. Different valid dimensions from the base are not automatically
wrong. Material depth bits follow verified T4/T8 behavior while retaining other
known rendering bits. A base with only T4 images is not evidence that all T8
images are forbidden; the existing native corpus also establishes T8 support.

The base is a compatibility reference, not an HCTP shape reference. The earlier
anatomical comparison remains available separately in
`desktop.source_reference_qa.validate_pac` and the existing conversion QA stage.
It is no longer the standalone validation dialog's workflow.

## Automatic repairs and evidence

**CONFIRMED by synthetic fixtures and strict round trips:**

- GIM normalization: convert a bounded padded linear pixel plane into the known
  swizzled layout without changing pixels/palette/alpha. Repair redundant GIM
  chunk lengths and pixel-pointer aliases only where header/frame address,
  dimensions, exact allocation and RGBA CLUT independently establish the layout.
  Opaque header bytes and row padding are retained. No palette or pixel data is
  invented from the base.
- Textures mode: if valid unchanged materials require another supported palette
  depth, convert the texture to that depth at the **same resolution**. RGBA remains
  exact when it fits. Otherwise RGB quantization is reported with RMSE/quantizer;
  alpha must remain exact. Unsupported dimension/depth pairs are withheld.
- Model/Full modes: fix a known T4/T8 material-depth mismatch by changing only the
  depth bit, retaining known remaining render-state bits. Do not copy donor
  material blobs or change material IDs. Unknown rendering states are reported.
- Model aliases: recover duplicate YOBJ size/descriptor-count/first-index aliases
  and final POF0 length from bounded authoritative arrays, strip addresses and
  the located POF0 boundary. Then strictly audit *all* allocations, indices,
  relocation entries and weights. An invalid authoritative index is never removed
  or substituted. The report lists every metadata byte offset and old/new value.
- Single-slot adaptation: pad float32 one-slot skinned buffers with zero-weight
  slots using a supported multi-slot convention observed in the base. Additional
  palette entries come from the **input** skeleton, never donor bone IDs. Exact
  vertex suffix/nonzero-weight bits, topology, materials, skeleton and opaque
  metadata are verified with the established native writer/preservation checker.
  No arbitrary larger palette limit or donor mesh count is imposed.
- POF0 zero padding and outer PAC alignment: retain relocation semantics and
  section identities/order. Refuse to discard unclassified nonzero gaps/trailers.
  Same-size section patches can preserve the complete existing wrapper in place.
- Reuse existing BPE compression when demonstrated by source/base storage for
  that role; always verify decoded equality. Oversized input may try selected
  sections' lossless base-compatible storage, without sacrificing model shape or
  silently downgrading textures.

**INFERRED:** applying the previously user-accepted Rock zero-slot compatibility
policy to the same supported layout using a base's slot convention is useful.
Native conventions are evidence, not universal SVR hardware/loader requirements.

## Post-repair acceptance

Build a private candidate, then run fresh native checks, selected-domain checks,
actual app extraction/export/rendering, and independent preservation checks.
Full requires five generated views for every model and a main model not provably
fully hidden by the app's alpha test. Every readable input model must retain its
positions, normals, UVs, vertex colors, effective bone weights, skeleton and
ordered triangles. Metadata-recovered models differ only at listed redundant
metadata offsets before their first successful audit. Never weld coincident
vertices or average legitimate distinct skinning records.

Measure final serialized bytes including headers/compression/padding. Texture
repairs also cannot increase total pixel/CLUT allocation beyond **both** the input
and usable base's observed allocation; report that envelope separately. It is a
reference safeguard, not a decoded engine heap limit. Try Model validation for a
depth mismatch that would otherwise grow textures too much.

If selected checks, allocation/size constraints or preservation fail, withhold the
repaired PAC. Keep diagnostic snapshots/reports. Never overwrite the input, base,
accepted baselines or an existing result folder. The converter is not changed.

## Output and reports

- `original.pac`, `base-psp.pac`: byte-exact snapshots and hashes.
- `base-preview/`: actual base app preview and native inventory.
- `before/`, `after/`: native audits, OBJ/MTL/PNG and five textured CPU rest views
  where recoverable. Failed previews remain explicit. Images are not Noesis/game
  screenshots. Auxiliary model identity is retained.
- `report.html`: selected/skipped domains, before/after findings, actual preview
  status/images, repairs, sizes, allocation, reference conventions and failures.
- `report.json`: machine-readable version 2 schema and complete preservation data.
- `repaired.pac`: only for a changed, accepted candidate. No redundant copy is
  created for an already compatible PAC.

**Last validation report** reopens the result. Validation runs in a background
worker; library navigation remains live. Originals and unselected data survive
cancellation. A final named PAC is atomically published, never partially written.

**UNKNOWN:** finite analytical poses and app preview do not prove actual SVR eye,
jaw, rigid attachment, animation, loader or runtime-memory semantics. Test changed
PACs in PPSSPP. Missing pixels, ambiguous texture bindings, invalid authoritative
indices/weights and unsupported GE formats are not reconstructible just by
looking at a different wrestler. They are reported for recovery/reconversion.
No HCTP anatomical correction or skeleton retargeting occurs in this validator.

## Developer API / evidence

```python
from desktop.pac_validator import validate_pac
report = validate_pac(
    'Existing.pac', 'Existing-qa-new',
    base='Known-working-PSP.pac', mode='full',  # textures / model / full
    repair=True, max_bytes=148000, resolution=256,
)
```

The frozen/source worker remains `--suite-validate REQUEST.json JOB_DIRECTORY`;
requests now require `base` and may set `mode`. `samples` is accepted for worker
backward compatibility but surface sampling belongs to the separate HCTP stage.
A completed inspection can still contain failed checks; inspect
`selected_validation_passed`, `app_viewable` and the selected-domain issues.

Tests: `tests/test_compatibility_validator.py` covers scopes, base-driven slots,
metadata/linear GIM/pointer recovery, depth mismatch choices, alpha, palette/RGB
preservation, unrelated payloads, unknown/corrupt data, size/allocation ceilings,
mode separation, no-op models and a different valid mesh count from the base.
Historical HCTP-source QA regression tests stay in `tests/test_pac_validator.py`.
Current evidence is in `downloads/model-suite-scoped-validator/`.

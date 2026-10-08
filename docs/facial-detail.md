# Facial detail candidate

The user confirms that vertex-opacity correction removes the transparency and
that overall shape is good. Close-up screenshots show missing eye detail and
an uncanny face. The preceding reduction removed all 64 eye triangles and one
8-triangle tooth material. Texture images alone cannot replace missing geometry.

The optional `--compact --detail` profile protects every source position used
by `rvd_eye`, `bn_ha`, `bn_ha2`, and `ts_naka`. It asserts that the protected
materials retain the exact original triangles by position. It allocates more
geometry to small facial features, and an indexed8/256-color palette to a
128x64 face image, versus 64x32/16 colors previously.
Other textures retain their preceding 4-bit budget. This improves the palette,
and image resolution. Less important body geometry is reduced more
aggressively and weights retain the two strongest influences to fit the budget.
This changes skinning; the largest discarded weight mass is about 49.8% and is
reported in the bundle. Joint and facial animation need an in-game check.
Shared source-mesh seam positions
remain protected and checked. The opacity correction and PSP base skeleton
are retained.

The complete PAC is 149504 bytes (146 KiB), below the user's original 148.5 KiB
slot size. It contains 830 triangles, 38 mesh chunks, 79 PSP bones and 15 textures.
This is a deliberate redistribution of detail, not an overall polygon increase.
All 64 eye, 16 tooth and 33 inner-mouth source triangles survive. Fresh conversion
checks serialized attributes, weights, winding, palette/depth material matching,
texture decoding and file alignment. The 36 existing unit tests pass. Blender
pose checks exercise the new geometry, but do not simulate PSP GPU state.

[Download the facial-detail test bundle](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-detail-test-bundle.zip).
Use `RVD-HCTP-to-PSP-detail-test.pac` with the same working injection workflow.
The matching native model and named PNG/GIM textures are in `preview`.
In-game appearance and stability of this variant require the user's test.
Keep the previous working opacity build for comparison.

To reproduce, add `--detail` to the existing `--compact` conversion command.
The converter still refuses to write a PAC larger than 148 KiB.

PAC SHA-256:

```text
3b83ab1e1489c0f00aa6b7b72e77cfe7e25f61f012a20c5409c60f60cf6d0f9a
```

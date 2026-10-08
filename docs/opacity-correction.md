# Opaque PSP body vertices

The user now reports successful game loading, entrance playback, and a match in
SVR 2011 PSP, without crashes. Screenshots show the converted wrestler with
see-through skin, missing face/body surfaces, and visible pants textures. This
is an in-game result reported by the user; PPSSPP was not run in this cloud.
It establishes a working baseline for appearance fixes, not a universal size
limit or approval of all animation behavior.

The exported model carried PS2 corner alpha values into PSP vertex colors:
1082 of its 1211 vertices were below fully opaque, including 225 with alpha zero.
Of the face-textured vertices, 182 had alpha zero; all 237 body-textured vertices
had alpha 152 rather than 255. Both the supplied PSP Kurt and Full Body reference
have alpha 255 for every vertex. The converted face and body GIM images have
opaque pixel alpha, so making those images opaque again would not address the
vertex opacity problem.

The HCTP preparation profile now sets vertex alpha to 255 while preserving RGB,
geometry, normals, UVs, skin weights, and material assignments. Source alpha is
retained in prepared JSON and its histogram is reported. The library's explicit
`vertex_alpha_policy='source'` override permits future profiles that need source
vertex transparency. Raw HCTP reading remains unchanged. Image alpha is kept,
including transparency in the two `bn_ha`/`bn_ha2` cutout textures.

The native alpha values are confirmed and match the missing-surface symptoms.
The corrected build still needs the user's in-game test to establish how much
of the reported appearance problem this fixes. Texture detail, UV layout,
deformation, or culling can be investigated separately if defects remain.
Triangle orientation relative to normals agrees with the PSP reference;
there is no evidence here supporting a global winding reversal.

## Candidate and checks

[Download the opacity-corrected PAC with matching Noesis YOBJ/textures](https://github.com/RyosSplitter/Wrestler-Importer/raw/refs/heads/main/downloads/RVD-HCTP-to-PSP-opacity-fix-test-bundle.zip).

Use `RVD-HCTP-to-PSP-opacity-fix-test.pac` with the same working injection
workflow. The PAC is still 147456 bytes (144 KiB). Compared with the preceding
material-corrected build, exactly 1082 native vertex alpha bytes change to 255;
every other byte in the PAC is identical. All 1211 vertices now have alpha 255.
All original 45 mesh chunks, 877 triangles, 79 PSP bones, material controls,
texture indices, 15 GIM payloads, texture-table order, section offsets/sizes,
and alignment are retained.

36 unit tests pass, including a regression test confirming that the opacity
profile preserves RGB, geometry, weights, UVs, materials and input files, and
that its explicit source-alpha override preserves the source values. A complete
fresh conversion passes independent serialization checks. Repacking again gives
identical bytes. The bundled preview YOBJ and every named GIM are exactly the
payloads embedded in the PAC.

Extract the ZIP and open `preview/prepared.yobj` beside its PNG/GIM textures in
Noesis. The DAE is retained for geometry/texture previews; that editor export
does not serialize the native vertex-opacity channel. Blender pose assets are
retained because geometry and skin weights are unchanged. Those Workbench
previews do not simulate PSP alpha testing, blending, face culling, or GPU state.

The previous package remains available as the user-tested loading baseline.
Archive/ARC debugging is no longer the primary investigation unless a new test
introduces a loading failure. No changes to the user's ISO, CH.PAC or ARC were
made in this environment.

PAC SHA-256:

```text
c3a89e2171c6d757b1d4ef1b76cd0041d1ca881c8370a3bfbc21f2658d4c2710
```

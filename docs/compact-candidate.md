# Compact HCTP RVD test candidate

This describes the previous compact build, which the user reports still does
not work. Use the [material-corrected candidate](material-state-fix.md) for the
next test. Size alone did not resolve the failure.

The user reported that the 424 KiB PAC crashed in SVR 2011 PSP after injection,
ARC update, and ISO save. The destination `EMD\00010001.pac` was originally
148.5 KiB. The new candidate is 144 KiB (147456 bytes), a 66% reduction,
below that original size. This does not confirm a hard slot limit or the cause
of the crash; a second game test is required.

The available donor/base is still the supplied SVR 2007 PSP Kurt PAC. This
candidate therefore tests a 2007-based model in the user's 2011 game. The
user confirms that PSP SVR PACs are interchangeable. Another 2011 destination
PAC is not required for investigating the converter's output. The supplied
base remains selected; playability of the converted model is unverified.

| Component | Original candidate | Compact candidate |
| --- | ---: | ---: |
| Model section | 247280 bytes | 116896 bytes |
| Main texture section | 179744 bytes | 21984 bytes |
| Preserved base section 8 | 7072 bytes | 7072 bytes |
| Complete padded PAC | 434176 bytes | 147456 bytes |
| Triangles | 2836 | 877 |
| Sectioned vertices | 2825 | 1211 |
| Mesh chunks | 58 | 45 |
| Native bones | 79 | 79 |

Blender 4.3 collapse simplifies the source before weight transfer. Every
original geometric position shared between source meshes is protected and
checked to remain exactly present after simplification. Per-corner UVs and
colors are carried through reduction; normal vectors are recalculated.
Textures are resized to at most 64 pixels per dimension and quantized to
16 RGBA colors, using the same swizzled 4-bit GIM layout seen in the PSP base.
These changes deliberately reduce detail. Weight transfer retains up to four
influences and eight palette bones per mesh; no skeleton is retargeted.

Independent checks confirm unchanged target bone-table bytes, valid normalized
weights, exact serialized vertex attributes, triangle winding, 16-byte section
alignment, and 2048-byte total alignment. Every GIM decodes to its budgeted PNG
pixels/palette. Repacking twice produces identical PAC bytes. Thirty unit
tests pass. Blender pose previews and deformation diagnostics accompany the
download; they do not exercise PSP animation or prove playability.

The `preview` folder includes `prepared.yobj`, `prepared.dae`, and all named
PNG/GIM textures together for Noesis. The YOBJ and every named GIM are
byte-for-byte identical to their payloads in the compact PAC. Noesis plugin
texture-loading support still varies.

PAC SHA-256:

```text
3336c609339b8000e83a03af3dee6e2987d5ef0abf332adb76cdf95f064de9ad
```

## Re-test from a clean archive

1. Start from backed-up, unmodified game archives. This experimental candidate
   uses the supplied SVR 2007 PSP Kurt base.
2. Inject the compact PAC into the intended wrestler entry using the original
   slot filename. Rebuild the containing archive as required by the editor,
   update its ARC, and reopen the resulting CH.PAC before saving the ISO.
3. Extract the injected entry again and compare its size/hash to the candidate.
   Also verify that the containing archive's entry ranges do not overlap.
4. Test loading, appearance, then movement/joints and entrances. If it still
   crashes, report the PSP game/version, whether loading or animation triggered
   it, and PPSSPP's error/log text.

The screenshot lists the replaced entry at `0x4000` and the next entry at
`0x6000`, only 8192 bytes apart. The supplied v4.3.2 DPK8 parser treats offsets
as physical byte addresses and the size as stored bytes, without decompression.
Under those semantics the shown 424 KiB entry overlaps its neighbor. v6.7.1's
table and the actual modified CH.PAC are unavailable here, so this is a separate
archive concern requiring verification, not a confirmed cause of the crash.
Even the 144 KiB candidate starting at `0x4000` ends at `0x28000`; a different
entry starting at `0x6000` would still overlap it. Updating ARC alone does not
establish that the internal CH.PAC table is consistent.

The user confirms that the original `00010001` was 148.5 KiB, so it was not an
8192-byte placeholder. That makes the screenshot's 8192-byte gap worth checking
against the actual saved archive. No changes to the user's ISO/CH.PAC were
performed in this environment.

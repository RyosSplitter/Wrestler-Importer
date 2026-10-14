# SVR 2011 instant-blood CWCheat experiment

This is an isolated PPSSPP test tool. It changes no PAC, ISO, model, production
converter or uploaded save state. The distributed code is specific to the
captured match allocation layout and defaults to disabled. It is not a verified
universal SVR cheat. Raw states, extracted RAM/VRAM and game-code dumps stay local.

## Evidence

**CONFIRMED:** The user identifies `ULUS10543_1.00_1.ppst` as before bleeding,
`ULUS10543_1.00_2.ppst` as afterward, and Player 2 as the bleeding wrestler.
Both use PPSSPP v1.20.4, revision-5 Zstandard save containers. Decompression
validates decoded lengths and Zstandard integrity; Memory-section markers
validate the 32 MiB RAM and 2 MiB VRAM boundaries. The embedded game code matches
the ULUS10543 profile and is unchanged at all four instruction fingerprints.

**CONFIRMED binary observations:** The native first-blood transition changes
Player 2's level byte and bleeding flag from 0 to 1. His live 16-colour RGBA CLUT
changes from 64 zero bytes to an exact copy of his cached first-blood CLUT.
Player 1's corresponding records remain at zero/transparent.

| Captured record | Address | Before | After |
|---|---|---|---|
| Player 2 actor pointer cell | 0x08D0F7B0 | 0x0920CFA0 | same |
| Player 2 level, actor +0x7BA | 0x0920D75A | 0 | 1 |
| Player 2 bleeding flag, actor +0x7C1 | 0x0920D761 | 0 | 1 |
| Cached first-blood CLUT | 0x09F0F1C0 | 64 native RGBA bytes | same |
| Live face CLUT | 0x04140A40, VRAM | 64 zero bytes | exact cached CLUT |

All scalar addresses/fields are little-endian. These heap and VRAM addresses
belong to these two snapshots; they are not asserted stable in other matches.

**CONFIRMED through disassembly:** Routine 0x08BF6594 locates named `blood`,
`blood_b` and bandage resources and caches the staged palette records. Routine
0x08BF3ED0 chooses the face/chest/bandage stage, updates the corresponding level
byte and copies 0x40 bytes into the live CLUT through native GIM accessors.
0x08C3EDC4 writes actor +0x7C1 on the first bleeding transition, followed by the
level write at 0x08C3EDC8 and native stage application. Actor +0x7C1 is also
consumed by the blood-emitter code. This is substantially stronger evidence than
an unclassified 0-to-1 memory scan.

**INFERRED:** Reproducing those blood records should immediately display the
first blood stage and let the native emitter observe the bleeding flag.
**CONFIRMED (user-reported gameplay):** The original captured-match code worked
in the user's test match. This establishes that layout's activation in PPSSPP,
not compatibility with every wrestler or fresh match allocation.
**UNKNOWN:** Success in other layouts, texture-cache timing in other situations,
game statistics, callback effects and match-rule handling without running every
original transition callback. New codes still require gameplay testing.

## Resolving the native CLUT

**CONFIRMED profile / implementation:** The analysis validates these pointer
chains instead of assuming a graphics byte range is a wrestler status flag:

```
Player actor = *(0x08D0F7AC + 4*slot)
Blood manager = *(GP - 0x2D60), GP = 0x08CF4F30
Cached model = *BloodManager + 0x220*slot
Face texture index = *(CachedModel + 0x6C)
Texture name container = *(CachedModel + 4)
Handle = *(*(Container + 4) + 8*FaceIndex)
Texture manager = *(GP - 0x2F68)
Handle node = *(TextureManager + 8) + 8*(Handle & 0xFFFF)
Texture object = *(HandleNode + 4), after verifying full handle generation
GIM reader = *(*(TextureObject + 0x58) + 4*TextureObjectFrame)
Palette header = *(GIMReader + 0x10)
CLUT = palette frame table entry; verified as PaletteHeader + 0x40 here
Cached first stage = CachedModel + 0x80
```

The actor slot/model identity must match the cache. The texture identifies itself
as `blood`. The palette header is checked as RGBA8888, 16×1 entries, 32 bits,
one frame and one level. Other palette layouts or missing overlays are rejected.

## CWCheat encoding and validation

**CONFIRMED PPSSPP v1.20.4 source semantics:** Normal CW addresses are
`(encoded_offset + 0x08800000) & 0x3FFFFFFF`. A type-5 memcpy adjusts both source
and destination this way and cannot express this low VRAM destination. The
generated code uses the supported type-6 pointer-copy command instead:

```
_L 0x6097B990 0x00000040  ; pointer cell, copy 64 bytes
_L 0x00000002 0x05DCE7C0 ; one copy subcommand, source delta
_L 0x10000040 0x00000000 ; destination delta +0x40
```

These explanatory inline comments are not included in the actual INI. In this
layout, `*0x0917B990 = 0x04140A00`; adding the source delta gives 0x09F0F1C0,
while adding the destination delta gives the live CLUT at 0x04140A40. Two
8-bit writes then set the captured actor's level and bleeding flag to 1.

**CONFIRMED implementation:** Fourteen type-C code-stopper guards precede every
write. They pin four relevant code words, Player 2's actor pointer/vtable/slot and
model identity, the cache manager/array/model, the texture reader array/frame,
and the palette-header pointer. A mismatch stops this cheat block. No scratch
allocation, code cave, injected function, game-code modification or guessed
VRAM-address conversion is used. Other cheat blocks are unaffected.

**CONFIRMED offline replay:** Applying the emitted commands to a copy of the
before snapshot reproduces the after snapshot at exactly the targeted blood
records. Restoring the declared writes makes both RAM/VRAM arrays byte-identical
to the original before snapshot. Player 1 and unrelated data remain untouched;
the separate match-end singleton is not written. This validates the encoding
and memory footprint, not execution in the actual emulator.

Ten synthetic-fixture tests verify the copy, two byte writes, other-player and
unrelated-memory preservation, guard rejection, idempotence, palette/handle
rejection, file boundaries, version rejection and truncated commands. The tests
contain no game/save-state data. The source and independent field measurements
are in `tools/svr2011_blood_cheat.py` and the downloadable report.

PPSSPP format/cheat implementation references:

- [Serializer.cpp, v1.20.4](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Common/Serialize/Serializer.cpp)
- [MemMap.cpp, v1.20.4](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/MemMap.cpp)
- [CwCheat.cpp, v1.20.4](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/CwCheat.cpp)
- [CwCheat.h, v1.20.4](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/CwCheat.h)

## Testing and regeneration

Enable Cheats in PPSSPP's System settings. Open Cheats → Edit cheat file and
append the supplied `_C0` block and its `_L` lines to `ULUS10543.ini`, preserving
existing cheats. Include the supplied `_S`/`_G` header only if creating an empty
file. Load the original before-bleeding save, `ULUS10543_1.00_1.ppst`, then enable
`Instant Blood P2 - Captured Match TEST`. Check whether Player 2 immediately
displays blood. Disable the checkbox after activation; leaving it enabled holds
the first blood palette and can obscure progression. Reload the untouched before
state to undo the in-memory changes.

**UNKNOWN:** Whether a First Blood match ends on this injected flag without the
original callback. That mode can finish as soon as the game observes bleeding;
a normal singles match is preferable for prolonged inspection. A different model,
arena, memory layout, ISO/PAC edit or fresh match can make guards refuse to apply.
It is not sufficient to copy this snapshot-specific code into another game ID.

Regenerate for another supported captured layout from a same-match before/after
pair rather than removing guards. Requires Python and either the `zstandard`
module or a system libzstd; this is an analysis-tool dependency, not an app change.

```sh
python -m tools.svr2011_blood_cheat before.ppst after.ppst new-output --player 2
python -m unittest tests.test_svr2011_blood_cheat -v
```

The generation profile currently requires v1.20.4, 32 MiB main RAM, supported
blood CLUT structure, identical allocations between states, and the observed
0→1/transparent→cached-first-stage transition. Other cases fail explicitly.

## New-layout activation from one before state

The original paired-state generation remains available and unchanged. Once the
native activation profile has been established, a new match can be inspected
and given its own guarded code without requiring blood to activate naturally:

```sh
python -m tools.svr2011_blood_cheat before.ppst new-output --snapshot-only --player 2
```

**CONFIRMED implementation:** This mode verifies the same code fingerprint,
actor/cache identity, texture handle and palette structure. It requires zero
blood status bytes and a transparent live CLUT. Offline replay must copy exactly
the cached 64-byte palette and set exactly the two target bytes. Restoring these
three declared writes must recover all original RAM and VRAM; repeated replay
must be idempotent. Reports explicitly mark `after: null` and
`observed_after_state_comparison: false`. This is a native-profile replay, not
an observed after-state comparison. Uploaded states remain private and unchanged.

**CONFIRMED binary observations in the supplied Benoit before state:** The old
code stops at the Player 2 actor-pointer guard before performing any writes.
Player 2 has a loaded named `blood` texture and a visible cached first-stage
palette, while both blood flags and the live palette are initially zero.

| Record | First captured match | New Benoit match |
|---|---|---|
| Actor | 0x0920CFA0 | 0x0921E210 |
| Cached model ID | 0x69DD | 0x2711 |
| Blood level | 0x0920D75A | 0x0921E9CA |
| Bleeding flag | 0x0920D761 | 0x0921E9D1 |
| Palette header pointer cell | 0x0917B990 | 0x0918C4E0 |
| Live face palette | 0x04140A40 | 0x04140A80 |
| Cached first-stage palette | 0x09F0F1C0 | 0x09F0F1C0 |

**UNKNOWN:** Visible overlay coverage and appearance on the experimental Benoit
PAC until the user tests this new code. A loaded blood resource alone does not
prove correct rendered overlays or identify the complete PAC by its hash.

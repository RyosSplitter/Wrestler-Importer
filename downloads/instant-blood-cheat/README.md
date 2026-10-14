# Instant Blood P2 — captured-match test

Use this first with your untouched **before-bleeding** state,
`ULUS10543_1.00_1.ppst`. It is for SVR 2011 US / ULUS10543 and PPSSPP 1.20.4.

1. Enable Cheats under PPSSPP Settings → System.
2. Open Cheats → Edit cheat file. Append the `_C0 Instant Blood P2...` block and
   all `_L` lines from `ULUS10543-Instant-Blood-TEST.ini` to your existing
   `ULUS10543.ini`. Keep existing cheats. If the file is empty, use the whole INI.
3. Load the before-bleeding save you sent, then enable
   **Instant Blood P2 - Captured Match TEST**.
4. Check Player 2's face. Disable the cheat after blood appears, so the game can
   advance blood stages. Reload the original before state to reset the test.

Fourteen guards protect the captured actor/cache/palette layout. If enabling it
does nothing, keep the guards; a new match or edited PAC may have different
allocations and need a regenerated code. It is **not a universal all-match cheat**.
A First Blood match may finish immediately; normal singles allows longer viewing.

Confirmed offline: the generated commands reproduce the observed Player 2 first-
blood palette and two blood flag bytes, preserve Player 1, and change no unrelated
RAM/VRAM. Seven generated-fixture tests pass. Live PPSSPP appearance, callback and
match-rule behavior remain untested. This freezes the initial stage while enabled.

No uploaded states, extracted memory, game executable, ISO or PAC are distributed.
The converter and accepted PACs remain unchanged. `report.json` contains the
captured addresses, input hashes, native-field evidence and replay checks.
See `docs/svr2011-instant-blood-cheat.md` and `tools/svr2011_blood_cheat.py` on
branch `experiment/svr2011-instant-blood` for analysis and regeneration.

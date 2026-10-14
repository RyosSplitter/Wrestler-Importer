Benoit Player 2 instant-blood test - SVR 2011 US (ULUS10543)

1. Enable Cheats in PPSSPP System settings.
2. Open Cheats -> Edit cheat file (ULUS10543.ini).
3. Append the supplied _C0 block and ALL its _L lines; keep existing cheats.
   Include _S/_G only if creating an empty file.
4. Disable the old "Captured Match TEST" instant-blood code.
5. Load your untouched ULUS10543_1.00_3.ppst state.
6. Enable "Instant Blood P2 - Benoit Match TEST" and resume the match.
7. Disable after the blood appears. Leaving enabled holds the first blood stage.

This new code uses this match's Player 2 addresses. The old code stops at its
actor-pointer guard without making any changes here. Both status bytes and the
live palette are initially zero in your new state; the loaded native cache has
a visible first-blood palette. Offline replay passed and changes only the live
64-byte blood palette and two Player 2 status bytes. Gameplay remains to test.

Keep using Benoit-PSP-Blood-Overlay-EXPERIMENTAL.pac. Neither that PAC nor your
state was edited. Reload the untouched state to undo activation. New matches
can change addresses; do not remove the guards to force this code to apply.
This does not emulate every native bleeding callback or match statistic.
Your uploaded state and extracted memory are not included in this download.

# Current PAC file-size policy

**CONFIRMED — user instruction, 2026-10-21:** The in-ring output cap is exactly
**152,064 bytes = 148.5 KiB = 152.064 kB** for all conversion formats, including
HCTP, JBI, SYM/OBJ experiments, and WWE ’13 ring models. WWE ’13 entrance trials
retain their separately requested **180,000-byte** cap.

The shared constants are in `desktop/limits.py`. HCTP's packaged JSON profile
matches the shared ring constant and is checked by a regression test. Texture
allocation, Default/ATO/Priority/Downgrade/Maximum Downgrade, compatibility
repair, native readback, creator budgets, UI messages and reports use this
policy. Existing native PAC import/inspection remains independent of the
conversion output cap; editor round trips may preserve a larger native source.
The creator still warns on oversized export rather than silently changing its
previously agreed warning-only behavior.

**CONFIRMED — arithmetic and real native validation:** Sector-padded exports
use 2,048-byte alignment. The largest aligned ring PAC below the configured cap
is **151,552 bytes**. The next aligned size, **153,600**, exceeds the cap. The
policy is not rounded down internally: reports retain the exact 152,064-byte
target and separately report their effective aligned ceiling. Compared with
the old 148,000-byte policy, this allows 4,096 additional stored bytes after
sector padding.

**CONFIRMED — scope:** This is a stored-file limit, not an instruction to change
geometry, rigging, weights, alpha handling, native pointer/alignment checks or
the separately enforced donor pixel/CLUT allocation envelopes. Existing working
PACs are preserved. They are not silently regenerated to consume more space.

**UNKNOWN:** The repository does not independently prove the complete SVR 2011
runtime heap or every loader condition from this policy value. Continue the
existing per-model PPSSPP validation workflow.

**CONFIRMED — historical preservation:** Old reports/downloads retain their
original measured sizes and 148,000-byte policy. The hash-verified
`stable_pipeline` backend and archived experiment fixtures are preserved for
reproduction; the legacy beta application wrapper supplies the corrected
current limit without changing that backend's attested files. New code and new
reports use today's shared policy. Do not copy an old report's ceiling into a
new implementation.

QA accepts an explicit `max_pac_bytes` parameter (CLI `--max-pac-bytes`) and
reports `configured_max_pac_bytes` and `within_configured_pac_budget`, rather
than a field whose name permanently embeds the old 148000-byte threshold.

Procedural regressions in `tests/test_shared_pac_limit.py` exercise the real
native reader with a 151,552-byte PAC, verify that 153,600 bytes is rejected,
and check that active entry-point defaults and the HCTP profile agree.

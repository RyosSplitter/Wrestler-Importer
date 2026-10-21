"""Shared output-size policy, separate from format and runtime-memory checks.

The user corrected the in-ring file limit to exactly 152,064 bytes. Do not
round the policy itself to KiB or sectors; packers measure their actual output.
"""

IN_RING_MAX_PAC_BYTES = 152_064
WWE13_ENTRANCE_MAX_PAC_BYTES = 180_000
PAC_SECTOR_BYTES = 2_048


def aligned_ceiling(limit=IN_RING_MAX_PAC_BYTES):
    return limit // PAC_SECTOR_BYTES * PAC_SECTOR_BYTES

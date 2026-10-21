"""Explicit WWE '13 trial budgets; costume index does not identify costume role.

The entrance limit is user-configured, not a demonstrated runtime heap limit.
Other format, alignment and observed donor texture-memory gates still apply.
"""

from desktop.limits import IN_RING_MAX_PAC_BYTES, WWE13_ENTRANCE_MAX_PAC_BYTES

PAC_LIMITS = {'ring': IN_RING_MAX_PAC_BYTES, 'entrance': WWE13_ENTRANCE_MAX_PAC_BYTES}


def budget(role='ring'):
    if role not in PAC_LIMITS:
        raise ValueError('Costume role must be ring or entrance; do not infer it from bundle index')
    limit = PAC_LIMITS[role]
    return dict(costume_role=role, max_pac_bytes=limit,
                maximum_sector_aligned_bytes=limit // 2048 * 2048,
                authority='User-configured WWE13 trial limit; runtime compatibility requires in-game testing',
                texture_memory_policy='Keep independently measured native donor envelope unchanged')


def result_role(result):
    """Old reports had one conservative cap. Never reinterpret them by index."""
    role = result.get('budget', {}).get('costume_role', 'ring')
    expected = budget(role)
    recorded = result.get('budget', {}).get('max_pac_bytes', expected['max_pac_bytes'])
    # Retain original attestations from before the corrected ring limit. Reading
    # them does not rewrite their budget or assert they were built under today's.
    historical_ring = role == 'ring' and recorded == 148_000
    if recorded != expected['max_pac_bytes'] and not historical_ring:
        raise ValueError('Recorded WWE13 budget disagrees with costume role')
    return role

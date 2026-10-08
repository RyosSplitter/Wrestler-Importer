"""Greedy oriented triangle strips and optional degenerate strip bridges."""
from collections import defaultdict


def stripify(triangles):
    triangles = [tuple(t) for t in triangles]
    adjacency = defaultdict(list)
    for index, (a, b, c) in enumerate(triangles):
        if len({a, b, c}) != 3:
            raise ValueError('Degenerate triangle passed to stripifier')
        for u, v, w in ((a, b, c), (b, c, a), (c, a, b)):
            adjacency[(u, v)].append((index, w))
    remaining = set(range(len(triangles)))
    strips = []
    while remaining:
        index = min(remaining)
        a, b, c = triangles[index]
        candidates = []
        for start in ((a, b, c), (b, c, a), (c, a, b)):
            strip, used = list(start), {index}
            while True:
                u, v = strip[-2:]
                edge = (v, u) if (len(strip) - 2) % 2 else (u, v)
                options = [(i, w) for i, w in adjacency.get(edge, []) if i in remaining and i not in used]
                if not options:
                    break
                next_index, w = min(options)
                strip.append(w)
                used.add(next_index)
            candidates.append((strip, used))
        strip, used = max(candidates, key=lambda candidate: len(candidate[1]))
        strips.append(strip)
        remaining.difference_update(used)
    return strips


def join_strips(strips, max_indices=65535):
    """Join disconnected strips without adding visible faces or reversing winding.

    Repeated indices create zero-area bridges. An extra repeated start index
    keeps the next strip's first real triangle at even parity. Respect the
    PSP GE's 16-bit draw count when batching.
    """
    if max_indices < 3:
        raise ValueError('A strip needs room for at least three indices')
    result = []
    for strip in strips:
        if len(strip) < 3 or len(strip) > max_indices:
            raise ValueError('Strip length is outside the PSP draw-count limit')
        if not result:
            result.append(list(strip))
            continue
        current = result[-1]
        bridge = [current[-1], strip[0]]
        if len(current) % 2:
            bridge.append(strip[0])
        if len(current)+len(bridge)+len(strip) > max_indices:
            result.append(list(strip))
        else:
            current.extend(bridge)
            current.extend(strip)
    return result

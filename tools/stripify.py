"""Greedy oriented triangle strips without degenerate bridge triangles."""
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

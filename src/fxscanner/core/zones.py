from __future__ import annotations

from collections.abc import Sequence

from fxscanner.models import Pivot, Zone


def _split_wide(cluster: list[Pivot], max_width: float) -> list[list[Pivot]]:
    """Recursively cut a cluster at its largest internal gap until it is narrow enough."""
    if len(cluster) < 2 or cluster[-1].price - cluster[0].price <= max_width:
        return [cluster]
    gaps = [cluster[i + 1].price - cluster[i].price for i in range(len(cluster) - 1)]
    cut = gaps.index(max(gaps)) + 1
    return _split_wide(cluster[:cut], max_width) + _split_wide(cluster[cut:], max_width)


def build_zones(
    pivots: Sequence[Pivot], tolerance: float, min_touches: int = 2, max_zones: int = 3
) -> list[Zone]:
    """Cluster pivot prices (highs and lows) into zones; keep the strongest.

    Neighbouring prices within ``tolerance`` of each other join a cluster, and any
    cluster wider than ``tolerance`` is cut at its largest gap. Nothing here prefers
    the top or bottom of the chart, so a flipped chart yields the mirror-image zones
    (support and resistance are treated identically). Using both highs and lows
    captures role reversal. Strength is touches, then recency.
    """
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    clusters: list[list[Pivot]] = []
    for p in sorted(pivots, key=lambda x: x.price):
        if clusters and p.price - clusters[-1][-1].price <= tolerance:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    narrow = [part for c in clusters for part in _split_wide(c, tolerance)]
    zones = [
        Zone(
            low=min(p.price for p in c),
            high=max(p.price for p in c),
            touches=len(c),
            last_index=max(p.index for p in c),
        )
        for c in narrow
        if len(c) >= min_touches
    ]
    zones.sort(key=lambda z: (z.touches, z.last_index), reverse=True)
    return zones[:max_zones]

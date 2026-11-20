from __future__ import annotations

from collections.abc import Sequence

from fxscanner.models import Pivot, Zone


def build_zones(
    pivots: Sequence[Pivot], tolerance: float, min_touches: int = 2, max_zones: int = 3
) -> list[Zone]:
    """Cluster pivot prices (highs and lows) into zones; keep the strongest.

    Using both highs and lows captures role reversal. Strength is touches, then recency.
    """
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    clusters: list[list[Pivot]] = []
    for p in sorted(pivots, key=lambda x: x.price):
        if clusters and p.price - clusters[-1][0].price <= tolerance:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    zones = [
        Zone(
            low=min(p.price for p in c),
            high=max(p.price for p in c),
            touches=len(c),
            last_index=max(p.index for p in c),
        )
        for c in clusters
        if len(c) >= min_touches
    ]
    zones.sort(key=lambda z: (z.touches, z.last_index), reverse=True)
    return zones[:max_zones]

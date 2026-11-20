from __future__ import annotations

from collections.abc import Sequence

from fxscanner.models import Candle, Pivot


def find_pivots(candles: Sequence[Candle], n: int = 2) -> list[Pivot]:
    """Swing highs/lows confirmed by ``n`` lower/higher bars on each side.

    A pivot at index i is only reported once bars i+1..i+n exist, so results on
    truncated data are always a prefix of results on the full data (no lookahead).
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    pivots: list[Pivot] = []
    for i in range(n, len(candles) - n):
        around = [candles[j] for j in range(i - n, i + n + 1) if j != i]
        c = candles[i]
        if all(c.high > o.high for o in around):
            pivots.append(Pivot(i, c.high, True))
        if all(c.low < o.low for o in around):
            pivots.append(Pivot(i, c.low, False))
    return pivots

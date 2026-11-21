"""Property test: the rules must treat buys and sells identically.

Flip a price series upside down and every buy must become a sell with the same R, and
vice versa. This caught a real bug (zone clustering anchored on the lowest price).
Costs are zero because spread is genuinely asymmetric (longs pay it on entry, shorts on exit).
"""

from __future__ import annotations

import random

import pytest

from fxscanner.backtest.engine import CostModel, run_backtest
from fxscanner.config import StrategyConfig
from fxscanner.core.zones import build_zones
from fxscanner.models import Candle, Pivot, Side

PIP = 0.0001
AXIS = 1.10


def random_market(seed: int, n_h1: int = 5000) -> tuple[list[Candle], list[Candle]]:
    rnd = random.Random(seed)
    price, drift = AXIS, 0.0
    t0 = 1_700_000_000 - (1_700_000_000 % 14400)
    h1: list[Candle] = []
    for i in range(n_h1):
        if i % 400 == 0:
            drift = rnd.uniform(-0.00004, 0.00004)  # slow regimes so trends and pullbacks occur
        close = price + drift + rnd.gauss(0, 0.0007)
        high = max(price, close) + abs(rnd.gauss(0, 0.0003))
        low = min(price, close) - abs(rnd.gauss(0, 0.0003))
        h1.append(Candle(t0 + i * 3600, price, high, low, close))
        price = close
    h4 = [
        Candle(g[0].time, g[0].open, max(c.high for c in g), min(c.low for c in g), g[-1].close)
        for g in (h1[k : k + 4] for k in range(0, len(h1) - 3, 4))
    ]
    return h4, h1


def flip(candles: list[Candle]) -> list[Candle]:
    return [
        Candle(c.time, 2 * AXIS - c.open, 2 * AXIS - c.low, 2 * AXIS - c.high, 2 * AXIS - c.close)
        for c in candles
    ]


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_backtest_is_mirror_symmetric(seed: int) -> None:
    cfg, costs = StrategyConfig(), CostModel()
    h4, h1 = random_market(seed)
    original = run_backtest("X", h4, h1, cfg, PIP, costs)
    mirrored = run_backtest("X", flip(h4), flip(h1), cfg, PIP, costs)
    assert len(original) > 5  # the test must actually exercise trades

    def key(trades: list, side: Side) -> list[tuple[int, float]]:  # type: ignore[type-arg]
        return sorted((t.entry_time, round(t.r, 6)) for t in trades if t.side is side)

    assert key(original, Side.BUY) == key(mirrored, Side.SELL)
    assert key(original, Side.SELL) == key(mirrored, Side.BUY)


def test_zones_are_mirror_symmetric_and_bounded() -> None:
    rnd = random.Random(7)
    pivots = [Pivot(i, 1.0 + rnd.random() * 0.02, i % 2 == 0) for i in range(60)]
    tolerance = 0.0015
    flipped = [Pivot(p.index, 2 * AXIS - p.price, p.is_high) for p in pivots]
    a = build_zones(pivots, tolerance, min_touches=1, max_zones=100)
    b = build_zones(flipped, tolerance, min_touches=1, max_zones=100)
    norm_a = sorted((round(z.low, 9), round(z.high, 9), z.touches) for z in a)
    norm_b = sorted((round(2 * AXIS - z.high, 9), round(2 * AXIS - z.low, 9), z.touches) for z in b)
    assert norm_a == norm_b
    assert all(z.high - z.low <= tolerance + 1e-12 for z in a)
    assert sum(z.touches for z in a) == len(pivots)  # every pivot lands in exactly one zone

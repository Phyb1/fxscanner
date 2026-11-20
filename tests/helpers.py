from __future__ import annotations

from collections.abc import Sequence

from fxscanner.models import Candle

WICK = 0.0003
H4 = 14400


def path_candles(
    waypoints: Sequence[float], steps: int = 6, start_time: int = 0, step_seconds: int = H4
) -> list[Candle]:
    """Candles tracing straight legs between waypoints.

    Rising candles carry an upper wick, falling candles a lower wick, so swing
    points are unambiguous (no tied highs/lows).
    """
    candles: list[Candle] = []
    prev = waypoints[0]
    t = start_time
    for a, b in zip(waypoints, waypoints[1:], strict=False):
        for k in range(1, steps + 1):
            close = a + (b - a) * k / steps
            rising = close >= prev
            high = close + WICK if rising else prev
            low = prev if rising else close - WICK
            candles.append(Candle(t, prev, high, low, close))
            prev = close
            t += step_seconds
    return candles


def mirror(candles: Sequence[Candle], axis: float) -> list[Candle]:
    """Reflect prices around ``axis`` (uptrend fixture -> downtrend fixture)."""
    return [
        Candle(c.time, 2 * axis - c.open, 2 * axis - c.low, 2 * axis - c.high, 2 * axis - c.close)
        for c in candles
    ]


UPTREND_WAYPOINTS = [1.0700, 1.0850, 1.0780, 1.0950, 1.0850, 1.1050, 1.0950, 1.0965]


def uptrend_htf() -> list[Candle]:
    """Higher highs/lows; support zone ~1.0945-1.0955 (old high + new low)."""
    return path_candles(UPTREND_WAYPOINTS)


def bullish_engulfing_ltf() -> list[Candle]:
    t = 1_000_000
    return [
        Candle(t, 1.1000, 1.1005, 1.0985, 1.0990),
        Candle(t + 3600, 1.0990, 1.0995, 1.0975, 1.0976),
        Candle(t + 7200, 1.0975, 1.0978, 1.0956, 1.0958),
        Candle(t + 10800, 1.0950, 1.0982, 1.0947, 1.0980),
    ]

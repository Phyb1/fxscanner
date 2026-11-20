from __future__ import annotations

from collections.abc import Sequence

from fxscanner.models import Candle, Trend


def atr(candles: Sequence[Candle], period: int = 14) -> float:
    if len(candles) < period + 1:
        raise ValueError(f"need at least {period + 1} candles for ATR({period})")
    total = 0.0
    for i in range(len(candles) - period, len(candles)):
        prev_close = candles[i - 1].close
        c = candles[i]
        total += max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
    return total / period


def ma_agrees(closes: Sequence[float], trend: Trend, period: int, slope_lookback: int) -> bool:
    """True when price and the SMA slope both support the trend."""
    if trend is Trend.NONE or len(closes) < period + slope_lookback:
        return False
    now = sum(closes[-period:]) / period
    before = sum(closes[-period - slope_lookback : -slope_lookback]) / period
    last = closes[-1]
    if trend is Trend.UP:
        return last > now and now > before
    return last < now and now < before

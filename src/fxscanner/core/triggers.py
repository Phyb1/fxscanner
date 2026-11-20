from __future__ import annotations

from fxscanner.models import Candle, Side


def is_pin_bar(c: Candle, side: Side, min_wick_ratio: float = 2.0) -> bool:
    """Long rejection wick toward the level, close in the far third of the range."""
    rng = c.high - c.low
    if rng <= 0:
        return False
    body = abs(c.close - c.open)
    if side is Side.BUY:
        wick = min(c.open, c.close) - c.low
        close_pos = (c.close - c.low) / rng
    else:
        wick = c.high - max(c.open, c.close)
        close_pos = (c.high - c.close) / rng
    return wick >= min_wick_ratio * body and wick >= 0.5 * rng and close_pos >= 2 / 3


def is_engulfing(prev: Candle, cur: Candle, side: Side) -> bool:
    """Current body fully covers the previous opposite-colour body."""
    prev_body = abs(prev.close - prev.open)
    cur_body = abs(cur.close - cur.open)
    if cur_body <= prev_body:
        return False
    if side is Side.BUY:
        return (
            prev.close < prev.open
            and cur.close > cur.open
            and cur.open <= prev.close
            and cur.close >= prev.open
        )
    return (
        prev.close > prev.open
        and cur.close < cur.open
        and cur.open >= prev.close
        and cur.close <= prev.open
    )

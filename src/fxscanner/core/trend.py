from __future__ import annotations

from collections.abc import Sequence

from fxscanner.models import Pivot, Trend


def _increasing(values: Sequence[float]) -> bool:
    return all(b > a for a, b in zip(values, values[1:], strict=False))


def _decreasing(values: Sequence[float]) -> bool:
    return all(b < a for a, b in zip(values, values[1:], strict=False))


def classify_trend(pivots: Sequence[Pivot], swings: int = 3) -> Trend:
    """UP = higher highs and higher lows; DOWN = lower both; otherwise NONE."""
    highs = [p.price for p in pivots if p.is_high][-swings:]
    lows = [p.price for p in pivots if not p.is_high][-swings:]
    if len(highs) < swings or len(lows) < swings:
        return Trend.NONE
    if _increasing(highs) and _increasing(lows):
        return Trend.UP
    if _decreasing(highs) and _decreasing(lows):
        return Trend.DOWN
    return Trend.NONE

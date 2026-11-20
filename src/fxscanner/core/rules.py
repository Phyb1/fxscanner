from __future__ import annotations

from collections.abc import Sequence

from fxscanner.config import StrategyConfig
from fxscanner.core.indicators import atr, ma_agrees
from fxscanner.core.pivots import find_pivots
from fxscanner.core.trend import classify_trend
from fxscanner.core.triggers import is_engulfing, is_pin_bar
from fxscanner.core.zones import build_zones
from fxscanner.models import Candle, Side, Signal, Trend, Zone


def _touches(zone: Zone, cur: Candle, side: Side) -> bool:
    """Candle reached the zone without closing through it."""
    if side is Side.BUY:
        return cur.low <= zone.high and cur.close >= zone.low
    return cur.high >= zone.low and cur.close <= zone.high


def _trigger_name(prev: Candle, cur: Candle, side: Side, cfg: StrategyConfig) -> str | None:
    if is_engulfing(prev, cur, side):
        return "engulfing"
    if is_pin_bar(cur, side, cfg.pin_wick_ratio):
        return "pin_bar"
    return None


def build_signal(
    symbol: str,
    htf: Sequence[Candle],
    ltf: Sequence[Candle],
    cfg: StrategyConfig,
    pip: float,
) -> Signal | None:
    """Evaluate the trend-pullback rules on CLOSED candles only."""
    if len(ltf) < 2:
        raise ValueError("need at least 2 trigger-timeframe candles")
    pivots = find_pivots(htf[-cfg.zone_lookback :], cfg.pivot_n)
    trend = classify_trend(pivots, cfg.swings)
    if trend is Trend.NONE:
        return None
    if cfg.ma_filter and not ma_agrees(
        [c.close for c in htf], trend, cfg.ma_period, cfg.ma_slope_lookback
    ):
        return None

    side = Side.BUY if trend is Trend.UP else Side.SELL
    tolerance = atr(htf, cfg.atr_period) * cfg.zone_atr_mult
    zones = build_zones(pivots, tolerance, cfg.min_touches, cfg.max_zones)
    prev, cur = ltf[-2], ltf[-1]
    buffer = cfg.stop_buffer_pips * pip

    for zone in sorted(zones, key=lambda z: abs(cur.close - z.mid)):
        if not _touches(zone, cur, side):
            continue
        trigger = _trigger_name(prev, cur, side, cfg)
        if trigger is None:
            continue
        entry = cur.close
        if side is Side.BUY:
            stop = min(cur.low, zone.low) - buffer
            risk = entry - stop
            target = entry + risk * cfg.rr
            blockers = [z.low for z in zones if z.low > entry]
            blocked = bool(blockers) and min(blockers) < target
        else:
            stop = max(cur.high, zone.high) + buffer
            risk = stop - entry
            target = entry - risk * cfg.rr
            blockers = [z.high for z in zones if z.high < entry]
            blocked = bool(blockers) and max(blockers) > target
        risk_pips = risk / pip
        if risk <= 0 or risk_pips > cfg.max_stop_pips or blocked:
            continue
        return Signal(
            symbol=symbol,
            side=side,
            entry=entry,
            stop=stop,
            target=target,
            risk_pips=risk_pips,
            rr=cfg.rr,
            trigger=trigger,
            trigger_time=cur.time,
            zone_low=zone.low,
            zone_high=zone.high,
        )
    return None

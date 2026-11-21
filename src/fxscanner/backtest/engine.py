from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from fxscanner.config import StrategyConfig
from fxscanner.core.rules import evaluate
from fxscanner.models import Candle, Side, Signal

TIMEFRAME_SECONDS = {"M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}


@dataclass(frozen=True)
class CostModel:
    """Prices are bid. Longs pay ``spread`` on entry; shorts pay it when closing."""

    spread: float = 0.0  # in price units
    slippage: float = 0.0  # in price units, adverse on entry and stop exits


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: Side
    trigger: str
    entry_time: int
    exit_time: int
    entry: float
    exit: float
    stop: float
    target: float
    r: float
    outcome: str  # "target" | "stop" | "timeout"
    bars: int


def simulate_trade(
    signal: Signal, future: Sequence[Candle], costs: CostModel, max_hold: int
) -> Trade | None:
    """Walk forward from the candle after the trigger. Returns None if the trade is invalid.

    When one candle touches both stop and target, the stop is assumed to hit first
    (the conservative choice, since the order inside a candle is unknowable).
    """
    buy = signal.side is Side.BUY
    fill = signal.entry + costs.spread + costs.slippage if buy else signal.entry - costs.slippage
    risk = fill - signal.stop if buy else signal.stop - fill
    if risk <= 0 or not future:
        return None
    exit_price = future[-1].close if buy else future[-1].close + costs.spread
    outcome, exit_time, bars = "timeout", future[-1].time, len(future)
    for n, c in enumerate(future[:max_hold], start=1):
        if buy:
            stop_hit = c.low <= signal.stop
            target_hit = c.high >= signal.target
        else:
            stop_hit = c.high + costs.spread >= signal.stop
            target_hit = c.low + costs.spread <= signal.target
        if stop_hit:
            slip = -costs.slippage if buy else costs.slippage
            exit_price, outcome = signal.stop + slip, "stop"
        elif target_hit:
            exit_price, outcome = signal.target, "target"
        else:
            if n == min(max_hold, len(future)):
                last = c.close if buy else c.close + costs.spread
                exit_price, outcome = last, "timeout"
            else:
                continue
        exit_time, bars = c.time, n
        break
    r = (exit_price - fill) / risk if buy else (fill - exit_price) / risk
    return Trade(
        symbol=signal.symbol,
        side=signal.side,
        trigger=signal.trigger,
        entry_time=signal.trigger_time,
        exit_time=exit_time,
        entry=fill,
        exit=exit_price,
        stop=signal.stop,
        target=signal.target,
        r=r,
        outcome=outcome,
        bars=bars,
    )


def visible_htf_count(htf_times: Sequence[int], htf_seconds: int, now: int) -> int:
    """How many higher-timeframe candles have CLOSED by time ``now`` (no lookahead)."""
    return bisect.bisect_right(htf_times, now - htf_seconds)


def run_backtest(
    symbol: str,
    htf: Sequence[Candle],
    ltf: Sequence[Candle],
    cfg: StrategyConfig,
    pip: float,
    costs: CostModel,
    max_hold: int = 100,
    htf_bars: int = 300,
    ltf_bars: int = 50,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[Trade]:
    """Replay history through the live rules. One open trade per symbol at a time."""
    htf_seconds = TIMEFRAME_SECONDS[cfg.htf]
    ltf_seconds = TIMEFRAME_SECONDS[cfg.ltf]
    htf_times = [c.time for c in htf]
    trades: list[Trade] = []
    busy_until = -1
    for i in range(1, len(ltf)):
        if on_progress is not None and i % 500 == 0:
            on_progress(i, len(ltf))
        if i <= busy_until:
            continue
        closed_at = ltf[i].time + ltf_seconds
        k = visible_htf_count(htf_times, htf_seconds, closed_at)
        if k == 0:
            continue
        try:
            ev = evaluate(
                symbol,
                htf[max(0, k - htf_bars) : k],
                ltf[max(0, i - ltf_bars + 1) : i + 1],
                cfg,
                pip,
            )
        except ValueError:
            continue  # not enough history yet
        if ev.signal is None:
            continue
        trade = simulate_trade(ev.signal, ltf[i + 1 :], costs, max_hold)
        if trade is None:
            continue
        trades.append(trade)
        busy_until = i + trade.bars
    return trades

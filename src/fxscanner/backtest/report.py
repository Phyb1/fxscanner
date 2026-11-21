from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from fxscanner.backtest.engine import Trade
from fxscanner.backtest.stats import Stats, compute_stats
from fxscanner.models import Side

MIN_TRADES = 50


def _utc(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%d %H:%M")


def _row(label: str, s: Stats) -> str:
    pf = "n/a" if s.profit_factor is None else f"{s.profit_factor:.2f}"
    return (
        f"{label:<10}{s.trades:>7}{s.win_rate * 100:>8.0f}%{s.expectancy_r:>+10.2f}R"
        f"{s.total_r:>+9.1f}R{pf:>8}{s.max_drawdown_r:>9.1f}R"
    )


def breakeven_win_rate(rr: float) -> float:
    return 1 / (1 + rr)


def format_report(trades: Sequence[Trade], symbols: Sequence[str], rr: float, months: float) -> str:
    ordered = sorted(trades, key=lambda t: t.exit_time)
    lines = [
        f"{'':<10}{'trades':>7}{'win%':>9}{'expect.':>11}{'total':>10}{'PF':>8}{'max DD':>10}",
        "-" * 65,
    ]
    for symbol in symbols:
        lines.append(_row(symbol, compute_stats([t.r for t in ordered if t.symbol == symbol])))
    total = compute_stats([t.r for t in ordered])
    lines += ["-" * 65, _row("ALL", total), ""]
    for side in Side:
        part = [t.r for t in ordered if t.side is side]
        lines.append(f"{side.value:<5}: " + _row("", compute_stats(part)).strip())
    outcomes = {o: sum(1 for t in ordered if t.outcome == o) for o in ("target", "stop", "timeout")}
    lines.append("exits: " + ", ".join(f"{n} {o}" for o, n in outcomes.items()))
    per_month = total.trades / months if months > 0 else 0.0
    lines.append(f"frequency: {per_month:.1f} trades per month across {len(symbols)} pair(s)")
    lines.append(f"break-even win rate at {rr:g}R is {breakeven_win_rate(rr) * 100:.0f}%")
    if total.trades < MIN_TRADES:
        lines.append(
            f"WARNING: only {total.trades} trades. Fewer than {MIN_TRADES} says almost nothing "
            "about whether the method works; treat these numbers as noise."
        )
    return "\n".join(lines)


def save_trades(path: Path, trades: Sequence[Trade]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["symbol", "side", "trigger", "entry_time_utc", "exit_time_utc", "entry", "exit",
             "stop", "target", "r", "outcome", "bars"]
        )  # fmt: skip
        for t in sorted(trades, key=lambda x: x.exit_time):
            writer.writerow(
                [t.symbol, t.side.value, t.trigger, _utc(t.entry_time), _utc(t.exit_time),
                 f"{t.entry:.5f}", f"{t.exit:.5f}", f"{t.stop:.5f}", f"{t.target:.5f}",
                 f"{t.r:.3f}", t.outcome, t.bars]
            )  # fmt: skip

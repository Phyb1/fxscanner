from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Stats:
    trades: int
    wins: int
    win_rate: float
    expectancy_r: float
    total_r: float
    profit_factor: float | None
    max_drawdown_r: float


def compute_stats(results: Sequence[float]) -> Stats:
    """Stats over closed trades in R (1R = the amount risked). Mirrors fxhub.hub.stats."""
    n = len(results)
    if n == 0:
        return Stats(0, 0, 0.0, 0.0, 0.0, None, 0.0)
    wins = sum(1 for r in results if r > 0)
    gross_win = sum(r for r in results if r > 0)
    gross_loss = -sum(r for r in results if r < 0)
    cumulative = peak = drawdown = 0.0
    for r in results:
        cumulative += r
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return Stats(
        trades=n,
        wins=wins,
        win_rate=wins / n,
        expectancy_r=cumulative / n,
        total_r=cumulative,
        profit_factor=gross_win / gross_loss if gross_loss > 0 else None,
        max_drawdown_r=drawdown,
    )

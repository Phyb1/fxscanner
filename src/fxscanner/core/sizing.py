from __future__ import annotations

import math


def pip_size(symbol: str) -> float:
    """Heuristic for FX majors/crosses. Metals and indices need an explicit size."""
    return 0.01 if "JPY" in symbol.upper() else 0.0001


def position_size(
    balance: float,
    risk_pct: float,
    stop_pips: float,
    pip_value_per_lot: float,
    lot_step: float = 0.01,
    min_lot: float = 0.01,
    max_lot: float = 100.0,
) -> float:
    """Lots risking ``risk_pct`` of balance, rounded DOWN to the lot step.

    Returns 0.0 when even the minimum lot would risk more than intended.
    """
    if min(balance, risk_pct, stop_pips, pip_value_per_lot, lot_step) <= 0:
        raise ValueError("balance, risk_pct, stop_pips, pip_value and lot_step must be positive")
    raw = balance * risk_pct / 100 / (stop_pips * pip_value_per_lot)
    lots = math.floor(raw / lot_step + 1e-9) * lot_step
    if lots < min_lot:
        return 0.0
    decimals = max(0, round(-math.log10(lot_step)))
    return round(min(lots, max_lot), decimals)

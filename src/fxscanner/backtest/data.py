from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

from fxscanner.adapters.base import DataError
from fxscanner.models import Candle


def csv_path(directory: Path, symbol: str, timeframe: str) -> Path:
    return directory / f"{symbol}_{timeframe}.csv"


def save_candles(path: Path, candles: Sequence[Candle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "open", "high", "low", "close"])
        for c in candles:
            writer.writerow([c.time, c.open, c.high, c.low, c.close])


def load_candles(path: Path) -> list[Candle]:
    if not path.exists():
        raise DataError(f"no cached data at {path}; run once with MT5 connected")
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return [
                Candle(
                    int(r["time"]),
                    float(r["open"]),
                    float(r["high"]),
                    float(r["low"]),
                    float(r["close"]),
                )
                for r in csv.DictReader(f)
            ]
    except (KeyError, ValueError) as exc:
        raise DataError(f"corrupt data file {path}: {exc}") from exc

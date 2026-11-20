from __future__ import annotations

from typing import Protocol

from fxscanner.models import Candle


class DataError(RuntimeError):
    """Raised when a candle source cannot supply data."""


class CandleSource(Protocol):
    def get_candles(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        """Return up to ``count`` CLOSED candles, oldest first."""
        ...

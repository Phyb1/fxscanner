from __future__ import annotations

from fxscanner.adapters.base import DataError
from fxscanner.models import Candle


class FakeSource:
    """In-memory source for tests and demos."""

    def __init__(self, data: dict[tuple[str, str], list[Candle]]) -> None:
        self._data = data

    def get_candles(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        try:
            return self._data[(symbol, timeframe)][-count:]
        except KeyError as exc:
            raise DataError(f"no data for {symbol} {timeframe}") from exc

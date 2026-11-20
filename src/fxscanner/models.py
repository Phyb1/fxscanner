from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class Trend(StrEnum):
    UP = "up"
    DOWN = "down"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Candle:
    """A *closed* candle. Time is UTC epoch seconds."""

    time: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True, slots=True)
class Pivot:
    index: int
    price: float
    is_high: bool


@dataclass(frozen=True, slots=True)
class Zone:
    low: float
    high: float
    touches: int
    last_index: int

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2


@dataclass(frozen=True, slots=True)
class Signal:
    symbol: str
    side: Side
    entry: float
    stop: float
    target: float
    risk_pips: float
    rr: float
    trigger: str
    trigger_time: int
    zone_low: float
    zone_high: float

    @property
    def key(self) -> str:
        """Stable identity used to avoid alerting twice for the same setup."""
        return f"{self.symbol}:{self.side.value}:{self.trigger_time}"

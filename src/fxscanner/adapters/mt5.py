from __future__ import annotations

import importlib
import time
from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Any

from fxscanner.adapters.base import DataError
from fxscanner.config import BrokerProfile
from fxscanner.models import Candle

OFFSET_RECHECK_SECONDS = 6 * 3600


def infer_offset_seconds(tick_times: Sequence[int], now: float) -> int | None:
    """Server UTC offset from a fresh tick, or None when the tick cannot be trusted.

    MT5 tick times are server-local. A live tick is within seconds of "now", so
    (tick - now) rounds to the offset. A stale tick (market closed) lands far from
    a whole hour or outside the plausible range and is rejected.
    """
    if not tick_times:
        return None
    raw = max(tick_times) - now
    candidate = round(raw / 3600) * 3600
    if abs(raw - candidate) > 300 or not -12 * 3600 <= candidate <= 14 * 3600:
        return None
    return int(candidate)


class MT5Source:
    """Candle source backed by a running MetaTrader 5 terminal (Windows only).

    All broker specifics come from the BrokerProfile. ``mt5_module`` can be
    injected so the adapter is testable without MetaTrader installed.
    """

    def __init__(
        self,
        profile: BrokerProfile,
        mt5_module: Any | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._profile = profile
        self._mt5 = mt5_module
        self._clock = clock
        self._offset: int | None = None
        self._offset_checked_at = 0.0

    def _offset_seconds(self, broker_symbol: str) -> int:
        profile = self._profile
        if not isinstance(profile.server_utc_offset_hours, str):
            return profile.server_utc_offset_hours * 3600
        now = self._clock()
        if self._offset is not None and now - self._offset_checked_at < OFFSET_RECHECK_SECONDS:
            return self._offset
        tick = self._mt5.symbol_info_tick(broker_symbol) if self._mt5 is not None else None
        detected = infer_offset_seconds([int(tick.time)] if tick else [], now)
        if detected is not None:
            self._offset, self._offset_checked_at = detected, now
            return detected
        # Not detectable right now: keep the last good value, else the configured fallback.
        return self._offset if self._offset is not None else profile.offset_fallback_hours * 3600

    def connect(self) -> None:
        if self._mt5 is None:
            try:
                self._mt5 = importlib.import_module("MetaTrader5")
            except ImportError as exc:
                raise DataError("MetaTrader5 package not available (Windows only)") from exc
        login, password = self._profile.credentials()
        kwargs: dict[str, Any] = {
            "login": login,
            "password": password,
            "server": self._profile.server,
            "timeout": self._profile.timeout_ms,
        }
        if self._profile.terminal_path:
            kwargs["path"] = self._profile.terminal_path
        if not self._mt5.initialize(**kwargs):
            raise DataError(f"MT5 initialize failed: {self._mt5.last_error()}")

    def close(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()

    def __enter__(self) -> MT5Source:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def get_candles(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        if self._mt5 is None:
            raise DataError("call connect() first")
        broker_symbol = self._profile.broker_symbol(symbol)
        tf = getattr(self._mt5, f"TIMEFRAME_{timeframe}", None)
        if tf is None:
            raise DataError(f"unsupported timeframe {timeframe}")
        self._mt5.symbol_select(broker_symbol, True)
        rates = self._mt5.copy_rates_from_pos(broker_symbol, tf, 0, count + 1)
        if rates is None or len(rates) < 2:
            raise DataError(f"no rates for {broker_symbol} {timeframe}: {self._mt5.last_error()}")
        offset = self._offset_seconds(broker_symbol)
        # The last bar is still forming; only closed candles are ever returned.
        return [
            Candle(
                time=int(r["time"]) - offset,
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
            )
            for r in rates[:-1]
        ]

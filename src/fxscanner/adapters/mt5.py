from __future__ import annotations

import importlib
from types import TracebackType
from typing import Any

from fxscanner.adapters.base import DataError
from fxscanner.config import BrokerProfile
from fxscanner.models import Candle


class MT5Source:
    """Candle source backed by a running MetaTrader 5 terminal (Windows only).

    All broker specifics come from the BrokerProfile. ``mt5_module`` can be
    injected so the adapter is testable without MetaTrader installed.
    """

    def __init__(self, profile: BrokerProfile, mt5_module: Any | None = None) -> None:
        self._profile = profile
        self._mt5 = mt5_module

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
        offset = self._profile.server_utc_offset_hours * 3600
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

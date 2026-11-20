from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from fxscanner.adapters.base import CandleSource, DataError
from fxscanner.config import StrategyConfig
from fxscanner.core.rules import build_signal
from fxscanner.core.sizing import pip_size
from fxscanner.models import Signal


@dataclass
class ScanResult:
    signals: list[Signal] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


def scan(
    source: CandleSource,
    symbols: Sequence[str],
    cfg: StrategyConfig,
    pip_for: Callable[[str], float] = pip_size,
    htf_bars: int = 300,
    ltf_bars: int = 50,
) -> ScanResult:
    """Scan symbols independently; one bad symbol never aborts the rest."""
    result = ScanResult()
    for symbol in symbols:
        try:
            htf = source.get_candles(symbol, cfg.htf, htf_bars)
            ltf = source.get_candles(symbol, cfg.ltf, ltf_bars)
            signal = build_signal(symbol, htf, ltf, cfg, pip_for(symbol))
        except (DataError, ValueError) as exc:
            result.errors[symbol] = str(exc)
            continue
        if signal is not None:
            result.signals.append(signal)
    return result

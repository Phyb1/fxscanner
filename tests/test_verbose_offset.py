from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from helpers import bullish_engulfing_ltf, mirror, path_candles, uptrend_htf

from fxscanner.adapters.fake import FakeSource
from fxscanner.adapters.mt5 import MT5Source, infer_offset_seconds
from fxscanner.cli import scan_once
from fxscanner.config import AppConfig, BrokerProfile, ConfigError, RiskConfig, StrategyConfig
from fxscanner.core.rules import evaluate
from fxscanner.models import Candle, Trend
from fxscanner.scanner.state import SeenStore

CFG = StrategyConfig()
PIP = 0.0001


def test_evaluate_reports_setup() -> None:
    ev = evaluate("EURUSD", uptrend_htf(), bullish_engulfing_ltf(), CFG, PIP)
    assert ev.signal is not None and ev.note.startswith("SETUP") and ev.label == "uptrend"


def test_evaluate_explains_no_trend() -> None:
    chop = path_candles([1.09, 1.10, 1.09, 1.10, 1.09, 1.10, 1.09, 1.10])
    ev = evaluate("EURUSD", chop, bullish_engulfing_ltf(), CFG, PIP)
    assert ev.trend is Trend.NONE and "no clear trend" in ev.note and ev.signal is None


def test_evaluate_reports_distance_to_support_when_waiting() -> None:
    ltf = bullish_engulfing_ltf()
    higher = [
        Candle(c.time, c.open + 0.01, c.high + 0.01, c.low + 0.01, c.close + 0.01) for c in ltf
    ]
    ev = evaluate("EURUSD", uptrend_htf(), higher, CFG, PIP)
    assert ev.signal is None
    assert "pips above support" in ev.note and "waiting for a pullback" in ev.note


def test_evaluate_reports_waiting_for_trigger() -> None:
    ltf = bullish_engulfing_ltf()
    touching = Candle(ltf[-1].time, 1.0953, 1.0954, 1.0950, 1.0951)  # at the zone, no trigger
    ltf = ltf[:-1] + [touching]
    ev = evaluate("EURUSD", uptrend_htf(), ltf, CFG, PIP)
    assert ev.signal is None and "waiting for a trigger" in ev.note


def test_downtrend_distance_uses_resistance() -> None:
    axis = 1.09
    ltf = mirror(bullish_engulfing_ltf(), axis)
    lower = [
        Candle(c.time, c.open - 0.01, c.high - 0.01, c.low - 0.01, c.close - 0.01) for c in ltf
    ]
    ev = evaluate("EURUSD", mirror(uptrend_htf(), axis), lower, CFG, PIP)
    assert ev.label == "downtrend" and "below resistance" in ev.note


def test_verbose_scan_prints_a_line_per_pair(tmp_path: Path) -> None:
    cfg = AppConfig(
        symbols=("EURUSD", "GBPUSD"), strategy=CFG, risk=RiskConfig(),
        brokers={}, state_file=tmp_path / "seen.json",
    )  # fmt: skip
    source = FakeSource(
        {("EURUSD", "H4"): uptrend_htf(), ("EURUSD", "H1"): bullish_engulfing_ltf()}
    )
    out: list[str] = []
    scan_once(cfg, source, SeenStore(cfg.state_file), out.append, verbose=True)
    assert any(line.startswith("--- scan") for line in out)
    assert any(line.startswith("EURUSD: uptrend | SETUP") for line in out)
    assert any(line.startswith("! GBPUSD") for line in out)


def test_quiet_scan_stays_quiet_without_verbose(tmp_path: Path) -> None:
    cfg = AppConfig(
        symbols=("EURUSD",), strategy=CFG, risk=RiskConfig(),
        brokers={}, state_file=tmp_path / "seen.json",
    )  # fmt: skip
    chop = path_candles([1.09, 1.10, 1.09, 1.10, 1.09, 1.10, 1.09, 1.10])
    source = FakeSource({("EURUSD", "H4"): chop, ("EURUSD", "H1"): bullish_engulfing_ltf()})
    out: list[str] = []
    scan_once(cfg, source, SeenStore(cfg.state_file), out.append)
    assert out == []


@pytest.mark.parametrize(
    ("tick_offset", "expected"),
    [(7200, 7200), (10800, 10800), (0, 0), (-18000, -18000), (7200 + 40, 7200)],
)
def test_offset_inferred_from_live_tick(tick_offset: int, expected: int) -> None:
    now = 1_795_000_000.0
    assert infer_offset_seconds([int(now + tick_offset)], now) == expected


def test_stale_or_missing_tick_is_not_trusted() -> None:
    now = 1_795_000_000.0
    assert infer_offset_seconds([], now) is None
    assert infer_offset_seconds([int(now - 2 * 86400 + 1800)], now) is None  # weekend-old tick
    assert infer_offset_seconds([int(now + 30 * 3600)], now) is None  # implausible


class OffsetStub:
    TIMEFRAME_H1 = 16385

    def __init__(self, tick_time: int | None) -> None:
        self.tick_time = tick_time

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        return True

    def symbol_info_tick(self, symbol: str) -> Any:
        return None if self.tick_time is None else SimpleNamespace(time=self.tick_time)

    def copy_rates_from_pos(
        self, symbol: str, tf: int, pos: int, count: int
    ) -> list[dict[str, float]]:
        return [
            {"time": 100_000 + i * 3600, "open": 1, "high": 2, "low": 0.5, "close": 1.5}
            for i in range(3)
        ]

    def last_error(self) -> tuple[int, str]:
        return (1, "ok")


def source_for(profile: BrokerProfile, stub: OffsetStub, now: float) -> MT5Source:
    return MT5Source(profile, stub, clock=lambda: now)


def test_auto_offset_applied_to_candle_times() -> None:
    now = 1_795_000_000.0
    stub = OffsetStub(int(now + 10800))  # server is UTC+3 (summer)
    candles = source_for(BrokerProfile(name="b", server="s"), stub, now).get_candles(
        "EURUSD", "H1", 2
    )
    assert candles[0].time == 100_000 - 10800


def test_auto_offset_falls_back_when_market_closed() -> None:
    now = 1_795_000_000.0
    stub = OffsetStub(int(now - 2 * 86400))
    profile = BrokerProfile(name="b", server="s", offset_fallback_hours=2)
    assert source_for(profile, stub, now).get_candles("EURUSD", "H1", 2)[0].time == 100_000 - 7200


def test_auto_offset_keeps_last_good_value() -> None:
    now = [1_795_000_000.0]
    stub = OffsetStub(int(now[0] + 7200))
    src = MT5Source(
        BrokerProfile(name="b", server="s", offset_fallback_hours=0), stub, clock=lambda: now[0]
    )
    src.get_candles("EURUSD", "H1", 2)
    now[0] += 7 * 3600  # recheck due, but market now closed
    stub.tick_time = int(now[0] - 3 * 86400)
    assert src.get_candles("EURUSD", "H1", 2)[0].time == 100_000 - 7200


def test_fixed_offset_still_supported_and_validated() -> None:
    now = 1_795_000_000.0
    profile = BrokerProfile(name="b", server="s", server_utc_offset_hours=2)
    assert (
        source_for(profile, OffsetStub(None), now).get_candles("EURUSD", "H1", 2)[0].time
        == 100_000 - 7200
    )
    with pytest.raises(ConfigError):
        BrokerProfile(name="b", server="s", server_utc_offset_hours="two")

from pathlib import Path

import pytest
from helpers import bullish_engulfing_ltf, uptrend_htf

from fxscanner.adapters.fake import FakeSource
from fxscanner.cli import format_signal, scan_once
from fxscanner.config import AppConfig, RiskConfig, StrategyConfig
from fxscanner.scanner.scan import scan
from fxscanner.scanner.state import SeenStore


def make_source() -> FakeSource:
    return FakeSource({("EURUSD", "H4"): uptrend_htf(), ("EURUSD", "H1"): bullish_engulfing_ltf()})


def test_scan_isolates_failures_per_symbol() -> None:
    result = scan(make_source(), ["EURUSD", "GBPUSD"], StrategyConfig())
    assert [s.symbol for s in result.signals] == ["EURUSD"]
    assert "GBPUSD" in result.errors


def test_seen_store_dedupes_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "seen.json"
    signals = scan(make_source(), ["EURUSD"], StrategyConfig()).signals
    store = SeenStore(path)
    assert store.filter_new(signals) == signals
    store.mark_seen(signals)
    assert SeenStore(path).filter_new(signals) == []


def test_seen_store_recovers_from_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "seen.json"
    path.write_text("{not json", encoding="utf-8")
    assert SeenStore(path).filter_new([]) == []


def test_scan_once_emits_once_then_stays_quiet(tmp_path: Path) -> None:
    cfg = AppConfig(
        symbols=("EURUSD",),
        strategy=StrategyConfig(),
        risk=RiskConfig(balance=1000),
        brokers={},
        state_file=tmp_path / "seen.json",
    )
    out: list[str] = []
    store = SeenStore(cfg.state_file)
    assert scan_once(cfg, make_source(), store, out.append) == 1
    assert "EURUSD BUY" in out[0] and "0.02 lots" in out[0]
    assert scan_once(cfg, make_source(), store, out.append) == 0


def test_format_signal_uses_jpy_precision() -> None:
    sig = scan(make_source(), ["EURUSD"], StrategyConfig()).signals[0]
    assert "1.09800" in format_signal(sig, RiskConfig())
    assert pytest.approx(35, abs=0.01) == sig.risk_pips

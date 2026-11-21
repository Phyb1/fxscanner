from pathlib import Path
from typing import Any

import pytest

from fxscanner.adapters.base import DataError
from fxscanner.adapters.mt5 import MT5Source
from fxscanner.config import BrokerProfile, ConfigError, StrategyConfig, load_config

ROOT = Path(__file__).resolve().parent.parent


def test_example_config_loads() -> None:
    cfg = load_config(ROOT / "config.example.toml")
    assert set(cfg.brokers) == {"fusion", "justtrade"}
    assert cfg.symbols[0] == "EURUSD"


def test_unknown_config_key_fails_loudly(tmp_path: Path) -> None:
    p = tmp_path / "c.toml"
    p.write_text('symbols=["EURUSD"]\n[strategy]\nrr_typo = 2\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)


def test_invalid_strategy_values_rejected() -> None:
    with pytest.raises(ConfigError):
        StrategyConfig(htf="H7")
    with pytest.raises(ConfigError):
        StrategyConfig(rr=0)


def test_symbol_mapping_and_suffix() -> None:
    p = BrokerProfile(name="b", server="s", symbol_suffix=".r", symbol_map={"XAUUSD": "GOLD"})
    assert p.broker_symbol("EURUSD") == "EURUSD.r"
    assert p.broker_symbol("XAUUSD") == "GOLD"


def test_credentials_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    p = BrokerProfile(name="b", server="s", login_env="T_LOGIN", password_env="T_PASS")
    monkeypatch.delenv("T_LOGIN", raising=False)
    with pytest.raises(ConfigError):
        p.credentials()
    monkeypatch.setenv("T_LOGIN", "12345")
    monkeypatch.setenv("T_PASS", "pw")
    assert p.credentials() == (12345, "pw")


class StubMT5:
    TIMEFRAME_H1 = 16385

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.init_kwargs: dict[str, Any] = {}
        self.selected: list[str] = []

    def initialize(self, **kwargs: Any) -> bool:
        self.init_kwargs = kwargs
        return self.ok

    def last_error(self) -> tuple[int, str]:
        return (-1, "boom")

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        self.selected.append(symbol)
        return True

    def copy_rates_from_pos(
        self, symbol: str, tf: int, pos: int, count: int
    ) -> list[dict[str, float]]:
        base = 100_000
        return [
            {"time": base + i * 3600, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05}
            for i in range(3)
        ]

    def shutdown(self) -> None:
        pass


def test_mt5_source_drops_forming_candle_and_applies_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FX_MT5_LOGIN", "1")
    monkeypatch.setenv("FX_MT5_PASSWORD", "pw")
    stub = StubMT5()
    profile = BrokerProfile(name="b", server="Srv", symbol_suffix=".r", server_utc_offset_hours=2)
    with MT5Source(profile, stub) as src:
        candles = src.get_candles("EURUSD", "H1", 2)
    assert stub.init_kwargs["server"] == "Srv"
    assert stub.selected == ["EURUSD.r"]
    assert len(candles) == 2  # 3 rates returned, last one is still forming
    assert candles[0].time == 100_000 - 7200


def test_mt5_initialize_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FX_MT5_LOGIN", "1")
    monkeypatch.setenv("FX_MT5_PASSWORD", "pw")
    with pytest.raises(DataError):
        MT5Source(BrokerProfile(name="b", server="s"), StubMT5(ok=False)).connect()


def test_mt5_unsupported_timeframe() -> None:
    src = MT5Source(BrokerProfile(name="b", server="s"), StubMT5())
    with pytest.raises(DataError):
        src.get_candles("EURUSD", "H7", 5)


class AttachStub(StubMT5):
    def __init__(self, logged_in: bool = True) -> None:
        super().__init__()
        self.logged_in = logged_in

    def account_info(self) -> object | None:
        return object() if self.logged_in else None


def test_attach_mode_sends_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FX_MT5_LOGIN", raising=False)
    monkeypatch.delenv("FX_MT5_PASSWORD", raising=False)
    stub = AttachStub()
    profile = BrokerProfile(
        name="b", server="s", attach=True, terminal_path="C:/mt5/terminal64.exe"
    )
    MT5Source(profile, stub).connect()
    assert stub.init_kwargs == {"timeout": 60000, "path": "C:/mt5/terminal64.exe"}


def test_attach_mode_requires_a_logged_in_terminal() -> None:
    profile = BrokerProfile(name="b", server="s", attach=True)
    with pytest.raises(DataError, match="not logged in"):
        MT5Source(profile, AttachStub(logged_in=False)).connect()


def test_credential_mode_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FX_MT5_LOGIN", "7")
    monkeypatch.setenv("FX_MT5_PASSWORD", "pw")
    stub = StubMT5()
    MT5Source(BrokerProfile(name="b", server="Srv"), stub).connect()
    assert stub.init_kwargs["login"] == 7 and stub.init_kwargs["server"] == "Srv"

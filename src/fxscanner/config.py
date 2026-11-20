from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

TIMEFRAMES = ("M5", "M15", "M30", "H1", "H4", "D1")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class StrategyConfig:
    htf: str = "H4"
    ltf: str = "H1"
    pivot_n: int = 2
    swings: int = 3
    ma_filter: bool = False
    ma_period: int = 50
    ma_slope_lookback: int = 5
    atr_period: int = 14
    zone_atr_mult: float = 0.5
    min_touches: int = 2
    max_zones: int = 3
    zone_lookback: int = 300
    stop_buffer_pips: float = 2.0
    rr: float = 2.0
    max_stop_pips: float = 80.0
    pin_wick_ratio: float = 2.0

    def __post_init__(self) -> None:
        for tf in (self.htf, self.ltf):
            if tf not in TIMEFRAMES:
                raise ConfigError(f"unknown timeframe {tf!r}; use one of {TIMEFRAMES}")
        if self.pivot_n < 1 or self.swings < 2 or self.min_touches < 1:
            raise ConfigError("pivot_n>=1, swings>=2, min_touches>=1 required")
        if self.rr <= 0 or self.zone_atr_mult <= 0 or self.max_stop_pips <= 0:
            raise ConfigError("rr, zone_atr_mult and max_stop_pips must be positive")


@dataclass(frozen=True)
class RiskConfig:
    balance: float = 1000.0
    risk_pct: float = 1.0
    pip_value_per_lot: float = 10.0
    lot_step: float = 0.01
    min_lot: float = 0.01
    max_lot: float = 100.0


@dataclass(frozen=True)
class BrokerProfile:
    """Everything broker-specific lives here, never in code."""

    name: str
    server: str
    login_env: str = "FX_MT5_LOGIN"
    password_env: str = "FX_MT5_PASSWORD"
    terminal_path: str | None = None
    symbol_suffix: str = ""
    symbol_map: dict[str, str] = field(default_factory=dict)
    server_utc_offset_hours: int = 0

    def broker_symbol(self, symbol: str) -> str:
        return self.symbol_map.get(symbol, symbol + self.symbol_suffix)

    def credentials(self) -> tuple[int, str]:
        login = os.environ.get(self.login_env)
        password = os.environ.get(self.password_env)
        if not login or not password:
            raise ConfigError(
                f"set {self.login_env} and {self.password_env} for broker {self.name!r}"
            )
        try:
            return int(login), password
        except ValueError as exc:
            raise ConfigError(f"{self.login_env} must be a number") from exc


@dataclass(frozen=True)
class HubConfig:
    """Where to deliver signals. The shared secret is read from the environment."""

    base_url: str
    secret_env: str = "FX_HUB_SECRET"
    source: str = "scanner"
    outbox_file: Path = Path("hub_outbox.json")

    def __post_init__(self) -> None:
        object.__setattr__(self, "outbox_file", Path(self.outbox_file))

    def secret(self) -> str:
        value = os.environ.get(self.secret_env)
        if not value:
            raise ConfigError(f"set {self.secret_env} to the hub's shared secret")
        return value


@dataclass(frozen=True)
class AppConfig:
    symbols: tuple[str, ...]
    strategy: StrategyConfig
    risk: RiskConfig
    brokers: dict[str, BrokerProfile]
    state_file: Path
    hub: HubConfig | None = None


def load_config(path: Path) -> AppConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    try:
        brokers = {
            name: BrokerProfile(name=name, **data) for name, data in raw.get("brokers", {}).items()
        }
        hub_raw = raw.get("hub")
        return AppConfig(
            symbols=tuple(raw["symbols"]),
            strategy=StrategyConfig(**raw.get("strategy", {})),
            risk=RiskConfig(**raw.get("risk", {})),
            brokers=brokers,
            state_file=Path(raw.get("state_file", "seen_signals.json")),
            hub=HubConfig(**hub_raw) if hub_raw else None,
        )
    except (KeyError, TypeError) as exc:
        raise ConfigError(f"invalid config {path}: {exc}") from exc

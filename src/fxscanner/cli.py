from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from fxscanner.adapters.base import CandleSource, DataError
from fxscanner.adapters.mt5 import MT5Source
from fxscanner.config import AppConfig, ConfigError, HubConfig, RiskConfig, load_config
from fxscanner.core.sizing import position_size
from fxscanner.models import Signal
from fxscanner.publish.client import HubAuthError, HubClient
from fxscanner.publish.publisher import Publisher
from fxscanner.scanner.scan import scan
from fxscanner.scanner.state import SeenStore


def format_signal(signal: Signal, risk: RiskConfig) -> str:
    digits = 3 if "JPY" in signal.symbol else 5
    lots = position_size(
        risk.balance,
        risk.risk_pct,
        signal.risk_pips,
        risk.pip_value_per_lot,
        risk.lot_step,
        risk.min_lot,
        risk.max_lot,
    )
    when = datetime.fromtimestamp(signal.trigger_time, UTC).strftime("%Y-%m-%d %H:%M")
    return (
        f"[{when} UTC] {signal.symbol} {signal.side.value.upper()} "
        f"entry {signal.entry:.{digits}f} SL {signal.stop:.{digits}f} "
        f"TP {signal.target:.{digits}f} | {signal.risk_pips:.1f} pips, "
        f"{signal.rr:g}R, {lots} lots | {signal.trigger}"
    )


def scan_once(
    cfg: AppConfig,
    source: CandleSource,
    store: SeenStore,
    emit: Callable[[str], None] = print,
    publisher: Publisher | None = None,
) -> int:
    """Run one scan, emit new signals and errors. Returns the number of new signals."""
    if publisher is not None:
        flushed = publisher.flush()
        if flushed.sent:
            emit(f"hub: delivered {flushed.sent} queued signal(s)")
    result = scan(source, cfg.symbols, cfg.strategy)
    new = store.filter_new(result.signals)
    for signal in new:
        emit(format_signal(signal, cfg.risk))
    store.mark_seen(new)
    if publisher is not None:
        report = publisher.publish(new)
        if report.queued:
            emit(f"hub: unreachable, {report.queued} signal(s) queued for retry")
        for key in report.rejected:
            emit(f"hub: rejected signal {key}")
        if not publisher.heartbeat({"symbols": len(cfg.symbols), "errors": len(result.errors)}):
            emit("hub: heartbeat failed (unreachable)")
    for symbol, message in result.errors.items():
        emit(f"! {symbol}: {message}")
    return len(new)


def build_publisher(hub: HubConfig | None) -> Publisher | None:
    if hub is None:
        return None
    client = HubClient(hub.base_url, hub.secret())
    return Publisher(client, hub.outbox_file, hub.source)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fxscan")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan", help="scan configured symbols for setups")
    p.add_argument("--config", type=Path, default=Path("config.toml"))
    p.add_argument("--broker", required=True, help="broker profile name from the config")
    p.add_argument("--interval", type=int, default=0, help="repeat every N seconds (0 = once)")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
        profile = cfg.brokers.get(args.broker)
        if profile is None:
            parser.error(f"unknown broker {args.broker!r}; defined: {', '.join(cfg.brokers)}")
        store = SeenStore(cfg.state_file)
        publisher = build_publisher(cfg.hub)
        with MT5Source(profile) as source:
            while True:
                scan_once(cfg, source, store, publisher=publisher)
                if args.interval <= 0:
                    break
                time.sleep(args.interval)
    except (ConfigError, DataError, HubAuthError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

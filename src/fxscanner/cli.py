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
    verbose: bool = False,
) -> int:
    """Run one scan, emit new signals and errors. Returns the number of new signals."""
    if publisher is not None:
        flushed = publisher.flush()
        if flushed.sent:
            emit(f"hub: delivered {flushed.sent} queued signal(s)")
    result = scan(source, cfg.symbols, cfg.strategy)
    if verbose:
        stamp = datetime.now(UTC).strftime("%H:%M")
        emit(f"--- scan {stamp} UTC ---")
        for ev in result.evaluations:
            emit(f"{ev.symbol}: {ev.label} | {ev.note}")
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


def run_backtest_command(args: argparse.Namespace, cfg: AppConfig) -> int:
    from fxscanner.backtest.data import csv_path, load_candles, save_candles
    from fxscanner.backtest.engine import TIMEFRAME_SECONDS, CostModel, run_backtest
    from fxscanner.backtest.report import format_report, save_trades
    from fxscanner.core.sizing import pip_size

    bt, strat = cfg.backtest, cfg.strategy
    symbols = tuple(args.symbols) if args.symbols else cfg.symbols
    years = args.years if args.years is not None else bt.years
    bars_per_year = {tf: 365.25 * 86400 * 5 / 7 / sec for tf, sec in TIMEFRAME_SECONDS.items()}
    ltf_count = int(bars_per_year[strat.ltf] * years) + 100
    htf_count = int(bars_per_year[strat.htf] * years) + 350  # extra for indicator warm-up

    source: MT5Source | None = None
    if not args.offline:
        profile = cfg.brokers.get(args.broker or "")
        if profile is None:
            raise ConfigError("--broker is required unless --offline is used")
        source = MT5Source(profile)
        source.connect()
    all_trades = []
    first_time = last_time = 0
    try:
        for symbol in symbols:
            paths = {tf: csv_path(bt.data_dir, symbol, tf) for tf in (strat.htf, strat.ltf)}
            if source is not None:
                htf = source.get_candles(symbol, strat.htf, htf_count)
                ltf = source.get_candles(symbol, strat.ltf, ltf_count)
                save_candles(paths[strat.htf], htf)
                save_candles(paths[strat.ltf], ltf)
                live = source.spread_price(symbol)
            else:
                htf, ltf = load_candles(paths[strat.htf]), load_candles(paths[strat.ltf])
                live = 0.0
            pip = pip_size(symbol)
            if args.spread is not None:
                spread = args.spread * pip
            elif bt.spread_pips is not None:
                spread = bt.spread_pips * pip
            elif source is not None:
                spread = live
            else:
                spread = bt.default_spread_pips * pip
            costs = CostModel(spread=spread, slippage=bt.slippage_pips * pip)
            span_days = (ltf[-1].time - ltf[0].time) / 86400
            spread_pips = spread / pip
            print(
                f"{symbol}: {len(ltf)} {strat.ltf} bars ({span_days:.0f} days), "
                f"spread {spread_pips:.1f} pips"
            )
            trades = run_backtest(symbol, htf, ltf, strat, pip, costs, bt.max_hold_bars)
            all_trades.extend(trades)
            first_time = min(first_time or ltf[0].time, ltf[0].time)
            last_time = max(last_time, ltf[-1].time)
    finally:
        if source is not None:
            source.close()
    months = (last_time - first_time) / 86400 / 30.44 if last_time > first_time else 0.0
    print()
    print(format_report(all_trades, symbols, strat.rr, months))
    save_trades(bt.trades_file, all_trades)
    print(f"\ntrades saved to {bt.trades_file}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fxscan")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan", help="scan configured symbols for setups")
    p.add_argument("--config", type=Path, default=Path("config.toml"))
    p.add_argument("--broker", required=True, help="broker profile name from the config")
    p.add_argument("-v", "--verbose", action="store_true", help="explain each pair every scan")
    p.add_argument("--interval", type=int, default=0, help="repeat every N seconds (0 = once)")
    b = sub.add_parser("backtest", help="replay history through the rules")
    b.add_argument("--config", type=Path, default=Path("config.toml"))
    b.add_argument("--broker", help="broker profile (not needed with --offline)")
    b.add_argument("--offline", action="store_true", help="use cached CSV data, no MT5")
    b.add_argument("--years", type=float, help="history length (default from config)")
    b.add_argument("--spread", type=float, help="fixed spread in pips (default: live from MT5)")
    b.add_argument("--symbols", nargs="+", help="override the configured symbols")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
        if args.command == "backtest":
            return run_backtest_command(args, cfg)
        profile = cfg.brokers.get(args.broker)
        if profile is None:
            parser.error(f"unknown broker {args.broker!r}; defined: {', '.join(cfg.brokers)}")
        store = SeenStore(cfg.state_file)
        publisher = build_publisher(cfg.hub)
        with MT5Source(profile) as source:
            while True:
                scan_once(cfg, source, store, publisher=publisher, verbose=args.verbose)
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

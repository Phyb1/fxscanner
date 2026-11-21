from __future__ import annotations

from pathlib import Path

import pytest
from helpers import bullish_engulfing_ltf, mirror, uptrend_htf

from fxscanner.adapters.base import DataError
from fxscanner.backtest.data import csv_path, load_candles, save_candles
from fxscanner.backtest.engine import (
    CostModel,
    run_backtest,
    simulate_trade,
    visible_htf_count,
)
from fxscanner.backtest.report import breakeven_win_rate, format_report, save_trades
from fxscanner.backtest.stats import compute_stats
from fxscanner.config import BacktestConfig, ConfigError, StrategyConfig
from fxscanner.models import Candle, Side, Signal

CFG = StrategyConfig()
PIP = 0.0001
FREE = CostModel()


def buy_signal() -> Signal:
    # entry 1.1000, stop 1.0950 (50 pips), target 1.1100 (2R)
    return Signal(
        "EURUSD", Side.BUY, 1.1000, 1.0950, 1.1100, 50.0, 2.0, "engulfing", 0, 1.095, 1.096
    )


def sell_signal() -> Signal:
    return Signal(
        "EURUSD", Side.SELL, 1.1000, 1.1050, 1.0900, 50.0, 2.0, "engulfing", 0, 1.104, 1.105
    )


def c(t: int, o: float, h: float, low: float, cl: float) -> Candle:
    return Candle(t, o, h, low, cl)


def test_buy_hits_target_for_plus_two_r() -> None:
    future = [c(1, 1.1, 1.102, 1.099, 1.101), c(2, 1.101, 1.1105, 1.100, 1.110)]
    t = simulate_trade(buy_signal(), future, FREE, 100)
    assert t is not None and t.outcome == "target" and t.r == pytest.approx(2.0) and t.bars == 2


def test_buy_hits_stop_for_minus_one_r() -> None:
    t = simulate_trade(buy_signal(), [c(1, 1.1, 1.101, 1.094, 1.095)], FREE, 100)
    assert t is not None and t.outcome == "stop" and t.r == pytest.approx(-1.0)


def test_same_candle_touching_both_assumes_stop_first() -> None:
    t = simulate_trade(buy_signal(), [c(1, 1.1, 1.112, 1.094, 1.1)], FREE, 100)
    assert t is not None and t.outcome == "stop" and t.r == pytest.approx(-1.0)


def test_sell_mirrors_buy() -> None:
    win = simulate_trade(sell_signal(), [c(1, 1.1, 1.101, 1.089, 1.09)], FREE, 100)
    loss = simulate_trade(sell_signal(), [c(1, 1.1, 1.106, 1.099, 1.105)], FREE, 100)
    assert win is not None and win.r == pytest.approx(2.0)
    assert loss is not None and loss.r == pytest.approx(-1.0)


def test_spread_shrinks_a_long_win_and_a_stop_stays_minus_one_r() -> None:
    costs = CostModel(spread=2 * PIP)
    win = simulate_trade(buy_signal(), [c(1, 1.1, 1.1105, 1.1, 1.11)], costs, 100)
    loss = simulate_trade(buy_signal(), [c(1, 1.1, 1.101, 1.094, 1.095)], costs, 100)
    assert win is not None and win.r == pytest.approx((1.1100 - 1.1002) / 0.0052)
    assert loss is not None and loss.r == pytest.approx(-1.0)  # R is measured from the real fill
    assert win.r < 2.0


def test_short_pays_spread_on_the_exit_side() -> None:
    costs = CostModel(spread=2 * PIP)
    # bid low 1.0902 + spread 0.0002 = ask 1.0904 > target 1.0900: not hit
    miss = simulate_trade(sell_signal(), [c(1, 1.1, 1.101, 1.0902, 1.092)], costs, 1)
    assert miss is not None and miss.outcome == "timeout"
    hit = simulate_trade(sell_signal(), [c(1, 1.1, 1.101, 1.0898, 1.09)], costs, 100)
    assert hit is not None and hit.outcome == "target"


def test_slippage_hurts_entry_and_stop_exit() -> None:
    costs = CostModel(slippage=1 * PIP)
    t = simulate_trade(buy_signal(), [c(1, 1.1, 1.101, 1.094, 1.095)], costs, 100)
    assert t is not None and t.r == pytest.approx(-(50 + 1 + 1) / 51)


def test_timeout_closes_at_market() -> None:
    future = [c(i, 1.1, 1.102, 1.098, 1.101) for i in range(1, 6)]
    t = simulate_trade(buy_signal(), future, FREE, 3)
    assert t is not None and t.outcome == "timeout" and t.bars == 3
    assert t.r == pytest.approx((1.101 - 1.1) / 0.005)


def test_invalid_or_empty_trades_are_skipped() -> None:
    assert simulate_trade(buy_signal(), [], FREE, 100) is None
    inverted = Signal("EURUSD", Side.BUY, 1.1, 1.105, 1.11, 50.0, 2.0, "x", 0, 1.1, 1.1)
    assert simulate_trade(inverted, [c(1, 1, 1, 1, 1)], FREE, 100) is None


def test_htf_candle_is_visible_only_after_it_closes() -> None:
    times = [0, 14400, 28800]
    assert visible_htf_count(times, 14400, 14399) == 0
    assert visible_htf_count(times, 14400, 14400) == 1  # first H4 candle just closed
    assert visible_htf_count(times, 14400, 28799) == 1
    assert visible_htf_count(times, 14400, 28800) == 2


def follow_up(entry_time: int, high: float, low: float) -> list[Candle]:
    return [c(entry_time + 3600, 1.098, high, low, 1.104)]


def test_engine_finds_the_setup_and_scores_the_trade() -> None:
    ltf = bullish_engulfing_ltf() + follow_up(1_000_000 + 10800, 1.106, 1.0975)
    trades = run_backtest("EURUSD", uptrend_htf(), ltf, CFG, PIP, FREE)
    assert len(trades) == 1
    t = trades[0]
    assert t.side is Side.BUY and t.outcome == "target" and t.r == pytest.approx(2.0)


def test_engine_scores_a_losing_trade() -> None:
    ltf = bullish_engulfing_ltf() + follow_up(1_000_000 + 10800, 1.0985, 1.093)
    trades = run_backtest("EURUSD", uptrend_htf(), ltf, CFG, PIP, FREE)
    assert [t.outcome for t in trades] == ["stop"]


def test_engine_sees_the_same_setup_when_mirrored_to_a_downtrend() -> None:
    axis = 1.09
    ltf = mirror(bullish_engulfing_ltf() + follow_up(1_000_000 + 10800, 1.106, 1.0975), axis)
    trades = run_backtest("EURUSD", mirror(uptrend_htf(), axis), ltf, CFG, PIP, FREE)
    assert len(trades) == 1 and trades[0].side is Side.SELL and trades[0].r == pytest.approx(2.0)


def test_engine_never_uses_htf_candles_that_close_after_the_signal() -> None:
    htf = uptrend_htf()
    ltf = bullish_engulfing_ltf() + follow_up(1_000_000 + 10800, 1.106, 1.0975)
    # Move the whole higher timeframe so it only closes AFTER the trigger candle.
    late = [Candle(h.time + 1_000_000, h.open, h.high, h.low, h.close) for h in htf]
    assert run_backtest("EURUSD", late, ltf, CFG, PIP, FREE) == []


def test_engine_has_one_open_trade_per_symbol() -> None:
    ltf = bullish_engulfing_ltf()
    again = [Candle(x.time + 3600 * 4, x.open, x.high, x.low, x.close) for x in ltf]
    # second identical pattern appears while the first trade is still open (no exit candle between)
    flat = [c(1_000_000 + 10800 + 3600, 1.0985, 1.0990, 1.0975, 1.0980)]
    trades = run_backtest(
        "EURUSD", uptrend_htf(), ltf + flat + again, CFG, PIP, FREE, max_hold=1000
    )
    assert len(trades) <= 1


def test_stats_and_report_text() -> None:
    s = compute_stats([2, -1, -1, 2])
    assert (
        s.trades == 4
        and s.expectancy_r == pytest.approx(0.5)
        and s.max_drawdown_r == pytest.approx(2.0)
    )
    ltf = bullish_engulfing_ltf() + follow_up(1_000_000 + 10800, 1.106, 1.0975)
    trades = run_backtest("EURUSD", uptrend_htf(), ltf, CFG, PIP, FREE)
    text = format_report(trades, ["EURUSD", "GBPUSD"], 2.0, months=2.0)
    assert "EURUSD" in text and "ALL" in text and "WARNING: only 1 trades" in text
    assert "break-even win rate at 2R is 33%" in text
    assert breakeven_win_rate(2.0) == pytest.approx(1 / 3)


def test_report_flags_nothing_when_sample_is_large() -> None:
    ltf = bullish_engulfing_ltf() + follow_up(1_000_000 + 10800, 1.106, 1.0975)
    trade = run_backtest("EURUSD", uptrend_htf(), ltf, CFG, PIP, FREE)[0]
    assert "WARNING" not in format_report([trade] * 60, ["EURUSD"], 2.0, 12)


def test_csv_roundtrip_and_errors(tmp_path: Path) -> None:
    candles = uptrend_htf()
    path = csv_path(tmp_path / "data", "EURUSD", "H4")
    save_candles(path, candles)
    assert load_candles(path) == candles
    with pytest.raises(DataError, match="no cached data"):
        load_candles(tmp_path / "missing.csv")
    path.write_text("time,open\n1,x\n", encoding="utf-8")
    with pytest.raises(DataError, match="corrupt"):
        load_candles(path)


def test_trades_csv_written(tmp_path: Path) -> None:
    ltf = bullish_engulfing_ltf() + follow_up(1_000_000 + 10800, 1.106, 1.0975)
    trades = run_backtest("EURUSD", uptrend_htf(), ltf, CFG, PIP, FREE)
    out = tmp_path / "t.csv"
    save_trades(out, trades)
    lines = out.read_text().splitlines()
    assert lines[0].startswith("symbol,side") and len(lines) == 2 and "target" in lines[1]


def test_backtest_config_validation() -> None:
    assert BacktestConfig().years == 2.0
    with pytest.raises(ConfigError):
        BacktestConfig(years=0)

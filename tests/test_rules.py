from dataclasses import replace

import pytest
from helpers import bullish_engulfing_ltf, mirror, path_candles, uptrend_htf

from fxscanner.config import StrategyConfig
from fxscanner.core.rules import build_signal
from fxscanner.models import Side

CFG = StrategyConfig()
PIP = 0.0001


def test_buy_signal_in_uptrend_at_support() -> None:
    sig = build_signal("EURUSD", uptrend_htf(), bullish_engulfing_ltf(), CFG, PIP)
    assert sig is not None
    assert sig.side is Side.BUY
    assert sig.trigger == "engulfing"
    assert sig.entry == pytest.approx(1.0980)
    assert sig.stop == pytest.approx(1.0945)
    assert sig.risk_pips == pytest.approx(35)
    assert sig.target == pytest.approx(1.0980 + 2 * 0.0035)


def test_sell_signal_is_the_mirror_image() -> None:
    axis = 1.09
    sig = build_signal(
        "EURUSD", mirror(uptrend_htf(), axis), mirror(bullish_engulfing_ltf(), axis), CFG, PIP
    )
    assert sig is not None
    assert sig.side is Side.SELL
    assert sig.risk_pips == pytest.approx(35)
    assert sig.stop > sig.entry > sig.target


def test_no_signal_without_trend() -> None:
    chop = path_candles([1.09, 1.10, 1.09, 1.10, 1.09, 1.10, 1.09, 1.10])
    assert build_signal("EURUSD", chop, bullish_engulfing_ltf(), CFG, PIP) is None


def test_no_signal_when_price_is_not_at_a_level() -> None:
    ltf = bullish_engulfing_ltf()
    far = [
        replace(k, open=k.open + 0.01, high=k.high + 0.01, low=k.low + 0.01, close=k.close + 0.01)
        for k in ltf
    ]
    assert build_signal("EURUSD", uptrend_htf(), far, CFG, PIP) is None


def test_no_signal_without_trigger_candle() -> None:
    ltf = bullish_engulfing_ltf()[:-1] + [bullish_engulfing_ltf()[-2]]
    assert build_signal("EURUSD", uptrend_htf(), ltf, CFG, PIP) is None


def test_rejects_when_next_level_is_inside_target() -> None:
    cfg = replace(CFG, min_touches=1, rr=3.0)  # single-touch 1.1055 high now counts as a level
    assert build_signal("EURUSD", uptrend_htf(), bullish_engulfing_ltf(), cfg, PIP) is None


def test_rejects_oversized_stop() -> None:
    cfg = replace(CFG, max_stop_pips=20.0)
    assert build_signal("EURUSD", uptrend_htf(), bullish_engulfing_ltf(), cfg, PIP) is None


def test_ma_filter_uses_slower_average_to_confirm_uptrend() -> None:
    cfg = replace(CFG, ma_filter=True, ma_period=30, ma_slope_lookback=3)
    assert build_signal("EURUSD", uptrend_htf(), bullish_engulfing_ltf(), cfg, PIP) is not None


def test_ma_filter_rejects_when_price_is_below_a_fast_average() -> None:
    cfg = replace(CFG, ma_filter=True, ma_period=10, ma_slope_lookback=3)
    assert build_signal("EURUSD", uptrend_htf(), bullish_engulfing_ltf(), cfg, PIP) is None

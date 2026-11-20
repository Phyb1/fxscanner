from helpers import mirror, path_candles, uptrend_htf

from fxscanner.core.pivots import find_pivots
from fxscanner.core.trend import classify_trend
from fxscanner.models import Candle, Trend


def test_finds_alternating_swings() -> None:
    pivots = find_pivots(uptrend_htf(), n=2)
    kinds = [p.is_high for p in pivots]
    assert kinds == [True, False, True, False, True, False]


def test_pivots_have_no_lookahead() -> None:
    candles = uptrend_htf()
    full = find_pivots(candles, n=2)
    for cut in range(5, len(candles)):
        truncated = find_pivots(candles[:cut], n=2)
        assert truncated == [p for p in full if p.index <= cut - 1 - 2]


def test_uptrend_and_downtrend() -> None:
    up = uptrend_htf()
    assert classify_trend(find_pivots(up)) is Trend.UP
    down = mirror(up, 1.09)
    assert classify_trend(find_pivots(down)) is Trend.DOWN


def test_choppy_market_is_no_trend() -> None:
    chop = path_candles([1.09, 1.10, 1.09, 1.10, 1.09, 1.10, 1.09])
    assert classify_trend(find_pivots(chop)) is Trend.NONE


def test_too_few_swings_is_no_trend() -> None:
    short: list[Candle] = path_candles([1.09, 1.10, 1.095])
    assert classify_trend(find_pivots(short)) is Trend.NONE

import pytest

from fxscanner.core.sizing import pip_size, position_size
from fxscanner.core.triggers import is_engulfing, is_pin_bar
from fxscanner.models import Candle, Side


def c(o: float, h: float, low: float, cl: float) -> Candle:
    return Candle(0, o, h, low, cl)


def test_bullish_pin_bar() -> None:
    assert is_pin_bar(c(1.0860, 1.0865, 1.0830, 1.0862), Side.BUY)
    assert not is_pin_bar(c(1.0860, 1.0865, 1.0830, 1.0835), Side.BUY)  # closes low


def test_bearish_pin_bar() -> None:
    assert is_pin_bar(c(1.0900, 1.0935, 1.0895, 1.0898), Side.SELL)


def test_engulfing_both_sides() -> None:
    assert is_engulfing(
        c(1.0975, 1.0978, 1.0956, 1.0958), c(1.0950, 1.0982, 1.0947, 1.0980), Side.BUY
    )
    assert is_engulfing(
        c(1.0958, 1.0978, 1.0956, 1.0975), c(1.0980, 1.0982, 1.0947, 1.0950), Side.SELL
    )


def test_inside_body_is_not_engulfing() -> None:
    assert not is_engulfing(
        c(1.0975, 1.0978, 1.0950, 1.0952), c(1.0960, 1.0970, 1.0955, 1.0965), Side.BUY
    )


def test_position_size_matches_worked_example() -> None:
    assert position_size(5000, 1, 27, 10) == 0.18


def test_position_size_rounds_down_and_flags_too_small() -> None:
    assert position_size(1000, 1, 37, 10) == 0.02
    assert position_size(100, 1, 50, 10) == 0.0


@pytest.mark.parametrize("bad", [0, -1])
def test_position_size_rejects_non_positive(bad: float) -> None:
    with pytest.raises(ValueError):
        position_size(1000, 1, bad, 10)


def test_pip_size() -> None:
    assert pip_size("EURUSD") == 0.0001
    assert pip_size("USDJPY") == 0.01

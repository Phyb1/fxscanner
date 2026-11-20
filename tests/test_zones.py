import pytest

from fxscanner.core.zones import build_zones
from fxscanner.models import Pivot


def test_clusters_nearby_highs_and_lows_into_one_zone() -> None:
    pivots = [Pivot(5, 1.0855, True), Pivot(20, 1.0845, False), Pivot(30, 1.1055, True)]
    zones = build_zones(pivots, tolerance=0.0015, min_touches=2)
    assert len(zones) == 1
    assert zones[0].touches == 2
    assert zones[0].low == pytest.approx(1.0845)
    assert zones[0].high == pytest.approx(1.0855)


def test_stronger_then_more_recent_zones_win() -> None:
    pivots = [
        Pivot(1, 1.10, True), Pivot(2, 1.10, False), Pivot(3, 1.10, True),
        Pivot(4, 1.20, True), Pivot(5, 1.20, False),
        Pivot(9, 1.30, True), Pivot(10, 1.30, False),
    ]  # fmt: skip
    zones = build_zones(pivots, tolerance=0.001, max_zones=2)
    assert [z.touches for z in zones] == [3, 2]
    assert zones[1].last_index == 10


def test_invalid_tolerance_rejected() -> None:
    with pytest.raises(ValueError):
        build_zones([], tolerance=0)

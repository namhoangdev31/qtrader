import pytest
from qtrader.execution.microstructure.microprice import Microprice


def test_microprice_compute_balanced() -> None:
    (bid, ask) = (100.0, 101.0)
    (v_bid, v_ask) = (50.0, 50.0)
    mid = 100.5
    assert Microprice.compute(bid, ask, v_bid, v_ask) == mid


def test_microprice_compute_bid_heavy() -> None:
    (bid, ask) = (100.0, 101.0)
    (v_bid, v_ask) = (90.0, 10.0)
    micro = Microprice.compute(bid, ask, v_bid, v_ask)
    target = 100.9
    assert micro == pytest.approx(target)
    mid = 100.5
    assert micro > mid


def test_microprice_compute_ask_heavy() -> None:
    (bid, ask) = (100.0, 101.0)
    (v_bid, v_ask) = (10.0, 90.0)
    micro = Microprice.compute(bid, ask, v_bid, v_ask)
    target = 100.1
    assert micro == pytest.approx(target)
    mid = 100.5
    assert micro < mid


def test_microprice_catastrophic_safety() -> None:
    (bid, ask) = (100.0, 101.0)
    mid = 100.5
    assert Microprice.compute(bid, ask, 0.0, 0.0) == mid
    assert Microprice.compute(bid, ask, 1e-15, 1e-15) == mid
    assert Microprice.compute(bid, ask, None, 10.0) == mid

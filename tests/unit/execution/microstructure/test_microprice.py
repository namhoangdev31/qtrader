import pytest

from qtrader.execution.microstructure.microprice import Microprice


def test_microprice_compute_balanced() -> None:
    """Verify microprice computation for a perfectly balanced book."""
    # Mid-price = 100.5
    bid, ask = 100.0, 101.0
    v_bid, v_ask = 50.0, 50.0

    mid = 100.5
    # (100 * 50 + 101 * 50) / 100 = 100.5
    assert Microprice.compute(bid, ask, v_bid, v_ask) == mid  # noqa: S101


def test_microprice_compute_bid_heavy() -> None:
    """Verify microprice drifts toward ask when bid volume is higher (buy pressure)."""
    bid, ask = 100.0, 101.0
    v_bid, v_ask = 90.0, 10.0

    # (100 * 10 + 101 * 90) / 100 = (1000 + 9090) / 100 = 100.9
    micro = Microprice.compute(bid, ask, v_bid, v_ask)
    target = 100.9
    assert micro == pytest.approx(target)  # noqa: S101

    mid = 100.5
    assert micro > mid  # noqa: S101


def test_microprice_compute_ask_heavy() -> None:
    """Verify microprice drifts toward bid when ask volume is higher (sell pressure)."""
    bid, ask = 100.0, 101.0
    v_bid, v_ask = 10.0, 90.0

    # (100 * 90 + 101 * 10) / 100 = (9000 + 1010) / 100 = 100.1
    micro = Microprice.compute(bid, ask, v_bid, v_ask)
    target = 100.1
    assert micro == pytest.approx(target)  # noqa: S101

    mid = 100.5
    assert micro < mid  # noqa: S101


def test_microprice_catastrophic_safety() -> None:
    """Verify failsafe behavior during missing or zero-volume books."""
    bid, ask = 100.0, 101.0
    mid = 100.5

    # Zero volume on both sides
    assert Microprice.compute(bid, ask, 0.0, 0.0) == mid  # noqa: S101

    # Extreme small volume
    assert Microprice.compute(bid, ask, 1e-15, 1e-15) == mid  # noqa: S101

    # Malformed inputs (None causing TypeError in math logic)
    assert Microprice.compute(bid, ask, None, 10.0) == mid  # type: ignore # noqa: S101

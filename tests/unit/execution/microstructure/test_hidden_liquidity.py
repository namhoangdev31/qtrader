import pytest
from qtrader.execution.microstructure.hidden_liquidity import HiddenLiquidityDetector


def test_hidden_liquidity_instant_detection() -> None:
    detector = HiddenLiquidityDetector(window_size=1)
    (executed, visible, price) = (100.0, 20.0, 100.0)
    signal = detector.update(executed, visible, price)
    expected_h = 0.8
    assert signal == pytest.approx(expected_h)
    assert detector._last_iceberg_price == price


def test_hidden_liquidity_visible_only() -> None:
    detector = HiddenLiquidityDetector(window_size=1)
    (executed, visible, price) = (20.0, 20.0, 100.0)
    signal = detector.update(executed, visible, price)
    assert signal == 0.0


def test_hidden_liquidity_rolling_persistence() -> None:
    window = 5
    detector = HiddenLiquidityDetector(window_size=window)
    (executed, visible, price) = (100.0, 50.0, 150.0)
    for _ in range(3):
        detector.update(executed, visible, price)
    expected_avg = 0.375
    assert detector.update(0.0, 0.0, 0.0) == pytest.approx(expected_avg)


def test_hidden_liquidity_failsafe_noise() -> None:
    detector = HiddenLiquidityDetector()
    assert detector.update(0.0, 10.0, 100.0) == 0.0
    assert detector.update(10.0, -5.0, 100.0) == 0.0


def test_hidden_liquidity_catastrophic_failure() -> None:
    detector = HiddenLiquidityDetector()
    assert detector.update(None, 10.0, 100.0) == 0.0


def test_hidden_liquidity_reset() -> None:
    detector = HiddenLiquidityDetector()
    detector.update(100, 20, 100)
    assert len(detector._history) > 0
    detector.reset()
    assert len(detector._history) == 0
    assert detector._last_iceberg_price is None
    assert detector._aggregate_signal() == 0.0

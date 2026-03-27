import pytest

from qtrader.execution.microstructure.hidden_liquidity import HiddenLiquidityDetector


def test_hidden_liquidity_instant_detection() -> None:
    """Verify instantaneous iceberg detection (H = 80%)."""
    detector = HiddenLiquidityDetector(window_size=1)

    # 100 executed, 20 visible. Hidden = 80.
    # H = (100 - 20) / 100 = 0.8
    executed, visible, price = 100.0, 20.0, 100.0
    signal = detector.update(executed, visible, price)

    expected_h = 0.8
    assert signal == pytest.approx(expected_h)  # noqa: S101
    assert detector._last_iceberg_price == price  # noqa: S101


def test_hidden_liquidity_visible_only() -> None:
    """Verify neutral signal for fully visible liquidity."""
    detector = HiddenLiquidityDetector(window_size=1)

    # 20 executed, 20 visible. Hidden = 0.
    # Should not trigger iceberg condition (executed <= visible)
    executed, visible, price = 20.0, 20.0, 100.0
    signal = detector.update(executed, visible, price)

    assert signal == 0.0  # noqa: S101


def test_hidden_liquidity_rolling_persistence() -> None:
    """Verify signal persistence over a rolling window of 5 ticks."""
    window = 5
    detector = HiddenLiquidityDetector(window_size=window)

    # Send 3 identical iceberg events
    executed, visible, price = 100.0, 50.0, 150.0
    # H = 0.5 per event

    for _ in range(3):
        detector.update(executed, visible, price)

    # 3/5 window filled with 0.5. Average = 1.5/3 = 0.5 (Wait, average is across window)
    # len(history) is 3. sum = 1.5. average = 1.5/3 = 0.5.
    # Next call (4th tick): update(0, 0, 0) -> h_signal = 0.0.
    # History: [0.5, 0.5, 0.5, 0.0]. len = 4. sum = 1.5. average = 0.375.
    expected_avg = 0.375
    assert detector.update(0.0, 0.0, 0.0) == pytest.approx(expected_avg)  # noqa: S101


def test_hidden_liquidity_failsafe_noise() -> None:
    """Verify failsafe behavior for malformed or zero-volume events."""
    detector = HiddenLiquidityDetector()

    # zero volume is neutral
    assert detector.update(0.0, 10.0, 100.0) == 0.0  # noqa: S101

    # Negative depletion (simulating book replenishment)
    # Should not trigger iceberg
    assert detector.update(10.0, -5.0, 100.0) == 0.0  # noqa: S101


def test_hidden_liquidity_catastrophic_failure() -> None:
    """Verify industrial error recovery from malformed execution states."""
    detector = HiddenLiquidityDetector()

    # Malformed inputs (None causing TypeError in math logic)
    assert detector.update(None, 10.0, 100.0) == 0.0  # type: ignore # noqa: S101


def test_hidden_liquidity_reset() -> None:
    """Verify state reset for industrial lifecycle management."""
    detector = HiddenLiquidityDetector()
    detector.update(100, 20, 100)

    assert len(detector._history) > 0  # noqa: S101
    detector.reset()
    assert len(detector._history) == 0  # noqa: S101
    assert detector._last_iceberg_price is None  # noqa: S101
    assert detector._aggregate_signal() == 0.0  # noqa: S101

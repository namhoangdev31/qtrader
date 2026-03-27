import pytest

from qtrader.compliance.spoof_detector import SpoofDetector


@pytest.fixture
def detector() -> SpoofDetector:
    """Initialize a SpoofDetector with institutional thresholds."""
    # min_cancel_rate=0.9, max_fill_rate=0.05, min_orders=10
    return SpoofDetector(min_cancel_rate=0.8, max_fill_rate=0.05, min_orders=5)


def test_spoof_detector_malicious_signature(detector: SpoofDetector) -> None:
    """Verify that a sequence of large, short-lived, cancelled orders triggers a spoof flag."""
    user = "bad_actor"
    symbol = "BTC/USDT"

    # Sequence: 10 large SUBMITs + 10 rapid CANCELs (0 Fills)
    for _i in range(10):
        detector.record_event(user, symbol, "SUBMIT", size=500.0, filled_qty=0.0, lifespan_s=0.0)
        detector.record_event(user, symbol, "CANCEL", size=500.0, filled_qty=0.0, lifespan_s=0.05)

    # Cancel Rate: 100% (Threshold: 80%)
    # Fill Rate: 0% (Threshold: 5%)
    # Large Orders: 10
    # Short Lived: 10 (> 50% of 10)
    assert detector.is_spoofing(user, symbol) is True  # noqa: S101


def test_spoof_detector_market_maker_baseline(detector: SpoofDetector) -> None:
    """Verify that high cancellation with moderate fills (Market Maker) is NOT flagged."""
    user = "legit_mm"
    symbol = "ETH/USDT"

    # 10 Submits
    for _i in range(10):
        detector.record_event(user, symbol, "SUBMIT", size=1000.0, filled_qty=0.0, lifespan_s=0.0)

    # 8 Cancels (Cancel Rate: 80%)
    for _i in range(8):
        detector.record_event(user, symbol, "CANCEL", size=1000.0, filled_qty=0.0, lifespan_s=0.1)

    # 2 Fills (Fill Rate: 2 * 10.0 / (10 * 10) = 20% > 5% threshold)
    # Wait, in the code: fill_rate = stats.filled / (stats.submitted * 10.0)
    # So if fill=20 units / (10 * 10) = 0.2 (20%).
    for _i in range(2):
        detector.record_event(user, symbol, "FILL", size=10.0, filled_qty=10.0, lifespan_s=0.0)

    assert detector.is_spoofing(user, symbol) is False  # noqa: S101


def test_spoof_detector_small_order_immunity(detector: SpoofDetector) -> None:
    """Verify that high cancel rates on small orders are not flagged as manipulation."""
    user = "retail_trader"
    symbol = "SOL"

    # 10 Submits (Size: 1.0 - NOT Large)
    for _i in range(10):
        detector.record_event(user, symbol, "SUBMIT", size=1.0, filled_qty=0.0, lifespan_s=0.0)
        detector.record_event(user, symbol, "CANCEL", size=1.0, filled_qty=0.0, lifespan_s=0.05)

    # Cancel Rate: 100% but 0 Large Orders.
    assert detector.is_spoofing(user, symbol) is False  # noqa: S101


def test_spoof_detector_quorum_requirement(detector: SpoofDetector) -> None:
    """Verify that detection only triggers after minimum sample size (min_orders)."""
    user = "spoof_01"
    symbol = "BTC"

    # ONLY 2 orders (Threshold: 5)
    for _i in range(2):
        detector.record_event(user, symbol, "SUBMIT", size=1000.0, filled_qty=0.0, lifespan_s=0.0)
        detector.record_event(user, symbol, "CANCEL", size=1000.0, filled_qty=0.0, lifespan_s=0.01)

    assert detector.is_spoofing(user, symbol) is False  # noqa: S101


def test_spoof_detector_telemetry_check(detector: SpoofDetector) -> None:
    """Verify the operational governance report accuracy."""
    # Add some legitimate trading activity
    detector.record_event("u1", "S1", "SUBMIT", 100, 0, 0)
    detector.record_event("u1", "S1", "FILL", 100, 50, 0)  # FR: 50/100 = 50%

    report = detector.get_report()
    assert report["monitored_liquidity_entries"] == 1  # noqa: S101
    assert report["status"] == "SPOOF_CHECK"  # noqa: S101

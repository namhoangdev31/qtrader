import pytest
from qtrader.compliance.spoof_detector import SpoofDetector


@pytest.fixture
def detector() -> SpoofDetector:
    return SpoofDetector(min_cancel_rate=0.8, max_fill_rate=0.05, min_orders=5)


def test_spoof_detector_malicious_signature(detector: SpoofDetector) -> None:
    user = "bad_actor"
    symbol = "BTC/USDT"
    for _i in range(10):
        detector.record_event(user, symbol, "SUBMIT", size=500.0, filled_qty=0.0, lifespan_s=0.0)
        detector.record_event(user, symbol, "CANCEL", size=500.0, filled_qty=0.0, lifespan_s=0.05)
    assert detector.is_spoofing(user, symbol) is True


def test_spoof_detector_market_maker_baseline(detector: SpoofDetector) -> None:
    user = "legit_mm"
    symbol = "ETH/USDT"
    for _i in range(10):
        detector.record_event(user, symbol, "SUBMIT", size=1000.0, filled_qty=0.0, lifespan_s=0.0)
    for _i in range(8):
        detector.record_event(user, symbol, "CANCEL", size=1000.0, filled_qty=0.0, lifespan_s=0.1)
    for _i in range(2):
        detector.record_event(user, symbol, "FILL", size=10.0, filled_qty=10.0, lifespan_s=0.0)
    assert detector.is_spoofing(user, symbol) is False


def test_spoof_detector_small_order_immunity(detector: SpoofDetector) -> None:
    user = "retail_trader"
    symbol = "SOL"
    for _i in range(10):
        detector.record_event(user, symbol, "SUBMIT", size=1.0, filled_qty=0.0, lifespan_s=0.0)
        detector.record_event(user, symbol, "CANCEL", size=1.0, filled_qty=0.0, lifespan_s=0.05)
    assert detector.is_spoofing(user, symbol) is False


def test_spoof_detector_quorum_requirement(detector: SpoofDetector) -> None:
    user = "spoof_01"
    symbol = "BTC"
    for _i in range(2):
        detector.record_event(user, symbol, "SUBMIT", size=1000.0, filled_qty=0.0, lifespan_s=0.0)
        detector.record_event(user, symbol, "CANCEL", size=1000.0, filled_qty=0.0, lifespan_s=0.01)
    assert detector.is_spoofing(user, symbol) is False


def test_spoof_detector_telemetry_check(detector: SpoofDetector) -> None:
    detector.record_event("u1", "S1", "SUBMIT", 100, 0, 0)
    detector.record_event("u1", "S1", "FILL", 100, 50, 0)
    report = detector.get_report()
    assert report["monitored_liquidity_entries"] == 1
    assert report["status"] == "SPOOF_CHECK"

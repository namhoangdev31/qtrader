import time

import pytest

from qtrader.compliance.surveillance_engine import SurveillanceEngine, ViolationType


@pytest.fixture
def engine() -> SurveillanceEngine:
    """Initialize a SurveillanceEngine with institutional defaults."""
    return SurveillanceEngine(wash_window_ms=100)


def test_surveillance_wash_trading_detection(engine: SurveillanceEngine) -> None:
    """Verify that Buy/Sell orders for the same user within 100ms trigger a WASH_TRADING alert."""
    now = time.time()
    events = [
        {
            "user_id": "trader_01",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "order_id": "B1",
            "size": 1.0,
            "timestamp": now,
        },
        {
            "user_id": "trader_01",
            "symbol": "BTC/USDT",
            "side": "SELL",
            "order_id": "S1",
            "size": 1.0,
            "timestamp": now + 0.05,  # 50ms (within window)
        },
    ]

    alerts = engine.analyze_events(events)
    assert len(alerts) == 1
    assert alerts[0].type == ViolationType.WASH_TRADING
    assert alerts[0].evidence["e1_id"] == "B1"


def test_surveillance_spoofing_detection(engine: SurveillanceEngine) -> None:
    """Verify that rapid cancellation of a large order triggers a SPOOFING alert."""
    events = [
        {
            "type": "CANCEL",
            "user_id": "market_maker_01",
            "symbol": "ETH/USDT",
            "order_id": "C1",
            "is_large_order": True,
            "size": 1000.0,
            "time_in_book_s": 0.1,  # 100ms (within spoof window)
            "timestamp": time.time(),
        }
    ]

    alerts = engine.analyze_events(events)
    assert len(alerts) == 1
    assert alerts[0].type == ViolationType.SPOOFING
    assert alerts[0].evidence["order_id"] == "C1"


def test_surveillance_negative_baseline(engine: SurveillanceEngine) -> None:
    """Verify that normal trading sequences (different users, long time) DO NOT trigger alerts."""
    now = time.time()
    events = [
        # 1. Normal Trades (Different Users)
        {"user_id": "user_a", "symbol": "SOL", "side": "BUY", "timestamp": now},
        {"user_id": "user_b", "symbol": "SOL", "side": "SELL", "timestamp": now + 0.01},
        # 2. Normal Timing (Outside Wash Window)
        {"user_id": "user_c", "symbol": "SOL", "side": "BUY", "timestamp": now},
        {
            "user_id": "user_c",
            "symbol": "SOL",
            "side": "SELL",
            "timestamp": now + 0.2,  # 200ms (outside 100ms window)
        },
    ]

    alerts = engine.analyze_events(events)
    assert len(alerts) == 0


def test_surveillance_report_and_telemetry(engine: SurveillanceEngine) -> None:
    """Verify situational awareness report for violation density."""
    events = [
        {"user_id": "bad_actor", "symbol": "ABC", "side": "BUY", "timestamp": time.time()},
        {"user_id": "bad_actor", "symbol": "ABC", "side": "SELL", "timestamp": time.time() + 0.02},
    ]

    engine.analyze_events(events)
    report = engine.get_report()
    assert report["violations_detected"] == 1

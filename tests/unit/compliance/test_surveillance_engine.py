import time
import pytest
from qtrader.compliance.surveillance_engine import SurveillanceEngine, ViolationType


@pytest.fixture
def engine() -> SurveillanceEngine:
    return SurveillanceEngine(wash_window_ms=100)


def test_surveillance_wash_trading_detection(engine: SurveillanceEngine) -> None:
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
            "timestamp": now + 0.05,
        },
    ]
    alerts = engine.analyze_events(events)
    assert len(alerts) == 1
    assert alerts[0].type == ViolationType.WASH_TRADING
    assert alerts[0].evidence["e1_id"] == "B1"


def test_surveillance_spoofing_detection(engine: SurveillanceEngine) -> None:
    events = [
        {
            "type": "CANCEL",
            "user_id": "market_maker_01",
            "symbol": "ETH/USDT",
            "order_id": "C1",
            "is_large_order": True,
            "size": 1000.0,
            "time_in_book_s": 0.1,
            "timestamp": time.time(),
        }
    ]
    alerts = engine.analyze_events(events)
    assert len(alerts) == 1
    assert alerts[0].type == ViolationType.SPOOFING
    assert alerts[0].evidence["order_id"] == "C1"


def test_surveillance_negative_baseline(engine: SurveillanceEngine) -> None:
    now = time.time()
    events = [
        {"user_id": "user_a", "symbol": "SOL", "side": "BUY", "timestamp": now},
        {"user_id": "user_b", "symbol": "SOL", "side": "SELL", "timestamp": now + 0.01},
        {"user_id": "user_c", "symbol": "SOL", "side": "BUY", "timestamp": now},
        {"user_id": "user_c", "symbol": "SOL", "side": "SELL", "timestamp": now + 0.2},
    ]
    alerts = engine.analyze_events(events)
    assert len(alerts) == 0


def test_surveillance_report_and_telemetry(engine: SurveillanceEngine) -> None:
    events = [
        {"user_id": "bad_actor", "symbol": "ABC", "side": "BUY", "timestamp": time.time()},
        {"user_id": "bad_actor", "symbol": "ABC", "side": "SELL", "timestamp": time.time() + 0.02},
    ]
    engine.analyze_events(events)
    report = engine.get_report()
    assert report["violations_detected"] == 1

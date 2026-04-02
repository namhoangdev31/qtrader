import time
import uuid

import pytest
from pydantic import ValidationError

from qtrader.core.event_factory import EventFactory
from qtrader.core.event_validator import EventValidator, SchemaError
from qtrader.core.events import (
    BaseEvent,
    EventType,
    MarketEvent,
    MarketPayload,
    OrderEvent,
    OrderPayload,
)


def test_base_event_immutability():
    """Verify that events and their payloads are frozen and cannot be modified after creation."""
    payload = MarketPayload(symbol="BTC/USDT", bid=50000.0, ask=50001.0, seq_id=1)
    event = MarketEvent(
        event_id=uuid.uuid4(),
        trace_id=uuid.uuid4(),
        source="test_module",
        payload=payload
    )
    
    with pytest.raises(Exception):
        # Assignment to an attribute of a frozen Pydantic model raises ValidationError or AttributeError
        event.payload.symbol = "ETH/USDT"


def test_event_factory_creation():
    """Verify that the factory correctly generates metadata and validates schemas."""
    factory = EventFactory(source="StrategyEngine")
    
    payload = {
        "symbol": "BTC/USDT",
        "bid": 60000.0,
        "ask": 60005.0,
        "seq_id": 100
    }
    
    event = factory.create(EventType.MARKET_DATA, payload)
    
    assert event.source == "StrategyEngine"
    assert event.event_type == EventType.MARKET_DATA
    # In factory.create, we might want to cast it to the specialized event or it stays BaseEvent
    # For now, EventFactory returns BaseEvent.
    assert event.payload["symbol"] == "BTC/USDT" 
    assert isinstance(event.event_id, uuid.UUID)
    assert isinstance(event.trace_id, uuid.UUID)
    assert event.timestamp > 0


def test_event_validation_failure():
    """Verify that invalid payloads are rejected by the factory."""
    factory = EventFactory(source="StrategyEngine")
    
    # Missing 'bid' in MarketData payload
    invalid_payload = {
        "symbol": "BTC/USDT",
        "ask": 60005.0,
        "seq_id": 100
    }
    
    with pytest.raises(SchemaError):
        factory.create(EventType.MARKET_DATA, invalid_payload)


def test_validation_latency():
    """Verify that event creation and validation latency is < 1ms."""
    factory = EventFactory(source="ExecutionEngine")
    payload = {
        "order_id": "ORD-123",
        "symbol": "BTC/USDT",
        "action": "BUY",
        "quantity": 1.5,
        "price": 59000.0
    }
    
    # Warm up
    for _ in range(10):
        factory.create(EventType.ORDER, payload)
        
    start_time = time.perf_counter()
    iterations = 1000
    for _ in range(iterations):
        factory.create(EventType.ORDER, payload)
    end_time = time.perf_counter()
    
    avg_latency_ms = ((end_time - start_time) / iterations) * 1000
    print(f"Average latency per event: {avg_latency_ms:.4f} ms")
    
    assert avg_latency_ms < 1.0


def test_trace_id_propagation():
    """Verify that trace_id is correctly propagated between events."""
    factory_a = EventFactory(source="SourceA")
    factory_b = EventFactory(source="SourceB")
    
    event_a = factory_a.create(EventType.HEARTBEAT, {"status": "ok"})
    
    # Propagate trace_id from event_a to event_b
    event_b = factory_b.create(
        EventType.SYSTEM, 
        {"action": "LOG"}, 
        trace_id=event_a.trace_id
    )
    
    assert event_a.trace_id == event_b.trace_id
    assert event_a.event_id != event_b.event_id


def test_legacy_bridge_compatibility():
    """Verify that importing from legacy core/event.py bridge works."""
    from qtrader.core.event import EventType, MarketDataEvent
    from qtrader.core.events import MarketPayload
    
    payload = MarketPayload(symbol="BTC/USDT", bid=50000.0, ask=50001.0, seq_id=1)
    event = MarketDataEvent(
        trace_id=uuid.uuid4(),
        source="test_legacy",
        payload=payload
    )
    
    # Test property access (Legacy API)
    assert event.bid == 50000.0
    assert event.ask == 50001.0
    assert event.symbol == "BTC/USDT"
    
    # Test Type compatibility
    assert event.event_type == EventType.MARKET_DATA
    # Test legacy .type access
    assert event.type == EventType.MARKET_DATA


def test_specialized_properties():
    """Verify that specialized event properties like 'signal' calculation work."""
    from qtrader.core.events import SignalEvent, SignalPayload
    
    payload_buy = SignalPayload(symbol="BTC/USDT", signal_type="BUY", strength=0.8)
    event_buy = SignalEvent(trace_id=uuid.uuid4(), source="Alpha", payload=payload_buy)
    assert event_buy.signal == 0.8
    
    payload_sell = SignalPayload(symbol="BTC/USDT", signal_type="SELL", strength=0.5)
    event_sell = SignalEvent(trace_id=uuid.uuid4(), source="Alpha", payload=payload_sell)
    assert event_sell.signal == -0.5

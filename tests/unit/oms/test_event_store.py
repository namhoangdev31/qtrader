import json
import os
from datetime import datetime, timezone

import pytest

from qtrader.core.event import EventType, MarketDataEvent
from qtrader.oms.event_store import EventStore


@pytest.fixture
def temp_log(tmp_path):
    log_file = tmp_path / "test_events.jsonl"
    return str(log_file)

@pytest.mark.asyncio
async def test_record_and_get_last_sequence(temp_log):
    store = EventStore(log_path=temp_log)
    
    # Record some events
    for i in range(1, 6):
        event = MarketDataEvent(
            symbol="BTC-USDT",
            seq_id=i,
            data={"last_price": 50000 + i},
            trace_id=f"t-{i}"
        )
        await store.record_event(event)

    assert store.get_last_sequence("BTC-USDT") == 5
    assert store.get_last_sequence("ETH-USDT") == 0

@pytest.mark.asyncio
async def test_get_recent_prices(temp_log):
    store = EventStore(log_path=temp_log)
    
    for i in range(1, 11):
        event = MarketDataEvent(
            symbol="BTC-USDT",
            seq_id=i,
            data={"last_price": float(i)},
            trace_id=f"t-{i}"
        )
        await store.record_event(event)

    prices = store.get_recent_prices("BTC-USDT", window_size=5)
    assert len(prices) == 5
    assert prices == [6.0, 7.0, 8.0, 9.0, 10.0]

@pytest.mark.asyncio
async def test_get_latest_price_cross_exchange(temp_log):
    store = EventStore(log_path=temp_log)
    
    # Event from Binance
    ev1 = MarketDataEvent(
        symbol="BTC-USDT",
        seq_id=1,
        data={"last_price": 50000.0},
        metadata={"venue": "binance"},
        trace_id="t-1"
    )
    await store.record_event(ev1)
    
    # Event from Coinbase
    ev2 = MarketDataEvent(
        symbol="BTC-USDT",
        seq_id=2,
        data={"last_price": 50010.0},
        metadata={"venue": "coinbase"},
        trace_id="t-2"
    )
    await store.record_event(ev2)

    # Latest from *other* than Binance should be 50010 (Coinbase)
    ref_price = store.get_latest_price_cross_exchange("BTC-USDT", exclude_venue="binance")
    assert ref_price == 50010.0
    
    # Latest from *other* than Coinbase should be 50000 (Binance)
    ref_price = store.get_latest_price_cross_exchange("BTC-USDT", exclude_venue="coinbase")
    assert ref_price == 50000.0

@pytest.mark.asyncio
async def test_get_deltas(temp_log):
    store = EventStore(log_path=temp_log)
    
    for i in range(1, 6):
        event = MarketDataEvent(
            symbol="BTC-USDT",
            seq_id=i,
            data={"c": float(i)},
            trace_id=f"t-{i}"
        )
        await store.record_event(event)

    deltas = store.get_deltas("BTC-USDT", start_seq=3)
    assert len(deltas) == 3
    assert [d["seq_id"] for d in deltas] == [3, 4, 5]

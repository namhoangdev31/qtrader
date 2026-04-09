import asyncio
import os
import shutil
import uuid
from datetime import datetime
import pytest
from qtrader.core.event_store import FileEventStore
from qtrader.core.events import EventType, MarketEvent, MarketPayload


@pytest.fixture
def store():
    test_path = "tmp/test_event_store_distributed"
    if os.path.exists(test_path):
        shutil.rmtree(test_path)
    os.makedirs(test_path)
    store = FileEventStore(base_path=test_path)
    yield store
    if os.path.exists(test_path):
        shutil.rmtree(test_path)


@pytest.mark.asyncio
async def test_event_idempotency(store):
    payload = MarketPayload(symbol="BTC/USDT", bid=50000.0, ask=50001.0, seq_id=1)
    event_id = uuid.uuid4()
    event = MarketEvent(
        event_id=event_id,
        trace_id=uuid.uuid4(),
        source="Exchange",
        payload=payload,
        partition_key="BTC",
    )
    offset1 = await store.append(event)
    assert offset1 == 0
    offset2 = await store.append(event)
    assert offset2 is None
    assert store._index.total_event_count == 1


@pytest.mark.asyncio
async def test_partition_offsets(store):
    payload = MarketPayload(symbol="SOL/USDT", bid=150.0, ask=150.1)
    for _i in range(5):
        evt_btc = MarketEvent(
            trace_id=uuid.uuid4(), source="Test", payload=payload, partition_key="BTC"
        )
        evt_eth = MarketEvent(
            trace_id=uuid.uuid4(), source="Test", payload=payload, partition_key="ETH"
        )
        await store.append(evt_btc)
        await store.append(evt_eth)
    btc_events = await store.get_events(partition="BTC")
    assert [e.offset for e in btc_events] == [0, 1, 2, 3, 4]
    eth_events = await store.get_events(partition="ETH")
    assert [e.offset for e in eth_events] == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_startup_index_rebuild(store):
    payload = MarketPayload(symbol="LINK/USDT", bid=18.0, ask=18.1)
    event_id = uuid.uuid4()
    event = MarketEvent(
        event_id=event_id,
        trace_id=uuid.uuid4(),
        source="Init",
        payload=payload,
        partition_key="LINK",
    )
    await store.append(event)
    assert store._index.is_duplicate(event_id) is True
    new_store = FileEventStore(base_path=store.base_path)
    assert new_store._index.is_duplicate(event_id) is True
    assert new_store._index.total_event_count == 1
    assert new_store._index.get_next_offset("LINK") == 1


@pytest.mark.asyncio
async def test_offset_range_query(store):
    partition = "ADA"
    for i in range(10):
        evt = MarketEvent(
            trace_id=uuid.uuid4(),
            source="Feed",
            payload=MarketPayload(symbol="ADA/USDT", bid=i, ask=i + 1),
            partition_key=partition,
        )
        await store.append(evt)
    range_events = await store.get_events(partition=partition, start_offset=3, end_offset=7)
    assert len(range_events) == 5
    assert range_events[0].offset == 3
    assert range_events[-1].offset == 7


@pytest.mark.asyncio
async def test_write_latency_simulation(store):
    import time

    total_samples = 100
    latencies = []
    for i in range(total_samples):
        evt = MarketEvent(
            trace_id=uuid.uuid4(),
            source="HighFreq",
            payload=MarketPayload(symbol="TEST", bid=i, ask=i + 1),
            partition_key="TEST_PARTITION",
        )
        t0 = time.perf_counter()
        await store.append(evt)
        latencies.append((time.perf_counter() - t0) * 1000)
    avg_latency = sum(latencies) / total_samples
    print(f"\nAverage Write Latency: {avg_latency:.4f} ms")
    assert avg_latency < 10.0

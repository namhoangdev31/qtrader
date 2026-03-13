import asyncio

import pytest

from qtrader.core.bus import EventBus
from qtrader.core.event import EventType, MarketDataEvent


@pytest.mark.asyncio
async def test_shutdown_unblocks_start_when_queue_empty() -> None:
    bus = EventBus(queue_maxsize=10)
    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0)  # let start() enter queue.get()
    await bus.shutdown()
    await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_backpressure_blocks_when_queue_full() -> None:
    bus = EventBus(queue_maxsize=1)

    # No subscribers; start() will still consume events but we won't start it here
    # to force the queue to fill.
    event1 = MarketDataEvent(symbol="X", data={})
    event2 = MarketDataEvent(symbol="X", data={})

    await bus.publish(event1)

    # Second publish should block because queue is full (maxsize=1) and nothing is consuming.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(bus.publish(event2), timeout=0.1)


@pytest.mark.asyncio
async def test_handler_exception_does_not_stop_bus_and_increments_metric() -> None:
    bus = EventBus(queue_maxsize=10)

    async def bad_handler(_e: MarketDataEvent) -> None:
        raise RuntimeError("boom")

    seen: list[str] = []

    async def good_handler(_e: MarketDataEvent) -> None:
        seen.append("ok")

    bus.subscribe(EventType.MARKET_DATA, bad_handler)  # type: ignore[arg-type]
    bus.subscribe(EventType.MARKET_DATA, good_handler)  # type: ignore[arg-type]

    task = asyncio.create_task(bus.start())
    await bus.publish(MarketDataEvent(symbol="X", data={}))

    # Give event loop a moment to process.
    await asyncio.sleep(0.05)

    assert seen == ["ok"]
    assert bus.handler_errors_total >= 1

    await bus.shutdown()
    await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_handler_timeout_increments_metric() -> None:
    bus = EventBus(queue_maxsize=10, handler_timeout_s=0.01)

    async def slow_handler(_e: MarketDataEvent) -> None:
        await asyncio.sleep(0.2)

    bus.subscribe(EventType.MARKET_DATA, slow_handler)  # type: ignore[arg-type]

    task = asyncio.create_task(bus.start())
    await bus.publish(MarketDataEvent(symbol="X", data={}))
    await asyncio.sleep(0.05)

    assert bus.handler_timeouts_total >= 1

    await bus.shutdown()
    await asyncio.wait_for(task, timeout=1.0)

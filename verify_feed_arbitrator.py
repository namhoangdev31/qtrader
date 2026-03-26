import asyncio
import datetime
import time

from qtrader.core.event import FeedEvent, EventType
from qtrader.core.event_bus import EventBus
from qtrader.data.market.feed_arbitrator import FeedArbitrator


async def test_feed_arbitrator():
    """Verify deterministic feed arbitration and selection scoring."""
    bus = EventBus()
    await bus.start()
    
    arbitrator = FeedArbitrator(event_bus=bus)
    
    # 1. Event from Source A (Low Latency, High Staleness)
    feedA = FeedEvent(
        event_id="e1",
        trace_id="t1",
        source="Feed A",
        latency=10.0,
        timestamp=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(milliseconds=50) # 50ms old
    )
    
    # 2. Event from Source B (High Latency, Fresh)
    feedB = FeedEvent(
        event_id="e2",
        trace_id="t2",
        source="Feed B",
        latency=40.0,
        timestamp=datetime.datetime.now(datetime.timezone.utc) # Fresh
    )
    
    # 3. Perform selection
    print("\n--- Running Feed Arbitration Simulation ---")
    
    selected = await arbitrator.select(feedA, feedB)
    print(f"Selected: {selected.source} (Latency: {selected.latency}ms)")
    
    # Check switch count
    print(f"Feed Switch Count: {arbitrator.feed_switch_count}")
    
    # Check report
    report = arbitrator.report()
    print(f"Report: {report}")
    
    # 4. Trigger a switch (Flip the latency/staleness)
    feedA2 = FeedEvent(
        event_id="e3",
        trace_id="t3",
        source="Feed A",
        latency=200.0, # Now Feed A is extremely slow
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    
    feedB2 = FeedEvent(
        event_id="e4",
        trace_id="t4",
        source="Feed B",
        latency=5.0, # Now Feed B is the best
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    
    selected_new = await arbitrator.select(feedA2, feedB2)
    print(f"\n--- After Flipping Latency ---")
    print(f"Selected New: {selected_new.source} (Latency: {selected_new.latency}ms)")
    print(f"Feed Switch Count: {arbitrator.feed_switch_count}")
    
    # 5. Handle missing feeds
    print("\n--- Testing Fallback Logic ---")
    only_one = await arbitrator.select(feedA, None)
    print(f"Selected Only One (Feed A): {only_one.source}")
    
    await bus.stop()
    print("\nSimulation Complete")


if __name__ == "__main__":
    asyncio.run(test_feed_arbitrator())

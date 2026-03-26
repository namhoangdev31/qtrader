import asyncio
import json
import os
import pytest
from datetime import datetime
from decimal import Decimal
from qtrader.core.state_store import StateStore
from qtrader.oms.replay_engine import ReplayEngine
from qtrader.core.event import EventType

@pytest.mark.asyncio
async def test_deterministic_replay_state_reconstruction():
    """
    Test that State(t) = Σ Events[0 → t].
    Ensures replay engine can reconstruct positions exactly from an event log.
    """
    # Create temp log file
    log_path = "tests/tmp/order_event_log.jsonl"
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    events = [
        {
            "type": "ORDER", # Simulating legacy string type for backward-compat or enum-value
            "order_id": "ORD-1",
            "symbol": "BTC/USD",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 1.0,
            "timestamp": "2026-03-26T10:00:00Z"
        },
        {
            "type": "FILL",
            "order_id": "ORD-1",
            "symbol": "BTC/USD",
            "side": "BUY",
            "quantity": 0.4,
            "price": 50000.0,
            "timestamp": "2026-03-26T10:00:01Z"
        },
        {
            "type": "FILL",
            "order_id": "ORD-1",
            "symbol": "BTC/USD",
            "side": "BUY",
            "quantity": 0.6,
            "price": 50100.0,
            "timestamp": "2026-03-26T10:00:02Z"
        }
    ]
    
    with open(log_path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
            
    # Initialize ReplayEngine
    state_store = StateStore()
    replay_engine = ReplayEngine(state_store)
    
    # Load and Replay
    replay_engine.load_log(log_path)
    await replay_engine.replay_upto(datetime.fromisoformat("2026-03-26T10:00:05+00:00"))
    
    # Assert Position Reconstruction
    pos = await state_store.get_position("BTC/USD")
    assert pos is not None
    # 0.4 + 0.6 = 1.0
    assert float(pos.quantity) == 1.0
    
    # Cleanup
    if os.path.exists(log_path):
        os.remove(log_path)

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qtrader.audit.replay_audit import ReplayAudit
from qtrader.core.events import (
    DecisionTraceEvent,
    DecisionTracePayload,
    FillEvent,
    FillPayload,
    NAVEvent,
    NAVPayload,
)

# Testing Constants
PNL_VALUE = 50.0
SIGNAL_ORIGINAL = 0.75
SIGNAL_REPLAYED = 0.45


@pytest.mark.asyncio
async def test_replay_audit_deterministic_match() -> None:
    """Verify that a perfect trace reconstruction results in a 100% match."""
    trace_id = uuid.uuid4()
    
    # 1. Mock Registry
    registry = MagicMock()
    registry.load_model.return_value = MagicMock()
    
    # 2. Mock EventStore
    store = AsyncMock()
    payload = DecisionTracePayload(
        model_id="M1",
        features={"f1": 1.0},
        signal=SIGNAL_ORIGINAL,
        decision="BUY",
        config_version=1
    )
    events = [
        DecisionTraceEvent(
            trace_id=trace_id,
            source="Strat",
            timestamp=1000,
            payload=payload
        ),
        FillEvent(
            trace_id=trace_id,
            source="Exch",
            timestamp=2000,
            payload=FillPayload(
                order_id="ORD1", symbol="BTC", side="BUY", quantity=1.0, price=50000.0
            )
        ),
        NAVEvent(
            trace_id=trace_id,
            source="Port",
            timestamp=3000,
            payload=NAVPayload(
                nav=100000.0, cash=50000.0, realized_pnl=PNL_VALUE, 
                unrealized_pnl=0.0, total_fees=5.0
            )
        )
    ]
    store.get_events_by_trace_id.return_value = events
    
    auditor = ReplayAudit(store, registry)
    report = await auditor.run(trace_id)
    
    assert report.match is True # noqa: S101
    assert report.decision_original == "BUY" # noqa: S101
    assert report.decision_replayed == "BUY" # noqa: S101
    assert report.pnl == PNL_VALUE # noqa: S101
    assert report.execution_outcome == "COMPLETED" # noqa: S101


@pytest.mark.asyncio
async def test_replay_audit_missing_events_failure() -> None:
    """Verify that missing events trigger an appropriate audit failure."""
    trace_id = uuid.uuid4()
    store = AsyncMock()
    store.get_events_by_trace_id.return_value = [] # Empty trace
    registry = MagicMock()
    
    auditor = ReplayAudit(store, registry)
    
    with pytest.raises(ValueError, match=f"No events found for trace_id: {trace_id}"):
        await auditor.run(trace_id)


@pytest.mark.asyncio
async def test_replay_audit_mismatch_detection() -> None:
    """Verify that signal/decision deviations are captured in the report."""
    trace_id = uuid.uuid4()
    store = AsyncMock()
    registry = MagicMock()
    registry.load_model.return_value = MagicMock()
    
    payload = DecisionTracePayload(
        model_id="M1",
        features={"f1": 1.0},
        signal=SIGNAL_ORIGINAL,
        decision="BUY",
        config_version=1
    )
    events = [
        DecisionTraceEvent(
            trace_id=trace_id,
            source="Strat",
            timestamp=100,
            payload=payload
        )
    ]
    store.get_events_by_trace_id.return_value = events
    
    auditor = ReplayAudit(store, registry)
    
    with patch.object(auditor, "_recompute_decision", new_callable=AsyncMock) as mock_recompute:
        mock_recompute.return_value = {"signal": SIGNAL_REPLAYED, "decision": "HOLD"}
        
        report = await auditor.run(trace_id)
        
        assert report.match is False # noqa: S101
        assert report.decision_original == "BUY" # noqa: S101
        assert report.decision_replayed == "HOLD" # noqa: S101
        assert report.deviation_signal == pytest.approx(SIGNAL_ORIGINAL - SIGNAL_REPLAYED) # noqa: S101
        assert report.execution_outcome == "INCOMPLETE" # noqa: S101


@pytest.mark.asyncio
async def test_replay_audit_missing_trace_event() -> None:
    """Verify handling when a trace exists but lacks a DecisionTraceEvent."""
    trace_id = uuid.uuid4()
    store = AsyncMock()
    # Lifecycle without decision audit
    store.get_events_by_trace_id.return_value = [
        FillEvent(
            trace_id=trace_id, source="Exch", timestamp=1,
            payload=FillPayload(order_id="O1", symbol="BTC", side="BUY", quantity=1.0, price=1.0)
        )
    ]
    registry = MagicMock()
    
    auditor = ReplayAudit(store, registry)
    report = await auditor.run(trace_id)
    
    assert report.execution_outcome == "FAILED" # noqa: S101
    assert report.match is False # noqa: S101


@pytest.mark.asyncio
async def test_replay_audit_critical_exception() -> None:
    """Verify that system exceptions halt the audit and are logged."""
    trace_id = uuid.uuid4()
    store = AsyncMock()
    store.get_events_by_trace_id.side_effect = RuntimeError("Store CRASH")
    registry = MagicMock()
    
    auditor = ReplayAudit(store, registry)
    
    with pytest.raises(RuntimeError, match="Store CRASH"):
        await auditor.run(trace_id)

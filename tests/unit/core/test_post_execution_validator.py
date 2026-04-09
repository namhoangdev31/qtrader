import json
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from qtrader.core.events import BaseEvent, EventType
from qtrader.core.post_execution_validator import PostExecutionValidator
from qtrader.core.state_store import Position, StateStore, SystemState


@pytest.fixture
def validator(tmp_path):
    root = tmp_path / "qtrader"
    root.mkdir()
    return PostExecutionValidator(root_path=str(tmp_path))


@pytest.mark.asyncio
async def test_check_trace_completeness_success(validator):
    mock_event_store = MagicMock()
    trace_id = uuid4()
    events = [
        MagicMock(trace_id=trace_id, event_type=EventType.ORDER),
        MagicMock(trace_id=trace_id, event_type=EventType.FILL),
    ]
    mock_event_store.get_events = AsyncMock(return_value=events)
    results = await validator._check_trace_completeness(mock_event_store)
    assert results["complete"] is True
    assert results["issues"] == 0


@pytest.mark.asyncio
async def test_check_trace_completeness_failure(validator):
    mock_event_store = MagicMock()
    trace_id = uuid4()
    events = [MagicMock(trace_id=trace_id, event_type=EventType.ORDER)]
    mock_event_store.get_events = AsyncMock(return_value=events)
    results = await validator._check_trace_completeness(mock_event_store)
    assert results["complete"] is False
    assert results["issues"] == 1
    assert str(trace_id) in results["orphaned_traces"]


@pytest.mark.asyncio
async def test_check_state_consistency_success(validator):
    mock_state_store = MagicMock()
    state = SystemState(
        cash=Decimal("1000.0"),
        active_orders={},
        positions={"BTC/USDT": Position(symbol="BTC/USDT", quantity=Decimal("1.0"))},
    )
    mock_state_store.snapshot = AsyncMock(return_value=state)
    results = await validator._check_state_consistency(mock_state_store)
    assert results["consistent"] is True
    assert results["issues"] == 0
    assert results["metrics"]["position_count"] == 1


@pytest.mark.asyncio
async def test_check_state_consistency_failure(validator):
    mock_state_store = MagicMock()
    state = SystemState(
        cash=Decimal("1000.0"), active_orders={"order_1": MagicMock()}, positions={}
    )
    mock_state_store.snapshot = AsyncMock(return_value=state)
    results = await validator._check_state_consistency(mock_state_store)
    assert results["consistent"] is False
    assert results["issues"] == 1
    assert "STALE_ACTIVE_ORDERS" in results["detected_inconsistencies"][0]


@pytest.mark.asyncio
async def test_full_validation_report_generation(validator):
    mock_event_store = MagicMock()
    mock_event_store.get_events = AsyncMock(return_value=[])
    mock_state_store = MagicMock()
    mock_state_store.snapshot = AsyncMock(return_value=SystemState())
    report = await validator.validate(mock_event_store, mock_state_store)
    assert report["status"] == "VERIFIED"
    assert report["valid"] is True
    report_path = os.path.join(validator.audit_dir, "post_execution_report.json")
    assert os.path.exists(report_path)
    with open(report_path) as f:
        data = json.load(f)
        assert data["status"] == "VERIFIED"
    md_path = os.path.join(validator.audit_dir, "consistency_check.md")
    assert os.path.exists(md_path)

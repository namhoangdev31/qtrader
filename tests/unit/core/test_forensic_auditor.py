from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from qtrader.core.events import (
    EventType,
    FillEvent,
    FillPayload,
    OrderEvent,
    OrderPayload,
    SignalEvent,
    SignalPayload,
    SystemEvent,
    SystemPayload,
)
from qtrader.core.forensic_auditor import ForensicAuditor


@pytest.fixture
def mock_event_bus():
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_db_writer():
    writer = MagicMock()
    writer.write_forensic_note = AsyncMock()
    return writer


@pytest.fixture
def auditor(mock_event_bus, mock_db_writer):
    return ForensicAuditor(mock_event_bus, mock_db_writer, session_id="test-session")


@pytest.mark.asyncio
async def test_auditor_start_stop(auditor, mock_event_bus):
    auditor.start()
    # SIGNAL, ORDER, FILL, HALT, RISK_REJECTED, STRATEGY_KILL, PIPELINE_ERROR, ERROR, SYSTEM
    assert mock_event_bus.subscribe.call_count == 9

    auditor.stop()
    assert mock_event_bus.unsubscribe.call_count == 9


@pytest.mark.asyncio
async def test_on_signal_note_generation(auditor, mock_db_writer, mock_event_bus):
    event = SignalEvent(
        source="test",
        payload=SignalPayload(
            symbol="BTC-USD",
            signal_type="BUY",
            strength=Decimal("0.85"),
            confidence=Decimal("0.9"),
            metadata={"model_id": "GhostAlpha-01", "explanation": "Bullish trend confirmed"},
        ),
    )

    await auditor._on_signal(event)

    # Verify DB writing
    mock_db_writer.write_forensic_note.assert_called_once()
    args, kwargs = mock_db_writer.write_forensic_note.call_args
    assert "[ALPHA] GhostAlpha-01 generated BUY signal" in kwargs["content"]
    assert "Confidence: 90%" in kwargs["content"]
    assert "Reasoning: Bullish trend confirmed" in kwargs["content"]

    # Verify event re-publishing
    assert mock_event_bus.publish.call_count == 1


@pytest.mark.asyncio
async def test_on_risk_rejection(auditor, mock_db_writer):
    from qtrader.core.events import RiskRejectedEvent, RiskRejectedPayload

    event = RiskRejectedEvent(
        source="RiskEngine",
        payload=RiskRejectedPayload(
            order_id="ORD-001",
            reason="MAX_EXPOSURE_EXCEEDED",
            metric_value=150000.0,
            threshold=100000.0,
        ),
    )

    await auditor._on_risk_rejection(event)

    mock_db_writer.write_forensic_note.assert_called_once()
    args, kwargs = mock_db_writer.write_forensic_note.call_args
    assert "Order ORD-001 REJECTED" in kwargs["content"]
    assert "MAX_EXPOSURE_EXCEEDED" in kwargs["content"]
    assert kwargs["note_type"] == "ALERT"


@pytest.mark.asyncio
async def test_on_system_event_rejection(auditor, mock_db_writer):
    event = SystemEvent(
        source="UnifiedOMS",
        payload=SystemPayload(
            action="ORDER_REJECTED", reason="Insufficient Margin", metadata={"order_id": "ORD-999"}
        ),
    )

    await auditor._on_system_event(event)

    mock_db_writer.write_forensic_note.assert_called_once()
    args, kwargs = mock_db_writer.write_forensic_note.call_args
    assert "[OMS] Order ORD-999 REJECTED" in kwargs["content"]
    assert "Insufficient Margin" in kwargs["content"]
    assert kwargs["note_type"] == "ALERT"


@pytest.mark.asyncio
async def test_on_fill_note_generation(auditor, mock_db_writer):
    event = FillEvent(
        source="test",
        payload=FillPayload(
            order_id="order-123",
            symbol="ETH-USD",
            side="SELL",
            quantity=Decimal("1.5"),
            price=Decimal("3500.0"),
            commission=Decimal("2.5"),
        ),
    )

    await auditor._on_fill(event)

    mock_db_writer.write_forensic_note.assert_called_once()
    args, kwargs = mock_db_writer.write_forensic_note.call_args
    assert "Execution Successful: ETH-USD SELL 1.5 filled at 3500.00" in kwargs["content"]
    assert kwargs["note_type"] == "TRIAL"


@pytest.mark.asyncio
async def test_on_strategy_kill(auditor, mock_db_writer):
    from qtrader.core.events import StrategyKillEvent, StrategyKillPayload

    event = StrategyKillEvent(
        source="RiskEngine",
        payload=StrategyKillPayload(
            strategy_id="TrendFollower",
            reason="MAX_DRAWDOWN_BREACH",
            metric="drawdown",
            threshold=0.15,
        ),
    )

    await auditor._on_strategy_kill(event)

    mock_db_writer.write_forensic_note.assert_called_once()
    args, kwargs = mock_db_writer.write_forensic_note.call_args
    assert "Strategy 'TrendFollower' KILLED" in kwargs["content"]
    assert "MAX_DRAWDOWN_BREACH" in kwargs["content"]
    assert kwargs["note_type"] == "ALERT"

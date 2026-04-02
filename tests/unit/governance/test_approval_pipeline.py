import uuid
from typing import NoReturn
from unittest.mock import AsyncMock, MagicMock

import pytest

from qtrader.core.events import (
    EventType,
    ModelRiskScoreEvent,
    ModelRiskScorePayload,
    SandboxReportEvent,
    SandboxReportPayload,
)
from qtrader.governance.approval_pipeline import StrategyApprovalPipeline

# Test Constants
STRATEGY_ID = "STRATEGY_MOMENTUM_v1"


@pytest.mark.asyncio
async def test_approval_pipeline_successful_decision() -> None:
    """Verify that a strategy with good metrics is formally approved."""
    bus = AsyncMock()
    fsm = AsyncMock()
    fsm.transition.return_value = True

    pipeline = StrategyApprovalPipeline(bus, fsm, min_pnl=1.0, max_dd=0.05, max_risk=0.5)

    sandbox_report = SandboxReportEvent(
        trace_id=uuid.uuid4(),
        source="Sandbox",
        timestamp=100,
        payload=SandboxReportPayload(
            strategy_id=STRATEGY_ID,
            pnl=2.0,
            drawdown=0.02,
            sharpe=1.5,
            status="SUCCESS",
            trade_count=10,
        ),
    )

    risk_event = ModelRiskScoreEvent(
        trace_id=uuid.uuid4(),
        source="RiskScorer",
        timestamp=101,
        payload=ModelRiskScorePayload(
            model_id=STRATEGY_ID, risk_score=0.1, volatility=0.2, drawdown=0.02, stability=0.9
        ),
    )

    event = await pipeline.evaluate_strategy(sandbox_report, risk_event)

    # 1. Verification of the Decision
    assert event is not None
    assert event.payload.approved
    assert event.payload.strategy_id == STRATEGY_ID

    # 2. Verification of FSM Transition
    assert fsm.transition.called
    fsm.transition.assert_called_with(STRATEGY_ID, "APPROVED", reason="PIPELINE_APPROVAL_GRANTED")

    # 3. Verification of Event Bus Publish
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.STRATEGY_APPROVAL


@pytest.mark.asyncio
async def test_approval_pipeline_fsm_failure() -> None:
    """Verify that if FSM transition fails, the approval is retracted."""
    bus = AsyncMock()
    fsm = AsyncMock()
    fsm.transition.return_value = False  # Simulate FSM failure

    pipeline = StrategyApprovalPipeline(bus, fsm, min_pnl=1.0)

    sandbox_report = SandboxReportEvent(
        trace_id=uuid.uuid4(),
        source="S",
        timestamp=1,
        payload=SandboxReportPayload(
            strategy_id=STRATEGY_ID,
            pnl=2.0,
            drawdown=0.01,
            sharpe=1.0,
            status="S",
            trade_count=1,
        ),
    )
    risk_event = ModelRiskScoreEvent(
        trace_id=uuid.uuid4(),
        source="R",
        timestamp=2,
        payload=ModelRiskScorePayload(
            model_id=STRATEGY_ID, risk_score=0.1, volatility=0.1, drawdown=0.01, stability=1.0
        ),
    )

    event = await pipeline.evaluate_strategy(sandbox_report, risk_event)

    assert event is not None
    assert not event.payload.approved
    assert event.payload.reason == "FSM_TRANSITION_FAILURE"


@pytest.mark.asyncio
async def test_approval_pipeline_rejection_low_pnl() -> None:
    """Verify that a strategy with low PnL is formally rejected."""
    bus = AsyncMock()
    fsm = AsyncMock()
    pipeline = StrategyApprovalPipeline(bus, fsm, min_pnl=5.0)  # High PnL required

    sandbox_report = SandboxReportEvent(
        trace_id=uuid.uuid4(),
        source="S",
        timestamp=1,
        payload=SandboxReportPayload(
            strategy_id=STRATEGY_ID,
            pnl=2.0,
            drawdown=0.01,
            sharpe=1.0,
            status="S",
            trade_count=1,
        ),
    )
    risk_event = ModelRiskScoreEvent(
        trace_id=uuid.uuid4(),
        source="R",
        timestamp=2,
        payload=ModelRiskScorePayload(
            model_id=STRATEGY_ID, risk_score=0.1, volatility=0.1, drawdown=0.01, stability=1.0
        ),
    )

    event = await pipeline.evaluate_strategy(sandbox_report, risk_event)

    assert event is not None
    assert not event.payload.approved
    assert "INSUFFICIENT_PNL" in event.payload.reason
    assert not fsm.transition.called


@pytest.mark.asyncio
async def test_approval_pipeline_rejection_high_risk() -> None:
    """Verify that a strategy exceeding risk thresholds is formally rejected."""
    bus = AsyncMock()
    fsm = AsyncMock()
    pipeline = StrategyApprovalPipeline(bus, fsm, max_risk=0.3)

    sandbox_report = SandboxReportEvent(
        trace_id=uuid.uuid4(),
        source="S",
        timestamp=1,
        payload=SandboxReportPayload(
            strategy_id=STRATEGY_ID,
            pnl=2.0,
            drawdown=0.01,
            sharpe=1.0,
            status="S",
            trade_count=1,
        ),
    )
    risk_event = ModelRiskScoreEvent(
        trace_id=uuid.uuid4(),
        source="R",
        timestamp=2,
        payload=ModelRiskScorePayload(
            model_id=STRATEGY_ID, risk_score=0.4, volatility=0.1, drawdown=0.01, stability=1.0
        ),
    )

    event = await pipeline.evaluate_strategy(sandbox_report, risk_event)

    assert event is not None
    assert not event.payload.approved
    assert "EXCESSIVE_RISK" in event.payload.reason


@pytest.mark.asyncio
async def test_approval_pipeline_system_failure() -> None:
    """Verify industrial error handling during approval-level exceptions."""
    bus = AsyncMock()
    fsm = AsyncMock()
    pipeline = StrategyApprovalPipeline(bus, fsm)

    # Catastrophic failure recovery test
    class Crasher:
        @property
        def payload(self) -> NoReturn:
            raise Exception("SYSTEM_CRASH")

    event = await pipeline.evaluate_strategy(Crasher(), MagicMock())  # type: ignore

    assert event is None
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.APPROVAL_ERROR
    assert "SYSTEM_CRASH" in str(bus.publish.call_args)

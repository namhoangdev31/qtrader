from unittest.mock import AsyncMock

import pytest

from qtrader.core.events import EventType
from qtrader.governance.model_risk import ModelRiskScorer

# Test Constants
MODEL_ID = "STRATEGY_MOMENTUM_v1"


@pytest.mark.asyncio
async def test_model_risk_scoring_success() -> None:
    """Verify that a model's risk score is correctly calculated and broadcast."""
    bus = AsyncMock()
    scorer = ModelRiskScorer(bus)

    metrics = {"volatility": 0.20, "drawdown": 0.15, "stability": 0.8}

    # Expected Score Calculation:
    # (0.4 * 0.20) + (0.4 * 0.15) - (0.2 * 0.8)
    # = (0.08) + (0.06) - (0.16) = -0.02

    event = await scorer.compute_risk_score(MODEL_ID, metrics)

    # 1. Verification of the Score Event
    assert event is not None
    assert event.payload.model_id == MODEL_ID
    assert event.payload.risk_score == pytest.approx(-0.02)
    assert event.payload.volatility == 0.20

    # 2. Verification of Event Bus Publish
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.MODEL_RISK_SCORE


@pytest.mark.asyncio
async def test_model_risk_scoring_missing_metrics() -> None:
    """Verify that the scorer fails and emits error for missing metrics."""
    bus = AsyncMock()
    scorer = ModelRiskScorer(bus)

    # Insufficient metrics
    metrics = {"volatility": 0.20}  # Drawdown and Stability missing

    event = await scorer.compute_risk_score(MODEL_ID, metrics)

    assert event is None
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.RISK_SCORE_ERROR
    assert bus.publish.call_args[0][0].payload.error_type == "MISSING_METRICS"


@pytest.mark.asyncio
async def test_model_risk_scoring_failure() -> None:
    """Verify industrial error handling during risk scoring exceptions."""
    bus = AsyncMock()
    scorer = ModelRiskScorer(bus)

    # Malformed metrics triggering exception
    event = await scorer.compute_risk_score(None, None)  # type: ignore

    assert event is None
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.RISK_SCORE_ERROR
    assert "SYSTEM_FAILURE" in str(bus.publish.call_args)

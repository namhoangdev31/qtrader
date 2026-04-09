from unittest.mock import AsyncMock
import pytest
from qtrader.core.events import EventType
from qtrader.governance.model_risk import ModelRiskScorer

MODEL_ID = "STRATEGY_MOMENTUM_v1"


@pytest.mark.asyncio
async def test_model_risk_scoring_success() -> None:
    bus = AsyncMock()
    scorer = ModelRiskScorer(bus)
    metrics = {"volatility": 0.2, "drawdown": 0.15, "stability": 0.8}
    event = await scorer.compute_risk_score(MODEL_ID, metrics)
    assert event is not None
    assert event.payload.model_id == MODEL_ID
    assert event.payload.risk_score == pytest.approx(-0.02)
    assert event.payload.volatility == 0.2
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.MODEL_RISK_SCORE


@pytest.mark.asyncio
async def test_model_risk_scoring_missing_metrics() -> None:
    bus = AsyncMock()
    scorer = ModelRiskScorer(bus)
    metrics = {"volatility": 0.2}
    event = await scorer.compute_risk_score(MODEL_ID, metrics)
    assert event is None
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.RISK_SCORE_ERROR
    assert bus.publish.call_args[0][0].payload.error_type == "MISSING_METRICS"


@pytest.mark.asyncio
async def test_model_risk_scoring_failure() -> None:
    bus = AsyncMock()
    scorer = ModelRiskScorer(bus)
    event = await scorer.compute_risk_score(None, None)
    assert event is None
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.RISK_SCORE_ERROR
    assert "SYSTEM_FAILURE" in str(bus.publish.call_args)

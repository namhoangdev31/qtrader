from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import UUID
from qtrader.core.events import (
    ModelRiskScoreEvent,
    ModelRiskScorePayload,
    RiskScoreErrorEvent,
    RiskScoreErrorPayload,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus


class ModelRiskScorer:
    def __init__(
        self, event_bus: EventBus, w_vol: float = 0.4, w_dd: float = 0.4, w_stability: float = 0.2
    ) -> None:
        self._event_bus = event_bus
        self._w_vol = w_vol
        self._w_dd = w_dd
        self._w_stability = w_stability
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

    async def compute_risk_score(
        self, model_id: str, metrics: dict[str, float]
    ) -> ModelRiskScoreEvent | None:
        try:
            if metrics is None:
                raise ValueError("Metrics dictionary is NULL")
            vol = metrics.get("volatility")
            dd = metrics.get("drawdown")
            stability = metrics.get("stability")
            if vol is None or dd is None or stability is None:
                await self._emit_error(
                    str(model_id),
                    "MISSING_METRICS",
                    "Required risk metrics (vol, dd, stability) are missing.",
                )
                return None
            score = self._w_vol * vol + self._w_dd * dd - self._w_stability * stability
            event = ModelRiskScoreEvent(
                trace_id=self._system_trace,
                source="ModelRiskScorer",
                payload=ModelRiskScorePayload(
                    model_id=str(model_id),
                    risk_score=float(score),
                    volatility=float(vol),
                    drawdown=float(dd),
                    stability=float(stability),
                ),
            )
            await self._event_bus.publish(event)
            logger.info(f"MODEL_RISK_SCORED | {model_id} | Score: {score:.4f}")
            return event
        except Exception as e:
            logger.error(f"RISK_SCORING_FAILURE | {model_id} | {e!s}")
            try:
                await self._emit_error(str(model_id), "SYSTEM_FAILURE", str(e))
            except Exception as nested_e:
                logger.error(f"RISK_SCORING_CRITICAL_FAILURE | {nested_e!s}")
            return None

    async def _emit_error(self, model_id: str, err_type: str, details: str) -> None:
        error_event = RiskScoreErrorEvent(
            trace_id=self._system_trace,
            source="ModelRiskScorer",
            payload=RiskScoreErrorPayload(model_id=model_id, error_type=err_type, details=details),
        )
        await self._event_bus.publish(error_event)

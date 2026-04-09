from __future__ import annotations
import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from qtrader.ml.chronos_adapter import ChronosForecastAdapter
from qtrader.ml.ollama_adapter import OllamaDecisionAdapter
from qtrader.ml.ollama_forecast_adapter import OllamaForecastAdapter
from qtrader.ml.ollama_risk_adapter import OllamaRiskAdapter
from qtrader.ml.types import DecisionAction, TradingDecision
from qtrader.ml.vector_store import memory_store

logger = logging.getLogger("qtrader.ml.atomic_trio")


@dataclass(slots=True, frozen=True)
class PipelineConfig:
    forecast_model_id: str = "llama3.2:1b"
    risk_model_id: str = "qwen3.5:2b"
    decision_model_id: str = "llama3.2:1b"
    backend_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434")
    )


@dataclass(slots=True)
class PipelineResult:
    decision: Any
    forecast_results: dict[str, Any] | None = None
    risk_results: dict[str, Any] | None = None
    chronos_forecast: dict[str, Any] | None = None
    tabpfn_risk: dict[str, Any] | None = None
    pipeline_latency_ms: float = 0.0
    forecast_latency_ms: float = 0.0
    risk_latency_ms: float = 0.0
    decision_latency_ms: float = 0.0
    model_info: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_dict()
            if hasattr(self.decision, "to_dict")
            else str(self.decision),
            "forecast_results": self.forecast_results,
            "risk_results": self.risk_results,
            "pipeline_latency_ms": round(self.pipeline_latency_ms, 2),
            "forecast_latency_ms": round(self.forecast_latency_ms, 2),
            "risk_latency_ms": round(self.risk_latency_ms, 2),
            "decision_latency_ms": round(self.decision_latency_ms, 2),
            "model_info": self.model_info,
        }


class AtomicTrioPipeline:
    def __init__(
        self,
        config: PipelineConfig | None = None,
        forecast_model_id: str | None = None,
        risk_model_id: str | None = None,
        decision_model_id: str | None = None,
    ) -> None:
        if config:
            self.config = config
        else:
            self.config = PipelineConfig(
                forecast_model_id=forecast_model_id or "llama3.2:1b",
                risk_model_id=risk_model_id or "qwen3.5:2b",
                decision_model_id=decision_model_id or "llama3.2:1b",
            )
        self._forecast_engine: ChronosForecastAdapter | None = None
        self._risk_engine: OllamaRiskAdapter | None = None
        self._decision_engine: OllamaDecisionAdapter | None = None
        self._is_initialized = False
        self._run_count: int = 0
        self._last_result: PipelineResult | None = None

    def _initialize(self) -> None:
        if self._is_initialized:
            return
        logger.info("[ATOMIC_TRIO] Initializing Unified AI Pipeline...")
        ollama_url = self.config.backend_url
        logger.info(f"[ATOMIC_TRIO] Using Unified Ollama Backend at {ollama_url}")
        if ":" in self.config.forecast_model_id:
            logger.info(
                f"[ATOMIC_TRIO] Using Ollama Forcast Adapter for {self.config.forecast_model_id}"
            )
            self._forecast_engine = OllamaForecastAdapter(
                model_id=self.config.forecast_model_id, base_url=ollama_url
            )
        else:
            logger.info(
                f"[ATOMIC_TRIO] Using Specialized Chronos Adapter for {self.config.forecast_model_id}"
            )
            self._forecast_engine = ChronosForecastAdapter(model_id=self.config.forecast_model_id)
        self._risk_engine = OllamaRiskAdapter(
            model_id=self.config.risk_model_id, base_url=ollama_url
        )
        self._decision_engine = OllamaDecisionAdapter(
            model_id=self.config.decision_model_id, base_url=ollama_url
        )
        self._is_initialized = True
        logger.info("[ATOMIC_TRIO] Pipeline initialization complete")

    async def run(
        self,
        historical_prices: list[float] | None = None,
        market_features: dict[str, float] | None = None,
        market_context: dict[str, Any] | None = None,
        system_state: dict[str, Any] | None = None,
        prediction_length: int = 10,
    ) -> PipelineResult:
        self._initialize()
        self._run_count += 1
        pipeline_start = time.time()
        forecast_results = None
        forecast_latency = 0.0
        risk_results = None
        risk_latency = 0.0

        async def run_forecast():
            nonlocal forecast_results, forecast_latency
            if (
                historical_prices
                and len(historical_prices) > 0
                and (self._forecast_engine is not None)
            ):
                try:
                    t0 = time.time()
                    if hasattr(self._forecast_engine, "predict") and asyncio.iscoroutinefunction(
                        self._forecast_engine.predict
                    ):
                        forecast_res = await self._forecast_engine.predict(
                            historical_prices=historical_prices, prediction_length=prediction_length
                        )
                    else:
                        forecast_res = self._forecast_engine.predict(
                            historical_prices=historical_prices, prediction_length=prediction_length
                        )
                    forecast_results = forecast_res.to_dict()
                    forecast_latency = (time.time() - t0) * 1000
                except Exception as e:
                    logger.warning(f"[ATOMIC_TRIO] Forecast stage failed: {e}")

        async def run_risk():
            nonlocal risk_results, risk_latency
            if market_features and self._risk_engine is not None:
                try:
                    t0 = time.time()
                    risk_res = await self._risk_engine.classify(features=market_features)
                    risk_results = risk_res.to_dict()
                    risk_latency = (time.time() - t0) * 1000
                except Exception as e:
                    logger.warning(f"[ATOMIC_TRIO] Risk validation stage failed: {e}")

        await asyncio.gather(run_forecast(), run_risk())
        decision_latency = 0.0
        decision = None
        if self._decision_engine is not None:
            try:
                t0 = time.time()
                m_vector = [
                    float(market_context.get("price_change", 0.0)) if market_context else 0.0,
                    float(market_context.get("volatility", 0.0)) if market_context else 0.0,
                    float(risk_results.get("risk_score", 0.5)) if risk_results else 0.5,
                    float(self._run_count % 100) / 100.0,
                ]
                from qtrader.ml.embedding_worker import embedding_manager

                rag_context = memory_store.retrieve_similar(
                    market_vector=m_vector,
                    semantic_embedding=embedding_manager.current_sentiment_vector,
                    top_k=3,
                )
                decision = await self._decision_engine.decide(
                    chronos_forecast=forecast_results,
                    tabpfn_risk=risk_results,
                    market_context=market_context,
                    system_state=system_state,
                    rag_context=rag_context,
                )
                decision_latency = (time.time() - t0) * 1000
            except Exception as e:
                logger.error(f"[ATOMIC_TRIO] Decision engine failed: {e}")
                decision = self._create_safe_hold_decision(f"Inference critical failure: {e}")
        else:
            decision = self._create_safe_hold_decision("Decision engine not initialized")
        pipeline_latency = (time.time() - pipeline_start) * 1000
        result = PipelineResult(
            decision=decision,
            forecast_results=forecast_results,
            risk_results=risk_results,
            chronos_forecast=forecast_results,
            tabpfn_risk=risk_results,
            pipeline_latency_ms=pipeline_latency,
            forecast_latency_ms=forecast_latency,
            risk_latency_ms=risk_latency,
            decision_latency_ms=decision_latency,
            model_info={
                "forecast": self._forecast_engine.get_model_info() if self._forecast_engine else {},
                "risk": self._risk_engine.get_model_info() if self._risk_engine else {},
                "decision": self._decision_engine.get_model_info() if self._decision_engine else {},
            },
        )
        self._last_result = result
        return result

    def _create_safe_hold_decision(self, reason: str) -> TradingDecision:
        return TradingDecision(
            action=DecisionAction.HOLD,
            confidence=0.0,
            reasoning=reason,
            risk_adjustment=1.0,
            position_size_multiplier=0.0,
            stop_loss_pct=2.0,
            take_profit_pct=5.0,
            time_horizon="short",
            explanation="Safe default due to system error",
            inference_time_ms=0.0,
        )

    def get_trace(self) -> dict[str, Any]:
        if not self._last_result:
            return {}
        res = self._last_result.to_dict()
        res["run_count"] = self._run_count
        return res


app = FastAPI(title="QTrader ML Engine", version="1.0.0")
pipeline = AtomicTrioPipeline()


class PredictRequest(BaseModel):
    historical_prices: list[float] | None = None
    market_features: dict[str, float] | None = None
    market_context: dict[str, Any] | None = None
    system_state: dict[str, Any] | None = None
    prediction_length: int = 10


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "ML_ENGINE"}


@app.get("/info")
async def get_info() -> dict[str, Any]:
    return {
        "run_count": pipeline._run_count,
        "is_initialized": pipeline._is_initialized,
        "config": {
            "forecast": pipeline.config.forecast_model_id,
            "risk": pipeline.config.risk_model_id,
            "decision": pipeline.config.decision_model_id,
        },
    }


@app.post("/predict")
async def predict(req: PredictRequest) -> dict[str, Any]:
    try:
        result = await pipeline.run(
            historical_prices=req.historical_prices,
            market_features=req.market_features,
            market_context=req.market_context,
            system_state=req.system_state,
            prediction_length=req.prediction_length,
        )
        return result.to_dict()
    except Exception as e:
        logger.error(f"[SERVER] Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)

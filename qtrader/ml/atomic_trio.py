"""Atomic Trio ML Pipeline — Mac M4 Optimized.

Kết hợp bộ ba nguyên tử (Chronos-2, TabPFN 2.5, Phi-2) thành một pipeline thống nhất:

1. Chronos-2 → Dự báo chuỗi thời gian (Nhà tiên tri)
2. TabPFN 2.5 → Phân loại rủi ro (Người thẩm định)
3. Phi-2 → Ra quyết định (Người điều phối)

Pipeline được tối ưu cho Mac M4:
- Chronos-2: MLX backend (GPU/Neural Engine)
- TabPFN 2.5: CPU cores (không cần GPU)
- Phi-2: MLX backend (GPU/Neural Engine)

Usage:
    from qtrader.ml.atomic_trio import AtomicTrioPipeline

    pipeline = AtomicTrioPipeline(
        chronos_size="small",
        tabpfn_device="cpu",
        phi2_backend="auto",
    )

    decision = pipeline.run(
        historical_prices=[100.0, 101.0, ...],
        market_features={"rsi": 65, "volatility": 0.02, ...},
        market_context={"spread_bps": 5, "volume_ratio": 1.5},
        system_state={"kill_switch_active": False, "current_drawdown": 0.05},
    )
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from qtrader.ml.chronos_adapter import ChronosForecastAdapter
from qtrader.ml.ollama_adapter import OllamaDecisionAdapter
from qtrader.ml.ollama_risk_adapter import OllamaRiskAdapter
from qtrader.ml.types import DecisionAction, TradingDecision
from qtrader.ml.vector_store import memory_store

logger = logging.getLogger("qtrader.ml.atomic_trio")


@dataclass(slots=True, frozen=True)
class PipelineConfig:
    """Configuration for the Atomic Trio pipeline."""

    chronos_model_id: str = "amazon/chronos-2"
    chronos_backend: str = "auto"
    tabpfn_model_id: str = "xgboost"
    tabpfn_device: str = "cpu"
    tabpfn_n_estimators: int = 4
    phi2_model_id: str = "mlx-community/phi-2"
    phi2_backend: str = "auto"
    phi2_use_rule_based_fallback: bool = True


@dataclass(slots=True)
class PipelineResult:
    """Complete output of the Atomic Trio pipeline."""

    decision: Any  # TradingDecision
    chronos_forecast: dict[str, Any] | None = None
    tabpfn_risk: dict[str, Any] | None = None
    pipeline_latency_ms: float = 0.0
    chronos_latency_ms: float = 0.0
    tabpfn_latency_ms: float = 0.0
    phi2_latency_ms: float = 0.0
    model_info: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_dict()
            if hasattr(self.decision, "to_dict")
            else str(self.decision),
            "chronos_forecast": self.chronos_forecast,
            "tabpfn_risk": self.tabpfn_risk,
            "pipeline_latency_ms": round(self.pipeline_latency_ms, 2),
            "chronos_latency_ms": round(self.chronos_latency_ms, 2),
            "tabpfn_latency_ms": round(self.tabpfn_latency_ms, 2),
            "phi2_latency_ms": round(self.phi2_latency_ms, 2),
            "model_info": self.model_info,
        }


class AtomicTrioPipeline:
    """Atomic Trio ML Pipeline.

    Orchestrates Chronos-2, TabPFN 2.5, and Phi-2 into a unified pipeline
    optimized for Mac M4 architecture.

    Pipeline stages:
    1. Chronos-2: Time series forecasting → price prediction + trend
    2. TabPFN 2.5: Tabular risk classification → SAFE/WARNING/DANGER
    3. Phi-2: Decision orchestration → BUY/SELL/HOLD/HEDGE

    Latency targets (Mac M4):
    - Chronos-2 (small): < 50ms
    - TabPFN 2.5: < 10ms
    - Phi-2 (rule-based fallback): < 1ms
    - Total pipeline: < 100ms
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
    ) -> None:
        cfg = config or PipelineConfig()
        self.config = cfg

        # Lazy-loaded components
        self._chronos: ChronosForecastAdapter | None = None
        self._tabpfn: OllamaRiskAdapter | None = None
        self._phi2: OllamaDecisionAdapter | None = None
        self._is_initialized = False
        self._run_count: int = 0
        self._last_result: PipelineResult | None = None

    def _initialize(self) -> None:
        """Lazy initialize all three models."""
        if self._is_initialized:
            return

        logger.info("[ATOMIC_TRIO] Initializing pipeline...")

        self._chronos = ChronosForecastAdapter(
            model_id=self.config.chronos_model_id,
            device=self.config.chronos_backend,
        )

        ollama_url = os.getenv("OLLAMA_URL")
        if not ollama_url:
            raise RuntimeError(
                "[ATOMIC_TRIO] OLLAMA_URL not set. Unified Ollama backend is mandatory. "
                "Ensure 'qt-ollama' service is running."
            )

        logger.info(f"[ATOMIC_TRIO] Using Unified Ollama Backend at {ollama_url}")
        # Stage 2: Ollama Risk
        self._tabpfn = OllamaRiskAdapter(
            model_id=os.getenv("OLLAMA_RISK_MODEL", "qwen2:1.5b"),
            base_url=ollama_url,
        )
        # Stage 3: Ollama Decision
        self._phi2 = OllamaDecisionAdapter(
            model_id=os.getenv("OLLAMA_MODEL", "phi3:mini"),
            base_url=ollama_url,
        )

        self._is_initialized = True
        logger.info("[ATOMIC_TRIO] Pipeline initialized")

    async def run(
        self,
        historical_prices: list[float] | None = None,
        market_features: dict[str, float] | None = None,
        market_context: dict[str, Any] | None = None,
        system_state: dict[str, Any] | None = None,
        prediction_length: int = 10,
    ) -> PipelineResult:
        """Run the complete Atomic Trio pipeline.

        Args:
            historical_prices: Historical OHLCV close prices for Chronos-2.
            market_features: Feature dict for TabPFN (rsi, volatility, etc.).
            market_context: Current market conditions for Phi-2.
            system_state: Current system state for Phi-2.
            prediction_length: Number of future steps for Chronos-2.

        Returns:
            PipelineResult with decision, forecasts, and latency breakdown.
        """
        self._initialize()
        self._run_count += 1
        pipeline_start = time.time()

        # Stage 1: Chronos-2 Forecast
        chronos_forecast = None
        chronos_latency = 0.0
        if historical_prices and len(historical_prices) > 0 and self._chronos is not None:
            try:
                t0 = time.time()
                forecast_result = self._chronos.predict(
                    historical_prices=historical_prices,
                    prediction_length=prediction_length,
                )
                chronos_forecast = forecast_result.to_dict()
                chronos_latency = (time.time() - t0) * 1000
            except Exception as e:
                logger.warning(f"[ATOMIC_TRIO] Chronos-2 failed: {e}")

        # Stage 2: Ollama Risk Classification
        tabpfn_risk = None
        tabpfn_latency = 0.0
        if market_features and self._tabpfn is not None:
            try:
                t0 = time.time()
                # Unified async call across all adapters
                risk_result = await self._tabpfn.classify(features=market_features)
                tabpfn_risk = risk_result.to_dict()
                tabpfn_latency = (time.time() - t0) * 1000
            except Exception as e:
                logger.warning(f"[ATOMIC_TRIO] Risk ML stage failed: {e}")

        # Stage 3: Decision Engine (Phi-2 or Ollama) with RAG
        phi2_latency = 0.0
        if self._phi2 is not None:
            try:
                t0 = time.time()
                
                # RAG RETRIEVAL: Search for Elite Exemplars
                # Construct market vector: [price_change, vol, risk_score, confidence_ema]
                m_vector = [
                    float(market_context.get("price_change", 0.0)) if market_context else 0.0,
                    float(market_context.get("volatility", 0.0)) if market_context else 0.0,
                    float(tabpfn_risk.get("risk_score", 0.5)) if tabpfn_risk else 0.5,
                    float(self._run_count % 100) / 100.0 # Placeholder for time-of-day/seasonality
                ]
                
                # Fetch the latest semantic sentiment context (Zero Latency)
                from qtrader.ml.embedding_worker import embedding_manager
                semantic_context = embedding_manager.current_sentiment_vector
                
                rag_context = memory_store.retrieve_similar(
                    market_vector=m_vector, 
                    semantic_embedding=semantic_context,
                    top_k=3
                )
                
                decision = await self._phi2.decide(
                    chronos_forecast=chronos_forecast,
                    tabpfn_risk=tabpfn_risk,
                    market_context=market_context,
                    system_state=system_state,
                    rag_context=rag_context
                )
                
                # Apply Dynamic Config Overrides directly (Direct Write Authority)
                if hasattr(decision, "metadata") and "config_overrides" in decision.metadata:
                    from qtrader.core.dynamic_config import config_manager
                    overrides = decision.metadata["config_overrides"]
                    for k, v in overrides.items():
                        config_manager.set_override(k, v)
                        logger.info(f"[AI_CONTROL] Applied Dynamic Override: {k}={v}")

                phi2_latency = (time.time() - t0) * 1000
            except Exception as e:
                logger.error(f"[ATOMIC_TRIO] Phi-2 decision failed: {e}")
                # Create a safe HOLD decision
                decision = TradingDecision(
                    action=DecisionAction.HOLD,
                    confidence=0.0,
                    reasoning=f"Inference critical failure: {e}",
                    risk_adjustment=1.0,
                    position_size_multiplier=0.0,
                    stop_loss_pct=2.0,
                    take_profit_pct=5.0,
                    time_horizon="short",
                    explanation="Safe default due to ML error",
                    inference_time_ms=0.0,
                )
        else:
            decision = TradingDecision(
                action=DecisionAction.HOLD,
                confidence=0.0,
                reasoning="Decision engine not initialized",
                risk_adjustment=1.0,
                position_size_multiplier=0.0,
                stop_loss_pct=2.0,
                take_profit_pct=5.0,
                time_horizon="short",
                explanation="Safe default due to missing engine",
                inference_time_ms=0.0,
            )

        pipeline_latency = (time.time() - pipeline_start) * 1000

        result = PipelineResult(
            decision=decision,
            chronos_forecast=chronos_forecast,
            tabpfn_risk=tabpfn_risk,
            pipeline_latency_ms=pipeline_latency,
            chronos_latency_ms=chronos_latency,
            tabpfn_latency_ms=tabpfn_latency,
            phi2_latency_ms=phi2_latency,
            model_info={
                "chronos": self._chronos.get_model_info() if self._chronos else {},
                "tabpfn": self._tabpfn.get_model_info() if self._tabpfn else {},
                "phi2": self._phi2.get_model_info() if self._phi2 else {},
            },
        )
        self._last_result = result
        return result

    def get_trace(self) -> dict[str, Any]:
        """Produce forensic trace of ML pipeline."""
        if not self._last_result:
            return {}
        res = self._last_result.to_dict()
        res["run_count"] = self._run_count
        return res

        logger.info(
            f"[ATOMIC_TRIO] Pipeline complete | "
            f"Action={decision.action.value} | "
            f"Confidence={decision.confidence:.0%} | "
            f"Latency={pipeline_latency:.1f}ms | "
            f"Run #{self._run_count}"
        )

        return result

    def get_pipeline_info(self) -> dict[str, Any]:
        """Get pipeline information."""
        if not self._is_initialized:
            self._initialize()

        return {
            "chronos": self._chronos.get_model_info() if self._chronos else {},
            "tabpfn": self._tabpfn.get_model_info() if self._tabpfn else {},
            "phi2": self._phi2.get_model_info() if self._phi2 else {},
            "run_count": self._run_count,
            "estimated_total_memory_mb": (
                (
                    self._chronos.get_model_info().get("estimated_memory_mb", 0)
                    if self._chronos
                    else 0
                )
                + (
                    self._tabpfn.get_model_info().get("estimated_memory_mb", 0)
                    if self._tabpfn
                    else 0
                )
                + (self._phi2.get_model_info().get("estimated_memory_mb", 0) if self._phi2 else 0)
            ),
        }


if __name__ == "__main__":
    # Internal service for ML Engine
    import os

    import uvicorn
    from fastapi import FastAPI
    from pydantic import BaseModel

    app = FastAPI(title="QTrader ML Engine — Atomic Trio Service")

    # Shared pipeline instance
    config = PipelineConfig(
        chronos_model_id=os.getenv("CHRONOS_MODEL_ID", "amazon/chronos-2"),
        tabpfn_model_id=os.getenv("TABPFN_MODEL_ID", "Prior-Labs/tabpfn_2_5"),
        phi2_model_id=os.getenv("PHI2_MODEL_ID", "mlx-community/phi-2"),
    )
    pipeline = AtomicTrioPipeline(config=config)

    class PredictionRequest(BaseModel):
        historical_prices: list[float] | None = None
        market_features: dict[str, float] | None = None
        market_context: dict[str, Any] | None = None
        system_state: dict[str, Any] | None = None
        prediction_length: int = 10

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "ML_ENGINE"}

    @app.get("/info")
    async def info() -> dict[str, Any]:
        return pipeline.get_pipeline_info()

    @app.post("/predict")
    async def predict(req: PredictionRequest) -> dict[str, Any]:
        result = await pipeline.run(
            historical_prices=req.historical_prices,
            market_features=req.market_features,
            market_context=req.market_context,
            system_state=req.system_state,
            prediction_length=req.prediction_length,
        )
        return result.to_dict()

    # Start Uvicorn
    # S104: Binding to all interfaces for Docker accessibility
    uvicorn.run(app, host="0.0.0.0", port=8001)  # noqa: S104

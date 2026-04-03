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
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("qtrader.ml.atomic_trio")


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
        chronos_model_id: str = "amazon/chronos-2",
        chronos_backend: str = "auto",
        tabpfn_model_id: str = "Prior-Labs/tabpfn_2_5",
        tabpfn_device: str = "cpu",
        tabpfn_n_estimators: int = 4,
        phi2_model_id: str = "microsoft/phi-2",
        phi2_backend: str = "auto",
        phi2_use_rule_based_fallback: bool = True,
    ) -> None:
        self.chronos_model_id = chronos_model_id
        self.chronos_backend = chronos_backend
        self.tabpfn_model_id = tabpfn_model_id
        self.tabpfn_device = tabpfn_device
        self.tabpfn_n_estimators = tabpfn_n_estimators
        self.phi2_model_id = phi2_model_id
        self.phi2_backend = phi2_backend
        self.phi2_use_rule_based_fallback = phi2_use_rule_based_fallback

        # Lazy-loaded components
        self._chronos: Any = None
        self._tabpfn: Any = None
        self._phi2: Any = None
        self._is_initialized = False
        self._run_count: int = 0

    def _initialize(self) -> None:
        """Lazy initialize all three models."""
        if self._is_initialized:
            return

        from qtrader.ml.chronos_adapter import ChronosForecastAdapter
        from qtrader.ml.phi2_controller import Phi2DecisionController
        from qtrader.ml.tabpfn_adapter import TabPFNRiskAdapter

        logger.info("[ATOMIC_TRIO] Initializing pipeline...")

        self._chronos = ChronosForecastAdapter(
            model_id=self.chronos_model_id,
            device=self.chronos_backend,
        )

        self._tabpfn = TabPFNRiskAdapter(
            model_id=self.tabpfn_model_id,
            device=self.tabpfn_device,
            n_estimators=self.tabpfn_n_estimators,
        )

        self._phi2 = Phi2DecisionController(
            model_id=self.phi2_model_id,
            backend=self.phi2_backend,
            use_rule_based_fallback=self.phi2_use_rule_based_fallback,
        )

        self._is_initialized = True
        logger.info("[ATOMIC_TRIO] Pipeline initialized")

    def run(
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
        if historical_prices and len(historical_prices) > 0:
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

        # Stage 2: TabPFN Risk Classification
        tabpfn_risk = None
        tabpfn_latency = 0.0
        if market_features:
            try:
                t0 = time.time()
                risk_result = self._tabpfn.classify(features=market_features)
                tabpfn_risk = risk_result.to_dict()
                tabpfn_latency = (time.time() - t0) * 1000
            except Exception as e:
                logger.warning(f"[ATOMIC_TRIO] TabPFN failed: {e}")

        # Stage 3: Phi-2 Decision
        phi2_latency = 0.0
        try:
            t0 = time.time()
            decision = self._phi2.decide(
                chronos_forecast=chronos_forecast,
                tabpfn_risk=tabpfn_risk,
                market_context=market_context,
                system_state=system_state,
            )
            phi2_latency = (time.time() - t0) * 1000
        except Exception as e:
            logger.error(f"[ATOMIC_TRIO] Phi-2 decision failed: {e}")
            # Create a safe HOLD decision
            from qtrader.ml.phi2_controller import DecisionAction, TradingDecision

            decision = TradingDecision(
                action=DecisionAction.HOLD,
                confidence=0.0,
                reasoning=f"Pipeline error: {e}",
                risk_adjustment=1.0,
                position_size_multiplier=0.0,
                stop_loss_pct=1.0,
                take_profit_pct=2.0,
                time_horizon="short",
                explanation="Decision defaulted to HOLD due to pipeline error",
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
                "chronos": self._chronos.get_model_info(),
                "tabpfn": self._tabpfn.get_model_info(),
                "phi2": self._phi2.get_model_info(),
            },
        )

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
            "chronos": self._chronos.get_model_info(),
            "tabpfn": self._tabpfn.get_model_info(),
            "phi2": self._phi2.get_model_info(),
            "run_count": self._run_count,
            "estimated_total_memory_mb": (
                self._chronos.get_model_info().get("estimated_memory_mb", 0)
                + self._tabpfn.get_model_info().get("estimated_memory_mb", 0)
                + self._phi2.get_model_info().get("estimated_memory_mb", 0)
            ),
        }

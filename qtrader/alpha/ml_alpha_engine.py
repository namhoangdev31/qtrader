"""HF ML Alpha Engine — Integrates Atomic Trio into AlphaEngine.

Combines Chronos-2, TabPFN 2.5, and Phi-2 with traditional alpha signals
to produce ML-enhanced trading signals.

Pipeline:
1. Chronos-2 → Price forecast → trend alpha signal
2. TabPFN 2.5 → Risk classification → risk-adjusted signal
3. Phi-2 → Decision orchestration → final signal with explainability
4. Traditional alphas → Combined with ML signals
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from qtrader.alpha.base import AlphaBase
from qtrader.core.types import AlphaOutput, MarketData

logger = logging.getLogger("qtrader.alpha.ml_alpha_engine")


class MLAlphaEngine(AlphaBase):
    """ML-enhanced Alpha Engine using the Atomic Trio.

    Integrates:
    - Chronos-2 (amazon/chronos-2) for price forecasting
    - TabPFN 2.5 (Prior-Labs/tabpfn_2_5) for risk classification
    - Phi-2 (microsoft/phi-2) for decision orchestration

    Produces alpha signals that combine ML predictions with
    traditional technical indicators.
    """

    def __init__(
        self,
        name: str = "ml_alpha_engine",
        ml_weight: float = 0.6,
        traditional_weight: float = 0.4,
        chronos_model_id: str = "amazon/chronos-2",
        tabpfn_model_id: str = "Prior-Labs/tabpfn_2_5",
        phi2_model_id: str = "microsoft/phi-2",
        hf_token: str | None = None,
    ) -> None:
        super().__init__(name)
        self.ml_weight = ml_weight
        self.traditional_weight = traditional_weight
        self.chronos_model_id = chronos_model_id
        self.tabpfn_model_id = tabpfn_model_id
        self.phi2_model_id = phi2_model_id
        self.hf_token = hf_token

        # Lazy-loaded components
        self._chronos: Any = None
        self._tabpfn: Any = None
        self._phi2: Any = None
        self._atomic_pipeline: Any = None
        self._is_initialized = False

    def _initialize(self) -> None:
        """Lazy initialize ML components."""
        if self._is_initialized:
            return

        from qtrader.ml.atomic_trio import AtomicTrioPipeline

        self._atomic_pipeline = AtomicTrioPipeline(
            chronos_size="small",
            chronos_backend="auto",
            tabpfn_device="cpu",
            tabpfn_n_estimators=4,
            phi2_backend="auto",
            phi2_use_rule_based_fallback=True,
        )

        self._is_initialized = True
        logger.info("[ML_ALPHA] Atomic Trio pipeline initialized")

    async def generate(self, market_data: MarketData) -> AlphaOutput:
        """Generate ML-enhanced alpha signal.

        Args:
            market_data: Current market data with prices, volume, indicators.

        Returns:
            AlphaOutput with combined ML + traditional signal.
        """
        self._initialize()

        # Extract features for ML models
        historical_prices = market_data.metadata.get("historical_prices", [])
        market_features = market_data.metadata.get("market_features", {})
        market_context = market_data.metadata.get("market_context", {})
        system_state = market_data.metadata.get("system_state", {})

        # Run Atomic Trio pipeline
        result = self._atomic_pipeline.run(
            historical_prices=historical_prices if historical_prices else None,
            market_features=market_features if market_features else None,
            market_context=market_context if market_context else None,
            system_state=system_state if system_state else None,
            prediction_length=24,
        )

        # Convert ML decision to alpha value
        decision = result.decision
        action_map = {
            "BUY": 1.0,
            "SELL": -1.0,
            "HOLD": 0.0,
            "HEDGE": 0.3,
            "CLOSE_ALL": -1.0,
            "REDUCE_POSITION": -0.5,
        }
        ml_signal = action_map.get(decision.action.value, 0.0)
        ml_confidence = decision.confidence

        # Traditional alpha (from market data)
        traditional_signal = self._compute_traditional_alpha(market_data)

        # Combined signal
        combined_signal = (
            self.ml_weight * ml_signal * ml_confidence
            + self.traditional_weight * traditional_signal
        )

        # Clamp to [-1, 1]
        combined_signal = max(-1.0, min(1.0, combined_signal))

        return AlphaOutput(
            symbol=market_data.symbol,
            timestamp=market_data.timestamp,
            alpha_values={
                "ml_signal": ml_signal,
                "ml_confidence": ml_confidence,
                "traditional_signal": traditional_signal,
                "combined_signal": combined_signal,
                "chronos_trend": result.chronos_forecast.get("trend_direction", "FLAT")
                if result.chronos_forecast
                else "UNKNOWN",
                "tabpfn_risk": result.tabpfn_risk.get("class_label", "UNKNOWN")
                if result.tabpfn_risk
                else "UNKNOWN",
                "phi2_action": decision.action.value,
            },
            metadata={
                "pipeline_latency_ms": result.pipeline_latency_ms,
                "explanation": decision.explanation,
                "position_size_multiplier": decision.position_size_multiplier,
                "stop_loss_pct": decision.stop_loss_pct,
                "take_profit_pct": decision.take_profit_pct,
            },
        )

    def _compute_traditional_alpha(self, market_data: MarketData) -> float:
        """Compute traditional alpha signal from market data."""
        # Simple momentum-based alpha
        if hasattr(market_data, "close") and market_data.close > 0:
            return 0.0  # Placeholder — use actual indicators

        # Fallback: use metadata indicators
        metadata = market_data.metadata
        rsi = metadata.get("rsi", 50)
        macd = metadata.get("macd", 0)

        # RSI-based signal
        if rsi > 70:
            rsi_signal = -0.5  # Overbought
        elif rsi < 30:
            rsi_signal = 0.5  # Oversold
        else:
            rsi_signal = 0.0

        # MACD-based signal
        macd_signal = max(-1.0, min(1.0, macd / 100.0))

        return (rsi_signal + macd_signal) / 2.0

    def get_model_info(self) -> dict[str, Any]:
        """Get ML model information."""
        if not self._is_initialized:
            self._initialize()

        return {
            "ml_weight": self.ml_weight,
            "traditional_weight": self.traditional_weight,
            "chronos_model": self.chronos_model_id,
            "tabpfn_model": self.tabpfn_model_id,
            "phi2_model": self.phi2_model_id,
            "pipeline_info": self._atomic_pipeline.get_pipeline_info()
            if self._atomic_pipeline
            else {},
        }

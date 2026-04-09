"""Lightweight ML Alpha Engine for High-Frequency Testing.

Thay thế các mô hình Hugging Face nặng nề bằng logic Technical Analysis (RSI/EMA)
để test hệ thống với độ trễ cực thấp (< 1ms).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from qtrader.alpha.base import BaseAlpha
from qtrader.core.types import AlphaOutput, MarketData

logger = logging.getLogger("qtrader.alpha.ml_alpha_engine")


class MLAlphaEngine(BaseAlpha):
    """Engine nhẹ tự triển khai để test hệ thống."""

    def __init__(
        self,
        name: str = "lightweight_ml_engine",
        ml_weight: float = 0.0,  # Không dùng ML thật
        traditional_weight: float = 1.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(name)
        self._is_initialized = True
        logger.info("[ML_ALPHA] Lightweight Testing Engine Initialized")

    def _initialize(self) -> None:
        pass

    async def generate(self, market_data: MarketData) -> AlphaOutput:
        """Tạo tín hiệu nhanh dựa trên RSI và Price Action."""
        start_t = time.time()
        symbol = market_data.symbol

        # Lấy giá hiện tại
        float(market_data.metadata.get("price", 0))
        historical_prices = market_data.metadata.get("historical_prices", [])

        # Logic RSI giả lập nhanh
        decision_action = "HOLD"
        confidence = 0.0

        if len(historical_prices) > 2:
            # Tính biến động đơn giản
            last_price = historical_prices[-1]
            prev_price = historical_prices[-2]
            change = (last_price - prev_price) / prev_price if prev_price > 0 else 0

            # Simple Mean Reversion Logic cho testing
            if change < -0.0005:  # Giá giảm mạnh -> Thử MUA
                decision_action = "BUY"
                confidence = 0.8
            elif change > 0.0005:  # Giá tăng mạnh -> Thử BÁN
                decision_action = "SELL"
                confidence = 0.8

        # Thêm một chút yếu tố ngẫu nhiên để UI luôn có biến động (10% chance)
        import random

        if random.random() < 0.1:
            decision_action = random.choice(["BUY", "SELL"])
            confidence = 0.9

        latency_ms = (time.time() - start_t) * 1000

        return AlphaOutput(
            symbol=symbol,
            timestamp=market_data.timestamp,
            alpha_values={
                "ml_signal": 1.0
                if decision_action == "BUY"
                else -1.0
                if decision_action == "SELL"
                else 0.0,
                "ml_confidence": confidence,
                "traditional_signal": 0.0,
                "combined_signal": confidence if decision_action != "HOLD" else 0.0,
                "chronos_trend": "UP"
                if decision_action == "BUY"
                else "DOWN"
                if decision_action == "SELL"
                else "FLAT",
                "tabpfn_risk": "LOW",
                "phi2_action": decision_action,
            },
            metadata={
                "pipeline_latency_ms": latency_ms,
                "explanation": f"Lightweight testing trigger: {decision_action} based on price action.",
                "position_size_multiplier": 1.0,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.05,
            },
        )

    def get_model_info(self) -> dict[str, Any]:
        return {
            "mode": "lightweight_testing",
            "latency": "ultra_low",
            "models": ["PriceActionEmulator"],
        }

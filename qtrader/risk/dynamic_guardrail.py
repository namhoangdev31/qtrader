"""Dynamic Guardrail Management — Volatility-Adaptive SL/TP.

Calculates stop-loss and take-profit levels based on:
1. ML Forecast Intervals (Chronos-2)
2. ATR (Average True Range) fallback
"""

from __future__ import annotations

import logging
from typing import Any

from qtrader.risk.base import RiskModule

logger = logging.getLogger("qtrader.risk.dynamic")


class DynamicGuardrailManager(RiskModule):
    """Adaptive SL/TP manager using forecast intervals and ATR.

    Philosophy:
        - High Volatility -> Wider Stops (Avoid noise)
        - Low Volatility -> Tighter Stops (Capital efficiency)
    """

    def __init__(
        self,
        atr_multiplier: float = 2.0,
        forecast_multiplier: float = 1.5,
        min_sl_pct: float = 0.005,  # 0.5% floor
        max_sl_pct: float = 0.05,  # 5.0% ceiling
    ) -> None:
        self.atr_multiplier = atr_multiplier
        self.forecast_multiplier = forecast_multiplier
        self.min_sl_pct = min_sl_pct
        self.min_sl_pct = min_sl_pct
        self.max_sl_pct = max_sl_pct
        self.last_result: dict[str, Any] = {}

    def evaluate(self, *args: Any, **kwargs: Any) -> dict[str, float]:
        """Calculate dynamic SL/TP levels.

        Args:
            price: Current market price.
            atr: Current ATR value (fallback).
            forecast_range: (upper_bound - lower_bound) from ML pipeline.
            side: "BUY" or "SELL".
        """
        price = float(kwargs.get("price", 0))
        atr = float(kwargs.get("atr", 0))
        forecast_range = float(kwargs.get("forecast_range", 0))
        side = kwargs.get("side", "BUY")

        if price <= 0:
            return {}

        # 1. Determine the 'Volatility Unit'
        # Priority: Forecast Range (ML) > ATR (Stat)
        if forecast_range > 0:
            vol_unit = (forecast_range / price) * self.forecast_multiplier
            reason = "ML_FORECAST"
        elif atr > 0:
            vol_unit = (atr / price) * self.atr_multiplier
            reason = "ATR_FALLBACK"
        else:
            vol_unit = 0.025  # Global default 2.5%
            reason = "DEFAULT_FIXED"

        # 2. Bound the risk
        sl_pct = max(self.min_sl_pct, min(self.max_sl_pct, vol_unit))

        # 3. Compute levels
        # TP is usually scaled by a Risk/Reward ratio (e.g., 2.0)
        tp_pct = sl_pct * 2.0

        if side == "BUY":
            sl_price = price * (1.0 - sl_pct)
            tp_price = price * (1.0 + tp_pct)
        else:
            sl_price = price * (1.0 + sl_pct)
            tp_price = price * (1.0 - tp_pct)

        res = {
            "sl_price": sl_price,
            "tp_price": tp_price,
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "risk_source": reason,
        }
        self.last_result = res
        return res

    def get_trace(self) -> dict[str, Any]:
        """Produce forensic trace of dynamic risk offsets."""
        return self.last_result

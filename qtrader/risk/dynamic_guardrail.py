from __future__ import annotations
import logging
from typing import Any
from qtrader.risk.base import RiskModule

logger = logging.getLogger("qtrader.risk.dynamic")


class DynamicGuardrailManager(RiskModule):
    def __init__(
        self,
        atr_multiplier: float = 2.0,
        forecast_multiplier: float = 1.5,
        min_sl_pct: float = 0.005,
        max_sl_pct: float = 0.05,
    ) -> None:
        self.atr_multiplier = atr_multiplier
        self.forecast_multiplier = forecast_multiplier
        self.min_sl_pct = min_sl_pct
        self.min_sl_pct = min_sl_pct
        self.max_sl_pct = max_sl_pct
        self.last_result: dict[str, Any] = {}

    def evaluate(self, *args: Any, **kwargs: Any) -> dict[str, float]:
        price = float(kwargs.get("price", 0))
        atr = float(kwargs.get("atr", 0))
        forecast_range = float(kwargs.get("forecast_range", 0))
        side = kwargs.get("side", "BUY")
        if price <= 0:
            return {}
        if forecast_range > 0:
            vol_unit = forecast_range / price * self.forecast_multiplier
            reason = "ML_FORECAST"
        elif atr > 0:
            vol_unit = atr / price * self.atr_multiplier
            reason = "ATR_FALLBACK"
        else:
            vol_unit = 0.025
            reason = "DEFAULT_FIXED"
        sl_pct = max(self.min_sl_pct, min(self.max_sl_pct, vol_unit))
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
        return self.last_result

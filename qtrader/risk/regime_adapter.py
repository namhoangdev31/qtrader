from __future__ import annotations


class RegimeAdapter:
    def __init__(self) -> None:
        self._regime_scales: dict[int, dict[str, float]] = {
            0: {
                "var_threshold_scale": 1.0,
                "max_leverage_scale": 1.0,
                "max_position_size_scale": 1.0,
            },
            1: {
                "var_threshold_scale": 0.7,
                "max_leverage_scale": 0.6,
                "max_position_size_scale": 0.7,
            },
            2: {
                "var_threshold_scale": 0.5,
                "max_leverage_scale": 0.5,
                "max_position_size_scale": 0.5,
            },
        }

    def adjust_limits(
        self,
        regime_id: int,
        base_var_threshold: float,
        base_max_leverage: float,
        base_max_position_size: float,
    ) -> dict[str, float]:
        scales = self._regime_scales.get(regime_id, self._regime_scales[0])
        adjusted_var_threshold = base_var_threshold * scales["var_threshold_scale"]
        adjusted_max_leverage = base_max_leverage * scales["max_leverage_scale"]
        adjusted_max_position_size = base_max_position_size * scales["max_position_size_scale"]
        return {
            "var_threshold": adjusted_var_threshold,
            "max_leverage": adjusted_max_leverage,
            "max_position_size": adjusted_max_position_size,
        }

    def get_regime_description(self, regime_id: int) -> str:
        descriptions = {0: "Low Volatility", 1: "High Volatility", 2: "Crisis"}
        return descriptions.get(regime_id, f"Unknown Regime {regime_id}")

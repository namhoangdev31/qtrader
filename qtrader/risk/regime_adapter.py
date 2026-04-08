"""Regime adapter for dynamically adjusting risk limits based on market regime."""

from __future__ import annotations


class RegimeAdapter:
    """
    Adapter for adjusting risk limits based on market regime.

    Maps regime_id to scaling factors for VaR, leverage, and position limits:
    - Regime 0 (low vol): normal limits (scale = 1.0)
    - Regime 1 (high vol): reduce leverage by 40%, tighten var_threshold by 30%
    - Regime 2 (crisis): halve all limits
    """

    def __init__(self) -> None:
        """Initialize the regime adapter with predefined scaling factors."""
        # Regime -> {var_threshold_scale, max_leverage_scale, max_position_size_scale}
        self._regime_scales: dict[int, dict[str, float]] = {
            0: {  # Low volatility regime
                "var_threshold_scale": 1.0,
                "max_leverage_scale": 1.0,
                "max_position_size_scale": 1.0,
            },
            1: {  # High volatility regime
                "var_threshold_scale": 0.7,  # Tighten by 30%
                "max_leverage_scale": 0.6,  # Reduce by 40%
                "max_position_size_scale": 0.7,  # Reduce by 30%
            },
            2: {  # Crisis regime
                "var_threshold_scale": 0.5,  # Halve
                "max_leverage_scale": 0.5,  # Halve
                "max_position_size_scale": 0.5,  # Halve
            },
        }

    def adjust_limits(
        self,
        regime_id: int,
        base_var_threshold: float,
        base_max_leverage: float,
        base_max_position_size: float,
    ) -> dict[str, float]:
        """
        Adjust risk limits based on the current market regime.

        Args:
            regime_id: Current market regime (0=low vol, 1=high vol, 2=crisis)
            base_var_threshold: Base VaR threshold
            base_max_leverage: Base maximum leverage
            base_max_position_size: Base maximum position size

        Returns:
            Dictionary with adjusted limits:
            {
                "var_threshold": float,
                "max_leverage": float,
                "max_position_size": float
            }
        """
        # Get scaling factors for the regime, default to regime 0 (normal) if unknown
        scales = self._regime_scales.get(regime_id, self._regime_scales[0])

        # Apply scaling factors
        adjusted_var_threshold = base_var_threshold * scales["var_threshold_scale"]
        adjusted_max_leverage = base_max_leverage * scales["max_leverage_scale"]
        adjusted_max_position_size = base_max_position_size * scales["max_position_size_scale"]

        return {
            "var_threshold": adjusted_var_threshold,
            "max_leverage": adjusted_max_leverage,
            "max_position_size": adjusted_max_position_size,
        }

    def get_regime_description(self, regime_id: int) -> str:
        """
        Get human-readable description of a regime.

        Args:
            regime_id: Regime ID

        Returns:
            Description string
        """
        descriptions = {0: "Low Volatility", 1: "High Volatility", 2: "Crisis"}
        return descriptions.get(regime_id, f"Unknown Regime {regime_id}")

from __future__ import annotations

import polars as pl
from typing import Dict, List


class PortfolioAllocator:
    """
    Portfolio allocation risk module.

    Allocates capital to strategies based on risk parity (equal risk contribution) or other methods.

    Args:
        method: Allocation method ('equal_risk', 'inverse_volatility', 'equal_weight').
                Default is 'equal_risk'.
        lookback: Lookback period for estimating volatility and correlations (default 20).
        min_weight: Minimum weight allocated to any strategy (default 0.0).
        max_weight: Maximum weight allocated to any strategy (default 1.0).
    """

    def __init__(
        self,
        method: str = "equal_risk",
        lookback: int = 20,
        min_weight: float = 0.0,
        max_weight: float = 1.0,
    ) -> None:
        if method not in ["equal_risk", "inverse_volatility", "equal_weight"]:
            raise ValueError(f"Unsupported method: {method}")
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        if min_weight < 0 or max_weight > 1 or min_weight > max_weight:
            raise ValueError("min_weight and max_weight must be in [0,1] and min_weight <= max_weight")
        self.method = method
        self.lookback = lookback
        self.min_weight = min_weight
        self.max_weight = max_weight

    def allocate(
        self, strategy_returns: Dict[str, pl.Series]
    ) -> Dict[str, pl.Series]:
        """
        Allocate capital to strategies.

        Args:
            strategy_returns: Dictionary mapping strategy names to their return series.

        Returns:
            Dictionary of allocation weights (same keys as input, weights sum to 1.0).
        """
        if not strategy_returns:
            return {}
        
        # Align all series to the same length by truncating to the shortest
        min_len = min(len(series) for series in strategy_returns.values())
        if min_len == 0:
            # Return zero weights
            return {name: pl.Series(values=[0.0], name=name, dtype=pl.Float64) for name in strategy_returns.keys()}
        
        # Truncate series to min_len
        truncated_returns = {
            name: series.tail(min_len) for name, series in strategy_returns.items()
        }
        
        # Convert to DataFrame for easier computation
        returns_df = pl.DataFrame(truncated_returns)
        
        # Compute weights based on method
        if self.method == "equal_weight":
            weights_dict = self._equal_weight(returns_df)
        elif self.method == "inverse_volatility":
            weights_dict = self._inverse_volatility(returns_df)
        else:  # equal_risk
            weights_dict = self._equal_risk(returns_df)
        
        # Apply min/max weight constraints
        weights_dict = self._apply_constraints(weights_dict)
        
        # Normalize weights to sum to 1.0 (after constraints, may not sum to 1.0)
        weight_sum = sum(weights_dict.values())
        if weight_sum > 0:
            weights_dict = {name: w / weight_sum for name, w in weights_dict.items()}
        else:
            # If all weights are zero, fall back to equal weight
            n = len(weights_dict)
            equal_weight = 1.0 / n if n > 0 else 0.0
            weights_dict = {name: equal_weight for name in weights_dict.keys()}
        
        # Return as dictionary of series (each weight series is constant over time)
        result = {}
        for strat_name, weight in weights_dict.items():
            # Create a series of constant weight for each time point
            result[strat_name] = pl.Series(values=[weight] * min_len, name=strat_name, dtype=pl.Float64)
        
        return result

    def _equal_weight(self, returns_df: pl.DataFrame) -> Dict[str, float]:
        """Equal weight allocation: 1/n for each strategy."""
        n = len(returns_df.columns)
        weight = 1.0 / n if n > 0 else 0.0
        return {col: weight for col in returns_df.columns}

    def _inverse_volatility(self, returns_df: pl.DataFrame) -> Dict[str, float]:
        """Inverse volatility weighting."""
        # Compute volatility (std) of each strategy
        inv_vol_list = []
        for col in returns_df.columns:
            vol = returns_df[col].std()
            if vol == 0.0:
                inv_vol_list.append(0.0)
            else:
                inv_vol_list.append(1.0 / vol)
        total_inv_vol = sum(inv_vol_list)
        if total_inv_vol == 0.0:
            # Fall back to equal weight
            n = len(returns_df.columns)
            weight = 1.0 / n if n > 0 else 0.0
            return {col: weight for col in returns_df.columns}
        weights = {col: inv_vol_list[i] / total_inv_vol for i, col in enumerate(returns_df.columns)}
        return weights

    def _equal_risk(self, returns_df: pl.DataFrame) -> Dict[str, float]:
        """
        Equal risk contribution (risk parity) allocation.
        This is an approximation using the inverse volatility method for simplicity.
        A more accurate method would require solving for weights such that each
        strategy contributes equally to portfolio risk.
        For now, we use inverse volatility as a proxy, which is exact only if
        correlations are zero or equal.
        """
        return self._inverse_volatility(returns_df)

    def _apply_constraints(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Apply min and max weight constraints."""
        constrained = {}
        for strat_name, weight in weights.items():
            if weight < self.min_weight:
                constrained[strat_name] = self.min_weight
            elif weight > self.max_weight:
                constrained[strat_name] = self.max_weight
            else:
                constrained[strat_name] = weight
        return constrained
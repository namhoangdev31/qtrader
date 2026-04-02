"""Enhanced Portfolio Allocator with true risk parity implementation."""

from __future__ import annotations

import logging

import numpy as np
import polars as pl

from qtrader.risk.base import RiskModule

_LOG = logging.getLogger("qtrader.portfolio.allocator")


class EnhancedPortfolioAllocator(RiskModule):
    """
    Enhanced portfolio allocation risk module.
    
    Implements true risk parity (equal risk contribution) using optimization,
    rather than the inverse volatility approximation.
    
    The allocator:
    - Estimates covariance matrix using Ledoit-Wolf shrinkage for robustness
    - Solves for weights where each strategy contributes equal risk to portfolio
    - Applies turnover and concentration constraints
    - Scales to target volatility
    """

    def __init__(
        self,
        target_volatility: float = 0.15,  # 15% annual volatility target
        lookback: int = 60,               # Lookback for covariance estimation
        min_weight: float = 0.0,
        max_weight: float = 1.0,
        max_turnover: float = 0.2,        # Maximum 20% daily turnover
        max_concentration: float = 0.3,   # Maximum 30% weight in any single strategy
        risk_parity_tolerance: float = 1e-4,
    ) -> None:
        """
        Initialize the enhanced portfolio allocator.
        
        Args:
            target_volatility: Target annual volatility (e.g., 0.15 for 15%)
            lookback: Lookback period for estimating covariance
            min_weight: Minimum weight per strategy
            max_weight: Maximum weight per strategy
            max_turnover: Maximum daily turnover (sum of abs weight changes)
            max_concentration: Maximum weight concentration in any single strategy
            risk_parity_tolerance: Tolerance for risk parity optimization
        """
        if target_volatility <= 0:
            raise ValueError("target_volatility must be positive")
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        if min_weight < 0 or max_weight > 1 or min_weight > max_weight:
            raise ValueError("min_weight and max_weight must be in [0,1] and min_weight <= max_weight")
        if max_turnover < 0 or max_turnover > 1:
            raise ValueError("max_turnover must be in [0,1]")
        if max_concentration <= 0 or max_concentration > 1:
            raise ValueError("max_concentration must be in (0,1]")
            
        self.target_volatility = target_volatility
        self.lookback = lookback
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.max_turnover = max_turnover
        self.max_concentration = max_concentration
        self.risk_parity_tolerance = risk_parity_tolerance
        
        # Store previous weights for turnover calculation
        self._prev_weights: dict[str, float] = {}

    def compute(self, data: pl.DataFrame, **kwargs) -> pl.Series:
        """
        Compute portfolio allocation weights.
        
        Args:
            data: Market data DataFrame (not directly used, returns come from kwargs)
            **kwargs: Additional parameters
                - strategy_returns: Dict[str, pl.Series] of strategy returns
                - current_weights: Dict[str, float] of current weights (for turnover calc)
                
        Returns:
            pl.Series of portfolio weights (equal weight if only one strategy)
        """
        strategy_returns = kwargs.get('strategy_returns')
        current_weights = kwargs.get('current_weights', {})
        
        if not strategy_returns:
            _LOG.warning("No strategy returns provided for allocation")
            return pl.Series([0.0] * len(data), dtype=pl.Float64)
        
        # Compute allocation weights
        weights_dict = self.allocate(strategy_returns, current_weights)
        
        # Store current weights for next turnover calculation
        self._prev_weights = weights_dict.copy()
        
        # Return as series (constant weight for all time points)
        if not weights_dict:
            return pl.Series([0.0] * len(data), dtype=pl.Float64)
        
        # For simplicity, return the weight of the first strategy as representative
        # In production, this would be handled at the portfolio level
        first_weight = next(iter(weights_dict.values())) if weights_dict else 0.0
        return pl.Series([float(first_weight)] * len(data), dtype=pl.Float64)

    def allocate(
        self, 
        strategy_returns: dict[str, pl.Series],
        current_weights: dict[str, float] | None = None
    ) -> dict[str, float]:
        """
        Allocate capital to strategies using enhanced risk parity.
        
        Args:
            strategy_returns: Dictionary mapping strategy names to their return series
            current_weights: Current weights for turnover calculation (optional)
            
        Returns:
            Dictionary of allocation weights (same keys as input, weights sum to 1.0)
        """
        if not strategy_returns:
            return {}
        
        # Use provided current weights or fall back to stored ones
        if current_weights is None:
            current_weights = self._prev_weights
        
        # Align all series to the same length by truncating to the shortest
        min_len = min(len(series) for series in strategy_returns.values())
        if min_len < self.lookback:
            _LOG.warning(f"Insufficient data: {min_len} < lookback {self.lookback}")
            # Fall back to equal weight if insufficient data
            n = len(strategy_returns)
            equal_weight = 1.0 / n if n > 0 else 0.0
            return {name: equal_weight for name in strategy_returns.keys()}
        
        if min_len == 0:
            return {name: 0.0 for name in strategy_returns.keys()}
        
        # Truncate series to min_len
        truncated_returns = {
            name: series.tail(min_len) for name, series in strategy_returns.items()
        }
        
        # Convert to DataFrame for easier computation
        returns_df = pl.DataFrame(truncated_returns)
        
        # Check if we have enough data for covariance estimation
        if returns_df.height < 10:
            _LOG.warning("Insufficient returns for covariance estimation")
            n = len(strategy_returns)
            equal_weight = 1.0 / n if n > 0 else 0.0
            return {name: equal_weight for name in strategy_returns.keys()}
        
        # Compute weights based on enhanced risk parity
        try:
            weights_dict = self._enhanced_risk_parity(returns_df)
        except Exception as e:
            _LOG.error(f"Risk parity optimization failed: {e}. Falling back to inverse volatility.")
            weights_dict = self._inverse_volatility(returns_df)
        
        # Apply constraints
        weights_dict = self._apply_constraints(weights_dict, current_weights)
        
        # Normalize weights to sum to 1.0
        weight_sum = sum(weights_dict.values())
        if weight_sum > 0:
            weights_dict = {name: w / weight_sum for name, w in weights_dict.items()}
        else:
            # If all weights are zero, fall back to equal weight
            n = len(weights_dict)
            equal_weight = 1.0 / n if n > 0 else 0.0
            weights_dict = {name: equal_weight for name in weights_dict.keys()}
        
        # Scale to target volatility
        weights_dict = self._scale_to_target_volatility(weights_dict, returns_df)
        
        return weights_dict

    def _enhanced_risk_parity(self, returns_df: pl.DataFrame) -> dict[str, float]:
        """
        Compute true risk parity weights using optimization.
        
        Args:
            returns_df: DataFrame of strategy returns
            
        Returns:
            Dictionary of risk parity weights
        """
        # Convert to numpy for optimization
        returns_matrix = returns_df.to_numpy()
        n_assets = returns_matrix.shape[1]
        
        if n_assets == 1:
            # Single asset case
            return {returns_df.columns[0]: 1.0}
        
        # Estimate covariance matrix using Ledoit-Wolf shrinkage
        cov_matrix = self._ledoit_wolf_shrinkage(returns_matrix)
        
        # Initialize weights (equal weight as starting point)
        weights = np.ones(n_assets) / n_assets
        
        # Optimize for risk parity
        weights = self._optimize_risk_parity(weights, cov_matrix)
        
        # Convert back to dictionary
        return {col: float(weights[i]) for i, col in enumerate(returns_df.columns)}

    def _ledoit_wolf_shrinkage(self, returns_matrix: np.ndarray) -> np.ndarray:
        """
        Estimate covariance matrix using Ledoit-Wolf shrinkage.
        
        Args:
            returns_matrix: Matrix of returns (observations x assets)
            
        Returns:
            Shrunk covariance matrix
        """
        n_obs, n_assets = returns_matrix.shape
        
        # Sample covariance matrix
        sample_cov = np.cov(returns_matrix, rowvar=False)
        
        # Target matrix (constant correlation model)
        mean_var = np.mean(np.diag(sample_cov))
        target = np.eye(n_assets) * mean_var
        
        # Calculate shrinkage intensity
        # Simplified Ledoit-Wolf formula
        delta = np.sum((sample_cov - target) ** 2)
        beta = np.sum(sample_cov ** 2) - np.sum(np.diag(sample_cov) ** 2)
        
        if beta > 0:
            shrinkage = min(1.0, delta / (n_obs * beta))
        else:
            shrinkage = 0.0
        
        # Shrunk covariance
        shrunk_cov = (1 - shrinkage) * sample_cov + shrinkage * target
        
        return shrunk_cov

    def _optimize_risk_parity(self, init_weights: np.ndarray, cov_matrix: np.ndarray) -> np.ndarray:
        """
        Optimize weights for risk parity using iterative approach.
        
        Args:
            init_weights: Initial weight guess
            cov_matrix: Covariance matrix
            
        Returns:
            Optimized risk parity weights
        """
        weights = init_weights.copy()
        n_assets = len(weights)
        
        # Iterative risk parity optimization
        for _ in range(100):  # Max iterations
            # Calculate portfolio volatility
            port_var = np.dot(weights, np.dot(cov_matrix, weights))
            port_vol = np.sqrt(port_var) if port_var > 0 else 1e-8
            
            # Calculate marginal risk contributions
            mrc = np.dot(cov_matrix, weights)
            
            # Calculate risk contributions
            rc = weights * mrc
            
            # Target risk contribution (equal for all assets)
            target_rc = port_vol / n_assets
            
            # Calculate error
            error = np.sum((rc - target_rc) ** 2)
            
            if error < self.risk_parity_tolerance:
                break
            
            # Update weights (gradient descent step)
            # Avoid division by zero
            mrc_safe = np.where(mrc == 0, 1e-8, mrc)
            weights = weights * (target_rc / mrc_safe)
            
            # Normalize to sum to 1
            weights = weights / np.sum(weights)
            
            # Ensure weights are non-negative
            weights = np.maximum(weights, 0)
            weights = weights / np.sum(weights) if np.sum(weights) > 0 else np.ones(n_assets) / n_assets
        
        return weights

    def _inverse_volatility(self, returns_df: pl.DataFrame) -> dict[str, float]:
        """Inverse volatility weighting (fallback method)."""
        # Compute volatility (std) of each strategy
        inv_vol_list = []
        for col in returns_df.columns:
            vol = returns_df[col].std()
            if vol == 0.0 or vol.is_null():
                inv_vol_list.append(0.0)
            else:
                inv_vol_list.append(1.0 / float(vol))
        
        total_inv_vol = sum(inv_vol_list)
        if total_inv_vol == 0.0:
            # Fall back to equal weight
            n = len(returns_df.columns)
            weight = 1.0 / n if n > 0 else 0.0
            return {col: weight for col in returns_df.columns}
        
        weights = {col: inv_vol_list[i] / total_inv_vol for i, col in enumerate(returns_df.columns)}
        return weights

    def _apply_constraints(
        self, 
        weights: dict[str, float], 
        current_weights: dict[str, float]
    ) -> dict[str, float]:
        """Apply min/max weight, turnover, and concentration constraints."""
        # Start with min/max constraints
        constrained = {}
        for strat_name, weight in weights.items():
            if weight < self.min_weight:
                constrained[strat_name] = self.min_weight
            elif weight > self.max_weight:
                constrained[strat_name] = self.max_weight
            else:
                constrained[strat_name] = weight
        
        # Apply turnover constraint
        if current_weights:
            constrained = self._apply_turnover_constraint(constrained, current_weights)
        
        # Apply concentration constraint
        constrained = self._apply_concentration_constraint(constrained)
        
        return constrained

    def _apply_turnover_constraint(
        self, 
        new_weights: dict[str, float], 
        current_weights: dict[str, float]
    ) -> dict[str, float]:
        """Apply maximum turnover constraint."""
        # Calculate desired weight changes
        weight_changes = {}
        total_turnover = 0.0
        
        for name in set(new_weights.keys()) | set(current_weights.keys()):
            new_w = new_weights.get(name, 0.0)
            curr_w = current_weights.get(name, 0.0)
            change = abs(new_w - curr_w)
            weight_changes[name] = change
            total_turnover += change
        
        # If turnover exceeds limit, scale back the changes
        if total_turnover > self.max_turnover:
            scale_factor = self.max_turnover / total_turnover
            adjusted_weights = {}
            
            for name in new_weights.keys():
                new_w = new_weights.get(name, 0.0)
                curr_w = current_weights.get(name, 0.0)
                change = new_w - curr_w
                adjusted_change = change * scale_factor
                adjusted_weights[name] = curr_w + adjusted_change
            
            return adjusted_weights
        
        return new_weights

    def _apply_concentration_constraint(self, weights: dict[str, float]) -> dict[str, float]:
        """Apply maximum concentration constraint."""
        # Check if any weight exceeds concentration limit
        max_weight = max(weights.values()) if weights else 0.0
        
        if max_weight <= self.max_concentration:
            return weights  # No constraint violation
        
        # Need to reduce concentrated weights and redistribute
        adjusted_weights = {}
        excess_weight = 0.0
        
        for name, weight in weights.items():
            if weight > self.max_concentration:
                # Cap at max concentration
                adjusted_weights[name] = self.max_concentration
                excess_weight += weight - self.max_concentration
            else:
                adjusted_weights[name] = weight
        
        # Redistribute excess weight proportionally to under-weighted strategies
        if excess_weight > 0:
            under_weighted = {
                name: weight for name, weight in adjusted_weights.items()
                if weight < self.max_concentration
            }
            
            if under_weighted:
                total_under_capacity = sum(
                    self.max_concentration - weight 
                    for weight in under_weighted.values()
                )
                
                if total_under_capacity > 0:
                    for name in under_weighted:
                        current_weight = adjusted_weights[name]
                        available_capacity = self.max_concentration - current_weight
                        proportion = available_capacity / total_under_capacity
                        adjusted_weights[name] = current_weight + excess_weight * proportion
        
        return adjusted_weights

    def _scale_to_target_volatility(
        self, 
        weights: dict[str, float], 
        returns_df: pl.DataFrame
    ) -> dict[str, float]:
        """Scale weights to achieve target volatility."""
        if not weights:
            return weights
        
        # Convert weights to array in same order as returns_df
        weight_array = np.array([weights[col] for col in returns_df.columns])
        
        # Calculate portfolio volatility
        returns_matrix = returns_df.to_numpy()
        cov_matrix = np.cov(returns_matrix, rowvar=False)
        port_var = np.dot(weight_array, np.dot(cov_matrix, weight_array))
        port_vol = np.sqrt(port_var) if port_var > 0 else 0.0
        
        if port_vol > 0:
            # Scale to target volatility
            vol_ratio = self.target_volatility / port_vol
            scaled_weights = {
                name: weight * vol_ratio 
                for name, weight in weights.items()
            }
            return scaled_weights
        else:
            # Zero volatility case - return as is
            return weights


# Factory function
def create_enhanced_portfolio_allocator() -> EnhancedPortfolioAllocator:
    """
    Factory function to create an EnhancedPortfolioAllocator with default settings.
    
    Returns:
        Configured EnhancedPortfolioAllocator instance
    """
    return EnhancedPortfolioAllocator()
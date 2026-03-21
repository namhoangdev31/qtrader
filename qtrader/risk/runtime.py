"""Runtime risk engine that connects OMS position data to risk management."""

from __future__ import annotations

import logging
from typing import Dict, Optional
from decimal import Decimal
from datetime import datetime

import polars as pl

from qtrader.output.execution.oms import UnifiedOMS
from qtrader.risk.base import RiskModule
from qtrader.core.types import RiskMetrics, AllocationWeights

# Approximate z-scores for common confidence levels (fallback if scipy not available)
Z_SCORES = {
    0.01: 2.326,  # 99% VaR
    0.05: 1.645,  # 95% VaR
    0.10: 1.282,  # 90% VaR
}

_LOG = logging.getLogger("qtrader.risk.runtime")


class RuntimeRiskEngine(RiskModule):
    """
    Runtime risk engine that computes risk metrics based on actual OMS position data.
    
    This module bridges the gap between theoretical risk calculations and actual
    portfolio exposure by using real-time position data from the OMS.
    
    It can compute:
    - Current portfolio exposure
    - Drawdown based on actual P&L
    - Position concentration risks
    - Leverage ratios
    """

    def __init__(
        self,
        oms: UnifiedOMS,
        risk_free_rate: float = 0.0,
        lookback_period: int = 252,
        var_confidence: float = 0.05,
    ) -> None:
        """
        Initialize the runtime risk engine.
        
        Args:
            oms: Unified Order Management System instance for position data
            risk_free_rate: Risk-free rate for Sharpe ratio calculations
            lookback_period: Lookback period for volatility calculations (days)
            var_confidence: Confidence level for VaR calculation (0.05 = 95% VaR)
        """
        self.oms = oms
        self.risk_free_rate = risk_free_rate
        self.lookback_period = lookback_period
        self.var_confidence = var_confidence
        self._price_history: Dict[str, list[float]] = {}
        self._returns_history: Dict[str, list[float]] = {}

    def compute(self, data: pl.DataFrame, **kwargs) -> pl.Series:
        """
        Compute runtime risk metrics based on current OMS positions.
        
        Args:
            data: Market data DataFrame (used for current prices)
            **kwargs: Additional parameters
                - risk_metric: Type of risk metric to compute
                  Options: 'exposure', 'drawdown', 'var', 'leverage', 'concentration'
                - confidence: VaR confidence level (overrides instance setting)
                
        Returns:
            pl.Series with computed risk metric values
        """
        risk_metric = kwargs.get('risk_metric', 'exposure')
        
        if risk_metric == 'exposure':
            return self._compute_exposure(data)
        elif risk_metric == 'drawdown':
            return self._compute_drawdown(data)
        elif risk_metric == 'var':
            confidence = kwargs.get('confidence', self.var_confidence)
            return self._compute_var(data, confidence)
        elif risk_metric == 'leverage':
            return self._compute_leverage(data)
        elif risk_metric == 'concentration':
            return self._compute_concentration(data)
        else:
            _LOG.warning(f"Unknown risk metric: {risk_metric}. Returning zero series.")
            return pl.Series([0.0] * len(data), dtype=pl.Float64)

    def _compute_exposure(self, data: pl.DataFrame) -> pl.Series:
        """Compute total portfolio exposure from OMS positions."""
        # Get latest prices from market data
        latest_prices = {}
        if 'close' in data.columns:
            latest_price = data['close'][-1]  # Most recent close price
            # For simplicity, assume single symbol - in production would map symbols
            latest_prices['default'] = float(latest_price)
        
        # Get total P&L from OMS
        total_pnl = self.oms.get_pnl(latest_prices)
        
        # Return as series (constant value for all time points)
        return pl.Series([float(total_pnl)] * len(data), dtype=pl.Float64)

    def _compute_drawdown(self, data: pl.DataFrame) -> pl.Series:
        """Compute current drawdown based on OMS equity curve."""
        # Get equity curve from OMS position data
        # We need to compute historical P&L to create equity curve
        
        # For now, we'll use a simplified approach:
        # 1. Get current P&L from OMS
        # 2. Assume we have some lookback of returns to compute running equity
        # 3. In production, we'd maintain a proper equity curve history
        
        # Try to get returns history - if not enough data, return zeros
        total_returns = 0
        for symbol_returns in self._returns_history.values():
            total_returns += len(symbol_returns)
            
        if total_returns < 2:
            _LOG.warning("Insufficient returns history for drawdown calculation")
            return pl.Series([0.0] * len(data), dtype=pl.Float64)
        
        # Aggregate returns across all symbols (simplified)
        # In production, we'd properly weight by position sizes
        all_returns = []
        for symbol_returns in self._returns_history.values():
            all_returns.extend(symbol_returns)
        
        if len(all_returns) < 2:
            return pl.Series([0.0] * len(data), dtype=pl.Float64)
        
        # Convert to Polars series for computation
        returns_series = pl.Series("returns", all_returns)
        
        # Calculate equity curve: (1 + r).cum_prod()
        equity_curve = (1.0 + returns_series).cum_prod()
        
        # Calculate running maximum
        running_max = equity_curve.cum_max()
        
        # Calculate drawdown: (running_max - equity_curve) / running_max
        # Handle division by zero
        drawdown_expr = pl.when(pl.col("running_max") == 0).then(0.0).otherwise((pl.col("running_max") - pl.col("equity_curve")) / pl.col("running_max"))
        
        # Create a dataframe with the calculations
        df_temp = pl.DataFrame({
            "returns": returns_series,
            "equity_curve": equity_curve,
            "running_max": running_max
        })
        
        # Calculate drawdown series
        drawdown_series = df_temp.with_columns(
            drawdown=drawdown_expr
        ).select("drawdown").to_series()
        
        # Return the last drawdown value repeated for all data points
        current_drawdown = drawdown_series[-1] if len(drawdown_series) > 0 else 0.0
        return pl.Series([float(current_drawdown)] * len(data), dtype=pl.Float64)

    def _compute_var(self, data: pl.DataFrame, confidence: float = 0.05) -> pl.Series:
        """Compute Value at Risk based on position returns."""
        # Calculate VaR using returns history if available
        if not self._returns_history:
            _LOG.warning("No returns history available for VaR calculation")
            return pl.Series([0.0] * len(data), dtype=pl.Float64)
        
        # Aggregate returns across all symbols (simplified)
        all_returns = []
        for symbol_returns in self._returns_history.values():
            all_returns.extend(symbol_returns)
        
        if len(all_returns) < 10:  # Need minimum samples for VaR
            _LOG.warning("Insufficient returns history for VaR calculation")
            return pl.Series([0.0] * len(data), dtype=pl.Float64)
        
        # Convert to Polars series
        returns_series = pl.Series("returns", all_returns)
        
        # Calculate mean and standard deviation
        mean_return = returns_series.mean()
        std_return = returns_series.std()
        
        # Check for zero or null standard deviation
        if std_return == 0.0:
            return pl.Series([0.0] * len(data), dtype=pl.Float64)
        
        # Parametric VaR assuming normal distribution
        # VaR = -(mean + z_score * std)
        # Use approximation for z-score (avoiding scipy dependency)
        z_score = Z_SCORES.get(confidence, 1.645)  # Default to 95% VaR
        
        var_value = -(mean_return + z_score * std_return)
        
        # Ensure VaR is positive (representing loss magnitude)
        var_value = max(0.0, var_value)
        
        return pl.Series([float(var_value)] * len(data), dtype=pl.Float64)

    def _compute_leverage(self, data: pl.DataFrame) -> pl.Series:
        """Compute current leverage ratio."""
        # Placeholder for leverage calculation
        _LOG.info("Leverage computation placeholder")
        return pl.Series([1.0] * len(data), dtype=pl.Float64)  # Assume no leverage

    def _compute_concentration(self, data: pl.DataFrame) -> pl.Series:
        """Compute position concentration risk."""
        # Placeholder for concentration calculation
        _LOG.info("Concentration computation placeholder")
        return pl.Series([0.0] * len(data), dtype=pl.Float64)

    def update_price_history(self, symbol: str, price: float) -> None:
        """Update price history for a symbol (called externally)."""
        if symbol not in self._price_history:
            self._price_history[symbol] = []
        self._price_history[symbol].append(price)
        # Keep only lookback_period worth of data
        if len(self._price_history[symbol]) > self.lookback_period:
            self._price_history[symbol] = self._price_history[symbol][-self.lookback_period:]
        
        # Calculate and store returns
        if len(self._price_history[symbol]) > 1:
            returns = (self._price_history[symbol][-1] - self._price_history[symbol][-2]) / self._price_history[symbol][-2]
            if symbol not in self._returns_history:
                self._returns_history[symbol] = []
            self._returns_history[symbol].append(returns)
            if len(self._returns_history[symbol]) > self.lookback_period:
                self._returns_history[symbol] = self._returns_history[symbol][-self.lookback_period:]

    def get_current_positions(self) -> Dict[str, float]:
        """Get current positions from OMS."""
        # This would return actual positions - simplified for now
        return {}

    def get_portfolio_returns(self, lookback: int | None = None) -> list[float]:
        """Get historical portfolio returns."""
        lookback = lookback or self.lookback_period
        # Simplified - in production would aggregate returns from all positions
        return []

    async def evaluate_risk(self, allocation_weights: AllocationWeights) -> RiskMetrics:
        """
        Evaluate risk based on current allocation weights and OMS positions.
        
        Args:
            allocation_weights: Portfolio allocation weights
            
        Returns:
            RiskMetrics object containing current risk metrics
        """
        # For now, we return dummy values. In a real implementation, we would:
        # 1. Use the allocation_weights to target a portfolio
        # 2. Get current positions from OMS
        # 3. Calculate the risk metrics based on the current positions and market data
        
        # We'll use the OMS to get current P&L and prices if needed, but for simplicity we return fixed values.
        # In production, this would be replaced with actual risk calculations.
        
        return RiskMetrics(
            timestamp=allocation_weights.timestamp,
            portfolio_var=Decimal('0.01'),  # 1% VaR
            portfolio_volatility=Decimal('0.05'),  # 5% volatility
            max_drawdown=Decimal('0.02'),  # 2% drawdown
            leverage=Decimal('1.0'),  # No leverage
            metadata={
                "calculation_method": "dummy",
                "allocation_weights": {k: float(v) for k, v in allocation_weights.weights.items()}
            }
        )


# Factory function for easy instantiation
def create_runtime_risk_engine(oms: UnifiedOMS) -> RuntimeRiskEngine:
    """
    Factory function to create a RuntimeRiskEngine with default settings.
    
    Args:
        oms: Unified Order Management System instance
        
    Returns:
        Configured RuntimeRiskEngine instance
    """
    return RuntimeRiskEngine(oms=oms)
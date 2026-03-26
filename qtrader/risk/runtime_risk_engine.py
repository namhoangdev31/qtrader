from typing import Any, cast

import numpy as np
import polars as pl

from qtrader.risk.factor_risk import FactorRiskEngine
from qtrader.risk.regime_adapter import RegimeAdapter


class AdvancedRiskEngine:
    """
    Production-grade runtime risk engine for portfolio risk management.
    """

    def __init__(  # noqa: PLR0913
        self,
        max_lookback: int = 252,  # ~1 year of trading days
        max_drawdown_threshold: float = 0.20,
        var_threshold: float = 0.05,
        max_leverage: float = 5.0,
        max_position_size: float = 0.10,
        max_sector_exposure: float = 0.30,
        max_correlation: float = 0.70,
        kill_switch_drawdown: float = 0.30,
        kill_switch_consecutive_losses: int = 5,
    ) -> None:
        self.max_lookback = max_lookback
        self.max_drawdown_threshold = max_drawdown_threshold
        self.var_threshold = var_threshold
        self.max_leverage = max_leverage
        self.max_position_size = max_position_size
        self.max_sector_exposure = max_sector_exposure
        self.max_correlation = max_correlation
        self.kill_switch_drawdown = kill_switch_drawdown
        self.kill_switch_consecutive_losses = kill_switch_consecutive_losses

        # Risk Engines
        self.factor_engine = FactorRiskEngine()
        self.regime_adapter = RegimeAdapter()

        # Regime tracking
        self._current_regime_id: int = 0  # Default to low volatility regime
        self._base_var_threshold = var_threshold
        self._base_max_leverage = max_leverage
        self._base_max_position_size = max_position_size
        self._current_var_threshold = var_threshold
        self._current_max_leverage = max_leverage
        self._current_max_position_size = max_position_size

        self.kill_switch_active = False
        self.consecutive_losses = 0
        self.last_portfolio_return: float | None = None

    def set_regime(self, regime_id: int) -> None:
        """
        Set the current market regime and adjust risk limits accordingly.

        Args:
            regime_id: Market regime identifier (0=low vol, 1=high vol, 2=crisis)
        """
        self._current_regime_id = regime_id

        # Adjust limits based on regime
        adjusted_limits = self.regime_adapter.adjust_limits(
            regime_id=regime_id,
            base_var_threshold=self._base_var_threshold,
            base_max_leverage=self._base_max_leverage,
            base_max_position_size=self._base_max_position_size,
        )

        # Update current limits
        self._current_var_threshold = adjusted_limits["var_threshold"]
        self._current_max_leverage = adjusted_limits["max_leverage"]
        self._current_max_position_size = adjusted_limits["max_position_size"]

    def compute_risk(
        self,
        positions: dict[str, float],
        prices: dict[str, float],
        proposed_trade: dict[str, Any],
        asset_historical_returns: pl.DataFrame,
    ) -> dict[str, Any]:
        """
        Compute risk for a proposed trade and return a risk decision.

        Args:
            positions: Current positions {symbol: quantity}
            prices: Current prices {symbol: price}
            proposed_trade: Trade proposal {symbol, quantity, side, price?}
            asset_historical_returns: Historical returns of assets (columns=symbols, rows=time)

        Returns:
            RiskDecision dictionary with keys:
                - approved: bool
                - adjusted_size: float
                - reason: str
                - risk_metrics: dict
        """
        try:
            # Update consecutive losses based on latest portfolio return
            self._update_consecutive_losses(asset_historical_returns, positions, prices)

            # Check if kill switch is active
            if self.kill_switch_active:
                return {
                    "approved": False,
                    "adjusted_size": 0.0,
                    "reason": "Kill switch is active",
                    "risk_metrics": self._get_current_risk_metrics(
                        positions, prices, asset_historical_returns
                    ),
                }

            # Calculate current portfolio value
            portfolio_value = self._calculate_portfolio_value(positions, prices)
            if portfolio_value <= 0:
                return {
                    "approved": False,
                    "adjusted_size": 0.0,
                    "reason": "Portfolio value is zero or negative",
                    "risk_metrics": {},
                }

            # Calculate portfolio historical returns

            # Create temporary positions including the proposed trade
            temp_positions = positions.copy()
            symbol = proposed_trade["symbol"]
            quantity = float(proposed_trade["quantity"])
            side = proposed_trade["side"]

            if side.lower() == "buy":
                temp_positions[symbol] = temp_positions.get(symbol, 0.0) + quantity
            else:  # sell
                temp_positions[symbol] = temp_positions.get(symbol, 0.0) - quantity

            # Calculate temporary portfolio value and weights
            temp_portfolio_value = self._calculate_portfolio_value(temp_positions, prices)
            temp_weights = self._calculate_weights(temp_positions, prices, temp_portfolio_value)
            temp_p_returns = self._calculate_portfolio_returns(
                asset_historical_returns, temp_weights
            )

            # Calculate risk metrics for the temporary portfolio
            risk_metrics = self._calculate_risk_metrics(
                temp_positions, prices, temp_p_returns, asset_historical_returns
            )

            # Check risk limits and adjust trade size if needed
            approved, adjusted_size, reason = self._check_limits_and_adjust(
                positions, prices, proposed_trade, risk_metrics, portfolio_value
            )

            # If adjusted, recalculate risk metrics with the adjusted size
            if approved and adjusted_size != quantity:
                adj_positions = positions.copy()
                if side.lower() == "buy":
                    adj_positions[symbol] = adj_positions.get(symbol, 0.0) + adjusted_size
                else:
                    adj_positions[symbol] = adj_positions.get(symbol, 0.0) - adjusted_size

                adj_portfolio_value = self._calculate_portfolio_value(adj_positions, prices)
                adj_weights = self._calculate_weights(adj_positions, prices, adj_portfolio_value)
                adj_p_returns = self._calculate_portfolio_returns(
                    asset_historical_returns, adj_weights
                )
                risk_metrics = self._calculate_risk_metrics(
                    adj_positions, prices, adj_p_returns, asset_historical_returns
                )

            return {
                "approved": approved,
                "adjusted_size": float(adjusted_size),
                "reason": reason,
                "risk_metrics": risk_metrics,
            }

        except Exception as e:
            # Failsafe: return error state
            return {
                "approved": False,
                "adjusted_size": 0.0,
                "reason": f"Risk computation failure: {e!s}",
                "risk_metrics": {},
            }

    def check_limits(self, risk_metrics: dict[str, Any]) -> tuple[bool, str]:
        """
        Check if risk metrics exceed predefined limits.

        Args:
            risk_metrics: Dictionary of risk metrics

        Returns:
            Tuple (is_within_limits, reason)
        """
        # Check drawdown
        if risk_metrics.get("current_drawdown", 0) > self.max_drawdown_threshold:
            return False, (
                f"Current drawdown {risk_metrics['current_drawdown']:.2%} "
                f"exceeds threshold {self.max_drawdown_threshold:.2%}"
            )

        if risk_metrics.get("var", 0) > self._current_var_threshold:
            return False, (
                f"VaR {risk_metrics['var']:.2%} exceeds threshold {self._current_var_threshold:.2%}"
            )

        if risk_metrics.get("leverage", 0) > self._current_max_leverage:
            return False, (
                f"Leverage {risk_metrics['leverage']:.2f} "
                f"exceeds threshold {self._current_max_leverage:.2f}"
            )

        if risk_metrics.get("concentration_score", 0) > self.max_correlation:
            return False, (
                f"Concentration score {risk_metrics['concentration_score']:.2f} "
                f"exceeds threshold {self.max_correlation:.2f}"
            )

        return True, "Within risk limits"

    def adjust_position(
        self,
        base_size: float,
        volatility_scaling: float = 1.0,
        correlation_penalty: float = 1.0,
        confidence_multiplier: float = 1.0,
    ) -> float:
        """
        Adjust position size based on risk factors.

        Args:
            base_size: Base position size
            volatility_scaling: Scaling factor based on volatility (0-1+)
            correlation_penalty: Penalty factor based on correlation (0-1+)
            confidence_multiplier: Multiplier based on signal confidence (0-1+)

        Returns:
            Adjusted position size
        """
        adjusted = base_size * volatility_scaling * correlation_penalty * confidence_multiplier
        return max(0.0, adjusted)  # Ensure non-negative

    def kill_switch(self) -> bool:
        """
        Check if kill switch is active.

        Returns:
            True if kill switch is active, False otherwise
        """
        return self.kill_switch_active

    # Helper methods
    def _update_consecutive_losses(
        self,
        asset_historical_returns: pl.DataFrame,
        positions: dict[str, float],
        prices: dict[str, float],
    ) -> None:
        """Update consecutive losses counter based on latest portfolio return."""
        if asset_historical_returns.is_empty() or not positions:
            self.last_portfolio_return = None
            return

        # Calculate latest portfolio return
        p_val = self._calculate_portfolio_value(positions, prices)
        weights = self._calculate_weights(positions, prices, p_val)
        latest_returns = asset_historical_returns.tail(1)
        if latest_returns.is_empty():
            self.last_portfolio_return = None
            return

        # Calculate weighted sum for the latest row
        portfolio_return = 0.0
        for col in asset_historical_returns.columns:
            weight = weights.get(col, 0.0)
            ret = latest_returns[col].item()
            portfolio_return += weight * ret
        self.last_portfolio_return = portfolio_return

        if portfolio_return < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        # Check kill switch conditions
        current_dd = self._calculate_current_drawdown(
            pl.Series([portfolio_return])
            if self.last_portfolio_return is not None
            else pl.Series([0.0])
        )
        if (
            current_dd > self.kill_switch_drawdown
            or self.consecutive_losses >= self.kill_switch_consecutive_losses
        ):
            self.kill_switch_active = True

    def _calculate_portfolio_value(
        self, positions: dict[str, float], prices: dict[str, float]
    ) -> float:
        """Calculate total portfolio value."""
        value = 0.0
        for symbol, qty in positions.items():
            if symbol in prices:
                value += qty * prices[symbol]
        return value

    def _calculate_weights(
        self, positions: dict[str, float], prices: dict[str, float], portfolio_value: float
    ) -> dict[str, float]:
        """Calculate portfolio weights."""
        if portfolio_value == 0:
            return {symbol: 0.0 for symbol in positions}

        weights = {}
        for symbol, qty in positions.items():
            if symbol in prices:
                weights[symbol] = (qty * prices[symbol]) / portfolio_value
            else:
                weights[symbol] = 0.0
        return weights

    def _calculate_portfolio_returns(
        self, asset_historical_returns: pl.DataFrame, weights: dict[str, float]
    ) -> pl.Series:
        """Calculate portfolio historical returns from asset returns and weights."""
        if asset_historical_returns.is_empty() or not weights:
            return pl.Series([0.0])

        # Multiply each column by its weight and sum across columns
        weighted = asset_historical_returns.select(
            [pl.col(col) * weights.get(col, 0.0) for col in asset_historical_returns.columns]
        )
        # Sum horizontally (across columns) to get portfolio return for each row
        portfolio_returns = weighted.sum_horizontal()
        return portfolio_returns

    def _calculate_risk_metrics(
        self,
        positions: dict[str, float],
        prices: dict[str, float],
        portfolio_returns: pl.Series,
        asset_historical_returns: pl.DataFrame,
    ) -> dict[str, Any]:
        """Calculate all risk metrics."""
        metrics: dict[str, Any] = {}

        # Portfolio value
        portfolio_value = float(self._calculate_portfolio_value(positions, prices))
        metrics["portfolio_value"] = portfolio_value

        # Exposure metrics
        gross, net, leverage = self._calculate_exposure(positions, prices)
        metrics["gross_exposure"] = gross
        metrics["net_exposure"] = net
        metrics["leverage"] = leverage

        # VaR (historical)
        metrics["var"] = self._calculate_var(portfolio_returns)

        # Drawdown
        drawdown_series = self._calculate_drawdown_series(portfolio_returns)
        if len(drawdown_series) > 0:
            metrics["current_drawdown"] = float(cast("float", drawdown_series[-1]))
            metrics["max_drawdown"] = float(cast("float", drawdown_series.max()))
        else:
            metrics["current_drawdown"] = 0.0
            metrics["max_drawdown"] = 0.0

        # Correlation risk
        metrics["correlation_matrix"] = self._calculate_correlation_matrix(asset_historical_returns)
        metrics["concentration_score"] = self._calculate_concentration_score(
            asset_historical_returns
        )

        # Factor Risk Breakdown (if metadata provides factor info)
        metadata = getattr(asset_historical_returns, "metadata", {})
        if metadata and "factor_exposures" in metadata and "factor_covariance" in metadata:
            metrics["factor_risk"] = self.factor_engine.decompose_risk(
                positions=positions,
                prices=prices,
                factor_exposures=metadata["factor_exposures"],
                factor_covariance=metadata["factor_covariance"],
                idiosyncratic_vols=metadata.get("idiosyncratic_vols"),
            )

        return metrics

    def _calculate_exposure(
        self, positions: dict[str, float], prices: dict[str, float]
    ) -> tuple[float, float, float]:
        """Calculate gross exposure, net exposure, and leverage."""
        gross = 0.0
        net = 0.0
        for symbol, qty in positions.items():
            if symbol in prices:
                pos_value = qty * prices[symbol]
                gross += abs(pos_value)
                net += pos_value

        # Avoid division by zero
        eps = 1e-8
        if abs(net) < eps:
            leverage = 0.0 if gross < eps else float("inf")
        else:
            leverage = gross / abs(net)

        return gross, net, leverage

    def _calculate_var(self, returns: pl.Series, confidence_level: float = 0.95) -> float:
        """Calculate historical VaR."""
        min_len = 2
        if len(returns) < min_len:
            return 0.0

        sorted_returns = returns.sort()
        index = int((1 - confidence_level) * len(sorted_returns))
        if index < len(sorted_returns):
            var_val = -min(float(sorted_returns[index]), 0.0)  # Ensure non-negative
        else:
            var_val = 0.0
        return float(var_val)

    def _calculate_drawdown_series(self, returns: pl.Series) -> pl.Series:
        """Calculate drawdown series from returns."""
        if len(returns) == 0:
            return pl.Series([0.0])

        # Calculate cumulative returns: (1 + r1) * (1 + r2) * ... - 1
        cum_returns = (1 + returns).cum_prod() - 1
        # Calculate running maximum
        running_max = cum_returns.cum_max()
        # Calculate drawdown: (cum_returns - running_max) / (1 + running_max)
        # Handle division by zero when running_max == -1
        # Use a DataFrame to evaluate the expression cleanly
        drawdown = (
            pl.DataFrame({"cr": cum_returns, "rm": running_max})
            .select(
                pl.when(pl.col("rm") != -1)
                .then((pl.col("cr") - pl.col("rm")) / (1 + pl.col("rm")))
                .otherwise(0.0)
                .alias("drawdown")
            )
            .get_column("drawdown")
        )

        return drawdown

    def _calculate_current_drawdown(self, returns: pl.Series) -> float:
        """Calculate current drawdown from returns series."""
        if len(returns) == 0:
            return 0.0
        drawdown_series = self._calculate_drawdown_series(returns)
        return drawdown_series[-1] if len(drawdown_series) > 0 else 0.0

    def _calculate_correlation_matrix(self, asset_historical_returns: pl.DataFrame) -> pl.DataFrame:
        """Calculate correlation matrix of asset returns."""
        min_width = 2
        if asset_historical_returns.width < min_width:
            return pl.DataFrame()
        return asset_historical_returns.corr()

    def _calculate_concentration_score(self, asset_historical_returns: pl.DataFrame) -> float:
        """Calculate concentration score from correlation matrix.
        Uses the average absolute correlation as a proxy for concentration.
        """
        corr_matrix = self._calculate_correlation_matrix(asset_historical_returns)
        min_width = 2
        if corr_matrix.is_empty() or corr_matrix.width < min_width:
            return 0.0

        # Extract the correlation values (excluding diagonal)
        corr_values = corr_matrix.to_numpy()
        np.fill_diagonal(corr_values, 0)  # Exclude self-correlation
        # Calculate mean of absolute correlations
        mean_abs_corr = np.mean(np.abs(corr_values))
        return float(mean_abs_corr)

    def _get_current_risk_metrics(
        self,
        positions: dict[str, float],
        prices: dict[str, float],
        asset_historical_returns: pl.DataFrame,
    ) -> dict[str, Any]:
        """Get current risk metrics for the existing positions."""
        if not positions or asset_historical_returns.is_empty():
            return {}

        portfolio_value = self._calculate_portfolio_value(positions, prices)
        if portfolio_value == 0:
            return {}

        weights = self._calculate_weights(positions, prices, portfolio_value)
        p_returns = self._calculate_portfolio_returns(asset_historical_returns, weights)
        return self._calculate_risk_metrics(positions, prices, p_returns, asset_historical_returns)

    def _check_limits_and_adjust(
        self,
        positions: dict[str, float],
        prices: dict[str, float],
        proposed_trade: dict[str, Any],
        risk_metrics: dict[str, Any],
        portfolio_value: float,
    ) -> tuple[bool, float, str]:
        """Check risk limits and calculate adjusted trade size."""
        symbol = proposed_trade["symbol"]
        base_size = float(proposed_trade["quantity"])

        # Start with base size
        adjusted_size = base_size
        adjustment_reasons = []

        # Check position limit
        pos_value = abs(adjusted_size) * prices.get(symbol, 0.0)
        position_pct = pos_value / portfolio_value if portfolio_value > 0 else 0.0
        if position_pct > self._current_max_position_size:
            factor = self._current_max_position_size / position_pct if position_pct > 0 else 0.0
            adjusted_size *= factor
            adjustment_reasons.append(
                f"Position size exceeds {self._current_max_position_size:.0%} limit"
            )

        # Check leverage impact (simplified: assume trade increases gross exposure)
        # We'll approximate the change in leverage
        current_leverage = risk_metrics.get("leverage", 0.0)
        if current_leverage > self.max_leverage:
            # Scale down to meet leverage limit
            factor = self.max_leverage / current_leverage if current_leverage > 0 else 0.0
            adjusted_size *= factor
            adjustment_reasons.append(f"Leverage exceeds {self.max_leverage:.0f}x limit")

        # Check VaR impact (approximate: VaR scales with size)
        current_var = risk_metrics.get("var", 0.0)
        if current_var > self.var_threshold:
            factor = self.var_threshold / current_var if current_var > 0 else 0.0
            adjusted_size *= factor
            adjustment_reasons.append(f"VaR exceeds {self.var_threshold:.0%} limit")

        # Check drawdown impact (more complex, approximate)
        current_dd = risk_metrics.get("current_drawdown", 0.0)
        if current_dd > self.max_drawdown_threshold:
            # Reduce size to reduce drawdown impact (very approximate)
            factor = max(0.0, 1.0 - (current_dd - self.max_drawdown_threshold))
            adjusted_size *= factor
            adjustment_reasons.append(f"Drawdown exceeds {self.max_drawdown_threshold:.0%} limit")

        # Check concentration impact (reduce size if concentration is high)
        concentration = risk_metrics.get("concentration_score", 0.0)
        if concentration > self.max_correlation:
            factor = max(0.0, 1.0 - (concentration - self.max_correlation))
            adjusted_size *= factor
            adjustment_reasons.append(f"Concentration exceeds {self.max_correlation:.0%} limit")

        # Ensure non-negative size
        adjusted_size = max(0.0, adjusted_size)

        # Determine if trade is approved
        min_size = 1e-8
        approved = adjusted_size > min_size  # Essentially non-zero
        reason = "; ".join(adjustment_reasons) if adjustment_reasons else "Within risk limits"

        return approved, adjusted_size, reason

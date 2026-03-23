
import numpy as np
import polars as pl


class PerformanceAnalytics:
    """Calculates performance metrics from equity curve or returns."""

    @staticmethod
    def calculate_metrics(
        equity_curve: pl.DataFrame,
        trades: pl.DataFrame = pl.DataFrame(),
        initial_capital: float = 100_000.0
    ) -> dict[str, float]:
        # Extract equity series if it's a DataFrame
        if isinstance(equity_curve, pl.DataFrame):
            if "equity" in equity_curve.columns:
                equity_curve = equity_curve.get_column("equity")
            else:
                # Fallback or empty result
                return {}
        # Drop leading/trailing nulls so head(1) and tail(1) return valid values
        equity_curve = equity_curve.drop_nulls()
        if len(equity_curve) < 2:
            raise ValueError("equity_curve must have at least 2 non-null values")
        returns = equity_curve.pct_change().drop_nulls()
        
        total_return = (equity_curve.tail(1).item() / equity_curve.head(1).item()) - 1
        
        # Annualized metrics (assuming daily data)
        annualized_return = returns.mean() * 252
        annualized_vol = returns.std() * np.sqrt(252)
        
        sharpe_ratio = annualized_return / annualized_vol if annualized_vol > 0 else 0
        
        # Max Drawdown
        rolling_max = equity_curve.cum_max()
        drawdown = (equity_curve - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        
        return {
            "total_return": total_return,
            "annualized_return": annualized_return,
            "annualized_vol": annualized_vol,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown
        }

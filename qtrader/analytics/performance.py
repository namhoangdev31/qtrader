
import numpy as np
import polars as pl


class PerformanceAnalytics:
    """Calculates performance metrics from equity curve or returns."""

    @staticmethod
    def calculate_metrics(equity_curve: pl.Series) -> dict[str, float]:
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

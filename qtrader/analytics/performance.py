
import numpy as np
import polars as pl


class PerformanceAnalytics:
    """Calculates performance metrics from equity curve or returns."""

    def __init__(self, name: str = "performance", risk_free_rate: float = 0.0) -> None:
        self.name = name
        self.risk_free_rate = risk_free_rate

    def calculate_metrics(
        self,
        equity_curve: pl.DataFrame | pl.Series,
        trades: pl.DataFrame = pl.DataFrame(),
        initial_capital: float = 100_000.0
    ) -> dict[str, float]:
        # Extract equity series if it's a DataFrame
        if isinstance(equity_curve, pl.DataFrame):
            if "equity" in equity_curve.columns:
                equity_curve = equity_curve.get_column("equity")
            else:
                # Return zeroed metrics for missing columns
                return {
                    "total_return": 0.0, "annualized_return": 0.0,
                    "annualized_vol": 0.0, "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0, "peak_equity": 0.0
                }
        
        equity_curve = equity_curve.drop_nulls()
        if len(equity_curve) < 2:
            return {
                "total_return": 0.0, "annualized_return": 0.0,
                "annualized_vol": 0.0, "sharpe_ratio": 0.0,
                "max_drawdown": 0.0, "peak_equity": float(equity_curve.max()) if len(equity_curve) > 0 else 0.0
            }

        returns = equity_curve.pct_change().drop_nulls()
        total_return = (equity_curve.tail(1).item() / equity_curve.head(1).item()) - 1
        
        annualized_return = returns.mean() * 252
        annualized_vol = returns.std() * np.sqrt(252)
        sharpe_ratio = (annualized_return - self.risk_free_rate) / annualized_vol if annualized_vol > 1e-9 else 0.0
        
        rolling_max = equity_curve.cum_max()
        drawdown = (equity_curve - rolling_max) / rolling_max
        max_drawdown = abs(float(drawdown.min()))  # Institutional standard: positive %
        peak_equity = float(equity_curve.max())
        
        return {
            "total_return": total_return,
            "annualized_return": annualized_return,
            "annualized_vol": annualized_vol,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "peak_equity": peak_equity
        }

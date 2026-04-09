import logging

import numpy as np
import polars as pl

try:
    import qtrader_core

    HAS_RUST_CORE = True
    stats_engine = qtrader_core.StatsEngine()
    math_engine = qtrader_core.MathEngine()
    sizing_engine = qtrader_core.SizingEngine()
except ImportError:
    HAS_RUST_CORE = False
    logging.warning(
        "qtrader_core (Rust) not found. Falling back to slow Python/Polars implementations."
    )


class PerformanceAnalytics:
    def __init__(self, name: str = "performance", risk_free_rate: float = 0.0) -> None:
        self.name = name
        self.risk_free_rate = risk_free_rate

    def calculate_metrics(
        self,
        equity_curve: pl.DataFrame | pl.Series,
        trades: pl.DataFrame = pl.DataFrame(),
        initial_capital: float = 100000.0,
        confidence_level: float = 0.05,
    ) -> dict[str, float]:
        if isinstance(equity_curve, pl.DataFrame):
            if "equity" in equity_curve.columns:
                equity_series = equity_curve.get_column("equity")
            else:
                return self._empty_metrics()
        else:
            equity_series = equity_curve
        equity_series = equity_series.drop_nulls()
        if len(equity_series) < 2:
            return self._empty_metrics(
                peak=float(equity_series.max()) if len(equity_series) > 0 else 0.0
            )
        equity_vals = equity_series.to_list()
        returns_series = equity_series.pct_change().drop_nulls()
        returns_vals = returns_series.to_list()
        if HAS_RUST_CORE:
            (max_drawdown, peak_equity) = math_engine.calculate_max_drawdown(equity_vals)
            expected_shortfall = stats_engine.calculate_historical_es(
                returns_vals, confidence_level
            )
            omega_ratio = stats_engine.calculate_omega_ratio(
                returns_vals, self.risk_free_rate / 252.0
            )
            sortino_ratio = stats_engine.calculate_sortino_ratio(
                returns_vals, self.risk_free_rate / 252.0, 252.0
            )
            total_return = equity_vals[-1] / equity_vals[0] - 1
            annualized_return = returns_series.mean() * 252
            annualized_vol = returns_series.std() * np.sqrt(252)
            sharpe_ratio = (
                (annualized_return - self.risk_free_rate) / annualized_vol
                if annualized_vol > 1e-09
                else 0.0
            )
            calmar_ratio = stats_engine.calculate_calmar_ratio(annualized_return, max_drawdown)
        else:
            total_return = equity_vals[-1] / equity_vals[0] - 1
            annualized_return = returns_series.mean() * 252
            annualized_vol = returns_series.std() * np.sqrt(252)
            sharpe_ratio = (
                (annualized_return - self.risk_free_rate) / annualized_vol
                if annualized_vol > 1e-09
                else 0.0
            )
            rolling_max = equity_series.cum_max()
            drawdown = (equity_series - rolling_max) / rolling_max
            max_drawdown = abs(float(drawdown.min()))
            peak_equity = float(equity_series.max())
            expected_shortfall = 0.0
            omega_ratio = 0.0
            sortino_ratio = 0.0
            calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else 0.0
        return {
            "total_return": total_return,
            "annualized_return": annualized_return,
            "annualized_vol": annualized_vol,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "omega_ratio": omega_ratio,
            "calmar_ratio": calmar_ratio,
            "expected_shortfall_historical": expected_shortfall,
            "max_drawdown": max_drawdown,
            "peak_equity": peak_equity,
            "has_rust_acceleration": float(HAS_RUST_CORE),
        }

    def calculate_kelly_recommendation(
        self, win_rate: float, win_loss_ratio: float, risk_fraction: float = 0.5
    ) -> float:
        if HAS_RUST_CORE:
            return sizing_engine.calculate_kelly_fraction(win_rate, win_loss_ratio, risk_fraction)
        if win_loss_ratio <= 0:
            return 0.0
        f_star = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        return max(0.0, min(1.0, f_star * risk_fraction))

    def _empty_metrics(self, peak: float = 0.0) -> dict[str, float]:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "annualized_vol": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "omega_ratio": 0.0,
            "calmar_ratio": 0.0,
            "expected_shortfall_historical": 0.0,
            "max_drawdown": 0.0,
            "peak_equity": peak,
            "has_rust_acceleration": float(HAS_RUST_CORE),
        }

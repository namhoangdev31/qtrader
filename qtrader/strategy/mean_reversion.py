from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import List, Tuple

import numpy as np
import polars as pl
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
from statsmodels.tsa.stattools import coint

from qtrader.strategy.base import BaseStrategy

__all__ = ["OUMeanReversion", "StatisticalArbitrage"]


@dataclass(slots=True)
class OUMeanReversion(BaseStrategy):
    """Ornstein-Uhlenbeck process based mean-reversion utilities."""

    def fit_ou(self, spread: pl.Series) -> tuple[float, float, float]:
        """Estimate OU parameters (theta, mu, sigma) via OLS.

        Args:
            spread: Price spread series assumed to follow an OU process.

        Returns:
            Tuple of (theta, mu, sigma) where:
            - theta: Speed of mean reversion.
            - mu: Long-run mean level.
            - sigma: Volatility of the OU process.
        """
        if spread.len() < 3:
            return 0.0, 0.0, 0.0

        x = spread.to_numpy()
        x_t = x[:-1]
        dx = x[1:] - x[:-1]

        X = add_constant(x_t)
        model = OLS(dx, X).fit()
        a, b = model.params
        theta = float(max(-b, 0.0))
        mu = float(-a / b) if b != 0.0 else float(x.mean())
        sigma = float(np.std(model.resid, ddof=1))
        return theta, mu, sigma

    def compute_zscore(self, spread: pl.Series, window: int = 20) -> float:
        """Compute z-score of the latest spread value vs rolling mean/std.

        Args:
            spread: Series of spread values.
            window: Lookback window for mean and std.

        Returns:
            Z-score of the most recent spread; 0.0 if insufficient data or zero std.
        """
        if spread.len() < window:
            return 0.0
        tail = spread.tail(window)
        mean = float(tail.mean())
        std = float(tail.std())
        if std <= 0.0:
            return 0.0
        last = float(tail[-1])
        return (last - mean) / std


@dataclass(slots=True)
class StatisticalArbitrage(BaseStrategy):
    """Engle-Granger cointegration-based statistical arbitrage utilities."""

    def find_cointegrated_pairs(
        self,
        prices: pl.DataFrame,
        pvalue_threshold: float = 0.05,
    ) -> list[tuple[str, str, float]]:
        """Find cointegrated pairs and corresponding hedge ratios.

        Args:
            prices: Price DataFrame with columns as asset symbols.
            pvalue_threshold: Maximum p-value for cointegration test.

        Returns:
            List of tuples (asset_a, asset_b, hedge_ratio) for cointegrated pairs.
        """
        symbols = prices.columns
        if len(symbols) < 2 or prices.height < 5:
            return []

        out: List[Tuple[str, str, float]] = []
        price_np = prices.to_numpy()

        for i, j in combinations(range(len(symbols)), 2):
            x = price_np[:, i]
            y = price_np[:, j]
            _, pvalue, _ = coint(x, y)
            if pvalue < pvalue_threshold:
                X = add_constant(x)
                model = OLS(y, X).fit()
                beta = float(model.params[1])
                out.append((symbols[i], symbols[j], beta))

        return out


"""
Pytest-style examples (conceptual):

def test_ou_fit_returns_tuple() -> None:
    spread = pl.Series([1.0, 1.1, 0.9, 1.05, 0.95])
    strat = OUMeanReversion(symbol="SPREAD")
    theta, mu, sigma = strat.fit_ou(spread)
    assert isinstance(theta, float)
    assert isinstance(mu, float)
    assert isinstance(sigma, float)


def test_stat_arb_no_pairs_for_random() -> None:
    prices = pl.DataFrame(
        {
            "A": [1.0, 1.1, 1.2, 1.15, 1.17],
            "B": [0.9, 0.95, 1.0, 1.02, 1.01],
        },
    )
    strat = StatisticalArbitrage(symbol="A")
    pairs = strat.find_cointegrated_pairs(prices, pvalue_threshold=0.0)
    assert isinstance(pairs, list)
"""


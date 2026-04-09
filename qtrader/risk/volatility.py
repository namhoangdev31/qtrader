import logging

import polars as pl

from qtrader.risk.base import RiskModule

_LOG = logging.getLogger(__name__)

try:
    import qtrader_core

    math_engine = qtrader_core.MathEngine()
except ImportError as e:
    _LOG.error("[RISK] Institutional Risk Core (qtrader_core) is missing. System startup blocked.")
    raise ImportError(
        "qtrader_core is a mandatory dependency for institutional volatility targeting"
    ) from e


class VolatilityTargeting(RiskModule):
    """
    Volatility targeting risk module backed by Rust math core.

    Computes a volatility scaling factor to target a constant portfolio volatility.
    The scaling factor is calculated as: target_vol / current_vol
    """

    def __init__(
        self,
        lookback: int = 30,
        target_vol: float = 0.01,
        annualize: bool = True,
        trading_periods: int = 252,
        epsilon: float = 1e-8,
    ) -> None:
        """
        Initialize the VolatilityTargeting module.
        """
        self.lookback = lookback
        self.target_vol = target_vol
        self.annualize = annualize
        self.trading_periods = trading_periods
        self.epsilon = epsilon

    def compute(self, data: pl.DataFrame, **kwargs: Any) -> pl.Series:
        """
        Compute the volatility scaling factor using authoritative Rust math.
        """
        if data.is_empty():
            return pl.Series(name="volatility_scaling", values=[])

        if "close" not in data.columns:
            _LOG.warning("[RISK] VolatilityTargeting: 'close' column missing from data")
            return pl.Series(name="volatility_scaling", values=[0.0] * len(data))

        closes = data.get_column("close").to_list()

        if len(closes) < self.lookback:
            return pl.Series(name="volatility_scaling", values=[0.0] * len(closes))

        returns = [(closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes))]
        # Pad first return
        returns = [0.0] + returns

        vol_scaling = []
        for i in range(len(returns)):
            if i < self.lookback:
                vol_scaling.append(0.0)
                continue

            window = returns[i - self.lookback + 1 : i + 1]
            # Use Rust for the standard deviation
            from qtrader_core import StatsEngine

            stats = StatsEngine()
            vol = stats.calculate_std(window)

            if self.annualize:
                vol *= self.trading_periods**0.5

            scaling = self.target_vol / (vol + self.epsilon) if vol > 1e-9 else 0.0
            vol_scaling.append(scaling)

        return pl.Series(name="volatility_scaling", values=vol_scaling)

"""qtrader.features.statistical — Statistical transforms for signal processing."""

from qtrader.features.statistical.transforms import (
    cross_sectional_rank,
    cross_sectional_zscore,
    exponential_decay_ma,
    information_coefficient,
    rolling_zscore,
    winsorize,
)

__all__ = [
    "cross_sectional_rank",
    "cross_sectional_zscore",
    "exponential_decay_ma",
    "information_coefficient",
    "rolling_zscore",
    "winsorize",
]

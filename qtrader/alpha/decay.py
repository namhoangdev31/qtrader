from __future__ import annotations

from typing import TYPE_CHECKING

from qtrader.alpha.ic import SignalAnalyzer

if TYPE_CHECKING:
    import polars as pl


class AlphaDecayDetector:
    @staticmethod
    def is_decaying(rolling_ic: pl.Series, threshold: float = 0.01) -> bool:
        if rolling_ic.is_empty():
            return False
        clean_mu = rolling_ic.drop_nulls()
        if clean_mu.is_empty():
            return False
        current_mu = clean_mu.tail(1).item()
        return float(current_mu) < threshold

    @staticmethod
    def check_signal_health(
        df: pl.DataFrame,
        signal_col: str,
        return_col: str,
        monitoring_params: dict[str, float | int] | None = None,
    ) -> bool:
        if df.is_empty():
            return True
        params = monitoring_params or {}
        window = int(params.get("window", 252))
        threshold = float(params.get("threshold", 0.01))
        lag = int(params.get("lag", 1))
        rolling_ic = SignalAnalyzer.compute_rolling_ic(
            df, signal_col, return_col, window=window, lag=lag
        )
        ic_mu = rolling_ic.rolling_mean(window_size=window)
        return AlphaDecayDetector.is_decaying(ic_mu, threshold=threshold)

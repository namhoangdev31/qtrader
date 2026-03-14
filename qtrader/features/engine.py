"""FactorEngine: batch and streaming feature computation.

Central orchestrator that takes registered Feature implementations and
runs them over DataFrames in batch or real-time streaming mode.
The bot's _signal_loop() calls compute_latest() on each tick.
"""

from __future__ import annotations

import logging
from typing import Union

import polars as pl

from qtrader.features.base import Feature, FeaturePipeline
from qtrader.features.store import FeatureStore

__all__ = ["FactorEngine"]

_LOG = logging.getLogger("qtrader.features.engine")


class FactorEngine:
    """Orchestrates batch computation and storage of features.

    Supports three modes:
    - **Batch** (``compute_and_save``): Research / offline mode.
    - **Streaming** (``compute_latest``): Called by bot _signal_loop on each tick.
    - **Cross-sectional** (``compute_multi_symbol``): Runs all symbols for alpha research.

    Args:
        store: FeatureStore backend (DuckDB or Parquet).
    """

    def __init__(self, store: FeatureStore) -> None:
        self.store = store
        self._factors: list[Feature] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_factor(self, factor: Feature) -> None:
        """Register a feature for inclusion in all compute calls.

        Args:
            factor: Any object satisfying the ``Feature`` protocol.
        """
        self._factors.append(factor)
        _LOG.debug("Registered factor '%s'.", getattr(factor, "name", repr(factor)))

    def get_all_feature_names(self) -> list[str]:
        """Return the name of every registered factor.

        Returns:
            List of feature name strings; maintains registration order.
        """
        return [getattr(f, "name", f"factor_{i}") for i, f in enumerate(self._factors)]

    # ------------------------------------------------------------------
    # Core compute (internal)
    # ------------------------------------------------------------------

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute all registered factors without saving.

        Features whose ``validate_inputs`` fails are skipped with a warning.

        Args:
            df: Input OHLCV DataFrame, sorted ascending by time.

        Returns:
            Wide DataFrame with one column per feature; includes ``timestamp``
            column if present in ``df``.
        """
        feature_frames: list[pl.DataFrame] = []

        for factor in self._factors:
            try:
                if hasattr(factor, "validate_inputs"):
                    factor.validate_inputs(df)
                result = factor.compute(df)
                if isinstance(result, pl.Series):
                    feature_frames.append(result.to_frame())
                elif isinstance(result, pl.DataFrame):
                    feature_frames.append(result)
                else:
                    _LOG.warning(
                        "Factor '%s' returned unexpected type %s; skipping.",
                        getattr(factor, "name", "?"),
                        type(result),
                    )
            except ValueError as exc:
                _LOG.warning(
                    "Factor '%s' skipped (validation failed): %s",
                    getattr(factor, "name", "?"),
                    exc,
                )
            except Exception as exc:
                _LOG.error(
                    "Factor '%s' raised unexpected error: %s",
                    getattr(factor, "name", "?"),
                    exc,
                    exc_info=True,
                )

        if not feature_frames:
            return pl.DataFrame()

        combined = pl.concat(feature_frames, how="horizontal")
        if "timestamp" in df.columns:
            combined = pl.concat(
                [df.select("timestamp"), combined], how="horizontal"
            )
        return combined

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_and_save(
        self,
        df: pl.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> pl.DataFrame:
        """Compute all factors and persist to FeatureStore.

        Args:
            df: Input OHLCV DataFrame.
            symbol: Instrument symbol (e.g. "BTC/USDT").
            timeframe: Bar timeframe (e.g. "1d").

        Returns:
            Feature DataFrame (same as ``compute(df)``).
        """
        result = self.compute(df)
        if not result.is_empty():
            self.store.save_features(result, symbol, timeframe)
            _LOG.info(
                "Computed and saved %d features for %s/%s (%d rows).",
                len(result.columns),
                symbol,
                timeframe,
                result.height,
            )
        return result

    def compute_latest(self, df: pl.DataFrame) -> dict[str, float]:
        """Compute all factors for the **latest bar only** (streaming mode).

        Called by ``TradingBot._signal_loop()`` on each market-data tick.
        Returns a flat dict of {feature_name: value}. Returns NaN if the
        DataFrame does not have enough history (``min_periods`` not met).

        Args:
            df: Full historical DataFrame ending at the current bar.

        Returns:
            Dict mapping feature name → float. Returns NaN for features with
            insufficient history.
        """
        if df.is_empty():
            return {name: float("nan") for name in self.get_all_feature_names()}

        result: dict[str, float] = {}
        for factor in self._factors:
            fname = getattr(factor, "name", "?")
            min_p = getattr(factor, "min_periods", 1)
            if df.height < min_p:
                result[fname] = float("nan")
                continue
            try:
                if hasattr(factor, "validate_inputs"):
                    factor.validate_inputs(df)
                out = factor.compute(df)
                if isinstance(out, pl.Series):
                    last = out[-1]
                    result[fname] = float(last) if last is not None else float("nan")
                elif isinstance(out, pl.DataFrame):
                    # For multi-output factors, take last row of each col
                    last_row = out.tail(1)
                    for col in last_row.columns:
                        val = last_row[col][0]
                        result[col] = float(val) if val is not None else float("nan")
            except Exception as exc:
                _LOG.warning("compute_latest factor '%s' error: %s", fname, exc)
                result[fname] = float("nan")

        return result

    def compute_multi_symbol(
        self,
        dfs: dict[str, pl.DataFrame],
        timeframe: str,
    ) -> pl.DataFrame:
        """Compute features for multiple symbols and return long-format DataFrame.

        Args:
            dfs: Dict mapping symbol → OHLCV DataFrame.
            timeframe: Bar timeframe label (used for FeatureStore saves).

        Returns:
            Long-format DataFrame with columns:
            ``timestamp | symbol | feature_1 | feature_2 | ...``
        """
        symbol_frames: list[pl.DataFrame] = []
        for symbol, df in dfs.items():
            feats = self.compute_and_save(df, symbol, timeframe)
            if feats.is_empty():
                continue
            feats = feats.with_columns(pl.lit(symbol).alias("symbol"))
            symbol_frames.append(feats)

        if not symbol_frames:
            return pl.DataFrame()

        return pl.concat(symbol_frames, how="diagonal")


"""
# Pytest-style unit tests:

def test_engine_compute_latest_returns_dict() -> None:
    import polars as pl
    from qtrader.features.engine import FactorEngine
    from qtrader.features.store import FeatureStore
    from qtrader.features.factors.technical import RSI

    store = FeatureStore(use_duckdb=False)
    engine = FactorEngine(store=store)
    engine.register_factor(RSI(period=5))

    prices = [float(100 + i * 0.5) for i in range(20)]
    df = pl.DataFrame({"close": prices})
    result = engine.compute_latest(df)
    assert "rsi_5" in result
    assert isinstance(result["rsi_5"], float)

def test_engine_compute_returns_nan_when_insufficient_history() -> None:
    import polars as pl
    from qtrader.features.engine import FactorEngine
    from qtrader.features.store import FeatureStore
    from qtrader.features.factors.technical import ATR

    store = FeatureStore(use_duckdb=False)
    engine = FactorEngine(store=store)
    engine.register_factor(ATR(period=14))  # needs 14+ rows

    tiny_df = pl.DataFrame({
        "high": [10.0, 11.0], "low": [9.0, 10.0], "close": [9.5, 10.5]
    })
    result = engine.compute_latest(tiny_df)
    import math
    assert math.isnan(result["atr_14"]), "Should return NaN for insufficient history"
"""

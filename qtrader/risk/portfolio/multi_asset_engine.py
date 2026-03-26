"""Multi-asset portfolio allocation engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import polars as pl

from qtrader.core.logger import logger
from qtrader.core.types import AllocationWeights, SignalEvent


@dataclass
class AssetClassMapping:
    """Mapping of symbols to asset classes."""

    symbol_to_asset_class: dict[str, str]
    target_asset_class_weights: dict[str, float] | None = None
    base_currency: str = "USD"


class MultiAssetPortfolioEngine:
    """
    Multi-asset portfolio allocation engine.

    Features:
    - Cross-asset allocation based on volatility normalization
    - Within-asset allocation based on signal strength
    - Correlation matrix computation (simplified for now)
    - Base currency conversion (assumed handled in market data)
    - Hedging support via negative weights (if signals allow)
    """

    MIN_DATA_POINTS = 2
    DEFAULT_VOLATILITY = 0.01

    def __init__(
        self,
        asset_class_mapping: AssetClassMapping,
        lookback_period: int = 30,
    ) -> None:
        """
        Initialize the multi-asset portfolio engine.

        Args:
            asset_class_mapping: Mapping of symbols to asset classes and base currency
            lookback_period: Number of periods to use for volatility/correlation calculation
        """
        self.asset_class_mapping = asset_class_mapping
        self.lookback_period = lookback_period
        self.logger = logger

    def allocate_portfolio(
        self,
        signals: list[SignalEvent],
        current_positions: dict[str, Decimal],
        market_data: dict[str, pl.DataFrame],
    ) -> AllocationWeights:
        """
        Calculate portfolio allocation weights based on multi-asset inputs.

        Args:
            signals: List of trading signals from strategies
            current_positions: Current position quantities by symbol
            market_data: Historical market data by symbol (DataFrame with OHLCV columns)

        Returns:
            AllocationWeights containing portfolio weights
        """
        if not market_data:
            self.logger.warning("No market data provided for allocation")
            return AllocationWeights(
                timestamp=datetime.now(),
                weights={},
                metadata={"engine": "MultiAssetPortfolioEngine", "warning": "no_market_data"},
            )

        # 1. Prepare and combine returns data
        combined_returns, valid_symbols = self._prepare_returns_data(market_data)
        if combined_returns.is_empty() or not valid_symbols:
            return AllocationWeights(
                timestamp=datetime.now(),
                weights={},
                metadata={
                    "engine": "MultiAssetPortfolioEngine",
                    "warning": "insufficient_data_or_no_overlap",
                },
            )

        # 2. Calculate covariance matrix
        returns_only = combined_returns.select(valid_symbols)
        try:
            cov_matrix = self._calculate_covariance_matrix(returns_only, valid_symbols)
        except Exception as e:
            self.logger.error(f"Failed to calculate covariance matrix: {e}")
            return AllocationWeights(
                timestamp=datetime.now(),
                weights={},
                metadata={
                    "engine": "MultiAssetPortfolioEngine",
                    "error": "covariance_calculation_failed",
                },
            )

        # 3. Calculate volatilities and asset class mapping
        symbol_df = self._prepare_symbol_metadata(valid_symbols, cov_matrix)

        # 4. Calculate asset class weights
        # Use target weights if provided, otherwise fallback to inverse volatility
        if self.asset_class_mapping.target_asset_class_weights:
            asset_class_weights = self._get_target_asset_class_weights()
        else:
            asset_class_weights = self._calculate_asset_class_weights(symbol_df)

        # 5. Calculate correlation-based diversification weights
        corr_matrix = self._calculate_correlation_matrix(cov_matrix)
        symbol_df = self._apply_correlation_adjustment(symbol_df, corr_matrix, valid_symbols)

        # 6. Calculate final weights incorporating signals and hedging
        weights_dict = self._compute_final_weights(
            symbol_df, asset_class_weights, signals, valid_symbols
        )

        # Get latest timestamp from combined returns
        latest_timestamp = combined_returns.select(pl.col("timestamp").max()).item()

        return AllocationWeights(
            timestamp=latest_timestamp,
            weights=weights_dict,
            metadata={
                "engine": "MultiAssetPortfolioEngine",
                "asset_class_weights": {
                    row["asset_class"]: float(row["asset_class_weight"])
                    for row in asset_class_weights.iter_rows(named=True)
                },
            },
        )

    def _prepare_returns_data(
        self, market_data: dict[str, pl.DataFrame]
    ) -> tuple[pl.DataFrame, list[str]]:
        """Prepare and combine returns data for all symbols."""
        returns_data = {}
        valid_symbols = []
        for symbol, df in market_data.items():
            if df.is_empty() or len(df) < self.MIN_DATA_POINTS:
                self.logger.warning(f"Insufficient data for {symbol}")
                continue

            returns_df = df.select(
                pl.col("timestamp"), pl.col("close").pct_change().alias(symbol)
            ).drop_nulls()

            if returns_df.is_empty():
                continue

            returns_data[symbol] = returns_df
            valid_symbols.append(symbol)

        if not valid_symbols:
            return pl.DataFrame(), []

        combined_returns = returns_data[valid_symbols[0]]
        for symbol in valid_symbols[1:]:
            combined_returns = combined_returns.join(
                returns_data[symbol], on="timestamp", how="inner"
            )

        return combined_returns, valid_symbols

    def _calculate_covariance_matrix(
        self, returns_only: pl.DataFrame, valid_symbols: list[str]
    ) -> list[list[float]]:
        """Calculate covariance matrix using Polars expressions."""
        cov_exprs = []
        for i, col1 in enumerate(valid_symbols):
            for j, col2 in enumerate(valid_symbols):
                if i <= j:
                    cov_expr = pl.cov(col1, col2).alias(f"cov_{i}_{j}")
                    cov_exprs.append(cov_expr)

        cov_result = returns_only.select(cov_exprs)
        cov_values = {}
        idx = 0
        for i, _col1 in enumerate(valid_symbols):
            for j, _col2 in enumerate(valid_symbols):
                if i <= j:
                    cov_values[(i, j)] = float(cov_result[0, idx])
                    idx += 1

        n = len(valid_symbols)
        cov_matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i <= j:
                    cov_matrix[i][j] = cov_values[(i, j)]
                else:
                    cov_matrix[i][j] = cov_values[(j, i)]
        return cov_matrix

    def _prepare_symbol_metadata(
        self, valid_symbols: list[str], cov_matrix: list[list[float]]
    ) -> pl.DataFrame:
        """Calculate volatilities and map to asset classes."""
        volatilities = pl.DataFrame(
            {
                "symbol": valid_symbols,
                "variance": [cov_matrix[i][i] for i in range(len(valid_symbols))],
            }
        ).with_columns(pl.col("variance").sqrt().alias("volatility"))

        mapping_expr = pl.col("symbol").replace(
            self.asset_class_mapping.symbol_to_asset_class, default="UNKNOWN"
        )
        return volatilities.with_columns(mapping_expr.alias("asset_class"))

    def _get_target_asset_class_weights(self) -> pl.DataFrame:
        """Return target asset class weights from mapping."""
        targets = self.asset_class_mapping.target_asset_class_weights or {}
        return pl.DataFrame(
            {
                "asset_class": list(targets.keys()),
                "asset_class_weight": list(targets.values()),
            }
        )

    def _calculate_correlation_matrix(self, cov_matrix: list[list[float]]) -> list[list[float]]:
        """Calculate correlation matrix from covariance matrix."""
        n = len(cov_matrix)
        vols = [cov_matrix[i][i] ** 0.5 if cov_matrix[i][i] > 0 else 1e-8 for i in range(n)]
        corr_matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                corr_matrix[i][j] = cov_matrix[i][j] / (vols[i] * vols[j])
        return corr_matrix

    def _apply_correlation_adjustment(
        self, symbol_df: pl.DataFrame, corr_matrix: list[list[float]], valid_symbols: list[str]
    ) -> pl.DataFrame:
        """Calculate diversification factor based on correlation."""
        diversification_factors = []
        for i in range(len(valid_symbols)):
            abs_corr_sum = sum(abs(corr_matrix[i][j]) for j in range(len(valid_symbols)) if i != j)
            # Factor = 1 / (1 + sum_abs_corr)
            factor = 1.0 / (1.0 + abs_corr_sum)
            diversification_factors.append(factor)

        div_df = pl.DataFrame(
            {"symbol": valid_symbols, "diversification_factor": diversification_factors}
        )
        return symbol_df.join(div_df, on="symbol")

    def _calculate_asset_class_weights(self, symbol_df: pl.DataFrame) -> pl.DataFrame:
        """Calculate asset class weights using inverse volatility."""
        asset_class_vol = symbol_df.group_by("asset_class").agg(
            pl.col("volatility").mean().alias("asset_class_volatility")
        )

        # Inverse volatility weighting
        asset_class_weights = asset_class_vol.with_columns(
            (1.0 / pl.col("asset_class_volatility").fill_null(self.DEFAULT_VOLATILITY)).alias(
                "inv_vol"
            )
        )
        total_inv_vol = asset_class_weights["inv_vol"].sum()

        if total_inv_vol == 0:
            return asset_class_weights.with_columns(pl.lit(0.0).alias("asset_class_weight"))

        return asset_class_weights.with_columns(
            (pl.col("inv_vol") / total_inv_vol).alias("asset_class_weight")
        )

    def _compute_final_weights(
        self,
        symbol_df: pl.DataFrame,
        asset_class_weights: pl.DataFrame,
        signals: list[SignalEvent],
        valid_symbols: list[str],
    ) -> dict[str, Decimal]:
        """Compute final symbol weights incorporating signals, correlation, and hedging."""
        signals_df = (
            pl.DataFrame(
                {
                    "symbol": [s.symbol for s in signals],
                    "signal_strength": [float(s.strength) for s in signals],
                }
            )
            if signals
            else pl.DataFrame(
                {
                    "symbol": pl.Series(valid_symbols, dtype=pl.Utf8),
                    "signal_strength": pl.Series([0.0] * len(valid_symbols), dtype=pl.Float64),
                }
            )
        )

        # Join symbol data with signals, asset class weights, and diversification factors
        df = symbol_df.join(signals_df, on="symbol", how="left").join(
            asset_class_weights.select(["asset_class", "asset_class_weight"]),
            on="asset_class",
            how="left",
        )

        df = df.with_columns(pl.col("signal_strength").fill_null(0.0))

        # Adjust signal strength by diversification factor
        df = df.with_columns(
            (pl.col("signal_strength") * pl.col("diversification_factor")).alias("adjusted_signal")
        )

        # Calculate within-asset class weights using absolute adjusted signals for magnitude
        # but preserving sign for hedging
        df = df.with_columns(pl.col("adjusted_signal").abs().alias("signal_magnitude"))

        mag_sums = df.group_by("asset_class").agg(pl.col("signal_magnitude").sum().alias("mag_sum"))
        symbol_counts = df.group_by("asset_class").agg(
            pl.col("symbol").count().alias("symbol_count")
        )

        df = df.join(mag_sums, on="asset_class", how="left").join(
            symbol_counts, on="asset_class", how="left"
        )

        # Within-asset class weight: relative magnitude * original sign
        # If mag_sum is 0, use inverse volatility (all weights positive)
        df = df.with_columns(
            (1.0 / pl.col("volatility").fill_null(self.DEFAULT_VOLATILITY)).alias("inv_vol")
        )
        inv_vol_sums = df.group_by("asset_class").agg(pl.col("inv_vol").sum().alias("inv_vol_sum"))
        df = df.join(inv_vol_sums, on="asset_class", how="left")

        df = df.with_columns(
            pl.when(pl.col("mag_sum") > 0)
            .then(
                (pl.col("signal_magnitude") / pl.col("mag_sum"))
                * pl.col("adjusted_signal").sign()
            )
            .otherwise(pl.col("inv_vol") / pl.col("inv_vol_sum"))
            .alias("within_weight")
        )

        # Final weight = asset_class_weight * within_weight
        df = df.with_columns(
            (pl.col("asset_class_weight") * pl.col("within_weight")).alias("final_weight")
        )

        return {
            row["symbol"]: Decimal(str(row["final_weight"]))
            for row in df.iter_rows(named=True)
        }

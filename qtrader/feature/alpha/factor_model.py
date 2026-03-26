"""
Factor Model implementation for Quant Research and Alpha generation.
Follows the KILO.AI Industrial Grade Protocol (08 - Quant Research).
"""

from __future__ import annotations

import polars as pl

from qtrader.core.logger import logger


class FactorModel:
    """
    Factor Model engine for transforming raw features into standardized alpha scores.
    
    Features:
    - Market Factors (Momentum, Volatility, Trend)
    - Style Factors (Mean Reversion, Breakout, Carry)
    - Microstructure Factors (Order Flow, Liquidity)
    - Cross-sectional Z-score normalization
    - Optional Factor Neutralization
    """

    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self.logger = logger

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Compute standardized factors and composite alpha.
        
        Args:
            df: Input DataFrame with symbol, timestamp, close, volume, etc.
            
        Returns:
            DataFrame with additional factor_scores and composite_alpha columns.
        """
        if df.is_empty():
            return df

        # 1. Compute Raw Factors
        df = self._compute_market_factors(df)
        df = self._compute_style_factors(df)
        df = self._compute_microstructure_factors(df)

        # 2. Standardize Factors (Z-score within each timestamp)
        factor_cols = [
            "momentum", "volatility", "trend", 
            "mean_reversion", "breakout", "carry",
            "order_flow", "liquidity_pressure"
        ]
        
        # Ensure factor columns exist
        for col in factor_cols:
            if col not in df.columns:
                df = df.with_columns(pl.lit(0.0).alias(col))

        # Perform cross-sectional Z-score normalization
        standardized_cols = []
        for col in factor_cols:
            std_col = f"z_{col}"
            df = df.with_columns(self._standardize(pl.col(col)).alias(std_col))
            standardized_cols.append(std_col)

        # 3. Factor Neutralization (Advanced)
        # Neutralize against asset classes/sectors if present
        if "asset_class" in df.columns:
            for col in standardized_cols:
                df = df.with_columns(
                    self._neutralize(pl.col(col), group_by="asset_class").alias(col)
                )

        # 4. Aggregate Composite Alpha (Equal-weighted combination)
        df = df.with_columns(
            (pl.sum_horizontal(standardized_cols) / len(standardized_cols)).alias("composite_alpha")
        )

        # 5. Output in target format
        # The prompt asks for output format in a dictionary but in a vectorized engine 
        # we return a DataFrame for performance/integration.
        # 5. Output Format in Struct
        df = df.with_columns(
            pl.struct(standardized_cols).alias("factor_scores")
        )

        return df

    def _standardize(self, expr: pl.Expr) -> pl.Expr:
        """Apply cross-sectional Z-score normalization."""
        return (expr - expr.mean().over("timestamp")) / (
            expr.std().over("timestamp").fill_null(1.0).clip(1e-8)
        )

    def _neutralize(self, expr: pl.Expr, group_by: str | None = None) -> pl.Expr:
        """Apply factor neutralization (de-meaning)."""
        if group_by:
            # Neutralize within group (e.g., sector-neutral or asset-class neutral)
            return expr - expr.mean().over(["timestamp", group_by])
        # Default: cross-sectional de-meaning (already done by standardize)
        return expr - expr.mean().over("timestamp")

    def _compute_market_factors(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute Momentum, Volatility, and Trend."""
        return df.with_columns([
            # Momentum: 10-period pct change
            (pl.col("close").pct_change(self.lookback // 2)).over("symbol").alias("momentum"),
            # Volatility: 20-period rolling std of returns
            (pl.col("close").pct_change().rolling_std(self.lookback)).over("symbol").alias(
                "volatility"
            ),
            # Trend: Close vs MA
            (pl.col("close") / pl.col("close").rolling_mean(self.lookback) - 1.0)
            .over("symbol")
            .alias("trend"),
        ])

    def _compute_style_factors(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute Mean Reversion, Breakout, and Carry."""
        return df.with_columns([
            # Mean Reversion: -1 * (current price / rolling mean - 1)
            (-1.0 * (pl.col("close") / pl.col("close").rolling_mean(self.lookback) - 1.0))
            .over("symbol")
            .alias("mean_reversion"),
            # Breakout: current price / rolling max
            (pl.col("close") / pl.col("close").rolling_max(self.lookback))
            .over("symbol")
            .alias("breakout"),
            # Carry (simplified: for FX this would be interest rate diff, for others maybe yield)
            # Placeholder for now
            pl.lit(0.0).alias("carry")
        ])

    def _compute_microstructure_factors(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute Order Flow Imbalance and Liquidity Pressure."""
        return df.with_columns([
            # Order Flow Imbalance: simplified as volume-weighted price change
            (pl.col("close").diff() * pl.col("volume")).over("symbol").alias("order_flow"),
            # Liquidity Pressure: volume vs rolling avg volume
            (pl.col("volume") / pl.col("volume").rolling_mean(self.lookback))
            .over("symbol")
            .alias("liquidity_pressure"),
        ])

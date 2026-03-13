
import polars as pl


class VectorizedEngine:
    """
    High-performance research engine for rapid factor validation.
    Operates on complete DataFrames (no event loops).
    """

    def __init__(self) -> None:
        pass

    def backtest(
        self,
        df: pl.DataFrame,
        signal_col: str,
        price_col: str = "close",
        transaction_cost: float = 0.0001,
    ) -> pl.DataFrame:
        """
        Runs a vectorized backtest on a Polars DataFrame.
        Expects a signal column (e.g., -1, 0, 1).
        """
        # 1. Shift signal by 1 period to avoid lookahead (trade at next bar's price)
        df = df.with_columns(
            [
                pl.col(signal_col).shift(1).alias("_exec_signal"),
            ]
        )
        
        # 2. Calculate returns
        df = df.with_columns(
            [
                pl.col(price_col).pct_change().alias("_asset_return"),
            ]
        )
        
        # 3. Strategy returns (signal * return)
        df = df.with_columns(
            [
                (pl.col("_exec_signal") * pl.col("_asset_return")).alias("strategy_return"),
            ]
        )
        
        # 4. Subtract transaction costs only when signal changes (simplified)
        df = df.with_columns(
            [
                pl.col("_exec_signal").diff().abs().fill_null(0).alias("_turnover"),
            ]
        )
        df = df.with_columns(
            [
                (pl.col("strategy_return") - (pl.col("_turnover") * transaction_cost)).alias("net_return"),
            ]
        )
        
        # 5. Cumulative returns
        df = df.with_columns(
            [
                (pl.col("net_return") + 1).cum_prod().alias("equity_curve"),
            ]
        )
        
        return df

    def compare_assets(self, df_multi: pl.DataFrame) -> pl.DataFrame:
        """Example of a cross-sectional vectorized calculation."""
        # Assuming df_multi has 'symbol', 'timestamp', and 'return'
        return df_multi.with_columns(
            [
                pl.col("return").rank(descending=True).over("timestamp").alias("rank"),
            ]
        )

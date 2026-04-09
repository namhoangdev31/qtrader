import logging
from datetime import datetime, timedelta
from pathlib import Path
import polars as pl

__all__ = ["DataLake"]


class DataLake:
    def __init__(self, base_path: str = "qtrader/data/datalake") -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_path(self, symbol: str, timeframe: str) -> Path:
        return self.base_path / f"symbol={symbol}" / f"tf={timeframe}" / "data.parquet"

    def save_data(self, df: pl.DataFrame, symbol: str, timeframe: str) -> None:
        target_path = self._get_path(symbol, timeframe)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(target_path, compression="snappy")
        logging.info("Saved %s %s to %s", symbol, timeframe, target_path)

    def load_data(self, symbol: str, timeframe: str) -> pl.DataFrame:
        path = self._get_path(symbol, timeframe)
        if not path.exists():
            raise FileNotFoundError(f"No data found for {symbol} at {timeframe}")
        return pl.read_parquet(path)

    def load(
        self,
        symbols: list[str],
        timeframe: str,
        start_date: str | None = None,
        end_date: str | None = None,
        last_n_days: int | None = None,
    ) -> pl.DataFrame:
        dfs: list[pl.DataFrame] = []
        for sym in symbols:
            try:
                df = self.load_data(sym, timeframe)
            except FileNotFoundError:
                logging.warning("Skipping missing symbol %s %s", sym, timeframe)
                continue
            if df.is_empty():
                continue
            if "timestamp" not in df.columns and "date" in df.columns:
                df = df.rename({"date": "timestamp"})
            df = df.with_columns(pl.lit(sym).alias("symbol"))
            if start_date is not None or end_date is not None or last_n_days is not None:
                if last_n_days is not None:
                    max_str = df.select(pl.col("timestamp").dt.strftime("%Y-%m-%d").max()).item()
                    if max_str is not None:
                        max_d = datetime.strptime(str(max_str)[:10], "%Y-%m-%d")
                        min_d = max_d - timedelta(days=last_n_days)
                        min_str = min_d.strftime("%Y-%m-%d")
                        df = df.filter(pl.col("timestamp").dt.strftime("%Y-%m-%d") >= min_str)
                if start_date is not None:
                    df = df.filter(pl.col("timestamp").dt.strftime("%Y-%m-%d") >= start_date)
                if end_date is not None:
                    df = df.filter(pl.col("timestamp").dt.strftime("%Y-%m-%d") <= end_date)
            dfs.append(df)
        if not dfs:
            return pl.DataFrame()
        return pl.concat(dfs, how="vertical")

    def get_all_symbols(self) -> list[str]:
        return [p.name.split("=")[1] for p in self.base_path.glob("symbol=*")]

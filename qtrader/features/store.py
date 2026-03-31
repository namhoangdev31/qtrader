"""DuckDB-backed FeatureStore with Parquet fallback.

Stores features per symbol/timeframe with time-range and column filtering.
Uses DuckDB for fast analytical queries; falls back to Parquet on failure.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    import duckdb

__all__ = ["FeatureStore"]

_LOG = logging.getLogger("qtrader.features.store")


class FeatureStore:
    """Persistent feature storage: DuckDB primary, Parquet fallback.

    Features are stored in DuckDB table ``features_{symbol}_{timeframe}``.
    On write failure (missing DuckDB, schema mismatch), falls back to Parquet.

    Args:
        base_path: Root directory for Parquet fallback.
        use_duckdb: Enable DuckDB storage (default True).
        duckdb_path: Path to the DuckDB database file.
    """

    def __init__(
        self,
        base_path: str = "./data_lake/features",
        use_duckdb: bool = True,
        duckdb_path: str = "./qtrader.db",
    ) -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.use_duckdb = use_duckdb
        self.duckdb_path = duckdb_path
        self._conn: object | None = None
        if use_duckdb:
            self._init_duckdb()

    def _init_duckdb(self) -> None:
        try:
            import duckdb  # type: ignore[import]
            self._conn = duckdb.connect(self.duckdb_path)
            _LOG.debug("DuckDB feature store initialized at %s", self.duckdb_path)
        except Exception as exc:
            _LOG.warning("DuckDB unavailable (%s); using Parquet fallback.", exc)
            self._conn = None

    @staticmethod
    def _table_name(symbol: str, timeframe: str) -> str:
        safe_sym = symbol.replace("/", "_").replace("-", "_")
        return f"features_{safe_sym}_{timeframe}"

    def _parquet_path(self, symbol: str, timeframe: str) -> Path:
        safe_sym = symbol.replace("/", "_").replace("-", "_")
        return self.base_path / f"symbol={safe_sym}" / f"tf={timeframe}" / "features.parquet"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_features(
        self,
        df: pl.DataFrame,
        symbol: str,
        timeframe: str,
        mode: str = "append",
    ) -> None:
        """Persist features to DuckDB (or Parquet fallback).

        Args:
            df: Feature DataFrame; must contain a ``timestamp`` column.
            symbol: Instrument symbol (e.g. "BTC/USDT").
            timeframe: Bar timeframe (e.g. "1d").
            mode: ``"append"`` (default) or ``"overwrite"``.
        """
        if df.is_empty():
            _LOG.debug("save_features: empty DataFrame, skipping.")
            return
        if self._conn is not None:
            try:
                self._save_duckdb(df, symbol, timeframe, mode)
                return
            except Exception as exc:
                _LOG.warning("DuckDB write failed (%s); falling back to Parquet.", exc)
        self._save_parquet(df, symbol, timeframe, mode)

    def _save_duckdb(
        self, df: pl.DataFrame, symbol: str, timeframe: str, mode: str
    ) -> None:
        tbl = self._table_name(symbol, timeframe)
        conn: duckdb.DuckDBPyConnection = self._conn  # type: ignore[assignment]
        df.to_arrow()
        if mode == "overwrite":
            conn.execute(f'DROP TABLE IF EXISTS "{tbl}"')
        # CREATE or INSERT
        conn.execute(
            f'CREATE TABLE IF NOT EXISTS "{tbl}" AS SELECT * FROM arrow WHERE 1=0'
        )
        conn.execute(f'INSERT INTO "{tbl}" SELECT * FROM arrow')
        _LOG.debug("Saved %d rows to DuckDB table '%s'.", df.height, tbl)

    def _save_parquet(
        self, df: pl.DataFrame, symbol: str, timeframe: str, mode: str
    ) -> None:
        path = self._parquet_path(symbol, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append" and path.exists():
            existing = pl.read_parquet(path)
            df = pl.concat([existing, df], how="vertical").unique(
                subset=["timestamp"] if "timestamp" in df.columns else None,
                keep="last",
            )
        df.write_parquet(path, compression="snappy")
        _LOG.debug("Saved %d rows to Parquet at %s.", df.height, path)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load_features(
        self,
        symbol: str,
        timeframe: str,
        start_ts: str | None = None,
        end_ts: str | None = None,
        feature_names: list[str] | None = None,
    ) -> pl.DataFrame:
        """Load features with optional time-range and column filters.

        Args:
            symbol: Instrument symbol.
            timeframe: Bar timeframe.
            start_ts: ISO-format start timestamp filter (inclusive).
            end_ts: ISO-format end timestamp filter (inclusive).
            feature_names: Subset of feature columns to load (None = all).

        Returns:
            Feature DataFrame, or empty DataFrame if no data found.
        """
        if self._conn is not None:
            try:
                return self._load_duckdb(symbol, timeframe, start_ts, end_ts, feature_names)
            except Exception as exc:
                _LOG.warning("DuckDB read failed (%s); falling back to Parquet.", exc)
        return self._load_parquet(symbol, timeframe, start_ts, end_ts, feature_names)

    def _load_duckdb(
        self,
        symbol: str,
        timeframe: str,
        start_ts: str | None,
        end_ts: str | None,
        feature_names: list[str] | None,
    ) -> pl.DataFrame:
        conn: duckdb.DuckDBPyConnection = self._conn  # type: ignore[assignment]
        tbl = self._table_name(symbol, timeframe)
        tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
        if tbl not in tables:
            return pl.DataFrame()

        cols = "*"
        if feature_names is not None:
            safe_cols = ", ".join(f'"{c}"' for c in (["timestamp", *feature_names]))
            cols = safe_cols

        filters: list[str] = []
        if start_ts:
            filters.append(f"\"timestamp\" >= TIMESTAMP '{start_ts}'")
        if end_ts:
            filters.append(f"\"timestamp\" <= TIMESTAMP '{end_ts}'")
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        sql = f'SELECT {cols} FROM "{tbl}" {where} ORDER BY timestamp'
        arrow = conn.execute(sql).arrow()
        return pl.from_arrow(arrow)

    def _load_parquet(
        self,
        symbol: str,
        timeframe: str,
        start_ts: str | None,
        end_ts: str | None,
        feature_names: list[str] | None,
    ) -> pl.DataFrame:
        path = self._parquet_path(symbol, timeframe)
        if not path.exists():
            return pl.DataFrame()
        df = pl.read_parquet(path)
        if "timestamp" in df.columns:
            if start_ts:
                df = df.filter(pl.col("timestamp") >= pl.lit(start_ts).str.to_datetime())
            if end_ts:
                df = df.filter(pl.col("timestamp") <= pl.lit(end_ts).str.to_datetime())
        if feature_names is not None:
            select_cols = [c for c in (["timestamp", *feature_names]) if c in df.columns]
            df = df.select(select_cols)
        return df

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_feature_names(self, symbol: str, timeframe: str) -> list[str]:
        """Return list of stored feature column names for symbol/timeframe.

        Args:
            symbol: Instrument symbol.
            timeframe: Bar timeframe.

        Returns:
            List of column names excluding ``timestamp``.
        """
        df = self.load_features(symbol, timeframe)
        if df.is_empty():
            return []
        return [c for c in df.columns if c != "timestamp"]

    def list_symbols(self) -> list[str]:
        """Return all symbols that have feature data stored.

        Returns:
            List of symbol strings with stored features.
        """
        if self._conn is not None:
            try:
                conn: duckdb.DuckDBPyConnection = self._conn  # type: ignore[assignment]
                tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
                syms = set()
                for t in tables:
                    if t.startswith("features_"):
                        parts = t[len("features_"):].rsplit("_", 1)
                        if parts:
                            syms.add(parts[0].replace("_", "/"))
                return sorted(syms)
            except Exception:
                pass
        # Parquet fallback
        symbols: list[str] = []
        for sym_dir in self.base_path.glob("symbol=*"):
            sym = sym_dir.name.replace("symbol=", "").replace("_", "/")
            symbols.append(sym)
        return sorted(symbols)


"""
# Pytest-style unit tests:

def test_feature_store_parquet_roundtrip(tmp_path) -> None:
    import polars as pl
    from datetime import datetime
    from qtrader.features.store import FeatureStore

    store = FeatureStore(base_path=str(tmp_path), use_duckdb=False)
    df = pl.DataFrame({
        "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
        "rsi_14": [55.0, 60.0],
        "atr_14": [1.2, 1.3],
    })
    store.save_features(df, "BTC/USDT", "1d", mode="overwrite")
    loaded = store.load_features("BTC/USDT", "1d")
    assert loaded.height == 2
    assert "rsi_14" in loaded.columns

def test_feature_store_list_symbols(tmp_path) -> None:
    import polars as pl
    from datetime import datetime
    from qtrader.features.store import FeatureStore

    store = FeatureStore(base_path=str(tmp_path), use_duckdb=False)
    df = pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "rsi_14": [50.0]})
    store.save_features(df, "ETH/USDT", "1h")
    syms = store.list_symbols()
    assert any("ETH" in s for s in syms)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import httpx
import numpy as np
import polars as pl
from loguru import logger

from qtrader.analytics.ev_calculator import EVCalculator
from qtrader.analytics.performance import PerformanceAnalytics
from qtrader.backtest.engine_vectorized import VectorizedEngine
from qtrader.backtest.tearsheet import TearsheetGenerator
from qtrader.core.config import Config
from qtrader.data.datalake import DataLake
from qtrader.data.datalake_universal import UniversalDataLake
from qtrader.data.duckdb_client import DuckDBClient
from qtrader.data.market.coinbase_market import CoinbaseMarketDataClient
from qtrader.execution.paper_engine import PaperTradingEngine
from qtrader.features.store import FeatureStore
from qtrader.research.report import ReportBuilder

try:
    from scripts.generate_test_data import generate_synthetic_data
except ImportError:
    generate_synthetic_data = None

API_SUCCESS_CODE = 200


class RoleContext(str, Enum):
    ANALYST = "analyst"
    RESEARCHER = "researcher"
    TRADER = "trader"


class AnalystSession:
    def __init__(self, role: RoleContext | str = RoleContext.ANALYST) -> None:
        self._log = logging.getLogger("qtrader.research")
        self.role = RoleContext(role) if isinstance(role, str) else role
        self._log.info("AnalystSession initialised | role=%s", self.role.value)

    async def load_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        filter_sql: str | None = None,
        source: str = "duckdb",
        days: int | None = None,
    ) -> pl.DataFrame:
        if source == "duckdb":
            try:
                return self._load_from_duckdb(symbol, timeframe, filter_sql)
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                self._log.warning("DuckDB load failed (%s). Falling back to datalake.", exc)
                return await self.load_from_datalake(symbol, timeframe, days=days)
        return await self.load_from_datalake(symbol, timeframe, days=days)

    async def load_from_datalake(
        self, symbol: str, timeframe: str, days: int | None = None
    ) -> pl.DataFrame:
        try:
            return self._load_from_universal(symbol, timeframe)
        except FileNotFoundError as exc:
            self._log.warning("UniversalDataLake missing (%s). Falling back to DataLake.", exc)
            try:
                return self._load_from_local_datalake(symbol, timeframe)
            except FileNotFoundError:
                self._log.warning("DataLake missing. Falling back to Live API.")
                if days is None:
                    days = 365 if self.role == RoleContext.RESEARCHER else 7
                return await self.load_live_ohlcv(symbol, timeframe, days=days)

    def sample_ohlcv(self, symbol: str = "AAPL", days: int = 5) -> pl.DataFrame:
        self._log.warning(f"⚠️ DATA_SOURCE: Generating SYNTHETIC data for {symbol}.")
        if generate_synthetic_data:
            return generate_synthetic_data(symbol=symbol, days=days)
        self._log.error("generate_synthetic_data function missing. Return empty df.")
        return pl.DataFrame()

    async def load_live_ohlcv(self, symbol: str, timeframe: str, days: int = 7) -> pl.DataFrame:
        self._log.info(f"Requesting {days} days of live data for {symbol}...")
        tf_map = {
            "1m": "ONE_MINUTE",
            "5m": "FIVE_MINUTE",
            "15m": "FIFTEEN_MINUTE",
            "30m": "THIRTY_MINUTE",
            "1h": "ONE_HOUR",
            "2h": "TWO_HOUR",
            "6h": "SIX_HOUR",
            "1d": "ONE_DAY",
        }
        granularity = tf_map.get(timeframe, "ONE_HOUR")
        client = CoinbaseMarketDataClient()
        end_dt = datetime.now(Config.tz)
        start_dt = end_dt - timedelta(days=days)
        df = await client.get_candles(symbol, granularity, start=start_dt, end=end_dt)
        if not df.is_empty():
            self._log.info(f"Loaded {len(df)} live candles for {symbol} ({granularity})")
            try:
                lake = UniversalDataLake()
                lake.save_data(df, symbol, timeframe)
            except Exception as e:
                self._log.warning(f"Failed to persist live data to DataLake: {e}")
        else:
            self._log.warning(
                f"No live data returned for {symbol}. Falling back to synthetic mock data."
            )
            df = self.sample_ohlcv(symbol, days)
        return df

    async def get_live_orderbook(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        client = CoinbaseMarketDataClient()
        return await client.get_product_book(symbol, limit)

    async def run_paper_simulation(
        self, symbol: str, strategy_fn: Any, timeframe: str = "1h", days: int = 7
    ) -> Any:
        df = await self.load_live_ohlcv(symbol, timeframe, days)
        engine = PaperTradingEngine(starting_capital=10000.0)
        for row in df.iter_rows(named=True):
            market_state = {
                "bid": float(row["close"]) * 0.9999,
                "ask": float(row["close"]) * 1.0001,
                "top_depth": 5.0,
                "venue": "Coinbase_Sim",
            }
            order = strategy_fn(row)
            if order:
                engine.simulate_fill(order, market_state)
        calculator = EVCalculator(engine.closed_trades)
        return calculator.diagnose(symbol)

    def load_features(self, symbol: str, timeframe: str) -> pl.DataFrame:
        store = FeatureStore()
        df = store.load_features(symbol=symbol, timeframe=timeframe)
        if df.is_empty():
            self._log.warning(
                "No features found for %s/%s - run feature engine first.", symbol, timeframe
            )
        return df

    def make_returns(self, df: pl.DataFrame, price_col: str = "close") -> pl.DataFrame:
        if price_col not in df.columns:
            raise ValueError(f"Missing price column: {price_col}")
        return df.with_columns(pl.col(price_col).pct_change().alias("returns"))

    def add_rolling_features(
        self, df: pl.DataFrame, windows: list[int] | None = None, price_col: str = "close"
    ) -> pl.DataFrame:
        windows = windows or [5, 14, 21]
        cols = []
        for w in windows:
            cols.append(pl.col(price_col).rolling_mean(w).alias(f"sma_{w}"))
            cols.append(pl.col(price_col).rolling_std(w).alias(f"vol_{w}"))
        if "returns" not in df.columns:
            df = self.make_returns(df, price_col)
        w = 14
        cols.append(pl.col("returns").clip(lower_bound=0).rolling_mean(w).alias("avg_gain"))
        cols.append((-pl.col("returns").clip(upper_bound=0)).rolling_mean(w).alias("avg_loss"))
        df = df.with_columns(cols)
        df = df.with_columns(
            (100 - 100 / (1 + pl.col("avg_gain") / (pl.col("avg_loss") + 1e-10))).alias("rsi_14")
        )
        return df

    def describe(self, df: pl.DataFrame) -> dict[str, Any]:
        return {"shape": df.shape, "columns": df.columns, "head": df.head(5)}

    def rich_describe(self, df: pl.DataFrame, numeric_only: bool = True) -> dict[str, Any]:
        num_cols = (
            [c for c in df.columns if df[c].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32)]
            if numeric_only
            else df.columns
        )
        stats: dict[str, Any] = {"shape": df.shape, "numeric_columns": num_cols, "columns": {}}
        for col in num_cols:
            s = df[col].drop_nulls()
            arr = s.to_numpy()
            (q25, q75) = (float(np.percentile(arr, 25)), float(np.percentile(arr, 75)))
            iqr = q75 - q25
            outlier_pct = float(((arr < q25 - 1.5 * iqr) | (arr > q75 + 1.5 * iqr)).mean() * 100)
            mean_ = float(arr.mean())
            std_ = float(arr.std())
            skew_ = float(((arr - mean_) ** 3).mean() / (std_**3 + 1e-10))
            kurt_ = float(((arr - mean_) ** 4).mean() / (std_**4 + 1e-10)) - 3.0
            stats["columns"][col] = {
                "count": len(arr),
                "mean": round(mean_, 6),
                "std": round(std_, 6),
                "min": round(float(arr.min()), 6),
                "q25": round(q25, 6),
                "median": round(float(np.median(arr)), 6),
                "q75": round(q75, 6),
                "max": round(float(arr.max()), 6),
                "skew": round(skew_, 4),
                "kurtosis": round(kurt_, 4),
                "null_pct": round(df[col].null_count() / len(df) * 100, 2),
                "outlier_pct (IQR)": round(outlier_pct, 2),
            }
        return stats

    def rich_describe_table(self, df: pl.DataFrame) -> pl.DataFrame:
        info = self.rich_describe(df)
        rows = []
        for col, metrics in info["columns"].items():
            row = {"column": col, **metrics}
            rows.append(row)
        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def run_vector_backtest(
        self,
        df: pl.DataFrame,
        signal_col: str,
        price_col: str = "close",
        transaction_cost: float = 0.0001,
        slippage: float = 5e-05,
    ) -> pl.DataFrame:
        engine = VectorizedEngine()
        return engine.backtest(
            df=df,
            signal_col=signal_col,
            price_col=price_col,
            transaction_cost_bps=transaction_cost * 10000,
            slippage_bps=slippage * 10000,
        )

    def get_monthly_returns(self, backtest_df: pl.DataFrame) -> pl.DataFrame:
        gen = TearsheetGenerator()
        return gen.monthly_returns_table(backtest_df["equity_curve"], backtest_df["timestamp"])

    def performance_metrics(self, equity_curve: pl.Series | pl.DataFrame) -> dict[str, float]:
        series = self._resolve_equity_series(equity_curve)
        return PerformanceAnalytics.calculate_metrics(series)

    def compute_extended_metrics(
        self, equity_curve: pl.Series | pl.DataFrame, periods_per_year: int = 252
    ) -> dict[str, float]:
        series = self._resolve_equity_series(equity_curve)
        base = PerformanceAnalytics.calculate_metrics(series)
        returns = series.pct_change().drop_nulls().to_numpy()
        ann = float(periods_per_year)
        downside = returns[returns < 0]
        downside_vol = float(np.std(downside) * np.sqrt(ann)) if len(downside) > 0 else 1e-10
        ann_ret = float(returns.mean() * ann)
        sortino = ann_ret / downside_vol if downside_vol > 0 else 0.0
        max_dd = abs(base["max_drawdown"])
        calmar = ann_ret / max_dd if max_dd > 0 else 0.0
        win_rate = float((returns > 0).mean())
        gains = returns[returns > 0].sum()
        losses = abs(returns[returns < 0].sum())
        profit_factor = gains / losses if losses > 0 else float("inf")
        omega = gains / losses if losses > 0 else float("inf")
        return {
            **base,
            "sortino_ratio": round(sortino, 4),
            "calmar_ratio": round(calmar, 4),
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 4),
            "omega_ratio": round(omega, 4),
            "periods_per_year": periods_per_year,
        }

    def run_alpha_score(
        self, df: pl.DataFrame, forward_periods: list[int] | None = None
    ) -> pl.DataFrame:
        forward_periods = forward_periods or [1, 5, 10]
        if "returns" not in df.columns:
            df = self.make_returns(df)
        cols = []
        for n in forward_periods:
            cols.append(pl.col("returns").shift(-n).alias(f"fwd_ret_{n}"))
        df = df.with_columns(cols)
        fwd_cols = [f"fwd_ret_{n}" for n in forward_periods]
        df = df.with_columns(
            pl.concat_list([pl.col(c) for c in fwd_cols]).list.mean().alias("alpha_score")
        )
        return df

    def connect_live_api(
        self, host: str = "localhost", port: int = 8000, timeout: float = 5.0
    ) -> dict[str, Any]:
        url = f"http://{host}:{port}/status"
        try:
            resp = httpx.get(url, timeout=timeout)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            self._log.info("Live API connected - status: %s", data.get("engine_status"))
            return data
        except Exception as exc:
            raise RuntimeError(
                f"Could not reach QTrader API at {url}: {exc}\nMake sure the bot is running and the API is started (see docs/analyst.md)."
            ) from exc

    def ping_live_api(self, host: str = "localhost", port: int = 8000) -> bool:
        try:
            r = httpx.get(f"http://{host}:{port}/health", timeout=2.0)
            return r.status_code == API_SUCCESS_CODE
        except Exception:
            return False

    def export_report(
        self, title: str, sections: dict[str, Any], path: str = "analyst_report.html"
    ) -> str:
        rb = ReportBuilder(title)
        for heading, content in sections.items():
            if isinstance(content, str):
                rb.add_text(heading, content)
            elif isinstance(content, pl.DataFrame):
                rb.add_table(heading, content)
            elif isinstance(content, dict):
                rb.add_table(heading, content)
            elif isinstance(content, pl.Series):
                rb.add_polars_plot(heading, content)
            else:
                try:
                    rb.add_figure(heading, content)
                except Exception as exc:
                    self._log.warning("Skipping section %r: %s", heading, exc)
        saved = rb.save(path)
        return str(saved)

    def info(self) -> None:
        guides = {
            RoleContext.ANALYST: (
                "📊 Quant Analyst Workflow\n"
                "  1. load_ohlcv / sample_ohlcv → load market data\n"
                "  2. make_returns + add_rolling_features → prepare features\n"
                "  3. run_vector_backtest → backtest a signal\n"
                "  4. compute_extended_metrics → Sharpe, Sortino, Calmar, Win Rate\n"
                "  5. export_report → save interactive HTML report\n"
                "  📓 Notebooks: notebooks/analyst/01_EDA_Report.ipynb"
            ),
            RoleContext.RESEARCHER: (
                "🔬 Quant Researcher Workflow\n"
                "  1. load_ohlcv → raw OHLCV\n"
                "  2. add_rolling_features → compute features via FeatureStore\n"
                "  3. run_alpha_score → forward-return scoring\n"
                "  4. MLflow for tracking (see notebooks/researcher/)\n"
                "  5. load_features → pull pre-computed features\n"
                "  📓 Notebooks: notebooks/researcher/01_Feature_Lab.ipynb"
            ),
            RoleContext.TRADER: (
                "⚡ Quant Trader Workflow\n"
                "  1. ping_live_api → check if bot is running\n"
                "  2. connect_live_api → fetch live status\n"
                "  3. load_ohlcv + fills → execution audit\n"
                "  4. compute_extended_metrics on live curve\n"
                "  📓 Notebooks: notebooks/trader/01_Live_Monitor.ipynb"
            ),
        }
        logger.info(guides.get(self.role, "QTrader AnalystSession ready."))

    def __repr__(self) -> str:
        return f"AnalystSession(role={self.role.value!r})"

    def _resolve_equity_series(self, equity_curve: pl.Series | pl.DataFrame) -> pl.Series:
        if isinstance(equity_curve, pl.DataFrame):
            if "equity_curve" not in equity_curve.columns:
                raise ValueError("DataFrame must contain an 'equity_curve' column")
            return equity_curve["equity_curve"]
        return equity_curve

    def _load_from_duckdb(
        self, symbol: str, timeframe: str, filter_sql: str | None
    ) -> pl.DataFrame:
        client = DuckDBClient()
        try:
            return client.query_datalake(symbol=symbol, timeframe=timeframe, filter_sql=filter_sql)
        finally:
            client.close()

    def _load_from_universal(self, symbol: str, timeframe: str) -> pl.DataFrame:
        lake = UniversalDataLake()
        return lake.load_data(symbol=symbol, timeframe=timeframe)

    def _load_from_local_datalake(self, symbol: str, timeframe: str) -> pl.DataFrame:
        lake = DataLake()
        return lake.load_data(symbol=symbol, timeframe=timeframe)

"""Research pipeline: data → features → alpha → regime → ML → backtest → drift → export."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
import yaml

from qtrader.input.alpha.registry import AlphaEngine
from qtrader.output.analytics.drift import DriftMonitor
from qtrader.backtest.integration import BacktestHarness, BacktestResult
from qtrader.backtest.tearsheet import TearsheetMetrics
from qtrader.input.data.datalake import DataLake
from qtrader.input.features.engine import FactorEngine
from qtrader.input.features.store import FeatureStore
from qtrader.ml.regime import RegimeDetector
from qtrader.ml.walk_forward import WalkForwardPipeline

__all__ = ["ResearchPipeline", "ResearchResult"]

_LOG = logging.getLogger("qtrader.pipeline.research")


@dataclass(slots=True)
class ResearchResult:
    """Result of a full research pipeline run."""

    strategy_name: str
    tearsheet: TearsheetMetrics
    backtest_df: pl.DataFrame
    drift_report: dict[str, float]
    approved_for_deployment: bool
    config_path: str | None
    ic_report: dict[str, float]
    regime_stats: pl.DataFrame
    html_report_path: str | None = None


def _compute_multi_symbol_features(
    feature_engine: FactorEngine,
    raw_df: pl.DataFrame,
    timeframe: str,
    store: FeatureStore,
) -> pl.DataFrame:
    """Compute features per symbol and return concatenated DataFrame with symbol column."""
    if raw_df.is_empty() or "symbol" not in raw_df.columns:
        return raw_df
    symbols = raw_df["symbol"].unique().to_list()
    out: list[pl.DataFrame] = []
    for sym in symbols:
        sym_df = raw_df.filter(pl.col("symbol") == sym)
        feats = feature_engine.compute(sym_df)
        if feats.is_empty():
            out.append(sym_df)
            continue
        if "timestamp" in feats.columns:
            merged = sym_df.join(feats.drop("timestamp"), on="timestamp", how="left")
        else:
            merged = pl.concat([sym_df, feats], how="horizontal")
        store.save_features(
            merged.select([c for c in merged.columns if c in feats.columns or c == "timestamp"]),
            sym,
            timeframe,
        )
        out.append(merged)
    return pl.concat(out, how="vertical") if out else raw_df


def _walk_forward_fit_predict(
    df: pl.DataFrame,
    feature_cols: list[str],
    target_col: str,
    train_size: int = 504,
    test_size: int = 126,
    embargo: int = 5,
    predictor_factory: type | None = None,
) -> pl.Series:
    """Run walk-forward train/predict; returns OOS signal series aligned with df (same height)."""
    from qtrader.models.catboost_model import CatBoostPredictor

    pred_cls = predictor_factory or CatBoostPredictor
    wf = WalkForwardPipeline(train_size=train_size, test_size=test_size, embargo=embargo)
    splits = wf.get_splits(df)
    if not splits:
        return pl.Series("ml_signal", [0.0] * len(df))
    oos_rows: list[dict[str, object]] = []
    for train_df, test_df in splits:
        X_train = train_df.select(feature_cols)
        y_train = train_df.select(target_col).to_series()
        X_test = test_df.select(feature_cols)
        model = pred_cls()
        model.train(X_train, y_train)
        preds = model.predict(X_test)
        ts_col = test_df["timestamp"]
        for i in range(test_df.height):
            t = ts_col[i]
            v = float(preds[i]) if preds.dtype in (pl.Float32, pl.Float64) else 0.0
            oos_rows.append({"timestamp": t, "_ml_signal": v})
    if not oos_rows:
        return pl.Series("ml_signal", [0.0] * len(df))
    pred_df = pl.DataFrame(oos_rows)
    joined = df.join(pred_df, on="timestamp", how="left")
    return joined["_ml_signal"].fill_null(0.0).alias("ml_signal")


class ResearchPipeline:
    """
    Orchestrates the full offline research workflow: load data, compute features,
    run alphas, detect regimes, train ML (optional), backtest, drift check, export.
    """

    def __init__(
        self,
        datalake: DataLake,
        feature_engine: FactorEngine,
        alpha_engine: AlphaEngine,
        regime_detector: RegimeDetector,
        backtest_harness: BacktestHarness,
        drift_monitor: DriftMonitor,
        model_registry: object | None = None,
    ) -> None:
        self.datalake = datalake
        self.feature_engine = feature_engine
        self.alpha_engine = alpha_engine
        self.regime_detector = regime_detector
        self.backtest_harness = backtest_harness
        self.drift_monitor = drift_monitor
        self.model_registry = model_registry

    def run(
        self,
        symbols: list[str],
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy_name: str = "momentum",
        walk_forward: bool = True,
        transaction_cost_bps: float = 10.0,
        target_sharpe: float = 1.5,
        target_max_dd: float = 0.15,
        target_win_rate: float = 0.50,
    ) -> ResearchResult:
        """
        Run full pipeline: load → features → alpha → regime → (optional) ML → backtest → drift → gate.

        Args:
            symbols: Instrument symbols.
            timeframe: Bar timeframe (e.g. "1d").
            start_date: Start date YYYY-MM-DD.
            end_date: End date YYYY-MM-DD.
            strategy_name: "momentum" | "mean_reversion" | "stat_arb".
            walk_forward: If True, run walk-forward ML and use ml_signal for backtest.
            transaction_cost_bps: Cost in bps.
            target_sharpe: Minimum Sharpe to approve for deployment.
            target_max_dd: Maximum allowed max drawdown (e.g. 0.15).
            target_win_rate: Minimum win rate to approve.

        Returns:
            ResearchResult with tearsheet, backtest_df, drift_report, approval flag, config path.
        """
        raw_df = self.datalake.load(
            symbols=symbols,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )
        if raw_df.is_empty():
            _LOG.warning("No data loaded for %s %s–%s", symbols, start_date, end_date)
            empty_tearsheet = TearsheetMetrics(
                total_return=0.0, ann_return=0.0, ann_volatility=0.0,
                sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0, omega_ratio=0.0,
                max_drawdown=0.0, max_dd_duration_days=0, avg_dd_duration_days=0.0, recovery_time_days=0.0,
                total_trades=0, win_rate=0.0, avg_win_pct=0.0, avg_loss_pct=0.0,
                profit_factor=0.0, expected_value=0.0, avg_turnover_daily=0.0, total_cost_pct=0.0,
                skewness=0.0, kurtosis=0.0,
            )
            return ResearchResult(
                strategy_name=strategy_name,
                tearsheet=empty_tearsheet,
                backtest_df=pl.DataFrame(),
                drift_report={},
                approved_for_deployment=False,
                config_path=None,
                ic_report={},
                regime_stats=pl.DataFrame(),
                html_report_path=None,
            )

        full_df = _compute_multi_symbol_features(
            self.feature_engine,
            raw_df,
            timeframe,
            self.feature_engine.store,
        )
        feature_cols = self.feature_engine.get_all_feature_names()

        alpha_dfs: list[pl.DataFrame] = []
        for sym in full_df["symbol"].unique().to_list():
            sym_df = full_df.filter(pl.col("symbol") == sym)
            alpha_out = self.alpha_engine.compute_all(sym_df)
            alpha_out = alpha_out.with_columns(pl.lit(sym).alias("symbol"))
            alpha_dfs.append(alpha_out)
        alpha_df = pl.concat(alpha_dfs, how="vertical") if alpha_dfs else full_df

        regime_cols = [c for c in feature_cols if c in alpha_df.columns]
        if regime_cols:
            self.regime_detector.fit(alpha_df, regime_cols)
            regime_series = self.regime_detector.predict_regime(alpha_df, regime_cols)
            alpha_df = alpha_df.with_columns(regime_series)

        signal_col = "ml_signal"
        backtest_symbol = symbols[0]
        single_df = alpha_df.filter(pl.col("symbol") == backtest_symbol)
        if single_df.is_empty():
            single_df = alpha_df

        if walk_forward and regime_cols and "close" in single_df.columns:
            single_df = single_df.sort("timestamp")
            single_df = single_df.with_columns(
                pl.col("close").pct_change().shift(-1).alias("forward_return"),
            ).drop_nulls("forward_return")
            fcols = [c for c in feature_cols if c in single_df.columns]
            if fcols:
                oos = _walk_forward_fit_predict(
                    single_df,
                    feature_cols=fcols,
                    target_col="forward_return",
                )
                if oos.len() != single_df.height:
                    oos = pl.Series("ml_signal", [0.0] * single_df.height)
                single_df = single_df.with_columns(oos.alias(signal_col))
            else:
                signal_col = "composite_alpha"
        else:
            signal_col = "composite_alpha" if "composite_alpha" in single_df.columns else "momentum"

        if signal_col not in single_df.columns:
            single_df = single_df.with_columns(pl.lit(0.0).alias(signal_col))

        bt_result = self.backtest_harness.run(
            df=single_df,
            signal_col=signal_col,
            strategy_name=strategy_name,
            transaction_cost_bps=transaction_cost_bps,
            output_html=True,
            price_col="close",
        )
        result = bt_result

        ic_report: dict[str, float] = {}
        for name in self.alpha_engine.alpha_names:
            if name in single_df.columns and "close" in single_df.columns:
                ret = single_df["close"].pct_change()
                self.alpha_engine.update_ic(name, ret)
                ic_report[name] = self.alpha_engine._ic.get(name, 0.0)

        regime_stats = pl.DataFrame()
        if "regime" in single_df.columns:
            regime_stats = self.regime_detector.get_regime_stats(
                single_df.select("close"),
                single_df["regime"],
            )

        live_df = self.datalake.load(
            symbols=symbols,
            timeframe=timeframe,
            last_n_days=30,
        )
        drift_report: dict[str, float] = {}
        if not live_df.is_empty():
            live_features = _compute_multi_symbol_features(
                self.feature_engine,
                live_df,
                timeframe,
                self.feature_engine.store,
            )
            drift_report = self.drift_monitor.detect_drift(
                full_df.select([c for c in feature_cols if c in full_df.columns]),
                live_features.select([c for c in feature_cols if c in live_features.columns]),
                [c for c in feature_cols if c in full_df.columns and c in live_features.columns],
            )

        ts = result.tearsheet
        approved = (
            ts.sharpe_ratio >= target_sharpe
            and ts.max_drawdown <= target_max_dd
            and ts.win_rate >= target_win_rate
        )
        config_path = None
        if approved:
            config_path = self._export_to_bot_config(bt_result, strategy_name)

        return ResearchResult(
            strategy_name=strategy_name,
            tearsheet=bt_result.tearsheet,
            backtest_df=bt_result.backtest_df,
            drift_report=drift_report,
            approved_for_deployment=approved,
            config_path=config_path,
            ic_report=ic_report,
            regime_stats=regime_stats,
            html_report_path=bt_result.html_report_path,
        )

    def _export_to_bot_config(self, result: BacktestResult, strategy_name: str) -> str:
        """Write approved backtest params to configs/bot_paper.yaml. Returns path."""
        path = Path("configs/bot_paper.yaml")
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = result.tearsheet
        config: dict[str, object] = {
            "strategy": strategy_name,
            "signal_col": "composite_alpha",
            "execution_algo": "twap",
            "best_sharpe": ts.sharpe_ratio,
            "win_rate": ts.win_rate,
            "max_drawdown": ts.max_drawdown,
            "kelly_fraction": ts.expected_value,
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, default_flow_style=False)
        baseline_path = Path("reports/latest_baseline.json")
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        ts.to_json(str(baseline_path))
        _LOG.info("Exported bot config to %s and baseline to %s", path, baseline_path)
        return str(path)


if __name__ == "__main__":
    # Doctest / pytest-style: minimal smoke (requires data and harness)
    # def test_research_result_has_tearsheet() -> None:
    #     r = ResearchResult("m", TearsheetMetrics(...), pl.DataFrame(), {}, False, None, {}, pl.DataFrame())
    #     assert r.strategy_name == "m"
    pass

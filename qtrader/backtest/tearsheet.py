from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Literal

import numpy as np
import polars as pl

__all__ = ["TearsheetMetrics", "TearsheetGenerator"]


@dataclass(slots=True)
class TearsheetMetrics:
    """Comprehensive performance metrics for institutional strategies."""

    total_return: float
    ann_return: float
    ann_volatility: float

    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    omega_ratio: float

    max_drawdown: float
    max_dd_duration_days: int
    avg_dd_duration_days: float
    recovery_time_days: float

    total_trades: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float
    expected_value: float

    avg_turnover_daily: float
    total_cost_pct: float

    skewness: float
    kurtosis: float

    def to_json(self, path: str | Path) -> str:
        """Serialize metrics to a JSON file (e.g. sidecar next to HTML tearsheet).

        Args:
            path: File path to write.

        Returns:
            Absolute path to the written file.
        """
        p = Path(path).expanduser().absolute()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        return str(p)

    @classmethod
    def from_json(cls, path: str | Path) -> TearsheetMetrics:
        """Load TearsheetMetrics from a JSON file.

        Args:
            path: Path to JSON file (e.g. reports/latest_baseline.json).

        Returns:
            TearsheetMetrics instance.
        """
        p = Path(path).expanduser().absolute()
        if not p.exists():
            raise FileNotFoundError(f"Baseline metrics not found: {path}")
        with open(p, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TearsheetGenerator:
    """Generate summary metrics and HTML reports for backtests."""

    def generate(
        self,
        backtest_result: pl.DataFrame,
        strategy_name: str,
        benchmark_returns: pl.Series | None = None,
        periods_per_year: int = 252,
    ) -> TearsheetMetrics:
        """Compute TearsheetMetrics from a backtest result.

        Args:
            backtest_result: DataFrame with at least ``net_return``, ``equity_curve``,
                and ``drawdown`` columns.
            strategy_name: Name used for display (currently informational only).
            benchmark_returns: Optional benchmark return series.
            periods_per_year: Trading periods per year.

        Returns:
            TearsheetMetrics dataclass instance.
        """
        if "net_return" not in backtest_result.columns or "equity_curve" not in backtest_result.columns:
            raise ValueError("backtest_result must contain 'net_return' and 'equity_curve'.")

        net_ret = backtest_result["net_return"].to_numpy()
        eq = backtest_result["equity_curve"].to_numpy()
        if net_ret.size == 0 or eq.size == 0:
            raise ValueError("backtest_result is empty.")

        total_return = float(eq[-1] / eq[0] - 1.0)

        mean_ret = float(np.nanmean(net_ret))
        vol = float(np.nanstd(net_ret))
        ann_return = (1.0 + mean_ret) ** periods_per_year - 1.0
        ann_vol = vol * np.sqrt(periods_per_year)
        sharpe = 0.0 if ann_vol == 0.0 else ann_return / ann_vol

        downside = np.minimum(net_ret, 0.0)
        downside_vol = float(np.sqrt(np.nanmean(downside**2)) * np.sqrt(periods_per_year))
        sortino = 0.0 if downside_vol == 0.0 else ann_return / downside_vol

        running_max = np.maximum.accumulate(eq)
        drawdowns = eq / running_max - 1.0
        max_dd = float(np.min(drawdowns))

        calmar = 0.0 if max_dd == 0.0 else ann_return / abs(max_dd)

        gains = net_ret[net_ret > 0.0]
        losses = net_ret[net_ret < 0.0]
        omega = 0.0
        if losses.size > 0:
            omega = float(np.sum(gains) / abs(np.sum(losses))) if np.sum(losses) != 0.0 else 0.0

        # Drawdown durations (approximate by counting consecutive negative drawdowns).
        dd_durations: list[int] = []
        current = 0
        for d in drawdowns:
            if d < 0:
                current += 1
            elif current > 0:
                dd_durations.append(current)
                current = 0
        if current > 0:
            dd_durations.append(current)
        max_dd_duration = max(dd_durations) if dd_durations else 0
        avg_dd_duration = float(np.mean(dd_durations)) if dd_durations else 0.0
        recovery_time = avg_dd_duration

        # Trade statistics: infer from sign changes if trade-level data absent.
        exec_signal_col = "_exec_signal" if "_exec_signal" in backtest_result.columns else None
        total_trades = 0
        win_rate = 0.0
        avg_win_pct = 0.0
        avg_loss_pct = 0.0
        profit_factor = 0.0
        expected_value = 0.0
        if exec_signal_col is not None:
            sig = backtest_result[exec_signal_col].to_numpy()
            trade_returns: list[float] = []
            current_ret = 0.0
            for i in range(1, len(sig)):
                if sig[i] == sig[i - 1]:
                    current_ret += net_ret[i]
                else:
                    if current_ret != 0.0:
                        trade_returns.append(current_ret)
                    current_ret = 0.0
            if current_ret != 0.0:
                trade_returns.append(current_ret)
            if trade_returns:
                total_trades = len(trade_returns)
                tr_np = np.array(trade_returns, dtype=float)
                wins = tr_np[tr_np > 0.0]
                losses = tr_np[tr_np < 0.0]
                win_rate = float(len(wins) / total_trades)
                avg_win_pct = float(np.mean(wins)) if wins.size else 0.0
                avg_loss_pct = float(np.mean(losses)) if losses.size else 0.0
                profit_factor = (
                    float(np.sum(wins) / abs(np.sum(losses))) if losses.size and np.sum(losses) != 0.0 else 0.0
                )
                expected_value = float(np.mean(tr_np))

        # Execution metrics if turnover / cost present.
        avg_turnover_daily = 0.0
        total_cost_pct = 0.0
        if "_turnover" in backtest_result.columns and "_cost" in backtest_result.columns:
            avg_turnover_daily = float(backtest_result["_turnover"].mean())
            total_cost_pct = float(backtest_result["_cost"].sum())

        # Distribution stats.
        mu = mean_ret
        if vol > 0.0:
            skew = float(np.nanmean(((net_ret - mu) / vol) ** 3))
            kurt = float(np.nanmean(((net_ret - mu) / vol) ** 4) - 3.0)
        else:
            skew = 0.0
            kurt = 0.0

        return TearsheetMetrics(
            total_return=total_return,
            ann_return=ann_return,
            ann_volatility=ann_vol,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            omega_ratio=omega,
            max_drawdown=max_dd,
            max_dd_duration_days=int(max_dd_duration),
            avg_dd_duration_days=avg_dd_duration,
            recovery_time_days=recovery_time,
            total_trades=total_trades,
            win_rate=win_rate,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            profit_factor=profit_factor,
            expected_value=expected_value,
            avg_turnover_daily=avg_turnover_daily,
            total_cost_pct=total_cost_pct,
            skewness=skew,
            kurtosis=kurt,
        )

    def monthly_returns_table(
        self,
        equity_curve: pl.Series,
        timestamps: pl.Series,
    ) -> pl.DataFrame:
        """Return calendar-style monthly returns table.

        Args:
            equity_curve: Equity curve series.
            timestamps: Matching timestamp series.

        Returns:
            DataFrame with rows as years and columns Jan..Dec + YTD.
        """
        if equity_curve.len() != timestamps.len():
            raise ValueError("equity_curve and timestamps must have same length.")

        df = pl.DataFrame({"timestamp": timestamps, "equity_curve": equity_curve})
        df = df.sort("timestamp")
        df = df.with_columns(
            [
                pl.col("timestamp").dt.year().alias("year"),
                pl.col("timestamp").dt.month().alias("month"),
            ]
        )

        monthly = (
            df.group_by(["year", "month"])
            .agg(
                [
                    pl.col("equity_curve").first().alias("start"),
                    pl.col("equity_curve").last().alias("end"),
                ]
            )
            .with_columns(((pl.col("end") / pl.col("start") - 1.0) * 100.0).alias("ret_pct"))
        )

        pivot = monthly.pivot(
            values="ret_pct",
            index="year",
            columns="month",
        ).sort("year")

        # Compute YTD column.
        ytd = (
            monthly.group_by("year")
            .agg(
                [
                    ((pl.col("end").max() / pl.col("start").min() - 1.0) * 100.0).alias(
                        "YTD"
                    )
                ]
            )
            .sort("year")
        )

        result = pivot.join(ytd, on="year", how="left")
        return result

    def to_html(
        self,
        metrics: TearsheetMetrics,
        monthly_table: pl.DataFrame,
        backtest_df: pl.DataFrame,
        output_path: str,
        write_json_sidecar: bool = True,
    ) -> str:
        """Generate a minimal self-contained HTML tearsheet.

        The caller is expected to use this in offline research contexts.
        Optionally writes a JSON sidecar with the same base path for LiveMonitor baseline.

        Args:
            metrics: TearsheetMetrics instance.
            monthly_table: Monthly returns table.
            backtest_df: Backtest DataFrame (used for plots).
            output_path: Path where HTML file will be written.
            write_json_sidecar: If True, write metrics to same path with .json extension.

        Returns:
            Absolute path to the saved HTML file.
        """
        if write_json_sidecar:
            json_path = str(Path(output_path).with_suffix(".json"))
            metrics.to_json(json_path)
        metrics_dict = self.to_dict(metrics)
        eq = backtest_df.select(["timestamp", "equity_curve", "drawdown"])

        html = [
            "<html><head><meta charset='utf-8'><title>Tearsheet</title>",
            "<style>",
            "body { font-family: Arial, sans-serif; margin: 20px; }",
            "table { border-collapse: collapse; width: 100%; margin-bottom: 20px; }",
            "th, td { border: 1px solid #ddd; padding: 4px; font-size: 12px; }",
            "th { background-color: #f2f2f2; }",
            ".pos { background-color: #d4f4dd; }",
            ".neg { background-color: #f8d7da; }",
            "</style></head><body>",
            "<h1>Tearsheet</h1>",
            "<h2>Summary Metrics</h2><table><tbody>",
        ]
        for k, v in metrics_dict.items():
            html.append(f"<tr><th>{k}</th><td>{v:.4f}</td></tr>")
        html.append("</tbody></table>")

        html.append("<h2>Monthly Returns (%)</h2><table><thead><tr><th>Year</th>")
        month_cols = [c for c in monthly_table.columns if c != "year"]
        for c in month_cols:
            html.append(f"<th>{c}</th>")
        html.append("</tr></thead><tbody>")
        for row in monthly_table.iter_rows(named=True):
            html.append("<tr>")
            html.append(f"<td>{row['year']}</td>")
            for c in month_cols:
                val = row.get(c)
                if val is None:
                    html.append("<td></td>")
                else:
                    cls: Literal["pos", "neg"] | str = "pos" if val >= 0 else "neg"
                    html.append(f"<td class='{cls}'>{val:.2f}</td>")
            html.append("</tr>")
        html.append("</tbody></table>")

        # Simple equity curve listing (table-based).
        html.append("<h2>Equity Curve (sample)</h2><table><thead><tr><th>Timestamp</th><th>Equity</th><th>Drawdown</th></tr></thead><tbody>")
        for row in eq.tail(50).iter_rows(named=True):
            html.append(
                f"<tr><td>{row['timestamp']}</td><td>{row['equity_curve']:.2f}</td><td>{row['drawdown']:.4f}</td></tr>"
            )
        html.append("</tbody></table>")

        html.append("</body></html>")
        html_str = "".join(html)

        path = Path(output_path).expanduser().absolute()
        path.write_text(html_str, encoding="utf-8")
        return str(path)

    def to_dict(self, metrics: TearsheetMetrics) -> Dict[str, float]:
        """Serialize TearsheetMetrics to a flat dict."""
        raw = asdict(metrics)
        return {k: float(v) for k, v in raw.items()}


if __name__ == "__main__":
    _ts = pl.date_range(
        low=pl.datetime(2024, 1, 1),
        high=pl.datetime(2024, 3, 31),
        interval="1d",
        eager=True,
    )
    _net = pl.Series("net_return", np.random.normal(0.0005, 0.01, len(_ts)))
    _eq = (1.0 + _net).cum_prod() * 100_000.0
    _dd = _eq / np.maximum.accumulate(_eq) - 1.0
    _df = pl.DataFrame({"timestamp": _ts, "net_return": _net, "equity_curve": _eq, "drawdown": _dd})

    _gen = TearsheetGenerator()
    _m = _gen.generate(_df, strategy_name="demo")
    _mt = _gen.monthly_returns_table(_df["equity_curve"], _df["timestamp"])
    _ = _gen.to_html(_m, _mt, _df, "/tmp/tearsheet_demo.html")


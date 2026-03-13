# Analyst Platform – Jupyter & Google Colab

QTrader's Analyst Platform provides role-specific notebooks for Quant Analysts, Researchers, and Traders.

## Quick Launch

| Role | Command | Notebooks |
|---|---|---|
| **Quant Analyst** | `make analyst` | `notebooks/analyst/` |
| **Quant Researcher** | `make analyst-researcher` | `notebooks/researcher/` |
| **Quant Trader** | `make analyst-trader` | `notebooks/trader/` |

## Google Colab

Open **`notebooks/Colab_Quickstart.ipynb`** in Google Colab, set:

```python
REPO_URL = "https://github.com/YOUR_ORG/qtrader.git"
BRANCH   = "main"
ROLE     = "analyst"   # or "researcher" / "trader"
USE_GDRIVE = False     # True to mount Google Drive as datalake
```

Then **Run All**. The setup cell clones the repo, installs dependencies, and initialises the role-specific session.

---

## Notebook Library

### 📊 Analyst

| Notebook | Description |
|---|---|
| `analyst/01_EDA_Report.ipynb` | Load OHLCV → rich statistics → distributions → rolling vol → HTML export |
| `analyst/02_Backtest_Report.ipynb` | Signal → vector backtest → Sharpe/Sortino/Calmar/Win Rate → equity curve |
| `analyst/03_Risk_Report.ipynb` | Multi-asset → VaR/CVaR → correlation heatmap → tail distribution |

### 🔬 Researcher

| Notebook | Description |
|---|---|
| `researcher/01_Feature_Lab.ipynb` | Feature engineering → IC heatmap → drift check → FeatureStore save |
| `researcher/02_Regime_Lab.ipynb` | GMM regime detection → conditional stats → rotation backtest |
| `researcher/03_ML_Experiment.ipynb` | Train model → MLflow log → feature importance → compare runs |

### ⚡ Trader

| Notebook | Description |
|---|---|
| `trader/01_Live_Monitor.ipynb` | `connect_live_api` → live engine status → equity/drawdown dashboard |
| `trader/02_Execution_Audit.ipynb` | Fills → slippage analysis → SOR venue breakdown → cost attribution |

---

## AnalystSession API

```python
from qtrader.analyst import AnalystSession, RoleContext

session = AnalystSession(role=RoleContext.ANALYST)
session.info()   # Print role-specific workflow guide

# Data
df = session.load_ohlcv("BTC-USD", "1d")
df = session.sample_ohlcv("BTC", days=365)         # Synthetic fallback
df = session.make_returns(df)
df = session.add_rolling_features(df, windows=[5, 21])

# EDA
stats = session.rich_describe(df)
stats_df = session.rich_describe_table(df)

# Backtest
bt = session.run_vector_backtest(df, signal_col="signal")
metrics = session.compute_extended_metrics(bt["equity_curve"])
# → keys: total_return, sharpe_ratio, sortino_ratio, calmar_ratio, win_rate, profit_factor, ...

# Research
df = session.run_alpha_score(df, forward_periods=[1, 5, 10])
feat_df = session.load_features("BTC-USD", "1d")

# Live (Trader)
ok = session.ping_live_api(host="localhost", port=8000)
status = session.connect_live_api(host="localhost", port=8000)

# Report
out = session.export_report(
    title="My Report",
    sections={"Metrics": metrics, "Equity": bt["equity_curve"]},
    path="reports/my_report.html",
)
```

## HTML Report Builder

```python
from qtrader.analyst.report import ReportBuilder

rb = ReportBuilder("My Analysis")
rb.add_text("Overview", "Strategy: momentum 1h.")
rb.add_table("Metrics", metrics_dict)
rb.add_figure("Equity Curve", fig)           # matplotlib Figure
rb.add_polars_plot("Drawdown", dd_series)    # Polars Series → auto chart
rb.save("reports/analysis.html")
```

## Workflow (Core)

1. **Load** OHLCV from DuckDB datalake → `UniversalDataLake` fallback → `sample_ohlcv()` synthetic.
2. **Compute** returns, rolling features, alpha scores.
3. **Backtest** with `run_vector_backtest`, evaluate with `compute_extended_metrics`.
4. **Export** HTML report with `export_report` or `ReportBuilder`.
5. **Persist** features to `FeatureStore` for researcher workflows.
6. **Monitor** live bot via `connect_live_api` from Trader notebooks.

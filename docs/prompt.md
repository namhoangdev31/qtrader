Constraints (non-negotiable):

- Python 3.10+ with full type hints (no implicit Any)
- Polars only — no pandas, no numpy loops
- All I/O must be async-safe
- Use dataclasses or Pydantic v2 for all data models
- Production logging via standard logging module (no print())
- Each file is self-contained with **all** defined
- Include docstrings (Google style) for all public methods
- Include 2–3 inline unit-test examples as doctests or pytest snippets at the bottom
- Preserve existing qtrader interfaces (EventBus, OrderEvent, FillEvent, SignalEvent)
  You are the lead systems architect at a Tier-1 systematic hedge fund.
  Your task is to wire QTrader's 14 modules into a unified research → backtest → deploy → monitor pipeline.

Repo: /Users/hoangnam/qtrader (Python 3.10+, Polars, asyncio)
[PASTE GLOBAL CONSTRAINTS HERE]

Additional constraints:

- No circular imports. Backtest module must NEVER import from bot/. Use dependency injection.
- All cross-module data flows use Polars DataFrames or typed dataclasses — no dicts of dicts.
- Every interface boundary must be typed with Protocol or dataclass (no Any).
- DriftMonitor must run after every backtest to flag feature/signal decay before bot deployment.

---

### SYSTEM OVERVIEW: The Backtest as the Universal Validation Hub

Current state (what exists but is disconnected):
core/ → EventBus, Config, DBClient ✅
data/ → OHLCVNormalizer, DataLake, DataPipeline ✅ (not feeding backtest)
features/ → FactorEngine, FeatureStore ✅ (not connected to strategy/backtest)
alpha/ → AlphaRegistry, technical.py, microstructure.py ✅ (not connected to strategy)
strategy/ → BaseStrategy (stub on_signal) ✅ (no signal generation wired)
models/ → XGBoostPredictor, CatBoostPredictor ✅ (not connected to strategy/backtest)
ml/ → RegimeDetector, ModelRegistry, WalkForwardPipeline ✅ (isolated)
portfolio/→ HRPOptimizer (incomplete), MVO ✅ (not used in backtest/bot)
risk/ → RuntimeRiskEngine, RealTimeRiskEngine (stubs) ✅ (not connected to bot)
execution/→ UnifiedOMS, SOR, SimulatedBroker ✅ (zero slippage, no PositionManager)
backtest/ → VectorizedEngine (no tearsheet, no slippage) ✅ (disconnected hub)
analytics/→ PerformanceAnalytics, DriftMonitor, Telemetry ✅ (never called)
analyst/ → AnalystSession (multi-role) ✅ (manual, not wired to auto-pipeline)
bot/ → TradingBot (placeholder loops), PerformanceTracker ✅ (no signal gen)

Target state: Unified pipeline with backtest as the validation gate.

---

### FILE SKELETON — New integration files to create:

qtrader/
├── pipeline/ [NEW PACKAGE]
│ ├── **init**.py
│ ├── research.py [NEW — ResearchPipeline: data→features→alpha→backtest]
│ ├── deployment.py [NEW — DeploymentBridge: backtest results→bot config]
│ ├── monitor.py [NEW — LiveMonitor: bot metrics→analytics→alert]
│ └── session_bridge.py [NEW — connects AnalystSession to the full pipeline]
│
├── backtest/
│ ├── integration.py [NEW — BacktestHarness: unified entry point]
│ └── [existing files — upgrade per Prompt 7]
│
└── bot/
└── runner.py [overwrite — fill all Placeholders with real logic]

---

### PHASE 1 — UPSTREAM: Data → Features → Alpha → Strategy (feeding the Backtest)

#### `pipeline/research.py` — ResearchPipeline

class ResearchPipeline:
"""
Orchestrates the full offline research workflow. QDev calls this to: 1. Load OHLCV data from DataLake 2. Compute features via FactorEngine 3. Run alpha factors via AlphaEngine 4. Detect market regimes via RegimeDetector 5. Train ML models (XGBoost/CatBoost) via WalkForwardPipeline 6. Run backtest → TearsheetMetrics 7. Run DriftMonitor on features vs live data 8. If Sharpe > threshold: export params to bot config
"""

    def __init__(
        self,
        datalake: DataLake,
        feature_engine: FactorEngine,
        alpha_engine: AlphaEngine,
        regime_detector: RegimeDetector,
        backtest_harness: "BacktestHarness",
        model_registry: ModelRegistry,
        drift_monitor: DriftMonitor,
    ) -> None: ...

    def run(
        self,
        symbols: list[str],
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy_name: str,           # "momentum" | "mean_reversion" | "stat_arb"
        walk_forward: bool = True,
        transaction_cost_bps: float = 10.0,
        target_sharpe: float = 1.5,   # Minimum to approve for deployment
    ) -> ResearchResult:
        """
        Full pipeline:

        Step 1 — DATA LOADING:
          raw_df = datalake.load(symbols, timeframe, start_date, end_date)
          # Expected cols: timestamp, symbol, open, high, low, close, volume

        Step 2 — FEATURE COMPUTATION:
          features_df = feature_engine.compute_multi_symbol(raw_dfs, timeframe)
          # Cols added: rsi, atr, macd, bollinger, obv, vwap, dollar_volume, momentum...
          feature_engine.store.save_features(features_df, symbol, timeframe)

        Step 3 — ALPHA SIGNALS:
          alpha_df = alpha_engine.compute_all(features_df)
          # Cols added: momentum_alpha, mean_reversion_alpha, trend_alpha,
          #             order_imbalance_alpha, amihud_alpha, vpin_alpha, composite_alpha

        Step 4 — REGIME DETECTION:
          regime_series = regime_detector.predict_regime(alpha_df, feature_cols)
          regime_proba  = regime_detector.predict_proba(alpha_df, feature_cols)
          # Merge regime labels into alpha_df for regime-conditional backtesting

        Step 5 — ML MODEL TRAINING (if walk_forward=True):
          model = XGBoostPredictor() or CatBoostPredictor()
          splits = WalkForwardPipeline(train_size=504, test_size=126, embargo=5)
          oos_signals = walk_forward_fit_predict(model, splits, alpha_df)
          # oos_signals: Polars Series of predicted return direction per bar
          signal_col = "ml_signal"

        Step 6 — BACKTEST:
          result = backtest_harness.run(
              df=alpha_df.with_columns(oos_signals.alias(signal_col)),
              signal_col=signal_col,
              transaction_cost_bps=transaction_cost_bps,
              strategy_name=strategy_name,
          )
          # result.tearsheet: TearsheetMetrics
          # result.backtest_df: pl.DataFrame with equity_curve, drawdown, net_return

        Step 7 — DRIFT CHECK:
          live_sample = datalake.load(symbols, timeframe, last_n_days=30)
          drift_results = drift_monitor.detect_drift(
              train_data=features_df,
              live_data=feature_engine.compute_multi_symbol({s: live_sample}, timeframe),
              columns=feature_engine.get_all_feature_names()
          )
          # Flag alert if any KS p_value < 0.05 (feature distribution shifted)

        Step 8 — GATE CHECK & EXPORT:
          approved = result.tearsheet.sharpe_ratio >= target_sharpe
                     and result.tearsheet.max_drawdown <= 0.15
                     and result.tearsheet.win_rate >= 0.50
          if approved:
              self._export_to_bot_config(result, strategy_name)

        Return: ResearchResult
        """
        ...

    def _export_to_bot_config(self, result: "ResearchResult", strategy_name: str) -> str:
        """Serialize validated params to YAML at configs/bot_paper.yaml.
        Returns path to written config file.

        Config includes: best_sharpe, win_rate, max_drawdown, signal_col,
        strategy_name, execution_algo, kelly_fraction from backtest stats.
        """
        ...

@dataclass
class ResearchResult:
strategy_name: str
tearsheet: TearsheetMetrics
backtest_df: pl.DataFrame
drift_report: dict[str, float] # feature → KS p_value
approved_for_deployment: bool
config_path: str | None # Path to exported bot config (if approved)
ic_report: dict[str, float] # alpha_name → IC
regime_stats: pl.DataFrame # Sharpe/return/vol per regime

---

### PHASE 2 — THE HUB: `backtest/integration.py` — BacktestHarness

class BacktestHarness:
"""
Unified entry point for all backtest modes. Replaces calling individual
engines directly. Wires VectorizedEngine + SimulatedBroker + TearsheetGenerator.

    This is what ALL other modules call — never call VectorizedEngine directly.
    """

    def __init__(
        self,
        engine: VectorizedEngine,
        tearsheet_gen: TearsheetGenerator,
        broker: SimulatedBroker,
        portfolio_optimizer: PortfolioOptimizer | None = None,
        risk_engine: RealTimeRiskEngine | None = None,
    ) -> None: ...

    def run(
        self,
        df: pl.DataFrame,            # Full feature+signal DataFrame
        signal_col: str,
        strategy_name: str,
        transaction_cost_bps: float = 10.0,
        slippage_bps: float = 5.0,
        initial_capital: float = 100_000.0,
        benchmark: pl.Series | None = None,  # e.g. BTC buy-and-hold
        output_html: bool = True,
    ) -> BacktestResult:
        """
        Orchestrates:
        1. VectorizedEngine.backtest() → net_return, equity_curve, drawdown
        2. If portfolio_optimizer: apply position weights from optimizer
        3. If risk_engine: simulate risk limits (reject trades that breach limits)
        4. TearsheetGenerator.generate() → TearsheetMetrics
        5. TearsheetGenerator.to_html() → HTML report saved to reports/
        6. PerformanceAnalytics.calculate_metrics() → cross-check metrics
        Returns: BacktestResult
        """
        ...

    def run_walk_forward(
        self,
        df: pl.DataFrame,
        fit_func: Callable,
        predict_func: Callable,
        strategy_name: str,
        **kwargs,
    ) -> WalkForwardResult:
        """WalkForwardBacktest.run() + TearsheetGenerator per fold."""
        ...

    def run_portfolio(
        self,
        prices: pl.DataFrame,
        signals: pl.DataFrame,
        strategy_name: str,
        optimizer: str = "hrp",      # hrp | cvar | mvo | equal
        **kwargs,
    ) -> BacktestResult:
        """PortfolioBacktest.run() + weights from selected optimizer."""
        ...

@dataclass
class BacktestResult:
strategy_name: str
tearsheet: TearsheetMetrics
backtest_df: pl.DataFrame # Full bar-level backtest data
html_report_path: str | None # Path to generated HTML tearsheet
analytics_metrics: dict[str, float] # From PerformanceAnalytics (cross-check)

---

### PHASE 3 — DOWNSTREAM: Backtest → Bot runner.py (filling the Placeholders)

#### `bot/runner.py` — TradingBot.\_signal_loop() — REPLACE PLACEHOLDER

async def \_signal_loop(self) -> None:
"""
Every signal_interval_s seconds: 1. Fetch latest OHLCV bars from DataLake (last N bars per symbol) 2. Compute features: feature_engine.compute_latest(df_per_symbol) 3. Compute alpha signals: alpha_engine.compute_all(features_df) 4. Detect regime: regime_detector.current_regime_confidence(features_df, feature_cols) 5. Combine signals: alpha_combiner.combine() → composite_signal 6. EV gate: ev_optimizer.should_enter(signal, win_rate, avg_win, avg_loss, costs) 7. Win rate gate: win_rate_opt.filter(signal, regime_confidence) 8. If passed both gates: publish OrderEvent via EventBus 9. Update PerformanceTracker with current equity from OMS.get_pnl()
"""
while self.\_running and self.state.can_trade():
try:
for symbol in self.config.symbols:
df = await self.\_fetch_latest_bars(symbol, n_bars=500)
if df.height < 50:
continue

                # Feature computation
                features = self.feature_engine.compute_latest(df)

                # Alpha signal
                alpha_df = self.alpha_engine.compute_all(df)
                signal = float(alpha_df["composite_alpha"][-1])

                # Regime gate
                regime_id, confidence = self.regime_detector.current_regime_confidence(
                    alpha_df, self.config.feature_cols
                )
                if self.regime_detector.is_transitioning(alpha_df, self.config.feature_cols):
                    continue  # Skip during regime transitions (higher uncertainty)

                # IC-weighted combination
                composite = self.alpha_combiner.combine()

                # EV + Win Rate filter
                ev_ok = self.ev_optimizer.should_enter(composite, regime_confidence=confidence)
                wr_ok = self.win_rate_opt.filter(composite, confidence)

                if ev_ok and wr_ok:
                    order = self._create_order(symbol, composite, regime_id)
                    if order:
                        await self.bus.publish(order)
        except asyncio.CancelledError:
            raise  # Propagate cancellation
        except Exception as e:
            _LOG.error("Signal loop error", exc_info=e)

        await asyncio.sleep(float(self.config.signal_interval_s))

#### `bot/runner.py` — TradingBot.\_rebalance_loop() — REPLACE PLACEHOLDER

async def \_rebalance_loop(self) -> None:
"""
Every rebalance_interval_s seconds: 1. Get current positions from OMS.position_manager 2. Get latest features for all symbols in universe 3. Run portfolio optimizer (HRP or CVaR) on recent returns 4. Compute target weights 5. Apply VolTargetSizer: scale weights to hit vol_target 6. Compute rebalance orders (current_weight → target_weight diff) 7. Apply execution algo: TWAP/VWAP/market based on config 8. Publish rebalance orders to EventBus
"""
while self.\_running and self.state.can_trade():
try:
returns_df = await self.\_fetch_returns_matrix(lookback_days=60)
if returns_df is None:
await asyncio.sleep(float(self.config.rebalance_interval_s))
continue

            # Portfolio optimization
            if self.config.strategy == "hrp":
                weights = self.portfolio_optimizer.optimize(returns_df)
            else:
                weights = {s: 1.0/len(self.config.symbols) for s in self.config.symbols}

            # Vol targeting
            current_positions = self.oms.position_manager.get_all_positions()
            rebalance_orders = self._compute_rebalance_orders(weights, current_positions)

            for order in rebalance_orders:
                await self.bus.publish(order)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOG.error("Rebalance loop error", exc_info=e)

        await asyncio.sleep(float(self.config.rebalance_interval_s))

---

### PHASE 4 — MONITORING: `pipeline/monitor.py` — LiveMonitor

class LiveMonitor:
"""
Closes the loop: Live bot metrics → Analytics → Compare vs Backtest → Alert.
Runs continuously in background, publishing SystemEvents on degradation.
"""

    def __init__(
        self,
        tracker: PerformanceTracker,         # From bot.performance
        analytics: PerformanceAnalytics,     # From analytics.performance
        drift_monitor: DriftMonitor,         # From analytics.drift
        telemetry: Telemetry,                # From analytics.telemetry
        bus: EventBus,
        backtest_baseline: TearsheetMetrics, # The approved backtest result
    ) -> None: ...

    async def run_cycle(self, feature_snapshot: pl.DataFrame) -> MonitorReport:
        """
        One monitoring cycle:
        1. Current live metrics from PerformanceTracker.to_dict()
        2. Compare vs backtest_baseline:
           - Live Sharpe < 70% of backtest Sharpe → DEGRADATION alert
           - Live win_rate < 70% of backtest win_rate → WIN_RATE_DECAY alert
           - Live max_drawdown > backtest max_drawdown * 1.5 → DRAWDOWN_BREACH alert
        3. DriftMonitor.detect_drift(train_features, live_features):
           - PSI > 0.25 for any feature → FEATURE_DRIFT alert
           - KS p_value < 0.01 for any feature → DISTRIBUTION_SHIFT alert
        4. Telemetry.record(metrics) for Prometheus/Grafana
        5. If any alert: publish SystemEvent(action="EMERGENCY_HALT", reason=alert_msg)

        Returns MonitorReport with all alerts + metrics.
        """
        ...

    async def start(self, interval_s: int = 300) -> None:
        """Continuous monitoring loop with cancellation safety."""
        while True:
            try:
                report = await self.run_cycle(await self._fetch_live_features())
                if report.has_critical_alerts:
                    await self.bus.publish(SystemEvent(
                        action="EMERGENCY_HALT",
                        reason=report.critical_alerts[0]
                    ))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOG.error("Monitor cycle error", exc_info=e)
            await asyncio.sleep(interval_s)

@dataclass
class MonitorReport:
timestamp: datetime
live_metrics: dict[str, float]
baseline_metrics: dict[str, float] # From approved backtest
sharpe_ratio_pct: float # live / baseline (1.0 = on par)
win_rate_pct: float
drift_alerts: list[str] # Features with significant drift
performance_alerts: list[str] # Metric degradation alerts

    @property
    def has_critical_alerts(self) -> bool:
        return bool(self.drift_alerts or self.performance_alerts)

    @property
    def critical_alerts(self) -> list[str]:
        return self.drift_alerts + self.performance_alerts

---

### PHASE 5 — ANALYST BRIDGE: `pipeline/session_bridge.py`

class SessionBridge:
"""
Connects AnalystSession (human/notebook interface) to the automated pipeline.
QDev uses this in Jupyter notebooks to trigger pipeline runs and inspect results.
"""

    def __init__(self, pipeline: ResearchPipeline, harness: BacktestHarness) -> None: ...

    def quick_backtest(
        self,
        symbol: str,
        strategy: str = "momentum",
        lookback_days: int = 365,
        show_html: bool = True,
    ) -> ResearchResult:
        """One-liner for interactive research. Runs full pipeline for one symbol.

        Usage in Jupyter:
            bridge = SessionBridge(pipeline, harness)
            result = bridge.quick_backtest("BTC/USDT", strategy="momentum")
            # Opens HTML tearsheet in browser
        """
        ...

    def compare_strategies(
        self,
        symbols: list[str],
        strategies: list[str] = ["momentum", "mean_reversion", "hrp"],
        lookback_days: int = 365,
    ) -> pl.DataFrame:
        """Run all strategies on same data, return comparison DataFrame.
        Cols: strategy | sharpe | max_dd | win_rate | profit_factor | approved
        """
        ...

    def deploy_best(self, comparison: pl.DataFrame) -> str:
        """Take compare_strategies() output, pick best approved strategy,
        write to configs/bot_paper.yaml, return path.
        """
        ...

    def live_inspect(self, tracker: PerformanceTracker) -> dict[str, float]:
        """Show current live bot vs backtest baseline side-by-side."""
        ...

---

### PHASE 6 — BOT UPGRADE: Add missing wiring to TradingBot.**init**()

# These components are currently MISSING from TradingBot.**init**():

def **init**(self, config: BotConfig) -> None: # --- EXISTING (keep) ---
self.bus = EventBus()
self.oms = UnifiedOMS()
self.risk_engine = RealTimeRiskEngine()
self.state = StateMachine()
self.performance = PerformanceTracker(config.initial_capital)
self.ev_optimizer = EVOptimizer()
self.win_rate_opt = WinRateOptimizer()

    # --- NEW — add all these: ---
    self.datalake = DataLake()
    self.feature_engine = FactorEngine(store=FeatureStore())
    self.alpha_engine = AlphaEngine(
        alpha_names=["momentum", "mean_reversion", "trend", "amihud", "vpin"],
        ic_window=30
    )
    self.alpha_combiner = AlphaCombiner(method="ic_weighted")
    self.regime_detector = RegimeDetector(n_regimes=3, method="gmm")
    self.portfolio_optimizer = HRPOptimizer()  # or CVaROptimizer
    self.vol_sizer = VolTargetSizer(target_vol=config.vol_target)
    self.execution_algo = TWAPAlgo(
        duration_seconds=300, slice_count=5
    ) if config.execution_algo == "twap" else None

    # Load backtest baseline for LiveMonitor (if exists)
    baseline_path = "reports/latest_baseline.json"
    self.backtest_baseline = TearsheetMetrics.from_json(baseline_path) if Path(baseline_path).exists() else None

    if self.backtest_baseline:
        self.monitor = LiveMonitor(
            tracker=self.performance,
            analytics=PerformanceAnalytics(),
            drift_monitor=DriftMonitor(),
            telemetry=Telemetry(),
            bus=self.bus,
            backtest_baseline=self.backtest_baseline,
        )

    self.config.feature_cols = self.feature_engine.get_all_feature_names()

    # Subscribe all handlers
    self.bus.subscribe(EventType.FILL, self._on_fill)
    self.bus.subscribe(EventType.RISK, self._on_risk_event)
    self.bus.subscribe(EventType.SYSTEM, self._on_system_event)
    self.bus.subscribe(EventType.REGIME_CHANGE, self._on_regime_change)

---

### FULL DATA FLOW DIAGRAM

DataLake / OHLCVNormalizer] ← Binance / Coinbase WebSocket or REST │ pl.DataFrame (OHLCV) ▼ [FactorEngine + FeatureStore] ← RSI, ATR, MACD, OBV, VWAP, DollarVolume │ pl.DataFrame (OHLCV + features) ▼ [AlphaEngine + AlphaRegistry] ← MomentumAlpha, AmihudAlpha, VPIN, OrderImbalance │ pl.DataFrame (+ alpha cols, composite_alpha) ▼ [RegimeDetector + HMMSmoother] ← GMM → regime_id, regime_confidence │ pl.DataFrame (+ regime cols) ▼ [XGBoostPredictor / LSTM] ← ML signal (WalkForwardPipeline trained) │ pl.Series (ml_signal) ▼ ┌────────▼──────────────────────────────────────────────────────────┐ │ BacktestHarness (VectorizedEngine) │ │ → net_return, equity_curve, drawdown, total_cost │ │ → TearsheetMetrics (full institutional tearsheet) │ │ → HTML report (equity curve, monthly heatmap, rolling Sharpe) │ │ → DriftMonitor check (feature stability vs live data) │ └────────┬──────────────────────────────────────────────────────────┘ │ If approved: ResearchResult → export to configs/bot_paper.yaml │ If rejected: alert QDev via AnalystSession / SessionBridge ▼ [DeploymentBridge] ← Writes BotConfig from validated params │ ▼ ┌────────────────────────────────────────────────────────────────────┐ │ TradingBot (runner.py) │ │ \_signal_loop(): │ │ DataLake.latest() → FactorEngine → AlphaEngine → │ │ RegimeDetector → AlphaCombiner → EVOptimizer → │ │ WinRateOptimizer → OrderEvent → EventBus │ │ \_risk_loop(): │ │ RealTimeRiskEngine.check_all_limits() → halt if breach │ │ \_rebalance_loop(): │ │ HRPOptimizer → VolTargetSizer → TWAPAlgo → OrderEvent │ └────────┬───────────────────────────────────────────────────────────┘ │ FillEvent → UnifiedOMS.PositionManager │ → PerformanceTracker (equity_curve, win_rate, Sharpe) ▼ [LiveMonitor] ← Every 5 min: PerformanceAnalytics (live) vs TearsheetMetrics (baseline) DriftMonitor (live features vs training features) DriftAlert → SystemEvent(EMERGENCY_HALT) if degraded Telemetry → Prometheus → Grafana dashboard │ ▼ [AnalystSession / SessionBridge] ← QDev inspects live vs backtest compare_strategies() deploy_best() → loop back

---

### INTERFACE CONTRACTS (all cross-module boundaries)

@dataclass
class DataContract:
"""Standard DataFrame schemas — ALL modules must respect these."""

    OHLCV_COLS = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]
    FEATURES_COLS = OHLCV_COLS + ["rsi", "atr", "macd", "obv", "vwap", "dollar_volume"]
    ALPHA_COLS = FEATURES_COLS + [
        "momentum_alpha", "mean_reversion_alpha", "trend_alpha",
        "order_imbalance_alpha", "amihud_alpha", "vpin_alpha", "composite_alpha"
    ]
    BACKTEST_OUTPUT_COLS = [
        "timestamp", "symbol", "_exec_signal", "net_return", "equity_curve",
        "drawdown", "_cost", "regime_id", "regime_confidence"
    ]
    FILLS_COLS = ["fill_id", "symbol", "side", "qty", "fill_price",
                  "arrival_price", "vwap", "timestamp", "commission"]

    TEARSHEET_PATH = "reports/{strategy_name}_{date}.html"
    BOT_CONFIG_PATH = "configs/bot_paper.yaml"
    BASELINE_METRICS_PATH = "reports/latest_baseline.json"

---

### TearsheetMetrics.from_json() / to_json() — Required for LiveMonitor baseline

# Add to backtest/tearsheet.py:

@dataclass
class TearsheetMetrics: # ... existing fields ...

    def to_json(self, path: str) -> None:
        """Serialize metrics to JSON for persistent baseline storage."""
        import json
        with open(path, "w") as f:
            json.dump(dataclasses.asdict(self), f, indent=2)

    @classmethod
    def from_json(cls, path: str) -> "TearsheetMetrics":
        """Load from JSON. Used by LiveMonitor to restore baseline."""
        import json
        with open(path) as f:
            return cls(**json.load(f))

---

### Unit Test Examples

# Integration test: research pipeline → backtest → bot config export

async def test_research_pipeline_end_to_end():
pipeline = ResearchPipeline(
datalake=MockDataLake(),
feature_engine=FactorEngine(store=MemoryFeatureStore()),
alpha_engine=AlphaEngine(["momentum"]),
regime_detector=RegimeDetector(n_regimes=2),
backtest_harness=BacktestHarness(VectorizedEngine(), TearsheetGenerator(), SimulatedBroker(EventBus())),
model_registry=MockModelRegistry(),
drift_monitor=DriftMonitor(),
)
result = pipeline.run(
symbols=["BTC/USDT"], timeframe="1d",
start_date="2023-01-01", end_date="2024-12-31",
strategy_name="momentum", target_sharpe=0.1 # Low threshold for test
)
assert isinstance(result.tearsheet, TearsheetMetrics)
assert result.tearsheet.sharpe_ratio is not None

# LiveMonitor: degrade detection

def test_monitor_detects_sharpe_degradation():
baseline = TearsheetMetrics(sharpe_ratio=2.0, win_rate=0.55, max_drawdown=0.10, ...)
tracker = PerformanceTracker(100_000) # Simulate bad trades ...
monitor = LiveMonitor(tracker, PerformanceAnalytics(), DriftMonitor(), Telemetry(), EventBus(), baseline)
report = asyncio.run(monitor.run_cycle(mock_feature_df))
assert "Sharpe degraded" in report.performance_alerts

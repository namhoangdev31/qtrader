# QTrader Production-Readiness Execution Plan

## 1. SYSTEM RE-ARCHITECTURE PLAN

### Final Runtime Architecture

- Maintain modular architecture with EventBus as central nervous system
- Introduce Real-time Orchestration Loop as primary driver
- Add Shadow Trading Pipeline parallel to live execution
- Implement Drift Monitoring Service as independent process
- Enhance OMS with bidirectional reconciliation capabilities
- Add Network-Level Kill Switch at socket layer
- Introduce Resource Monitor for latency/memory control

### Component Communication

- Market Data → Feature Engine → Alpha Generation → Strategy → Risk Engine → OMS (live path)
- Market Data → Shadow Engine (parallel, no order submission)
- OMS → Position Reconciliation Service (bidirectional)
- Risk Engine → Drift Monitor (statistical comparison)
- All components → Telemetry Bus (metrics, logs, alerts)
- Kill Switch → Network Interface (hard termination)

## 2. CRITICAL FIXES (PRIORITY ORDERED)

1. Orchestrator Real Loop: Implement continuous market data processing in bot/runner.py
2. Shadow Mode: Build parallel execution path with paper trading
3. Drift Monitoring Live: Activate pipeline/monitor.py with scheduled comparison
4. Execution Realism: Enhance orderbook simulator with slippage/latency models
5. OMS Reconciliation: Implement 2-way state synchronization with exchange
6. Kill Switch (Network-Level): Add socket-level termination mechanism
7. Memory + Latency Control: Introduce rolling windows and CPU isolation

## 3. NEW MODULES TO BUILD

- qtrader/execution/shadow_engine.py: Parallel paper trading execution
- qtrader/execution/reconciliation_service.py: Bidirectional OMS state sync
- qtrader/risk/network_kill_switch.py: Hard kill switch at network layer
- qtrader/execution/slippage_model.py: Realistic slippage simulation
- qtrader/execution/latency_model.py: Network and processing latency modeling
- qtrader/core/resource_monitor.py: CPU/memory usage tracking and throttling
- qtrader/analytics/drift_detector.py: Statistical drift detection between research/live
- qtrader/execution/orderbook_enhanced.py: L2 orderbook with depletion modeling
- qtrader/feedback/feedback_engine.py: Closed-loop learning from execution
- qtrader/ml/meta_online.py: Online meta-learning for dynamic strategy/feature weighting

## 4. INTEGRATION PLAN

Market Data Feed → Feature Engine (qtrader/data/) → Alpha Generation (qtrader/alpha/)
→ Feature Validation (qtrader/strategy/validation/) → Strategy (qtrader/strategy/)
→ Risk Engine (qtrader/risk/runtime_risk_engine.py) → OMS Adapter (qtrader/execution/oms_adapter.py)
→ Execution Engine (qtrader/execution/execution_engine.py)
→ Exchange (via qtrader/api/)
Feedback Loop: Fill Data → OMS → Risk Engine → Strategy Adjustment
Shadow Path: Market Data → Shadow Engine (no order submission) → Performance Comparison
Drift Path: Research Distributions (from MLflow) ↔ Live Distributions (from OMS) → Drift Detector
Telemetry: All components → Core Logger → Analytics Pipeline
Meta Learning Path: Feedback Engine → Online Meta Learner → Ensemble Strategy & Portfolio Allocator

## 5. RISK HARDENING PLAN

- Hard Kill Switch: Network socket termination via qtrader/risk/network_kill_switch.py
- Daily Loss Enforcement: RuntimeRiskEngine with automatic position liquidation
- Max Leverage Cap: Portfolio allocator with hard leverage limit (5x)
- Turnover Constraint: Allocator with max daily turnover penalty
- Circuit Breakers: Volatility-based trading pauses
- Position Limits: Per-symbol and sector exposure caps
- Margin Monitoring: Real-time margin requirement tracking

## 6. EXECUTION REALISM PLAN

- Orderbook Simulation: Enhanced L2 book with depth and liquidity tiers
- Slippage Model: Market impact model based on order size/book depth (Almgren-Chriss)
- Latency Model: Simulated network (50ms) + processing (10ms) delays
- Fee Model: Maker/taker fees with rebate structure
- Partial Fill Modeling: Probabilistic fill based on displayed liquidity
- Latency Jitter: Randomized delay distribution to simulate real network conditions

## 7. SHADOW MODE DESIGN

- Parallel Execution: Shadow engine processes live market data without capital risk
- Fill Simulation: Uses enhanced orderbook simulator to estimate fill probability/price
- Logging Structure: Detailed comparison logs (shadow_fill vs expected_fill, slippage, latency)
- Performance Metrics: Tracking error, slippage bias, latency distribution
- Activation: Toggle via config (shadow_mode: true/false)
- Data Storage: Shadow performance stored in data_lake/shadow/ for analysis

## 8. DRIFT MONITORING ACTIVATION

- Comparison Method: KS-test and PSI between research feature distributions and live
- Frequency: Hourly comparison, daily retraining trigger
- Trigger Conditions: PSI > 0.2 or KS p-value < 0.05 for >3 consecutive hours
- Retraining Pipeline: Automatic MLflow model regeneration and staging
- Rollback Mechanism: Automatic revert if new model performs worse in shadow mode
- Alerting: Telegram/email alerts on drift detection

## 9. PERFORMANCE + LATENCY PLAN

- Async Architecture: Fully async event loop with priority queues
- CPU-bound Isolation: Offload ML inference to thread pool executor
- Batching: Feature computation batched per symbol per time window
- Throttling: Adaptive rate limiting based on latency measurements
- Memory Control: Rolling window (1000 ticks) for all in-memory DataFrames
- Garbage Collection: Scheduled GC pauses during low volatility periods
- Profiling: Continuous performance monitoring with automatic bottleneck reporting

## 10. FINAL ROADMAP (WEEKS)

### Week 1: Foundation

- Implement network kill switch
- Enhance orchestrator run loop with proper error handling
- Add resource monitor for CPU/memory tracking
- Milestone: System can run for 24h without crashing

### Week 2: Shadow & Drift

- Build shadow engine with basic order simulation
- Implement drift detector with PSI/KS tests
- Connect drift monitor to MLflow for retraining triggers
- Milestone: Shadow mode runs parallel to live, drift alerts functional

### Week 3: Execution Realism

- Develop slippage and latency models
- Enhance orderbook simulator with liquidity depletion
- Implement OMS reconciliation service
- Milestone: Backtest slippage matches live within 20% error

### Week 4: Risk Hardening

- Implement daily loss enforcement and leverage caps
- Add turnover constraints to portfolio allocator
- Test circuit breakers and position limits
- Milestone: System survives simulated flash crash without breach

### Week 5: Integration & Testing

- End-to-end testing of all new components
- Shadow/live performance comparison validation
- Latency and memory profiling under load
- Milestone: System passes 1-week shadow trading with Sharpe > 1.0

### Week 6: Production Cutover

- Gradual rollout: 10% capital → 50% → 100%
- Monitor kill switch and drift systems
- Final performance audit
- Milestone: Live trading with institutional risk controls active

# QTrader System Evolution Plan

## 1. System Diagnosis

### Core Weaknesses Identified:
- **Alpha Layer**: Generic features with no edge, no production validation, no decay tracking
- **Strategy Layer**: Weighted sum + static thresholds, no adaptive behavior, no probabilistic modeling  
- **Meta Strategy Layer**: Manual regime weighting, no dynamic alpha/strategy selection
- **Risk Layer (CRITICAL)**: No drawdown control, no portfolio-level risk, no dynamic capital allocation
- **Missing Layers**: Feature Validation, Portfolio Allocation, Alpha Selection/Meta-learning
- **Research-Production Gap**: Advanced ML in research not integrated into live system

### True Bottlenecks (Not Surface-Level):
1. **Risk Management Failure**: Current system lacks proper drawdown controls and portfolio-level risk management - this is existential
2. **Alpha Quality Decay**: No mechanism to validate, monitor, or retire decaying alphas in production
3. **Static Strategy Allocation**: Fixed weights prevent adaptation to changing market regimes
4. **Feature Overload**: Too many low-quality features diluting signal and increasing overfitting risk
5. **Execution-Risk Disconnect**: Risk calculations not connected to actual position/exposure data from OMS

## 2. Target Architecture (V2)

### New Layered Architecture:
**Market Data → Alpha Generation → Feature Validation → Strategy Engine → Meta Strategy → Portfolio Allocator → Risk Engine → Execution**

### Layer Responsibilities & Data Flow:

1. **Alpha Generation Layer**
   - Input: OHLCV + alternative data
   - Output: Raw feature series (z-scored)
   - Function: Pure feature engineering, no signal logic

2. **Feature Validation Layer** 
   - Input: Raw features + forward returns
   - Output: Validated features (invalid → zero) + quality metrics
   - Function: IC computation, decay tracking, stability scoring, feature filtering

3. **Strategy Engine Layer**
   - Input: Validated feature dictionary
   - Output: SignalEvents with conviction scores
   - Function: Probabilistic signal generation (not threshold-based), confidence scoring

4. **Meta Strategy Layer**
   - Input: Strategy signals + regime indicators + performance metrics
   - Output: Dynamic strategy weights
   - Function: Regime-aware strategy selection, performance-based weighting, exploration/exploitation balance

5. **Portfolio Allocator Layer**
   - Input: Strategy signals + correlation matrix + risk budgets
   - Output: Position targets per strategy
   - Function: Risk parity allocation, correlation-aware sizing, turnover constraints

6. **Risk Engine Layer (V2)**
   - Input: Position targets + portfolio PnL + drawdown metrics
   - Output: Final position limits + risk adjustments
   - Function: Drawdown control, VaR/CVaR limits, concentration limits, kill switches

7. **Execution Layer**
   - Input: Risk-adjusted position targets
   - Output: Orders to brokers
   - Function: Optimal execution, slippage modeling, venue selection

### Data Flow Characteristics:
- Event-driven between layers with clear contracts
- Each layer outputs standardized formats (pl.Series, SignalEvents, dict[str, float])
- Backward compatibility maintained through adapter patterns
- Metrics flowing backward for continuous improvement

## 3. Priority Roadmap (PHASED)

### Phase 1: Risk Stabilization (Weeks 1-3)
- **Objective**: Prevent catastrophic losses, establish risk foundation
- **Components**: 
  - Runtime Risk Engine connected to OMS equity/PnL
  - Drawdown Control with automatic position scaling
  - Portfolio-level VaR limits
  - Kill switch mechanisms
- **Why First**: Capital preservation is priority zero; current system lacks basic risk controls
- **Expected Impact**: Eliminates risk of blowup, enables safe experimentation

### Phase 2: Feature Validation & Quality Control (Weeks 4-6)
- **Objective**: Ensure only high-quality, non-decaying features reach strategy layer
- **Components**:
  - Feature Validator with IC calculation, decay tracking
  - Rolling window validation (20-day IC, 60-day stability)
  - Automatic feature zeroing when invalid
  - Metrics dashboard for feature quality
- **Why Second**: Garbage in = garbage out; need clean features before improving strategies
- **Expected Impact**: Improves signal-to-noise ratio, reduces overfitting

### Phase 3: Portfolio Intelligence Layer (Weeks 7-9)
- **Objective**: Move from equal-weight to intelligent, risk-aware allocation
- **Components**:
  - Advanced Portfolio Allocator (risk parity, correlation targeting)
  - Dynamic capital allocation based on strategy confidence
  - Turnover and concentration constraints
  - Regime-aware risk budgeting
- **Why Third**: Allocation efficiency directly impacts Sharpe ratio after risk and features are solid
- **Expected Impact**: 20-30% improvement in risk-adjusted returns through better capital allocation

### Phase 4: Strategy Engine Upgrade (Weeks 10-12)
- **Objective**: Replace threshold-based strategies with probabilistic, confidence-scoring models
- **Components**:
  - Strategy base class supporting probability outputs
  - Confidence-weighted signal generation
  - Uncertainty estimation in signals
  - Ensemble methods for strategy combination
- **Why Fourth**: Strategies can now effectively use validated features and intelligent allocation
- **Expected Impact**: Higher information ratio, better adaptation to market conditions

### Phase 5: Meta Learning & Dynamic Selection (Weeks 13-15)
- **Objective**: Automate regime detection and strategy selection
- **Components**:
  - Online regime detection with confidence scoring
  - Meta-learner for strategy weighting based on regime + performance
  - Exploration/exploitation bandit approach
  - Automatic model retraining triggers
- **Why Fifth**: Requires stable foundation below to learn meaningful patterns
- **Expected Impact**: Adaptive system that improves over time without manual intervention

### Phase 6: Research-Production Bridge (Weeks 16-18)
- **Objective**: Seamlessly move research innovations to live trading
- **Components**:
  - ML model registry with versioning
  - Automated retraining pipeline with walk-forward validation
  - A/B testing framework for new models
  - Gradual rollout mechanisms (canary deployments)
- **Why Sixth**: Only safe to innovate when core system is robust and monitored
- **Expected Impact**: Continuous improvement cycle with controlled risk

## 4. Component-Level Design

### A. Feature Validation Layer
- **IC Computation**: Rolling 20-day Spearman correlation (robust to outliers) between features and forward 1-day returns
- **Decay Tracking**: Monthly IC decay rate via linear regression; features retired if decay > 0.5/month
- **Stability Score**: Autocorrelation at lag 1 of IC series; requires mean-reverting or stable IC
- **Validation Gates**: 
  - |IC| > 0.02 minimum threshold
  - |Monthly Decay| < 0.5
  - Stability > 0 (no explosive behavior)
- **Output**: Validated features (others zeroed) + quality metrics dictionary

### B. Portfolio Allocator
- **Core Method**: Risk Parity via Iterative Optimization (not inverse volatility approximation)
- **Process**:
  1. Estimate covariance matrix (Ledoit-Wolf shrinkage)
  2. Solve for weights where each strategy contributes equal risk
  3. Apply turnover constraints (max 20% daily turnover)
  4. Apply concentration limits (max 30% to any single strategy)
  5. Scale to target volatility (e.g., 15% annual)
- **Inputs**: Strategy returns, confidence scores, correlation priors
- **Outputs**: Position weights summing to 1.0

### C. Risk Engine V2
- **Drawdown Control**: 
  - Soft limit at 60% of max DD (begin scaling)
  - Hard limit at 80% of max DD (zero exposure)
  - Linear decay between limits
- **VaR Limits**: Parametric VaR with Cornish-Fisher expansion (accounts for skew/kurtosis)
- **Position Scaling**: 
  - Volatility targeting (15% annual)
  - Correlation-adjusted position sizing
  - Liquidity-adjusted limits (based on avg daily volume)
- **Kill Switches**:
  - Daily loss limit (5% of capital)
  - Consecutive loss limit (3 days)
  - Technology failure timeout (30s no market data)

### D. Strategy Upgrade
- **From**: Deterministic thresholds (BUY if sum > 0.5)
- **To**: Probabilistic signaling:
  - Model P(signal | features) using logistic regression or small NN
  - Output: {BUY: 0.6, SELL: 0.2, HOLD: 0.2} probability distribution
  - Conviction = max probability - 0.33 (uniform baseline)
  - Expected value = Σ(profitability[signal] × probability[signal])
- **Implementation**: 
  - Each strategy maintains lightweight online model
  - Features standardized (z-scored) from validation layer
  - Regularization to prevent overfitting

### E. Meta Learning Layer
- **Regime Detection**: 
  - Online GMM with diagonal covariance (fast update)
  - Features: volatility, volume imbalance, spread, momentum (lookback: 5, 20, 60 days)
  - Output: regime probabilities + confidence entropy
- **Strategy Weighting**:
  - Base weights from regime-strategy performance matrix
  - Performance adjustment: exponential recency weighting (half-life: 10 days)
  - Exploration: Thompson sampling or UCB for uncertain strategies
  - Final weight = regime_weight × performance_weight × exploration_bonus
- **Adaptation**: 
  - Regime model retrained weekly
  - Strategy performance updated daily
  - Weight changes smoothed (max 10% daily change per strategy)

## 5. Data & Metrics Framework

### Core Metrics to Track:
- **Pre-Trade**: Feature IC, stability, decay rate, strategy confidence
- **Post-Trade**: Signal accuracy, turnover, slippage, execution quality
- **Portfolio**: Sharpe, Sortino, Calmar, max DD, VaR hit rate, turnover
- **Risk**: VaR violations, drawdown intensity, correlation spikes, leverage
- **Execution**: Fill rate, slippage vs benchmark, latency, venue distribution

### Update Frequencies:
- **Real-time (tick-level)**: Market data, feature computation, risk exposure
- **Daily (end-of-day)**: 
  - Feature validation metrics (IC, decay)
  - Strategy performance updates
  - Regime detection retraining
  - Portfolio rebalancing signals
- **Weekly**: 
  - Meta-learning weight updates
  - Model retraining triggers
  - Risk parameter calibration
- **Monthly**: 
  - Deep strategy performance analysis
  - Feature generation pipeline review
  - Risk limit adjustments

### Metrics Storage:
- Time-series database (TimescaleDB/Prometheus) for metrics
- Feature store (Feast/DuckDB) for validated features
- Model registry (MLflow) for strategy/meta models
- Audit trail: all decisions logged with context for post-mortem

## 6. Research → Production Bridge

### Model Promotion Process:
1. **Research Phase**: 
   - Develop model in isolated research environment
   - Validate with walk-forward backtesting (Purged K-fold, embargo)
   - Generate model card: performance, inputs, outputs, limitations
2. **Staging Phase**:
   - Deploy to shadow mode (live data, no execution)
   - Compare signals vs production champion
   - Track IC, turnover, capacity constraints
   - Require: 
     - IC > 0.015 (vs 0.02 production threshold)
     - Max drawdown < 50% of champion
     - Stable feature importance
3. **Promotion Phase**:
   - Canary deployment (5% capital)
   - Gradual ramp-up (+5% daily) if performance holds
   - Full promotion after 2 weeks of consistent outperformance
   - Immediate rollback if: 
     - Daily loss > 2% 
     - IC drops > 30% from research
     - Execution slippage > 2x research estimate

### Retraining Strategy:
- **Trigger Conditions**:
  - Performance degradation (IC < threshold for 5 days)
  - Regime shift detected (KL divergence > threshold)
  - Time-based (weekly for fast models, monthly for slow)
- **Process**:
  - Incremental learning where possible (avoid full retrain)
  - Walk-forward validation on recent data (60 days)
  - A/B test vs current model for 3 days before full switch
  - Rollback on validation failure

### Overfitting Prevention:
- **Feature Limits**: Max 50 features per model (L1 regularization)
- **Parameter Constraints**: 
  - Tree depth ≤ 6 for GBDT
  - Dropout ≥ 0.2 for neural nets
  - Early stopping on validation set
- **Data Hygiene**:
  - Purged cross-validation (remove look-ahead bias)
  - Embargo periods (4 hours) between train/test
  - Feature importance stability checks
- **Ensemble Requirement**: Single model weight < 0.3 in ensemble (promotes diversity)

## 7. Risk Analysis (Failure Scenarios)

### Regime Shift:
- **Scenario**: Market volatility spikes 3x, correlation → 1
- **Impact**: Strategies fail simultaneously, diversification breaks down
- **Current Vulnerability**: Static weights, no regime awareness
- **Mitigation**: 
  - Real-time regime detection with confidence scoring
  - Automatic risk budget reduction in high uncertainty
  - Correlation stress testing in risk engine
  - Flight-to-quality rules (increase cash allocation in crises)

### Alpha Decay:
- **Scenario**: Popular strategy gets arbitraged away, IC → 0
- **Impact**: Gradual performance deterioration, false confidence
- **Current Vulnerability**: No decay monitoring, manual review only
- **Mitigation**:
  - Automatic IC decay tracking with alerts
  - Feature retirement when decay > threshold
  - Continuous feature generation pipeline
  - Exploration budget for new alpha discovery

### Correlation Spike:
- **Scenario**: Unexpected event causes assets to move together
- **Impact**: Portfolio risk >> sum of parts, VaR models fail
- **Current Vulnerability**: Static correlation estimates, no tail risk
- **Mitigation**:
  - Dynamic covariance estimation (EWMA + Ledoit-Wolf)
  - Tail risk metrics (Expected Shortfall, not just VaR)
  - Stress testing against historical crisis periods
  - Volatility targeting that reduces leverage in high corr

### Liquidity Crunch:
- **Scenario**: Market dries up, wide spreads, slippage explodes
- **Impact**: Execution costs eat returns, impossible to exit
- **Current Vulnerability**: Execution ignores liquidity, static slippage models
- **Mitigation**:
  - Real-time liquidity scoring (volume, spread, depth)
  - Participation rate limits based on liquidity
  - Execution algorithms that adapt to venue liquidity
  - Position size limits tied to average daily volume

### Model Drift & Concept Shift:
- **Scenario**: Underlying relationships change slowly
- **Impact**: Models become increasingly wrong over time
- **Current Vulnerability**: No automatic retraining triggers
- **Mitigation**:
  - Online performance monitoring with drift detection
  - Scheduled retraining with validation gates
  - Ensemble methods that average over recent models
  - Simple baseline models as performance floor

## 8. Minimal Execution Plan (Actionable Steps)

### Phase 1 - Risk Stabilization:
1. [ ] Implement OMS equity curve extraction from position data
2. [ ] Create DrawdownControl module with soft/hard limits
3. [ ] Connect DrawdownControl to position sizing pipeline
4. [ ] Implement basic VaR calculator (parametric normal)
5. [ ] Add daily loss limit and kill switch to OMS
6. [ ] Write unit tests for all risk modules
7. [ ] Create integration test: simulate drawdown → position scaling

### Phase 2 - Feature Validation:
1. [ ] Deploy FeatureValidator with IC calculation (Polars rolling corr)
2. [ ] Add decay rate computation (linear regression slope)
2. [ ] Implement stability score (lag-1 autocorrelation)
3. [ ] Create validation gate: zero invalid features
4. [ ] Build metrics dashboard for feature quality
5. [ ] Add validation layer to alpha→strategy pipeline
6. [ ] Test with known good/bad features

### Phase 3 - Portfolio Intelligence:
1. [ ] Replace inverse vol allocation with true risk parity optimizer
2. [ ] Implement Ledoit-Wolf shrinkage for covariance estimation
3. [ ] Add turnover constraints (max weight change per day)
4. [ ] Add concentration limits (max weight per strategy)
5. [ ] Connect to strategy confidence scores from validation
6. [ ] Test allocation under various correlation regimes

### Phase 4 - Strategy Upgrade:
1. [ ] Modify Strategy base class to support probability outputs
2. [ ] Implement logistic regression strategy as reference
3. [ ] Add confidence scoring (max probability - uniform baseline)
4. [ ] Create ensemble strategy combiner
5. [ ] Update strategy layer to use probabilistic signals
6. [ ] Backtest comparison: threshold vs probabilistic

### Phase 5 - Meta Learning:
1. [ ] Implement online GMM regime detector (scikit-learn partial_fit)
2. [ ] Create regime-strategy performance matrix tracker
3. [ ] Add exponential recency weighting to performance scores
4. [ ] Implement Thompson sampling for exploration
5. [ ] Smooth weight changes (max 10% daily shift per strategy)
6. [ ] Test regime detection on synthetic data with known shifts

### Phase 6 - Research Bridge:
1. [ ] Create MLflow model registry integration
2. [ ] Build shadow mode deployment framework
3. [ ] Create automated retraining pipeline with walk-forward validation
4. [ ] Implement A/B testing framework for model promotion
5. [ ] Add gradual rollout (canary) mechanism
6. [ ] Test end-to-end: research model → shadow → canary → production

## 9. What NOT to Build

### Anti-Patterns to Avoid:
1. **Overfitting ML Too Early**:
   - Do not deploy complex neural nets before establishing feature validation
   - Do not use ML for signal generation without proper walk-forward validation
   - Do not ignore feature importance stability in production

2. **Feature Overload**:
   - Do not add more than 50 features per model without rigorous validation
   - Do not ignore feature decay and continue using degraded signals
   - Do not skip stability checks for IC time series

3. **Ignoring Risk Layer**:
   - Do not optimize for Sharpe ratio without drawdown constraints
   - Do not allocate capital without correlation awareness
   - Do not run strategies without position limits tied to liquidity

4. **Static Systems**:
   - Do not use fixed thresholds that don't adapt to volatility regimes
   - Do not run regime detection without online updating
   - Do not allocate capital with fixed weights regardless of performance

5. **Execution-Risk Disconnect**:
   - Do not calculate risk on theoretical positions without OMS sync
   - Do not ignore execution slippage in risk calculations
   - Do not use static latency/models for live trading

6. **Research-Production Gap Violations**:
   - Do not deploy models without shadow mode validation
   - Do not skip A/B testing before full promotion
   - Do not ignore execution costs in research backtests

### Specific Components to Defer or Avoid:
- **Complex Execution Algorithms**: Start with VWAP/TWAP before implementing optimal execution
- **Alternative Data Integration**: Solidify core pipeline before adding news/sentiment
- **High-Frequency Components**: Focus on daily/horizons before microsecond latency
- **Overly Complex Meta-Learners**: Start with simple regime weighting before bandits
- **Real-Time Retraining**: Begin with daily batch retraining before online learning
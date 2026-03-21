# QTrader Live Trading System Integration Plan

## 1. System Diagnosis

### Why Current System is Not Live-Ready

The QTrader system consists of well-designed, modular components that exist in isolation but lack the connective tissue to form an operational trading pipeline:

1. **No Central Orchestration**: Components operate as independent modules without a central coordinator to manage data flow and execution timing
2. **Missing Data Contracts**: No standardized formats defined for data exchange between layers (alpha features, signals, risk metrics)
3. **No Real-Time Connectivity**: Absence of event-driven mechanisms to process market data as it arrives
4. **Unvalidated Assumptions**: Components make assumptions about data formats and timing that aren't guaranteed in production
5. **Risk Decoupling**: Risk calculations are not integrated into the signal generation and order execution flow
6. **Execution Gap**: No mechanism to convert strategy signals into executable orders through the OMS

### Integration Gaps Identified

1. **Market Data → Alpha Layer**: No standardized feature extraction pipeline
2. **Alpha Layer → FeatureValidator**: Missing validation interface and feedback loops
3. **FeatureValidator → Strategy**: No mechanism to pass validated features to strategy layer
4. **Strategy → Ensemble**: Missing dynamic weighting based on regime and performance
5. **Ensemble → PortfolioAllocator**: No capital allocation based on risk-adjusted returns
6. **PortfolioAllocator → RiskEngine**: Missing real-time risk validation of proposed allocations
7. **RiskEngine → OMS**: No risk-based order filtering or position limit enforcement
8. **Feedback Loops**: Absence of performance tracking to enable adaptive learning
9. **Error Handling**: No graceful degradation when components fail
10. **Operational Controls**: Missing kill switches, circuit breakers, and manual override capabilities

## 2. End-to-End Data Flow Design

### Data Formats and Timing Specifications

**Market Data Input**
- Format: Polars DataFrame with OHLCV data
- Frequency: Per tick (real-time) or per bar (1m, 5m, etc.)
- Content: `{symbol: str, timestamp: datetime, open: float, high: float, low: float, close: float, volume: float}`

**Alpha Layer Output**
- Format: Dictionary of feature names to Polars Series
- Content: `{"feature_name": pl.Series([float values]), ...}`
- Timing: Computed per market data update

**FeatureValidator Output**
- Format: Dictionary of validated feature names to Polars Series (invalid features zeroed)
- Content: Same as input but with invalid features set to zero series
- Timing: Per feature set update

**Strategy Output**
- Format: SignalEvent with probability metadata
- Content: 
  ```python
  SignalEvent(
      symbol=str,
      signal_type="PROBABILISTIC",
      strength=float,
      metadata={
          "buy_prob": float,
          "sell_prob": float, 
          "hold_prob": float,
          "model_confidence": float,
          "latest_value": float
      }
  )
  ```
- Timing: Per validated feature update

**Ensemble Strategy Output**
- Format: SignalEvent with combined probabilities
- Content: Same as Strategy output but with ensemble metadata
- Timing: Per strategy signal update

**PortfolioAllocator Output**
- Format: Dictionary of strategy names to allocation weights
- Content: `{"strategy_name": float weight, ...}` where weights sum to 1.0
- Timing: Per strategy returns update (periodic)

**RuntimeRiskEngine Output**
- Format: Polars Series of risk metric values
- Content: Risk metrics per time point (exposure, drawdown, VaR, etc.)
- Timing: Per market data update with OMS position data

**OMS Input/Output**
- Input: OrderEvent objects from strategy layer
- Output: FillEvent objects and position updates
- Content: Standard order/execution events
- Timing: Asynchronous based on market conditions

### Data Flow Sequence

1. Market Data Feed → Feature Engineering (Alpha Layer)
2. Alpha Features → Feature Validation (IC testing, decay analysis)
3. Validated Features → Strategy Layer (Probabilistic signal generation)
4. Strategy Signals → Ensemble Strategy (Dynamic weighting)
5. Ensemble Signals → Portfolio Allocation (Risk parity weighting)
6. Allocation + OMS Positions → Runtime Risk Engine (Pre-trade risk check)
7. Risk-Approved Signals → OMS (Order generation and execution)
8. OMS Fills → Position Updates → Performance Tracking → Feature Validation (Feedback loop)

## 3. Integration Plan

### A. Alpha → FeatureValidator
- **Input**: Dictionary `{feature_name: pl.Series}` from alpha layer
- **Output**: Dictionary `{feature_name: pl.Series}` with invalid features zeroed
- **Control Logic**: 
  - FeatureValidator.validate() called on each feature update
  - Uses forward returns (from lookahead data) to compute IC
  - Applies IC threshold, decay threshold, and stability filters
- **Failure Handling**: 
  - If validation fails, return zero series for affected features
  - Log validation failures for monitoring
  - Continue processing with remaining valid features

### B. FeatureValidator → Strategy
- **Input**: Dictionary of validated features (same format as Alpha output)
- **Output**: SignalEvent with probabilistic signal
- **Control Logic**:
  - Strategy.compute_signals() called with validated features
  - ProbabilisticStrategy weights features and converts to buy/sell/hold probabilities
  - Signal strength derived from probability deviation from uniform distribution
- **Failure Handling**:
  - If strategy computation fails, return HOLD signal with zero strength
  - Log computation errors for debugging
  - Prevent order generation on strategy failure

### C. Strategy → Ensemble
- **Input**: List of Strategy objects (each with compute_signals method)
- **Output**: Combined SignalEvent from EnsembleStrategy
- **Control Logic**:
  - EnsembleStrategy.compute_signals() calls each strategy's compute_signals()
  - Tracks performance of each strategy using signal strength as proxy
  - Dynamically rebalances weights based on recent performance
  - Combines signals using weighted voting of probabilities
- **Failure Handling**:
  - Individual strategy failures return neutral HOLD signals
  - Ensemble continues operating with remaining strategies
  - Performance tracking excludes failed strategies during recovery period

### D. Ensemble → PortfolioAllocator
- **Input**: Dictionary `{strategy_name: pl.Series of returns}` from strategy performance tracking
- **Output**: Dictionary `{strategy_name: float weight}` for capital allocation
- **Control Logic**:
  - EnhancedPortfolioAllocator.allocate() called periodically (e.g., hourly)
  - Uses strategy returns to compute covariance matrix
  - Applies Ledoit-Wolf shrinkage for robust estimation
  - Solves for true risk parity (equal risk contribution)
  - Applies volatility targeting and constraints (turnover, concentration)
- **Failure Handling**:
  - If allocation fails, fall back to equal weighting
  - If insufficient data, maintain current weights
  - Log allocation errors but continue with last known good weights

### E. PortfolioAllocator → RiskEngine
- **Input**: 
  - Portfolio weights dictionary from allocator
  - Current OMS positions
  - Market data for pricing
- **Output**: Risk-approved trade signals or rejection
- **Control Logic**:
  - RuntimeRiskEngine.compute() called with proposed portfolio changes
  - Checks projected exposure, leverage, VaR against limits
  - Computes projected drawdown based on proposed positions
  - Returns risk metrics for decision making
- **Failure Handling**:
  - If risk computation fails, adopt most conservative stance (block trades)
  - Fail-safe defaults to zero risk tolerance on computation errors
  - Manual override available for emergency situations

### F. RiskEngine → OMS
- **Input**: 
  - SignalEvent from ensemble strategy
  - Risk assessment (approved/rejected with limits)
  - Current portfolio state from OMS
- **Output**: OrderEvent objects submitted to venues
- **Control Logic**:
  - OMS receives signals only after risk approval
  - Position sizing incorporates risk engine adjustments
  - Order generation respects portfolio-level constraints
  - Execution algorithms selected based on volatility and liquidity
- **Failure Handling**:
  - If risk engine rejects signal, no orders generated
  - If OMS fails, orders queued for retry with exponential backoff
  - Circuit breaker triggers on repeated OMS failures
  - Manual intervention path for extended outages

## 4. Real-Time Execution Model

### Hybrid Event-Driven/Batch Architecture

**Event-Driven Components (Real-Time)**
- Market data ingestion and processing
- Feature calculation (technical indicators, microstructure features)
- Signal generation (strategy and ensemble layers)
- Order routing and execution
- Position and P&L updates

**Batch Components (Periodic)**
- Feature validation (IC calculation requires lookback windows)
- Portfolio allocation (returns estimation needs historical data)
- Risk metric calculation (VaR, drawdown need historical context)
- Model retraining and regime detection updates
- Performance analytics and reporting

### Signal Generation Frequency
- **High-Frequency Strategies**: Signal generation per market data tick (sub-second)
- **Medium-Frequency Strategies**: Signal generation per bar (1m, 5m intervals)
- **Low-Frequency Strategies**: Signal generation per session or daily
- **Adaptive**: Frequency adjusted based on volatility and regime

### OMS Execution Model
- **Order Types**: Market, limit, iceberg, TWAP based on urgency and liquidity
- **Execution Venues**: Smart order routing across connected exchanges
- **Position Limits**: Real-time checking against risk engine limits
- **Throttling**: Rate limiting based on venue constraints and risk parameters
- **Confirmation**: Fill-driven position updates with reconciliation

## 5. Risk Enforcement Layer

### Risk Check Locations
1. **Pre-Signal Generation**: Feature validation prevents weak features from influencing strategies
2. **Pre-Order Generation**: Strategy signals filtered through risk-adjusted position sizing
3. **Pre-Execution**: Portfolio allocation validated by runtime risk engine
4. **Post-Fill**: Position limits and leverage monitored continuously
5. **Periodic**: VaR and stress testing against market scenarios

### Trade Blocking Mechanism
- **Hard Limits**: Absolute blocks on leverage, concentration, drawdown
- **Soft Limits**: Warning thresholds that reduce position sizes
- **Conditional Blocks**: Regime-dependent restrictions (e.g., no momentum in sideways markets)
- **Volatility Filters**: Reduced sizing during high volatility periods
- **Liquidity Constraints**: Size limits based on order book depth

### Kill Switch Design
- **Emergency Stop**: Immediate cancellation of all open orders and cessation of new signal processing
- **Gradual Wind-Down**: Systematic reduction of positions to target levels
- **Selective Halting**: Ability to pause specific strategies or symbol groups
- **Manual/Auto Triggers**: 
  - Manual: Operator-activated kill switch
  - Automatic: Breached risk limits, system failures, connectivity loss
  - Time-Based: Scheduled trading halts (market close, news events)

### Daily Loss Limit Enforcement
- **Intraday Monitoring**: Realized + unrealized P&L tracked continuously
- **Tiered Response**:
  - 50% of daily limit: Reduce new position sizes by 50%
  - 75% of daily limit: Only allow position reductions
  - 90% of daily limit: Cancel all open orders, halt new signals
  - 100% of daily limit: Activate kill switch, initiate position liquidation
- **Reset Mechanism**: Daily limits reset at exchange-defined session close

## 6. Feature Lifecycle Automation

### Feature Disabling Process
1. **Detection**: FeatureValidator identifies degraded features via:
   - IC falling below threshold
   - Excessive decay rate (> decay_threshold per month)
   - Poor stability score (negative autocorrelation)
2. **Validation Period**: Features must fail validation for N consecutive periods (configurable)
3. **Automatic Zeroing**: Invalid features replaced with zero series in validation output
4. **Notification**: Degraded features logged and reported for research review
5. **Re-Validation Schedule**: Disabled features re-evaluated on reduced frequency

### Feature Re-enabling Criteria
1. **Recovery Period**: Feature must show sustained improvement
2. **Backtesting Validation**: Recent performance must justify re-enablement
3. **Regime Compatibility**: Feature must be appropriate for current market regime
4. **Correlation Check**: Re-enabled feature must not cause excessive multicollinearity
5. **Gradual Re-introduction**: Initial reduced weighting, increasing over time

### Decay Tracking Automation
- **Rolling Windows**: IC decay computed over configurable lookback (default 1 month)
- **Trend Analysis**: Linear regression slope of IC time series
- **Regime-Conditioned**: Decay tracked separately for each market regime
- **Alert Generation**: Automatic notifications when decay acceleration detected
- **Research Integration**: Decay metrics fed back to feature development pipeline

## 7. Strategy Adaptation Logic

### Regime-Dependent Weighting
- **Regime Detection**: Online GMM regime detector outputs regime probabilities
- **Strategy-Regime Mapping**: Historical performance matrix (strategy × regime)
- **Dynamic Weights**: Strategy weights adjusted by regime probability × historical performance
- **Confidence Scaling**: Higher regime confidence → stronger regime-based adjustments
- **Transition Handling**: Smooth weighting during regime transitions (linear interpolation)

### Ensemble Dynamic Weighting
- **Performance Window**: Rolling window of strategy performance (default 20 signals)
- **Performance Metric**: Signal strength as proxy for confidence (replaced with actual P&L when available)
- **Weighting Algorithm**: Softmax-like normalization with min/max constraints
- **Rebalancing Frequency**: Periodic weight updates (default every 5 signals)
- **Constraints**: 
  - Minimum weight per strategy (prevents complete elimination)
  - Maximum weight per strategy (prevents over-concentration)
  - Turnover limits on weight changes

### Confidence-Based Position Sizing
- **Base Size**: Derived from portfolio allocation and risk targets
- **Confidence Multiplier**: Position size scaled by signal strength (0-1 range)
- **Volatility Adjustment**: Inverse volatility scaling for risk parity
- **Regime Adjustment**: Regime-specific multipliers (e.g., reduce size in uncertain regimes)
- **Correlation Adjustment**: Size reduction for strategies with high correlation to existing positions

## 8. Portfolio-Level Control

### Capital Allocation Framework
- **Core Allocation**: Risk parity weighting from EnhancedPortfolioAllocator
- **Satellite Allocation**: Tactical tilts based on regime and opportunity
- **Risk Budgeting**: Allocation of risk contributions rather than capital
- **Expected Return Integration**: Adjust weights for strategies with higher risk-adjusted returns
- **Liquidity Constraints**: Allocation adjustments based on strategy liquidity profiles

### Correlation-Aware Adjustments
- **Real-Time Correlation**: Rolling correlation matrix of strategy returns
- **Diversification Bonus**: Increased allocation to low-correlation strategies
- **Correlation Penalties**: Reduced allocation for strategies adding marginal diversification
- **Cluster Recognition**: Identification of strategy groups with similar return drivers
- **Beta Hedging**: Allocation adjustments to control factor exposures

### Risk Budgeting Implementation
- **Target Risk Contributions**: Equal risk contribution as baseline
- **Active Risk Budget**: Deviations from risk parity based on conviction
- **Risk Limits**: Maximum risk contribution per strategy
- **Leverage Constraints**: Portfolio-level leverage limits translated to strategy limits
- **Drawdown Budgeting**: Allocation of maximum drawdown tolerance across strategies

## 9. OMS Integration

### Signal-to-Order Conversion
- **Probabilistic to Deterministic**: Convert signal probabilities to order sides
  - BUY signal: buy_prob > sell_prob and buy_prob > hold_prob
  - SELL signal: sell_prob > buy_prob and sell_prob > hold_prob
  - HOLD signal: otherwise (or insufficient strength)
- **Strength to Size**: Order size proportional to signal strength and conviction
- **Urgency Determination**: 
  - High strength + trending market → Market or aggressive limit orders
  - Medium strength + ranging market → Passive limit orders
  - Low strength → No order or iceberg orders for accumulation
- **Timing Considerations**: 
  - Immediate execution for high-conviction signals
  - Patient execution for low-conviction or mean-reverting signals

### Position Sizing Logic
- **Base Calculation**: 
  ```
  base_size = portfolio_value * strategy_weight * signal_strength
  ```
- **Risk Adjustments**:
  - Volatility scaling: Inverse volatility for risk parity
  - Correlation adjustment: Reduction for correlated positions
  - Liquidity adjustment: Size capped by % of average daily volume
  - Volatility regime: Reduced sizing in high volatility periods
- **Final Size**: 
  ```
  final_size = base_size * volatility_adj * correlation_adj * liquidity_adj
  ```

### Order Throttling Mechanisms
- **Rate Limiting**: Maximum orders per second per strategy/symbol
- **Size Throttling**: Maximum order size as % of average volume
- **Execution Algorithms**: 
  - TWAP for large orders over extended periods
  - VWAP for volume-participation strategies
  - Implementation shortfall for urgency-based execution
  - Market orders only for emergency liquidation
- **Venue Distribution**: Smart routing to minimize market impact

### Execution Safety Checks
- **Pre-Trade Validation**:
  - Order size limits (absolute and % of volume)
  - Price sanity checks (away from inside market)
  - Duplicate order detection
  - Venues connectivity and permissions verification
- **Pre-Execution Checks**:
  - Margin requirements verification
  - Position limit checking (per symbol, sector, strategy)
  - Regulatory compliance (short sale restrictions, etc.)
  - Market halt and volatility interruption checks
- **Post-Execution Verification**:
  - Fill price reasonableness checks
  - Position reconciliation with expected fills
  - P&L attribution to correct strategies
  - Breach reporting for any limit violations

## 10. MLOps & Continuous Learning

### Shadow Mode Execution
- **Parallel Processing**: New strategies run in shadow mode alongside production
- **Performance Comparison**: Shadow performance tracked vs. live benchmarks
- **Deployment Criteria**: Shadow strategy must outperform benchmark for N periods
- **Risk Isolation**: Shadow strategies use separate capital allocation (paper trading)
- **Automated Rollback**: Immediate withdrawal if shadow strategy shows adverse characteristics

### Model Registry (MLflow)
- **Experiment Tracking**: All feature iterations, strategy versions, and parameter sets logged
- **Model Versioning**: Each strategy/feature set versioned with performance metrics
- **Stage Transitions**: Models progress from Staging → Production → Archived
- **Metadata Capture**: 
  - Training data characteristics
  - Performance metrics (IC, Sharpe, drawdown)
  - Regime-specific performance
  - Deployment timestamps and operators
- **Rollback Capability**: Instant reversion to previous known-good versions

### Retraining Pipeline (Walk-Forward)
- **Scheduled Retraining**: Periodic model updates (daily/weekly/monthly based on strategy frequency)
- **Walk-Forward Windows**: 
  - Training: Expanding window or fixed lookback
  - Testing: Immediate out-of-sample period
  - Validation: Performance must exceed walk-forward baseline
- **Automated Triggers**:
  - Performance degradation beyond threshold
  - Regime change detection
  - Feature validity expiration
  - Scheduled maintenance windows
- **Validation Gates**: 
  - Statistical significance testing
  - Economic significance (transaction cost adjusted)
  - Robustness across multiple periods
  - Overfitting detection (in-sample vs out-of-sample performance)

### Deployment of New Models
- **Canary Deployment**: Small capital allocation to new model initially
- **Gradual Scaling**: Increase allocation as out-of-sample performance validates
- **Performance Monitoring**: Real-time tracking vs. benchmark and shadow mode
- **Automatic Promotion**: Full deployment after meeting performance criteria
- **Emergency Rollback**: Immediate reversion on adverse performance or risk violations
- **A/B Testing**: Parallel running of champion vs. challenger models

## 11. Failure Scenarios

### Feature Failure
- **Scenario**: Feature calculation pipeline breaks (data source issue, calculation error)
- **Detection**: 
  - Missing feature data validated at ingestion
  - Statistical tests for anomalous feature values
  - Cross-validation with alternative feature calculations
- **Response**:
  - Substitute with last known good value (with staleness penalty)
  - Use alternative feature calculation if available
  - Zero out feature if no reliable substitute
  - Alert research team for urgent investigation
  - Continue operation with degraded feature set

### Strategy Failure
- **Scenario**: Strategy logic error, exception in signal generation, or performance collapse
- **Detection**:
  - Exception handling in strategy.compute_signals()
  - Performance monitoring (sharp drop in signal quality)
  - Unusual signal patterns (all same side, extreme values)
  - Comparison with ensemble and peer strategies
- **Response**:
  - Isolate failing strategy (return HOLD signals)
  - Increase weight of remaining strategies in ensemble
  - Activate shadow mode investigation for root cause
  - Research team notified for strategy review
  - Potential strategy replacement from model registry

### Risk Breach
- **Scenario**: Actual portfolio exposure exceeds risk limits
- **Detection**:
  - Real-time P&L and position monitoring
  - VaR and drawdown calculations vs. limits
  - Leverage and concentration threshold breaches
  - OMS position reconciliation discrepancies
- **Response**:
  - Automatic cancellation of new orders
  - Systematic position reduction to comply with limits
  - Increase in cash allocation to reduce leverage
  - Activation of kill switch if breach severe or persistent
  - Post-mortem analysis to prevent recurrence
  - Potential adjustment of risk limits if breach was false positive

### OMS Failure
- **Scenario**: Connectivity loss to exchanges, order submission failures, or position tracking errors
- **Detection**:
  - Failed order submissions and timeouts
  - Position reconciliation mismatches
  - Missing fill events or duplicate fills
  - Venue health check failures
- **Response**:
  - Local queuing of orders with exponential backoff retry
  - Failover to backup venues or adapters
  - Position tracking via alternative methods (exchange API polling)
  - Reduction in trading aggression to minimize risk during outage
  - Manual intervention procedures for extended outages
  - Post-incident analysis and system hardening

### Systemic Failures
- **Scenario**: Multiple component failures or cascading failures
- **Detection**:
  - Health check failures across multiple systems
  - Degraded performance metrics
  - Inconsistent state between components
  - Manual override activations
- **Response**:
  - Graduated response: 
    - Level 1: Reduce trading activity, increase monitoring
    - Level 2: Halt new signals, manage existing positions
    - Level 3: Cancel all orders, initiate position liquidation
    - Level 4: Complete system shutdown, manual control
  - Communication protocols for operator notification
  - Runbook procedures for each failure level
  - Post-incident reviews and system resilience improvements

## 12. Minimal Execution Plan

### Phase 1: Foundation (Weeks 1-2)
1. **Create System Orchestrator**
   - Design and implement main trading loop
   - Establish event bus for inter-component communication
   - Create configuration management system
   - Implement basic logging and monitoring
   - *Test*: Verify components can communicate via event bus

2. **Define Data Contracts**
   - Specify exact formats for all inter-component data
   - Create data validation schemas
   - Implement type checking at boundaries
   - *Test*: Validate data contracts with synthetic data

3. **Implement Market Data Adapter**
   - Connect to market data feed (simulated or real)
   - Normalize data to standard format
   - Publish market data events
   - *Test*: Verify market data flows through system

### Phase 2: Signal Generation (Weeks 3-4)
4. **Integrate Alpha Layer**
   - Connect market data to feature calculation
   - Implement feature caching and staleness detection
   - *Test*: Verify feature generation from market data

5. **Connect Feature Validation**
   - Wire alpha output to FeatureValidator input
   - Implement forward returns lookahead
   - *Test*: Validate feature zeroing for invalid features

6. **Integrate Strategy Layer**
   - Connect validated features to strategy inputs
   - Implement signal generation pipeline
   - *Test*: Verify probabilistic signal generation

### Phase 3: Ensemble and Allocation (Weeks 5-6)
7. **Implement Ensemble Strategy**
   - Create ensemble container for multiple strategies
   - Implement dynamic weighting based on performance
   - *Test*: Verify weight adjustment based on signal quality

8. **Connect Portfolio Allocator**
   - Wire ensemble strategy returns to allocator
   - Implement periodic allocation updates
   - *Test*: Verify risk parity weight generation

### Phase 4: Risk and Execution (Weeks 7-8)
9. **Integrate Runtime Risk Engine**
   - Connect OMS positions to risk engine
   - Implement pre-trade risk checks
   - *Test*: Verify risk metric calculation and limit enforcement

10. **Complete OMS Integration**
    - Connect risk-approved signals to order generation
    - Implement position sizing logic
    - Add execution safety checks
    - *Test*: Verify order generation and submission

### Phase 5: Operational Systems (Weeks 9-10)
11. **Implement Risk Enforcement Layer**
    - Add kill switch and circuit breaker functionality
    - Implement daily loss limit monitoring
    - Add regime-based controls
    - *Test*: Verify automatic responses to risk scenarios

12. **Deploy Monitoring and Alerting**
    - Create system health dashboard
    - Implement performance tracking and alerting
    - Add audit trail for all decisions
    - *Test*: Verify monitoring catches system anomalies

### Phase 6: Learning and Adaptation (Weeks 11-12)
13. **Implement Feature Lifecycle Automation**
    - Add automatic feature validation and zeroing
    - Implement re-enablement criteria
    - *Test*: Verify feature enabling/disabling based on performance

14. **Deploy MLOps Pipeline**
    - Set up model registry and experiment tracking
    - Implement shadow mode testing
    - Create automated retraining pipeline
    - *Test*: Verify model promotion and rollback procedures

### Phase 7: Validation and Go-Live (Weeks 13-14)
15. **End-to-End Testing**
    - Run system with historical data in replay mode
    - Validate performance matches expectations
    - Test failure scenarios and recovery procedures
    - *Test*: Verify system behaves correctly under stress

16. **Paper Trading Validation**
    - Deploy system in paper trading mode
    - Monitor performance vs. benchmarks
    - Validate risk controls and operational procedures
    - *Test*: Verify system operates safely with zero capital risk

17. **Gradual Capital Deployment**
    - Start with minimal capital allocation
    - Scale up as performance validates
    - Monitor for any unexpected behavior
    - *Test*: Verify system scales appropriately with capital

18. **Go-Live and Hypercare**
    - Full production deployment
    - Enhanced monitoring during initial period
    - Daily review meetings for first two weeks
    - *Test*: Verify system meets all operational requirements

## 13. Anti-Patterns (STRICT)

### MUST NOT DO:

1. **Skipping Risk Checks**
   - Never allow raw strategy signals to bypass risk engine
   - Never disable risk limits for "special opportunities"
   - Never bypass pre-trade validation for speed

2. **Using Raw Alpha Without Validation**
   - Never use features that haven't passed FeatureValidator
   - Never ignore IC thresholds or decay limits
   - Never use features with poor stability scores

3. **Direct Strategy → OMS Execution**
   - Never allow strategies to generate orders directly
   - Never bypass portfolio allocation and risk checks
   - Never let individual strategies control position sizing

4. **Ignoring Regime**
   - Never use static strategy weights regardless of market conditions
   - Never fail to adjust risk parameters by regime
   - Never overlook regime-specific feature performance

5. **Overfitting to Recent Performance**
   - Never chase recent winners without statistical significance
   - Never increase allocation based on short-term luck
   - Never ignore transaction costs in performance evaluation

6. **Neglecting Latency**
   - Never ignore processing delays in real-time decisions
   - Never assume zero-latency communication between components
   - Never fail to timestamp and latency-track all events

7. **Inadequate Error Handling**
   - Never let exceptions crash the entire system
   - Never fail to degrade gracefully when components fail
   - Never ignore partial system failures

8. **Hardcoding Parameters**
   - Never embed strategy parameters in code
   - Never require code changes for parameter adjustments
   - Never fail to version control all parameters

9. **Missing Audit Trails**
   - Never fail to log all decisions and rationales
   - Never allow untracked changes to system behavior
   - Never fail to reconstruct decision-making process

10. **Single Point of Failure**
    - Never rely on any single component for system operation
    - Never fail to implement redundancy for critical functions
    - Never ignore failure modes in system design

### Specific Prohibitions:

- ❌ `strategy.compute_signals() → oms.create_order()` (bypasses allocation and risk)
- ❌ `alpha_features → strategy` (bypasses validation)
- ❌ `Fixed leverage limits regardless of volatility regime`
- ❌ `Equal strategy weighting regardless of performance`
- ❌ `Manual override of risk limits without review and logging`
- ❌ `Using same lookback window for all features regardless of stability`
- ❌ `Ignoring transaction costs in performance calculations`
- ❌ `Failing to validate order prices against market data`
- ❌ `Not reconciling OMS positions with internal calculations`
- ❌ `Using production capital for strategy development/testing`
- ❌ `Deploying strategy changes without shadow mode validation`
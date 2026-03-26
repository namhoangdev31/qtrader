# HFTOptimizer Implementation Plan

## Overview

This plan outlines the implementation of the HFTOptimizer module to achieve sub-second execution latency (<100ms end-to-end) as specified in the requirements.

## Current State Analysis

The existing `qtrader/hft/optimizer.py` provides a foundation but needs enhancements to fully meet the requirements:

- Basic latency profiling exists but needs stage-specific tracking
- HFT mode enabling/disabling is present but needs integration with TradingBot
- Missing adaptive throttling based on latency
- Missing failsafe mechanisms for high latency scenarios
- Missing configuration support for HFT mode
- Missing specific optimization implementations for the 9 areas outlined

## Implementation Plan

### 1. Enhanced HFTOptimizer Module (`qtrader/hft/optimizer.py`)

#### Core Enhancements

- **Latency Tracking**: Extend LatencyProfiler to track specific pipeline stages (market_data → alpha, alpha → signal, signal → order, order → fill)
- **JSON Logging**: Ensure latency data is logged in the required JSON format
- **Adaptive Throttling**: Implement rate limiting based on latency measurements
- **Failsafe Mechanisms**: Automatic reduction of trading frequency and switch to safe mode when latency exceeds thresholds
- **Configuration Support**: Add ability to toggle HFT mode via configuration
- **Performance Optimizations**: Implement the 9 optimization areas specified

#### Specific Changes

1. Enhanced LatencyProfiler:
   - Track cumulative latencies for each pipeline stage
   - Provide method to get latency breakdown as dictionary
   - Log latency data in required JSON format
   - Add methods to reset specific stage tracking

2. HFTOptimizer Class Enhancements:
   - Add adaptive throttling mechanism
   - Implement failsafe logic (reduce trading frequency, safe mode)
   - Add configuration loading/saving capabilities
   - Enhance optimization methods to actually implement the specified optimizations
   - Add integration hooks for TradingBot

3. New Methods:
   - `get_latency_breakdown()`: Returns latency breakdown dictionary
   - `should_throttle()`: Determines if trading should be throttled based on latency
   - `enter_safe_mode()`: Switches to conservative trading parameters
   - `exit_safe_mode()`: Returns to normal trading parameters
   - `update_config()`: Updates optimizer configuration

### 2. Configuration Enhancements

#### Add HFT Mode Configuration

- Add `hft_mode` section to bot configuration YAML files
- Parameters: `enabled`, `latency_target_ms`, `throttle_threshold_ms`, `safe_mode_latency_ms`
- Update `BotConfig` to parse HFT configuration

#### Example Configuration

```yaml
hft_mode:
  enabled: true
  latency_target_ms: 100
  throttle_threshold_ms: 120
  safe_mode_latency_ms: 150
```

### 3. TradingBot Integration

#### Modifications to `qtrader/bot/runner.py`

1. **Initialization**:
   - Create HFTOptimizer instance during bot initialization
   - Load HFT configuration from BotConfig

2. **Latency Tracking Integration**:
   - Wrap key pipeline stages with HFTOptimizer latency tracking
   - Market data fetching → alpha computation
   - Alpha computation → signal generation
   - Signal generation → order creation
   - Order creation → fill handling

3. **Adaptive Trading Logic**:
   - Modify signal loop to check HFTOptimizer.should_throttle()
   - Adjust signal_interval_s based on throttling recommendations
   - Modify risk loop to respond to HFTOptimizer failsafe triggers

4. **Performance Reporting**:
   - Add HFTOptimizer performance metrics to bot logs
   - Periodically log latency statistics

### 4. Latency Tracking Implementation Details

#### Pipeline Stages to Track

1. `market_data_to_alpha`: Time from receiving market data to computing alpha signals
2. `alpha_to_signal`: Time from alpha computation to final signal generation
3. `signal_to_order`: Time from signal generation to order creation
4. `order_to_fill`: Time from order submission to fill receipt

#### Implementation Approach

- Use HFTOptimizer.latency_context() as context managers around each stage
- Alternatively, use HFTOptimizer.latency_tracker() decorator on key methods
- Collect and aggregate latency data for reporting

### 5. Adaptive Throttling & Failsafe Mechanisms

#### Throttling Logic

- Monitor average latency over recent window (e.g., last 100 operations)
- If average latency > throttle_threshold_ms (e.g., 120ms):
  - Increase signal_interval_s by factor (e.g., 1.5x)
  - Log throttling event
- If average latency < latency_target_ms (e.g., 100ms) for sustained period:
  - Gradually decrease signal_interval_s back to baseline

#### Failsafe Logic

- If average latency > safe_mode_latency_ms (e.g., 150ms):
  - Enter safe mode: reduce position sizes, increase stop limits, disable aggressive strategies
  - Log failsafe activation
- If latency returns to acceptable levels:
  - Exit safe mode and restore normal parameters

### 6. Performance Optimization Implementation

#### The 9 Optimization Areas

1. **Event Loop**: Already implemented via uvloop setup
2. **Data Pipeline**:
   - Implement actual Polars lazy execution in optimize_data_pipeline()
   - Add batch processing capabilities per tick window
3. **CPU Isolation**:
   - Enhance thread pool usage for heavy computations
   - Offload ML inference to thread pool
4. **Memory Management**:
   - Implement rolling window with max 1000 ticks (already partially implemented)
   - Ensure views are used instead of copies where possible
5. **Network Optimization**:
   - Implement persistent WebSocket connections in optimize_network()
   - Replace REST polling with WebSocket where applicable
6. **Serialization**:
   - Implement msgpack serialization option in optimize_serialization()
   - Provide fallback to current JSON serialization
7. **Feature Computation**:
   - Implement actual expression precompilation in optimize_feature_computation()
   - Ensure vectorized operations only
8. **Strategy Optimization**:
   - Implement actual ML weight precomputation in optimize_strategy()
   - Avoid heavy ML in hot path
9. **Risk Engine**:
   - Implement fast-path checks in optimize_risk_engine()
   - Provide async fallback for full risk checks

## Files to Modify/Create

1. `qtrader/hft/optimizer.py` - Main implementation (enhance existing)
2. `qtrader/core/config.py` - Add HFT configuration parsing (if needed)
3. `qtrader/bot/runner.py` - Integrate HFTOptimizer with TradingBot
4. `configs/bot_paper.yaml` - Add HFT mode configuration example
5. `configs/bot_prod.yaml` - Add HFT mode configuration example
6. `tests/unit/hft/test_optimizer.py` - Update/enhance unit tests

## Dependencies Check

- Verify uvloop is in pyproject.toml (optional dependency)
- Verify msgpack is in pyproject.toml (for serialization optimization)
- All other dependencies (polars, etc.) should already be present

## Testing Strategy

1. Unit tests for HFTOptimizer latency tracking
2. Integration tests verifying TradingBot-HFTOptimizer interaction
3. Performance tests to verify latency improvements
4. Configuration loading tests
5. Edge case tests for throttling and failsafe mechanisms

## Acceptance Criteria

1. Latency profiling tracks all required pipeline stages
2. Latency data is logged in required JSON format
3. Adaptive throttling functions correctly based on latency measurements
4. Failsafe mechanisms activate when latency exceeds thresholds
5. HFT mode can be toggled via configuration
6. All 9 optimization areas are implemented and functional
7. Integration with TradingBot works without breaking existing functionality
8. Unit test coverage >= 90%
9. All linting and type checking passes
10. DoD verification passes (ruff, mypy, pytest, cargo test)

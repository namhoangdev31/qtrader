```json
{
  "modules_checked": 300,
  "violations": 120,
  "coverage": "60%",
  "status": "NON-COMPLIANT"
}
```

# Dependency Violation Report

## Core Authorities (Set A)

| Authority | Implementation Module           | Requirement |
|:----------|:--------------------------------|:------------|
| Config    | `qtrader.core.config_manager`   | Mandatory   |
| Trace     | `qtrader.core.trace_authority`  | Mandatory   |
| FailFast  | `qtrader.core.fail_fast_engine` | Mandatory   |
| Logger    | `qtrader.core.logger`           | Mandatory   |
| Decimal   | `qtrader.core.decimal_adapter`  | Mandatory   |

## Detected Violations (Sample)

| Module                                   | Missing Authorities                         | Impact           |
|:-----------------------------------------|:--------------------------------------------|:-----------------|
| `qtrader.strategy.ensemble_strategy`     | {Config, Trace, FailFast, Decimal}         | Low reliability  |
| `qtrader.strategy.probabilistic_strategy`| {Config, Trace, FailFast, Logger, Decimal} | **UNCONTROLLED** |
| `qtrader.strategy.mean_reversion`        | {Config, Trace, FailFast, Logger, Decimal} | **UNCONTROLLED** |
| `qtrader.analytics.drift_detector`       | {Config, Trace, FailFast, Logger, Decimal} | **UNCONTROLLED** |
| `qtrader.analytics.drift`                | {Config, Trace, FailFast, Decimal}         | No trace context |

## Remediation Plan

1. Inject `ConfigManager` and `TraceAuthority` into all strategy entry points.
2. Replace vanilla `decimal.Decimal` with `DecimalAdapter.d` in all arithmetic paths.
3. Ensure all `except Exception` blocks are replaced with `FailFastEngine.handle_error()`.
4. Wrap all execution loops with `TraceAuthority.start_trace()`.

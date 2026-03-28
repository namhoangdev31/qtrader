# System Impact Analysis — Phase -1 Pre-Alignment

> Audit Date: 2026-03-28 | System: qtrader | Phase: PHASE_-1

---

## Executive Summary

Phase -1 introduced foundational infrastructure for six critical system qualities:
Determinism, Failure Transparency, Config Authority, Numeric Precision, Async Discipline,
and Observability. **The infrastructure was successfully designed and implemented**, but
**adoption and integration across the codebase remains critically low**, rendering the
system **NOT READY** for Phase 0.

---

## Codebase Impact Metrics

| Metric                    | Value   |
|---------------------------|---------|
| Total Python Files        | 427     |
| Total Lines of Code       | 56,890  |
| Files Added (Phase -1)    | 86      |
| Lines Modified            | 11,519  |
| Lines Inserted            | 11,519  |
| Lines Deleted             | 1,552   |
| Test Files                | 232     |
| Modules (directories)     | 34      |
| Config Files Created      | 15      |

---

## Quality Delta (ΔQ)

| Quality Dimension    | Q_before | Q_after | ΔQ      | Notes                                                |
|---------------------|----------|---------|---------|------------------------------------------------------|
| Reliability         | 0.20     | 0.45    | +0.25   | FailFast, ErrorBus, error taxonomy defined           |
| Reproducibility     | 0.05     | 0.15    | +0.10   | SeedManager built but 0 downstream adopters          |
| Latency Control     | 0.30     | 0.65    | +0.35   | LatencyMonitor + budget YAML active                  |
| Risk Control        | 0.25     | 0.50    | +0.25   | Kill switch + escalation logic, not yet wired        |
| Debuggability       | 0.15     | 0.40    | +0.25   | TraceManager + structured logger, low adoption       |

**Aggregate ΔQ = +0.24 (from 0.19 → 0.43)**

---

## Infrastructure vs. Integration Gap

The central finding of this audit is the **Infrastructure-Integration Gap**: all six
Phase -1 authorities have been implemented as standalone modules, but almost none have been
wired into the production execution paths.

| Authority               | Module                              | Importers | Status              |
|------------------------|--------------------------------------|-----------|---------------------|
| SeedManager            | `core/seed_manager.py`               | 0         | ❌ ORPHANED          |
| DecimalAdapter         | `core/decimal_adapter.py`            | 1         | ❌ NEAR-ORPHANED     |
| AsyncAdapter           | `core/async_adapter.py`              | 0         | ❌ ORPHANED          |
| FailFastEngine         | `core/fail_fast_engine.py`           | 1         | ❌ NEAR-ORPHANED     |
| TraceManager           | `core/trace_manager.py`              | 37        | ⚠️ PARTIAL           |
| QTraderLogger          | `core/logger.py`                     | 37        | ⚠️ PARTIAL           |
| ConfigEnforcer         | `core/config_enforcer.py`            | 1         | ❌ NEAR-ORPHANED     |
| LatencyMonitor         | `core/latency_monitor.py`            | 1         | ❌ NEAR-ORPHANED     |
| PrecisionValidator     | `core/precision_validator.py`        | 1         | ❌ NEAR-ORPHANED     |

---

## Risk Assessment

### Critical Risks

1. **Non-Deterministic Execution**: 94.82% of entropy sources uncontrolled. Backtests
   cannot be reproduced. Strategy optimization results are unreliable.

2. **Silent Financial Losses**: 128 silent failures in critical paths (execution, OMS, risk).
   Position errors, missed fills, and risk breaches can go undetected.

3. **Precision Drift**: 785 high-risk float operations in financial arithmetic.
   Cumulative rounding error can produce material P&L discrepancies over time.

4. **Latency Opacity**: Despite having a LatencyMonitor, it is not integrated into the
   critical path. Actual pipeline latency is unmeasured.

### Moderate Risks

5. **Config Sprawl**: 1881 hardcoded values across 10 modules. Parameter changes require
   code deployment instead of config rollover.

6. **Incomplete Audit Trail**: Only ~9.84% of files emit structured logs. Regulatory
   compliance and incident forensics are compromised.

---

## Module-Level Heat Map

| Module         | D | F | CFG | P | A | O | Overall Risk |
|---------------|---|---|-----|---|---|---|-------------|
| execution      | 🔴 | 🔴 | 🔴  | 🔴 | 🟡 | 🟡 | **CRITICAL** |
| oms            | 🟡 | 🔴 | 🔴  | 🔴 | 🟡 | 🟡 | **CRITICAL** |
| risk           | 🔴 | 🔴 | 🟡  | 🔴 | 🟢 | 🟡 | **CRITICAL** |
| hft            | 🔴 | 🔴 | 🔴  | 🟡 | 🔴 | 🟡 | **CRITICAL** |
| portfolio      | 🔴 | 🟡 | 🟡  | 🔴 | 🟢 | 🟡 | **HIGH**     |
| meta           | 🔴 | 🟡 | 🟡  | 🟡 | 🟢 | 🟡 | **HIGH**     |
| certification  | 🔴 | 🟡 | 🔴  | 🟡 | 🟢 | 🔴 | **HIGH**     |
| compliance     | 🔴 | 🟡 | 🔴  | 🟡 | 🟢 | 🔴 | **HIGH**     |
| core           | 🟢 | 🔴 | 🔴  | 🟢 | 🟢 | 🟡 | **MODERATE** |
| data           | 🟡 | 🟡 | 🟡  | 🟡 | 🔴 | 🟡 | **MODERATE** |
| governance     | 🟡 | 🔴 | 🔴  | 🟡 | 🟢 | 🔴 | **HIGH**     |

Legend: 🟢 Compliant | 🟡 Warning | 🔴 Violation

---

## Positive Outcomes

Despite the integration gap, Phase -1 delivered significant architectural value:

1. **Error Taxonomy**: Clean 3-tier severity model (`Recoverable → Critical → Fatal`)
   with automatic escalation in `FailFastEngine`.

2. **Precision Architecture**: `DecimalAdapter` with banker's rounding, domain-specific
   quantization (price/8, qty/6, notional/2), and float rejection.

3. **Trace Propagation**: `TraceManager` using `contextvars` for implicit async-safe
   trace_id propagation across coroutine boundaries.

4. **Replay Validation**: `ReplayValidator` with bit-perfect state comparison including
   Polars DataFrame-aware equality.

5. **Latency Budget Framework**: Config-driven per-stage latency enforcement with
   nanosecond-resolution timing via `time.perf_counter_ns()`.

6. **Audit Scanner Suite**: Five automated scanners (entropy, exception, hardcode,
   float, blocking) producing machine-readable reports.

---

## Recommended Phase 0 Priorities

1. **Wire SeedManager into GlobalOrchestrator**: Call `apply_global()` at system boot.
   Derive module seeds for all stochastic modules.

2. **Replace all `except Exception: pass` patterns**: Mandate `FailFastEngine.handle_error()`
   or typed exception handlers.

3. **Migrate critical-path arithmetic to DecimalAdapter**: Start with execution, OMS,
   risk, and portfolio modules.

4. **Eliminate `time.sleep()` from production code**: Replace `coinbase_market.py`
   blocking calls with async event-driven waiting.

5. **Mandatory structured logging**: Every module must import `qtrader.core.logger`
   and emit `log_event()` for all state transitions.

6. **Config extraction sprint**: Convert the top 649 critical hardcodes to
   `configs/*.yaml` entries loaded via `ConfigManager`.

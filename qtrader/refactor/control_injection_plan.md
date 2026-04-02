# Control Injection Plan - PHASE_-1_5_G3_P2

Governance and authority enforcement system for the QTrader 7-stage execution pipeline.

## 1. Authority Vector (C) Definition

C = { `trace_id`, `config_manager`, `fail_fast_engine`, `logger`, `math_authority` }

All production pipeline stages must have the full control vector injected as mandatory dependencies.

## 2. Stage Injection Mapping

| Pipeline Stage | Logic Location | C - Trace | C - Config | C - FailFast | C - Logger | C - Math |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| 1. Market | `handle_market_data` | ✅ | ✅ | ✅ | ✅ | ✅ |
| 2. Feature | `handle_features` | ✅ | ✅ | ✅ | ✅ | ✅ |
| 3. Signal | `handle_validated_features` | ✅ | ✅ | ✅ | ✅ | ✅ |
| 4. Risk | `handle_signals` | ✅ | ✅ | ✅ | ✅ | ✅ |
| 5. Order/Exec | `handle_orders` | ✅ | ✅ | ✅ | ✅ | ✅ |
| 6. Fill | `handle_fills` | ✅ | ✅ | ✅ | ✅ | ✅ |
| 7. Feedback | `_handle_feedback_update` | ✅ | ✅ | ✅ | ✅ | ✅ |

## 3. Enforcement Pattern (Code Logic)

All stages must follow the sovereign wrapper pattern to ensure deterministic recovery and auditability:

```python
async def execute_stage(self, stage_input):
    trace_id = TraceAuthority.propagate(stage_input)
    log = logger.bind(trace_id=trace_id)
    try:
        # Numeric Normalization via math_authority
        # Config Retrieval via config_manager
        # Process stage
        # Publish success
    except Exception as e:
        # Atomic failure response via fail_fast_engine
        await self.fail_fast_engine.handle_error(source="stage_name", error=e)
```

## 4. Constraint Checklist

- [x] No stage without full control vector.
- [x] Numerical safety (ε=0) enforced at price/qty/strength gates.
- [x] Dynamic configuration version gating for risk limits.
- [x] End-to-end trace propagation (Market → Fill).

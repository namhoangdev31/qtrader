# Operational Protocol for System Errors

The following protocol defines the deterministic handling behavior of `qtrader` for every error category within the hierarchy.

## 1. Hierarchy & Severity

| Class | Severity | Priority | Default Policy |
| :--- | :--- | :--- | :--- |
| `RecoverableError` | 1 | LOW | **Automated Retry** (Exponential Backoff) |
| `ValidationError` | 1 | LOW | **Log & Audit** (Drop invalid payload) |
| `CriticalError` | 2 | MEDIUM | **Module Isolation** (Stop module execution) |
| `FatalError` | 3 | HIGH | **Hard Halt** (Global system termination) |

> [!CAUTION]
> If an exception occurs that is **not** part of this hierarchy, the `classify_error()` helper will auto-escalate it to `FatalError`.

## 2. Policy Definitions

### RecoverableError (s=1)
- **Retry Logic**: Max 3 attempts, exponentially increasing delay (min 100ms, max 5s).
- **Escalation**: After 3 failed retries, the error escalates to **CriticalError**.

### CriticalError (s=2)
- **Isolation Logic**: The specific strategy or execution execution thread responsible for the error is stopped.
- **Alerting**: High-priority alert emitted to the `ErrorBus` and captured in PagerDuty/similar.
- **Human Intervention**: Required for a module restart.

### FatalError (s=3)
- **Halt Protocol**: 
    1.  Cancel all active/pending orders immediately.
    2.  Set all strategy states to `HALTED`.
    3.  Commit current memory state to `StateStore`.
    4.  Exit process with non-zero status.

## 3. Implementation Guards

- **No bare `except: pass`**: All exceptions in critical paths MUST be re-raised or handled according to this spec.
- **Logging Rule**: Every error must be logged with its `code` and `severity`.

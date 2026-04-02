```json
{
  "constraints": 6,
  "critical": 4,
  "coverage": "100%",
  "status": "DEFINED"
}
```

# System Runtime Constraint Specification

This document defines the hard runtime constraints enforced across the QTrader system to guarantee deterministic execution, exact arithmetic, traceable contexts, and robust error handling.

## 1. Constraint Vector

The system maintains a fundamental constraint vector $C$ defined as:

$$C = \{determinism, config\_usage, trace\_propagation, no\_float, failfast, async\_compliance\}$$

## 2. Mathematical Model

Let $C(S)$ be the constraint vector of system $S$.

**Valid System:**
A system is considered valid if and only if all constraints evaluate to TRUE:
$$S_{valid} \Leftrightarrow \forall c \in C: c(S) = TRUE$$

**Violation Condition:**
If any constraint evaluates to FALSE, the system enters an INVALID state and must halt execution deterministically:
$$\exists c \in C: c(S) = FALSE \rightarrow INVALID$$

## 3. Constraint Definitions

### C1: Determinism (Severity: Critical)
- **Rule:** No uncontrolled or implicit randomness is permitted. 
- **Enforcement:** The `SeedManager` must be used to generate all seeds and random states. Native `random` or unseeded `numpy.random` calls will trigger a violation.

### C2: Config Usage (Severity: High)
- **Rule:** No hardcoded operational parameters or magic numbers.
- **Enforcement:** All parameters must be injected via the `ConfigManager`.

### C3: Trace Propagation (Severity: High)
- **Rule:** Every execution path and event must carry a universal `trace_id`.
- **Enforcement:** `TraceAuthority` context must be propagated across asynchronous boundaries; missing trace IDs yield an immediate violation.

### C4: Numeric (Severity: Critical)
- **Rule:** Floating-point operations (`float`) are strictly prohibited in financial logic (pricing, position sizing, PnL computation).
- **Enforcement:** Use `DecimalAdapter` or strict `Decimal` precision mapping for all monetary calculations.

### C5: FailFast (Severity: Critical)
- **Rule:** Silent exceptions (`except Exception: pass`) are banned.
- **Enforcement:** All unexpected exceptions must be routed through the `FailFastEngine` to deterministically transition the system to an ERROR/SHUTDOWN state.

### C6: Async Compliance (Severity: Critical)
- **Rule:** Blocking synchronous calls are banned inside the `asyncio` event loop.
- **Enforcement:** I/O operations must use `aiohttp`, `asyncpg`, or `asyncio.sleep()`. Usage of `time.sleep()` is prohibited.

## 4. Execution Enforcement

Future CI/CD and AST parsers will read the `constraint_matrix.json` and `enforcement_priority_map.json` to dynamically inject pre-commit hooks and static analysis checks to validate the constraint vector $C$.

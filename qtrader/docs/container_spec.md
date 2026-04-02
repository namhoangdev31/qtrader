```json
{
  "services": 5,
  "singleton_enforced": true,
  "status": "READY"
}
```

# DI Container Specification (Phase -1.5)

## 1. Objective

Provide a centralized mechanism for injecting core system dependencies (Authorities) into all modules, ensuring deterministic execution and eliminating static bypass.

## 2. Mathematical Model

Let:
- **C**: The DI Container, defined as a set of services {s₁ ... sₙ}.
- **S**: The subset of core authorities required for all modules {Config, Trace, Logger, FailFast, Decimal}.
- **resolve(M)**: Dependency resolution for module M, mapping to s ∈ S.

### Constraint:

∀ module **M**:
**resolve(M) ⊆ C**

This ensures that no module M can possess a dependency that is not registered and managed by the container C.

## 3. Dependency Roles (Set S)

| Key      | Implementation Module           | Interface (Singleton) | Role                          |
|:---------|:--------------------------------|:----------------------|:------------------------------|
| `config` | `qtrader.core.config_manager`   | `ConfigManager`       | Dynamic Parameter Enforcement |
| `trace`  | `qtrader.core.trace_authority`  | `TraceAuthority`      | Context Correlation           |
| `logger` | `qtrader.core.logger`           | `QTraderLogger`       | Structured Audit Log          |
| `failfast`| `qtrader.core.fail_fast_engine`| `FailFastEngine`      | Deterministic Halt            |
| `decimal` | `qtrader.core.decimal_adapter` | `DecimalAdapter`      | Financial Arithmetic Authority |

## 4. Constraint Enforcement

1. **Singleton Sovereignty**: All services in the container MUST be singletons.
2. **Access Control**: Modules MUST NOT directly instantiate any service in Set S.
3. **Trace Mandatory**: No service call should bypass the `TraceAuthority` derived context.

## 5. Implementation Usage

To resolve a dependency:

```python
from qtrader.core.container import container

config = container.get("config")
trace = container.get("trace")
```

## 6. Observability

The container tracks:
- `services_registered`: Total count (Target = 5).
- `container_usage_rate`: Frequency of system-wide resolutions.
- `status`: SET to `READY` upon successful registration of all 5 authorities.

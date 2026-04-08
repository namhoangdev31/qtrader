# QTRADER UNIFIED SYSTEM ARCHITECTURE

> **Version:** 1.0  
> **Standard:** `standash-document.md`  
> **Protocol:** KILO.AI Industrial Grade

---

## 1. LAYERED HIERARCHY

The system is organized into **7 functional layers**. Each module MUST belong to exactly one layer.

| Layer | Name | Responsibility | Core Modules |
|-------|------|----------------|--------------|
| **L1** | **Market Data** | Feed ingestion, arbitration, normalization, and quality gates. | `data/`, `pipeline/sources/` |
| **L2** | **Feature / Alpha** | Factor engineering, neutralized features, and alpha signal models. | `features/`, `alpha/` |
| **L3** | **Strategy** | Signal generation, machine learning, research labs, and autonomous agents. | `strategy/`, `ml/`, `research/`, `meta/`, `pipeline/research.py` |
| **L4** | **Risk** | Real-time risk engine, portfolio allocation (HRP/RP), and limits enforcement. | `risk/`, `portfolio/` |
| **L5** | **Execution** | Smart Order Routing (SOR), HFT micro-price models, and exchange adapters. | `execution/`, `hft/` |
| **L6** | **OMS** | Order lifecycle management, position tracking, and fill reconciliation. | `oms/` |
| **L7** | **Monitoring** | War Room controls, system metrics, alerting, and post-trade feedback. | `monitoring/`, `analytics/`, `api/`, `feedback/` |

---

## 2. DEPENDENCY RULES

To maintain system determinism and prevent circular dependencies, the following rules are ENFORCED:

1. **Down-Stream Dependency Only**: Layer $N$ can only import from Layer $M$ where $M < N$.
   - *Example:* `Strategy (L3)` can import `Alpha (L2)`, but `Alpha (L2)` CANNOT import `Strategy (L3)`.
2. **Infrastructure (L0)**: `core/`, `utils/`, and `configs/` are considered Layer 0. All layers can depend on L0.
3. **Internal Boundaries**: Sub-modules within a layer should minimize cross-module dependencies to avoid "spaghetti" clusters.
4. **Monitoring (L7) Exception**: Monitoring can observe all layers ($L1-L6$) for data collection, but NO low-level layer can depend on L7 for operational logic.

---

## 3. ARCHITECTURE RESOLVER CONTRACT

The `ArchitectureResolver` is a logical mapping engine used during code generation and validation.

### `resolve_module(module_name) -> layer`

| input | output |
|-------|--------|
| `qtrader.data` | `Market Data (L1)` |
| `qtrader.alpha` | `Feature / Alpha (L2)` |
| `qtrader.strategy` | `Strategy (L3)` |
| `qtrader.risk` | `Risk (L4)` |
| `qtrader.portfolio` | `Risk (L4)` |
| `qtrader.execution` | `Execution (L5)` |
| `qtrader.hft` | `Execution (L5)` |
| `qtrader.oms` | `OMS (L6)` |
| `qtrader.monitoring` | `Monitoring (L7)` |

---

## 4. ENFORCEMENT & VALIDATION

### CI/CD Integration
- **Import Check**: Every PR must pass an import boundary check (no "bottom-up" imports).
- **Mapping Check**: New top-level modules MUST be added to this document before code is accepted.

### Failure Modes
- **Unknown Module**: If `resolve_module` encounters an unmapped path (e.g. `qtrader/new_tool/`), it triggers an `ArchitectureMappingError`.
- **Violation**: If `risk (L4)` imports from `execution (L5)`, the build fails with a `LayerViolationError`.

---

## 5. DESIGN PRINCIPLES

- **Determinism**: Higher layers must not affect the deterministic output of lower layers.
- **Isolation**: Each layer is a "Fortress". A failure in `Execution (L5)` must not corrupt the state of `Market Data (L1)`.
- **Event-Driven**: Communication between layers is primarily via the `Event Bus` (L0) to maintain decoupling.

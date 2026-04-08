# 2. ATOMIC CODING & LOGIC

---

## 2.1 Single Responsibility

**One method should solve only one problem.**

```python
# ✅ Correct — clearly separated
def compute_momentum(df: pl.DataFrame) -> pl.Series: ...
def check_signal(series: pl.Series) -> bool: ...

# ❌ Incorrect — two responsibilities in one function
def compute_momentum_and_check_signal(df): ...
```

---

## 2.2 Type Hints — Mandatory 100%

All public functions and methods **must** have full type annotations.

```python
# ✅ Correct
async def route_order(
    self,
    order: OrderEvent,
    market_data: dict[str, dict[str, Any]],
    fees_data: dict[str, dict[str, Decimal]] | None = None,
) -> list[OrderEvent]:
    ...

# ❌ Incorrect — missing type hints
def order_route(self, order, market_data):
    ...
```

- Run `mypy qtrader/ --strict` before committing. Zero errors required.

---

## 2.3 No Hardcoding — Config First

All numeric parameters must come from arguments or a config object; no hardcoding.

```python
# ✅ Correct — configurable dataclass field
@dataclass(slots=True)
class MomentumAlpha:
    lookback: int = 20
    zscore_window: int = 252

    def compute(self, df: pl.DataFrame) -> pl.Series:
        return df["close"].rolling_mean(self.lookback)

# ❌ Incorrect — magic number
def compute(df):
    return df["close"].rolling_mean(20)
```

---

## 2.4 Documentation & Comments — Parameter Focus

Minimize code examples in comments/docstrings. Focus on explaining the meaning and constraints of input values.

- **✅ Priority**: Explain parameter meaning, units (e.g., USD, seconds), or constraints (e.g., must be > 0).
- **❌ Avoid**: Writing verbose code examples inside docstrings.

```python
# ✅ Correct
def calculate_position_size(
    equity: float,        # Total available account equity (USD)
    risk_percent: float,  # Max % of equity to risk per trade (0.0 < x < 1.0)
    stop_loss: float      # Absolute distance from entry to SL
) -> float:
    ...

# ❌ Incorrect — excessive examples, missing parameter explanations
def calculate_position_size(equity, risk_percent, stop_loss):
    """
    Example: 
    >>> calculate_position_size(10000, 0.01, 50)
    2.0
    """
    ...
```

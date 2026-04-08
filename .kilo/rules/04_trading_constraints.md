# 4. TRADING SPECIFIC CONSTRAINTS

> Applicable to all code in the bot's production trading path.

---

## 4.1 Zero Latency — No `time.sleep()`

`time.sleep()` and `await asyncio.sleep()` are **absolutely forbidden** in production code.
All timing logic must be based on the **candle/event timestamp**.

```python
# ❌ FORBIDDEN
time.sleep(1)
await asyncio.sleep(0.5)

# ✅ Correct — event-driven timing
async def on_bar(self, bar: BarEvent) -> None:
    if bar.timestamp >= self._next_signal_ts:
        await self._generate_signal(bar)
```

Check: `grep -rn "time.sleep" qtrader/` → must be empty.

---

## 4.2 Memory Safety — Polars First

**DO NOT** use pandas `df.iloc` in loops.
Use **Polars vectorized expressions**.

```python
# ❌ Slow — row-by-row
for i in range(len(df)):
    val = df.iloc[i]["close"]

# ✅ Fast — Polars vectorized
signal = df.select(
    (pl.col("close") / pl.col("close").shift(1) - 1).alias("return")
)
```

**Large Datasets (>100k rows):** Use `df.lazy()` → `.collect()` to prevent OOM.
**History Buffer:** Use `.tail(n)` or `rolling_*(window_size=n)` — do not retain unbounded history.

---

## 4.3 Log Standard — Trade Events

Every entry/exit order **must** log the following format:

```text
[TRADE] {timestamp} | {symbol} {side} {qty}@{price} | SL={sl} TP={tp} | Reason: {reason}
```

```python
from loguru import logger

logger.info(
    "[TRADE] {} | {} {} {}@{} | SL={} TP={} | Reason: {}",
    bar.timestamp, order.symbol, order.side, order.quantity,
    order.price, sl, tp, reason,
)
```

---

## 4.4 Look-Ahead Bias Prevention

Alpha/Feature computation must use **only past data** at each timestep:

- ✅ `pl.col("close").shift(1)` — access the previous bar (safe)
- ❌ `pl.col("close").shift(-1)` — leak future data (forbidden)
- ✅ `rolling_mean`, `rolling_std` — backward-looking by default (safe)

**Mandatory Test** for every alpha:

```python
def test_no_look_ahead_bias():
    df_past = build_prices(40)
    df_full = build_prices(60)   # 20 "future" rows appended
    alpha = MomentumAlpha(lookback=5, zscore_window=20)
    # Value at index 35 MUST be identical regardless of whether future data exists
    assert alpha.compute(df_past)[35] == alpha.compute(df_full)[35]
```

# 6. EDGE CASES — Required Coverage Matrix

Every module's test suite **must** include the following edge cases (apply as relevant):

| Category | Edge Cases to Cover |
| :--- | :--- |
| **Data** | Empty DataFrame, single-row DF, NaN values, Inf values, price = 0 |
| **Orders** | Quantity = 0 or negative, partial fill, full close, position flip (long→short) |
| **Risk** | Drawdown exactly at limit, drawdown exceeds limit, zero peak equity (first trade) |
| **Signal** | All-zero feature, constant price series (std = 0), perfectly correlated assets |
| **ML** | Untrained model predict, empty PnL history, model version not found in registry |
| **Execution** | Empty exchange list, all exchanges missing market data, order size > max_order_size |
| **Async** | Concurrent risk signals trigger kill switch, network timeout during cancel orders |
| **HFT** | Empty route list, all routes exceed latency target, route missing `latency` key |

---

## Pattern Examples

```python
# ✅ Test empty DataFrame
def test_optimizer_empty_input():
    opt = HRPOptimizer()
    assert opt.optimize(pl.DataFrame()) == {}

# ✅ Test NaN input does not crash
def test_feature_nan_input():
    df = pl.DataFrame({"close": [100.0, float("nan"), 110.0]})
    result = MomentumAlpha(lookback=1).compute(df)
    assert result is not None  # must not raise

# ✅ Test drawdown exactly at the limit
def test_risk_drawdown_at_limit():
    engine = RealTimeRiskEngine()
    engine.update_position("BTC", 1.0, 100_000.0)  # HWM = 100k
    engine.update_position("BTC", 1.0, 90_000.0)   # DD = 10%
    assert engine.current_drawdown == pytest.approx(0.10, abs=1e-4)

# ✅ Test position flip long → short
def test_oms_position_flip():
    pos = Position("BTC")
    pos.add_fill("BUY", 2.0, 50_000.0)
    pos.add_fill("SELL", 5.0, 60_000.0)  # close 2 long, open 3 short
    assert pos.qty == pytest.approx(-3.0)
```

import pytest
from qtrader.risk.dynamic_guardrail import DynamicGuardrailManager


def test_dynamic_guardrail_buy():
    manager = DynamicGuardrailManager(
        atr_multiplier=2.0, forecast_multiplier=1.5, min_sl_pct=0.01, max_sl_pct=0.05
    )
    result = manager.evaluate(price=100, atr=2.0, forecast_range=1.0, side="BUY")
    assert result["sl_pct"] == 0.015
    assert result["sl_price"] == 98.5
    assert result["tp_price"] == 100 + 100 * 0.015 * 2
    assert result["risk_source"] == "ML_FORECAST"


def test_dynamic_guardrail_fallback_atr():
    manager = DynamicGuardrailManager(atr_multiplier=2.5)
    result = manager.evaluate(price=100, atr=2.0, forecast_range=0.0, side="BUY")
    assert result["sl_pct"] == 0.05
    assert result["sl_price"] == 95.0
    assert result["risk_source"] == "ATR_FALLBACK"


def test_dynamic_guardrail_clipping():
    manager = DynamicGuardrailManager(min_sl_pct=0.01, max_sl_pct=0.05)
    result_high = manager.evaluate(price=100, atr=10.0, forecast_range=0.0)
    assert result_high["sl_pct"] == 0.05
    result_low = manager.evaluate(price=100, atr=0.1, forecast_range=0.0)
    assert result_low["sl_pct"] == 0.01

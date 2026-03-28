import pytest
from decimal import Decimal
from qtrader.core.decimal_adapter import d
from qtrader.core.financial_engine import financial_authority

def test_financial_engine_pnl_exact():
    # Buy at 45000.0, Sell at 45100.5, Quantity 1.25
    # Expect: (45100.5 - 45000.0) * 1.25 = 100.5 * 1.25 = 125.625
    res = financial_authority.pnl(d("45000.0"), d("45100.5"), d("1.25"))
    assert res == d("125.625")
    assert isinstance(res, Decimal)

def test_financial_engine_nav_exact():
    # Cash: 10000.0
    # Portfolio: BTC (0.5 qty @ 60000.0 price), SOL (100 qty @ 150.0 price)
    # Total: 10000.0 + (0.5 * 60000.0) + (100 * 150.0) 
    #        = 10000.0 + 30000.0 + 15000.0 = 55000.0
    positions = {
        "BTC": {"qty": d("0.5"), "market_price": d("60000.0")},
        "SOL": {"qty": d("100"), "market_price": d("150.0")}
    }
    nav = financial_authority.nav(d("10000.0"), positions)
    assert nav == d("55000.0")

def test_financial_engine_fee_exact():
    # Notional: 50000, FeeRate: 10 bps (0.1%)
    # Expect: 50000 * 0.001 = 50.0
    res = financial_authority.fee(d("50000.0"), d("10.0"))
    assert res == d("50.0")

def test_financial_engine_slippage_exact():
    # Exec: 45050, Ref: 45000, Qty: 2
    # Abs Slippage: (45050 - 45000) * 2 = 100
    res = financial_authority.slippage(d("45050.0"), d("45000.0"), d("2.0"))
    assert res == d("100.0")
    
    # Bps Slippage: (50 / 45000) * 10000 = 11.111111...
    res_bps = financial_authority.slippage_bps(d("45050.0"), d("45000.0"))
    assert res_bps > d("11.111")
    assert res_bps < d("11.112")

def test_financial_engine_float_reject():
    # Ensure float arguments trigger our numerical guard
    with pytest.raises(TypeError):
        financial_authority.pnl(45000.0, 45100.5, 1.25)

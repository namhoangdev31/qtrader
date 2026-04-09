import inspect
import sys
import time
from decimal import Decimal
import pytest
from qtrader.core.state_store import Position, SystemState
from qtrader.portfolio.nav_engine import NAVEngine

print(f"DEBUG: sys.path = {sys.path}")
print(f"DEBUG: NAVEngine file = {NAVEngine.__module__}")
try:
    print(f"DEBUG: NAVEngine source file = {inspect.getfile(NAVEngine)}")
except Exception as e:
    print(f"DEBUG: inspect error = {e}")


def test_nav_calculation_accuracy():
    engine = NAVEngine()
    state = SystemState()
    state.cash = Decimal("50000.0")
    state.total_fees = Decimal("120.0")
    symbol_btc = "BTC/USDT"
    state.positions[symbol_btc] = Position(
        symbol=symbol_btc,
        quantity=Decimal("0.5"),
        average_price=Decimal("45000.0"),
        realized_pnl=Decimal("500.0"),
    )
    symbol_eth = "ETH/USDT"
    state.positions[symbol_eth] = Position(
        symbol=symbol_eth,
        quantity=Decimal("-10.0"),
        average_price=Decimal("2500.0"),
        realized_pnl=Decimal("0.0"),
    )
    mark_prices = {symbol_btc: Decimal("48000.0"), symbol_eth: Decimal("2400.0")}
    evt = engine.compute(state, mark_prices)
    res = evt.payload
    assert res.nav == 49880.0
    assert res.unrealized_pnl == 2500.0
    assert res.realized_pnl == 500.0


def test_missing_price_fallback_logic():
    engine = NAVEngine()
    state = SystemState()
    state.cash = Decimal("100.0")
    symbol = "PEPE/USDT"
    state.positions[symbol] = Position(
        symbol=symbol,
        quantity=Decimal("1000.0"),
        average_price=Decimal("0.01"),
        market_value=Decimal("15.0"),
    )
    evt = engine.compute(state, {})
    res = evt.payload
    assert res.nav == 115.0
    assert res.unrealized_pnl == 5.0


def test_computational_latency_benchmark():
    engine = NAVEngine()
    state = SystemState()
    num_positions = 1000
    prices = {}
    for i in range(num_positions):
        sym = f"TOKEN_{i}"
        state.positions[sym] = Position(
            symbol=sym, quantity=Decimal(str(i)), average_price=Decimal("1.0")
        )
        prices[sym] = Decimal("1.1")
    t0 = time.perf_counter()
    engine.compute(state, prices)
    dt = (time.perf_counter() - t0) * 1000
    print(f"\nNAV Compute Latency: {dt:.4f}ms")
    assert dt < 10.0

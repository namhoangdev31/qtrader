import sys
from decimal import Decimal

import pytest

from qtrader.core.state_store import Position, SystemState
from qtrader.portfolio.nav_engine import NAVEngine

print(f"DEBUG: sys.path = {sys.path}")
print(f"DEBUG: NAVEngine file = {NAVEngine.__module__}")
# Use a more descriptive attribute if available
try:
    import inspect

    print(f"DEBUG: NAVEngine source file = {inspect.getfile(NAVEngine)}")
except Exception as e:
    print(f"DEBUG: inspect error = {e}")


def test_nav_calculation_accuracy():
    """Verify that NAV, Unrealized PnL, and Realized PnL are correctly aggregated."""
    engine = NAVEngine()
    state = SystemState()
    state.cash = Decimal("50000.0")
    state.total_fees = Decimal("120.0")

    # --- Position 1: Long BTC ---
    # Entry @ 45,000. Current @ 48,000.
    # Quantity 0.5. Realized PnL 500 (from previous partial close).
    symbol_btc = "BTC/USDT"
    state.positions[symbol_btc] = Position(
        symbol=symbol_btc,
        quantity=Decimal("0.5"),
        average_price=Decimal("45000.0"),
        realized_pnl=Decimal("500.0"),
    )

    # --- Position 2: Short ETH ---
    # Entry @ 2,500. Current @ 2,400 (Profit).
    # Quantity -10.0.
    symbol_eth = "ETH/USDT"
    state.positions[symbol_eth] = Position(
        symbol=symbol_eth,
        quantity=Decimal("-10.0"),
        average_price=Decimal("2500.0"),
        realized_pnl=Decimal("0.0"),
    )

    mark_prices = {symbol_btc: Decimal("48000.0"), symbol_eth: Decimal("2400.0")}

    # --- Calculation ---
    evt = engine.compute(state, mark_prices)
    res = evt.payload

    # 1. Market Value (MtM)
    # BTC: 0.5 * 48000 = 24000
    # ETH: -10 * 2400 = -24000
    # Total MtM = 0
    # NAV = Cash + MtM - Fees = 50000 + 0 - 120 = 49880
    assert res.nav == 49880.0

    # 2. Unrealized PnL
    # BTC: 0.5 * (48000 - 45000) = 1500
    # ETH: -10 * (2400 - 2500) = 1000
    # Total UPnL = 2500
    assert res.unrealized_pnl == 2500.0

    # 3. Realized PnL
    # BTC: 500. ETH: 0.
    assert res.realized_pnl == 500.0


def test_missing_price_fallback_logic():
    """Verify system resilience when mark prices are temporarily missing."""
    engine = NAVEngine()
    state = SystemState()
    state.cash = Decimal("100.0")

    symbol = "PEPE/USDT"
    # Last known valuation from position record
    state.positions[symbol] = Position(
        symbol=symbol,
        quantity=Decimal("1000.0"),
        average_price=Decimal("0.01"),
        market_value=Decimal("15.0"),  # Implied price 0.015
    )

    # Compute without mark_prices dict
    evt = engine.compute(state, {})
    res = evt.payload

    # Should fallback to implied price (0.015)
    # NAV = 100 + 15 = 115
    assert res.nav == 115.0
    # UPnL = 1000 * (0.015 - 0.01) = 5.0
    assert res.unrealized_pnl == 5.0


def test_computational_latency_benchmark():
    """Ensure the engine meets the sub-10ms performance target."""
    import time

    engine = NAVEngine()
    state = SystemState()

    # Large portfolio simulation
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

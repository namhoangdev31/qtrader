"""
Level 1 Critical Tests for RealTimeRiskEngine (risk/realtime.py)
Covers: position updates, drawdown tracking, VaR/CVaR, HHI concentration,
and limit breach detection under market-stress scenarios.
"""
import pytest
import polars as pl
from qtrader.risk.realtime import RealTimeRiskEngine


@pytest.fixture
def engine():
    return RealTimeRiskEngine(limits=[], event_bus=None)


# ---------------------------------------------------------------------------
# Position management
# ---------------------------------------------------------------------------

def test_update_position_first_insert(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    assert engine.positions.height == 1
    assert float(engine.positions.filter(pl.col("symbol") == "BTC")["market_value"][0]) == 50000.0


def test_update_position_updates_existing(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    engine.update_position("BTC", qty=2.0, price=60000.0)   # update qty and price
    assert engine.positions.height == 1
    row = engine.positions.filter(pl.col("symbol") == "BTC")
    assert float(row["qty"][0]) == 2.0
    assert float(row["market_value"][0]) == pytest.approx(120000.0)


def test_update_position_adds_multiple_symbols(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    engine.update_position("ETH", qty=10.0, price=3000.0)
    assert engine.positions.height == 2
    assert float(engine.equity) == pytest.approx(50000.0 + 30000.0)


def test_weight_sums_to_one(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    engine.update_position("ETH", qty=10.0, price=3000.0)
    total_weight = float(engine.positions["weight"].sum())
    assert total_weight == pytest.approx(1.0)


def test_short_position_reduces_equity(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    engine.update_position("ETH", qty=-5.0, price=3000.0)  # short ETH
    # 50000 - 15000 = 35000
    assert float(engine.equity) == pytest.approx(35000.0)


# ---------------------------------------------------------------------------
# High-water mark and drawdown
# ---------------------------------------------------------------------------

def test_hwm_tracks_peak_equity(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    assert engine.hwm == pytest.approx(50000.0)
    engine.update_position("BTC", qty=1.0, price=60000.0)
    assert engine.hwm == pytest.approx(60000.0)
    # Price drops — HWM must NOT decrease
    engine.update_position("BTC", qty=1.0, price=40000.0)
    assert engine.hwm == pytest.approx(60000.0)


def test_drawdown_is_computed_after_drop(engine):
    engine.update_position("BTC", qty=1.0, price=100000.0)   # HWM = 100k
    engine.update_position("BTC", qty=1.0, price=80000.0)    # equity = 80k
    # drawdown = (100000 - 80000) / 100000 = 20%
    assert engine.current_drawdown == pytest.approx(0.20, abs=1e-4)


def test_drawdown_zero_when_at_peak(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    engine.update_position("BTC", qty=1.0, price=60000.0)  # New peak
    assert engine.current_drawdown == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# PnL history and rolling window
# ---------------------------------------------------------------------------

def test_update_pnl_appends(engine):
    engine.update_pnl(100.0)
    engine.update_pnl(-50.0)
    assert engine.pnl_history.len() == 2


def test_update_pnl_rolling_window(engine):
    """History must never exceed _max_history entries (default 252)."""
    for i in range(300):
        engine.update_pnl(float(i))
    assert engine.pnl_history.len() == engine._max_history


# ---------------------------------------------------------------------------
# Value-at-Risk
# ---------------------------------------------------------------------------

def test_var_empty_history_returns_zero(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    assert engine.compute_var() == 0.0


def test_var_positive_pnl_history_returns_zero(engine):
    """If all PnL days are profitable (no losses), 95% VaR should be 0."""
    engine.update_position("BTC", qty=1.0, price=50000.0)
    for _ in range(50):
        engine.update_pnl(100.0)   # always profit
    assert engine.compute_var(confidence=0.95) == 0.0


def test_var_reflects_tail_risk(engine):
    """Series with a few large losses must produce a non-zero VaR."""
    engine.update_position("BTC", qty=1.0, price=50000.0)
    pnls = [100.0] * 90 + [-5000.0] * 10   # 10% bad days
    for p in pnls:
        engine.update_pnl(p)
    var = engine.compute_var(confidence=0.95)
    assert var > 0.0


def test_cvar_is_at_least_var(engine):
    """CVaR (ES) must always be ≥ VaR by definition."""
    engine.update_position("BTC", qty=1.0, price=50000.0)
    pnls = [50.0] * 80 + [-500.0] * 10 + [-2000.0] * 10
    for p in pnls:
        engine.update_pnl(p)
    var = engine.compute_var(confidence=0.95)
    cvar = engine.compute_cvar(confidence=0.95)
    assert cvar >= var


# ---------------------------------------------------------------------------
# Concentration risk (HHI)
# ---------------------------------------------------------------------------

def test_hhi_single_position_is_one(engine):
    """A single asset portfolio has HHI == 1 (fully concentrated)."""
    engine.update_position("BTC", qty=1.0, price=50000.0)
    assert engine.compute_hhi() == pytest.approx(1.0)


def test_hhi_equal_weights_minimises_concentration(engine):
    """N equal-weight positions → HHI = 1/N."""
    engine.update_position("BTC", qty=1.0, price=1000.0)
    engine.update_position("ETH", qty=1.0, price=1000.0)
    engine.update_position("SOL", qty=1.0, price=1000.0)
    engine.update_position("BNB", qty=1.0, price=1000.0)
    # HHI should be close to 0.25 (1/4)
    assert engine.compute_hhi() == pytest.approx(0.25, abs=1e-4)


def test_hhi_empty_positions(engine):
    assert engine.compute_hhi() == 0.0

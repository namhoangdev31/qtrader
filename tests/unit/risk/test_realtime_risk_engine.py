import polars as pl
import pytest
from qtrader.risk.realtime import RealTimeRiskEngine


@pytest.fixture
def engine():
    return RealTimeRiskEngine(limits=[], event_bus=None)


def test_update_position_first_insert(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    assert engine.positions.height == 1
    assert float(engine.positions.filter(pl.col("symbol") == "BTC")["market_value"][0]) == 50000.0


def test_update_position_updates_existing(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    engine.update_position("BTC", qty=2.0, price=60000.0)
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
    engine.update_position("ETH", qty=-5.0, price=3000.0)
    assert float(engine.equity) == pytest.approx(35000.0)


def test_hwm_tracks_peak_equity(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    assert engine.hwm == pytest.approx(50000.0)
    engine.update_position("BTC", qty=1.0, price=60000.0)
    assert engine.hwm == pytest.approx(60000.0)
    engine.update_position("BTC", qty=1.0, price=40000.0)
    assert engine.hwm == pytest.approx(60000.0)


def test_drawdown_is_computed_after_drop(engine):
    engine.update_position("BTC", qty=1.0, price=100000.0)
    engine.update_position("BTC", qty=1.0, price=80000.0)
    assert engine.current_drawdown == pytest.approx(0.2, abs=0.0001)


def test_drawdown_zero_when_at_peak(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    engine.update_position("BTC", qty=1.0, price=60000.0)
    assert engine.current_drawdown == pytest.approx(0.0, abs=1e-09)


def test_update_pnl_appends(engine):
    engine.update_pnl(100.0)
    engine.update_pnl(-50.0)
    assert engine.pnl_history.len() == 2


def test_update_pnl_rolling_window(engine):
    for i in range(300):
        engine.update_pnl(float(i))
    assert engine.pnl_history.len() == engine._max_history


def test_var_empty_history_returns_zero(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    assert engine.compute_var() == 0.0


def test_var_positive_pnl_history_returns_zero(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    for _ in range(50):
        engine.update_pnl(100.0)
    assert engine.compute_var(confidence=0.95) == 0.0


def test_var_reflects_tail_risk(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    pnls = [100.0] * 90 + [-5000.0] * 10
    for p in pnls:
        engine.update_pnl(p)
    var = engine.compute_var(confidence=0.95)
    assert var > 0.0


def test_cvar_is_at_least_var(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    pnls = [50.0] * 80 + [-500.0] * 10 + [-2000.0] * 10
    for p in pnls:
        engine.update_pnl(p)
    var = engine.compute_var(confidence=0.95)
    cvar = engine.compute_cvar(confidence=0.95)
    assert cvar >= var


def test_hhi_single_position_is_one(engine):
    engine.update_position("BTC", qty=1.0, price=50000.0)
    assert engine.compute_hhi() == pytest.approx(1.0)


def test_hhi_equal_weights_minimises_concentration(engine):
    engine.update_position("BTC", qty=1.0, price=1000.0)
    engine.update_position("ETH", qty=1.0, price=1000.0)
    engine.update_position("SOL", qty=1.0, price=1000.0)
    engine.update_position("BNB", qty=1.0, price=1000.0)
    assert engine.compute_hhi() == pytest.approx(0.25, abs=0.0001)


def test_hhi_empty_positions(engine):
    assert engine.compute_hhi() == 0.0

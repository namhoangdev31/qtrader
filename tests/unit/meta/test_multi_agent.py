from datetime import datetime, timedelta

import polars as pl
import pytest

from qtrader.meta.multi_agent import MultiAgentSystem

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

START_TIME = datetime(2025, 1, 1, 10, 0, 0)

AGENT_METRICS = pl.DataFrame(
    {
        "agent_id": ["A1", "A2", "A3"],
        "sharpe": [2.0, 1.0, 0.5],
        "volatility": [0.1, 0.1, 0.2],  # A1 is best, A3 has high vol
    }
)

AGENT_PNLS = pl.DataFrame(
    {
        "timestamp": [
            START_TIME,
            START_TIME,
            START_TIME + timedelta(hours=1),
            START_TIME + timedelta(hours=1),
        ],
        "agent_id": ["A1", "A2", "A1", "A2"],
        "pnl": [10.0, 5.0, 20.0, -2.0],
    }
)

# Configuration for unit tests
TOTAL_CAP = 1_000_000.0


def test_multi_agent_capital_allocation() -> None:
    """Verify that capital is distributed according to risk/return ratios."""
    system = MultiAgentSystem(total_capital=TOTAL_CAP)
    allocation = system.allocate_capital(AGENT_METRICS)

    # Sum of allocations should match total capital
    total_allocated = allocation["allocated_capital"].sum()
    assert total_allocated == pytest.approx(TOTAL_CAP)

    expected_len = 3
    assert len(allocation) == expected_len

    # A1 (Sharpe 2.0, Vol 0.1) should receive significantly more than A3 (Sharpe 0.5, Vol 0.2)
    # Weight_1 = 2.0 / 0.1 = 20
    # Weight_3 = 0.5 / 0.2 = 2.5
    a1_val = allocation.filter(pl.col("agent_id") == "A1")["allocated_capital"][0]
    a3_val = allocation.filter(pl.col("agent_id") == "A3")["allocated_capital"][0]

    # 20 / 2.5 = 8.0 Ratio
    assert a1_val / a3_val == pytest.approx(8.0)


def test_multi_agent_pnl_aggregation() -> None:
    """Verify that individual agent PnLs are correctly summmated over time."""
    system = MultiAgentSystem()
    total_pnl = system.aggregate_portfolio_pnl(AGENT_PNLS)

    # 1. Total count (unique timestamps)
    expected_len = 2
    assert len(total_pnl) == expected_len

    # 2. Sum at t=0 (10 + 5 = 15)
    val_0 = 15.0
    assert total_pnl[0] == pytest.approx(val_0)

    # 3. Sum at t=1 (20 - 2 = 18)
    val_1 = 18.0
    assert total_pnl[1] == pytest.approx(val_1)


def test_multi_agent_empty_robustness() -> None:
    """Ensure behavior with no agent metrics."""
    system = MultiAgentSystem()
    empty = pl.DataFrame()

    res_alloc = system.allocate_capital(empty)
    assert res_alloc.is_empty()

    res_pnl = system.aggregate_portfolio_pnl(empty)
    assert len(res_pnl) == 0

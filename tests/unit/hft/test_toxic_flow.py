from datetime import datetime, timedelta

import polars as pl
import pytest

from qtrader.hft.toxic_flow import ToxicFlowDetector

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

START_TIME = datetime(2025, 1, 1, 10, 0, 0)
TIMES = [START_TIME + timedelta(seconds=i) for i in range(20)]

# 1. Market Data: Gradual price decline (Bearish)
MARKET_DATA = pl.DataFrame(
    {
        "timestamp": TIMES,
        "mid_price": [100.0 - (0.1 * i) for i in range(20)],
    }
)

# 2. Execution Fills:
# - Buy at t=2 (P=99.8), P_future (t=5=2+3) is 99.5. (Adverse)
# - Sell at t=10 (P=99.0), P_future (t=13) is 98.7. (Favorable)
FILLS = pl.DataFrame(
    {
        "timestamp": [TIMES[2], TIMES[10]],
        "price": [99.8, 99.0],
        "side": [1, -1],  # 1=Buy, -1=Sell
    }
)

# Configuration for unit tests
LOOKAHEAD = 3  # (Small lookahead for test verification)


def test_toxic_flow_adverse_selection_detection() -> None:
    """Verify that toxic (adverse) and favorable fills are correctly flagged."""
    processor = ToxicFlowDetector()
    enriched = processor.compute_toxicity(FILLS, MARKET_DATA, lookahead_steps=LOOKAHEAD)

    # First row: Buy at 99.8, Future is 99.5.
    # Toxicity = -1 * (99.5 - 99.8) / 99.8 ≈ 0.3 / 99.8 ≈ 0.003006
    val_buy = 0.003006
    assert enriched["toxicity_score"][0] == pytest.approx(val_buy, rel=1e-3)
    assert enriched["toxicity_score"][0] > 0.0  # Positive toxicity = adverse selection

    # Second row: Sell at 99.0, Future is 98.7.
    # Toxicity = -(-1) * (98.7 - 99.0) / 99.0 = -0.3 / 99.0 ≈ -0.0030303
    val_sell = -0.0030303
    assert enriched["toxicity_score"][1] == pytest.approx(val_sell, rel=1e-3)
    assert enriched["toxicity_score"][1] < 0.0  # Favorable = micro-profit/edge


def test_toxic_flow_temporal_alignment() -> None:
    """Verify that join_asof correctly aligns fills with future market state."""
    processor = ToxicFlowDetector()
    enriched = processor.compute_toxicity(FILLS, MARKET_DATA, lookahead_steps=LOOKAHEAD)

    # Check future_price alignment (lookahead=3)
    # t=2 -> future is t=5 (99.5)
    expect_fut_0 = 99.5
    assert enriched["future_price"][0] == pytest.approx(expect_fut_0)
    # t=10 -> future is t=13 (98.7)
    expect_fut_1 = 98.7
    assert enriched["future_price"][1] == pytest.approx(expect_fut_1)


def test_toxic_flow_empty_robustness() -> None:
    """Ensure edge cases (empty data) are handled without crashing."""
    processor = ToxicFlowDetector()
    empty = pl.DataFrame()

    # Empty fills: returns empty
    res = processor.compute_toxicity(empty, MARKET_DATA)
    assert res.is_empty()

    # Empty market: returns original fills
    res2 = processor.compute_toxicity(FILLS, empty)
    assert res2.height == FILLS.height

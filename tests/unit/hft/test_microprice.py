import polars as pl
import pytest

from qtrader.hft.microprice import MicropriceCalculator

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

OB_DATA = pl.DataFrame(
    {
        "bid_price_0": [100.0, 100.0, 100.0],
        "ask_price_0": [101.0, 101.0, 101.0],
        "bid_vol_0": [10.0, 90.0, 10.0],
        "ask_vol_0": [90.0, 10.0, 10.0],
    }
)

# 1. Row 0: BidVol 10, AskVol 90.
#    Mid-price = 100.5
#    Micro-price = (101*10 + 100*90) / 100 = (1010 + 9000) / 100 = 100.1
#    (Sentiment: Strong sell pressure, micro-price tilts towards bid)

# 2. Row 1: BidVol 90, AskVol 10.
#    Micro-price = (101*90 + 100*10) / 100 = (9090 + 1000) / 100 = 100.9
#    (Sentiment: Strong buy pressure, micro-price tilts towards ask)

# 3. Row 2: BidVol 10, AskVol 10.
#    Micro-price = (101*10 + 100*10) / 20 = (1010 + 1000) / 20 = 100.5
#    (Sentiment: Neutral, micro-price = mid-price)


def test_microprice_compute_logic() -> None:
    """Verify micro-price calculation with different imbalance levels."""
    processor = MicropriceCalculator()
    micro_prices = processor.compute(OB_DATA)
    mid_prices = processor.compute_mid_price(OB_DATA)

    expected_len = 3
    assert len(micro_prices) == expected_len

    # Assert values match manual calculation
    val_0 = 100.1
    val_1 = 100.9
    val_2 = 100.5
    assert micro_prices[0] == pytest.approx(val_0)
    assert micro_prices[1] == pytest.approx(val_1)
    assert micro_prices[2] == pytest.approx(val_2)

    # Assert mid-price for reference
    expected_mid = 100.5
    assert mid_prices[0] == pytest.approx(expected_mid)


def test_microprice_empty_robustness() -> None:
    """Verify stability with empty input and zero volumes."""
    processor = MicropriceCalculator()
    empty = pl.DataFrame()
    res = processor.compute(empty)
    assert len(res) == 0

    zero_vol = pl.DataFrame(
        {
            "bid_price_0": [100.0],
            "ask_price_0": [105.0],
            "bid_vol_0": [0.0],
            "ask_vol_0": [0.0],
        }
    )
    # Should not crash (epsilon protection)
    # With zero vols, P_micro = 0/0 -> handled by epsilon
    res_zero = processor.compute(zero_vol)
    # (105*0 + 100*0) / (0 + 0 + eps) = 0.0
    val_0 = 0.0
    assert res_zero[0] == pytest.approx(val_0)

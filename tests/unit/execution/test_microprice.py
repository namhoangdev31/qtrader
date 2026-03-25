import polars as pl

from qtrader.execution.microprice import MicroPriceCalculator
from qtrader.execution.sor_microprice import MicroPriceSOR

# Constants to avoid PLR2004 (Magic Numbers)
BID_PRICE = 100.0
ASK_PRICE = 101.0
MID_PRICE = 100.5
SMALL_SIZE = 10.0
LARGE_SIZE = 30.0
HUGE_SIZE = 90.0
EXTREME_SIZE = 1000.0
THRESHOLD = 0.6
IMBALANCE_BALANCED = 0.0
IMBALANCE_UPWARD = 0.5
IMBALANCE_DOWNWARD = -0.5
IMBALANCE_STRONG_UP = 0.8
IMBALANCE_STRONG_DOWN = -0.8
PRICE_UPWARD = 100.75
PRICE_DOWNWARD = 100.25


def test_microprice_calculation() -> None:
    """Verify micro-price and imbalance math."""
    calc = MicroPriceCalculator()

    # Case 1: Balanced book
    state = calc.calculate(
        bid_price=BID_PRICE, ask_price=ASK_PRICE, bid_size=SMALL_SIZE, ask_size=SMALL_SIZE
    )
    assert state.mid_price == MID_PRICE
    assert state.micro_price == MID_PRICE
    assert state.imbalance == IMBALANCE_BALANCED

    # Case 2: Upward pressure (bid size > ask size)
    state = calc.calculate(
        bid_price=BID_PRICE, ask_price=ASK_PRICE, bid_size=LARGE_SIZE, ask_size=SMALL_SIZE
    )
    assert state.mid_price == MID_PRICE
    assert state.micro_price == PRICE_UPWARD
    assert state.imbalance == IMBALANCE_UPWARD

    # Case 3: Downward pressure (ask size > bid size)
    state = calc.calculate(
        bid_price=BID_PRICE, ask_price=ASK_PRICE, bid_size=SMALL_SIZE, ask_size=LARGE_SIZE
    )
    assert state.mid_price == MID_PRICE
    assert state.micro_price == PRICE_DOWNWARD
    assert state.imbalance == IMBALANCE_DOWNWARD


def test_calculate_batch() -> None:
    """Verify vectorized micro-price calculations."""
    calc = MicroPriceCalculator()
    df = pl.DataFrame(
        {
            "bid_price": [BID_PRICE, BID_PRICE],
            "ask_price": [ASK_PRICE, ASK_PRICE],
            "bid_size": [SMALL_SIZE, LARGE_SIZE],
            "ask_size": [SMALL_SIZE, SMALL_SIZE],
        }
    )

    result = calc.calculate_batch(df)
    assert result["mid_price"][0] == MID_PRICE
    assert result["micro_price"][0] == MID_PRICE
    assert result["imbalance"][0] == IMBALANCE_BALANCED

    assert result["micro_price"][1] == PRICE_UPWARD
    assert result["imbalance"][1] == IMBALANCE_UPWARD


def test_sor_decisions() -> None:
    """Verify SOR decisions based on pressure."""
    sor = MicroPriceSOR(pressure_threshold=THRESHOLD)

    # BUY - Strong Upward Pressure
    result = sor.get_decision("BUY", BID_PRICE, ASK_PRICE, HUGE_SIZE, SMALL_SIZE)
    assert result["execution_decision"] == "market"
    assert result["target_price"] == ASK_PRICE
    assert result["imbalance"] == IMBALANCE_STRONG_UP

    # BUY - Low Upward Pressure
    result = sor.get_decision("BUY", BID_PRICE, ASK_PRICE, 60.0, 40.0)  # 60/40 is 0.2
    assert result["execution_decision"] == "limit"
    assert result["target_price"] == BID_PRICE

    # SELL - Strong Downward Pressure
    result = sor.get_decision("SELL", BID_PRICE, ASK_PRICE, SMALL_SIZE, HUGE_SIZE)
    assert result["execution_decision"] == "market"
    assert result["target_price"] == BID_PRICE

    # SELL - Low Downward Pressure
    result = sor.get_decision("SELL", BID_PRICE, ASK_PRICE, 40.0, 60.0)
    assert result["execution_decision"] == "limit"
    assert result["target_price"] == ASK_PRICE


def test_get_decision_batch() -> None:
    """Verify vectorized SOR decisions."""
    sor = MicroPriceSOR(pressure_threshold=THRESHOLD)
    df = pl.DataFrame(
        {
            "bid_price": [BID_PRICE, BID_PRICE],
            "ask_price": [ASK_PRICE, ASK_PRICE],
            "bid_size": [SMALL_SIZE, HUGE_SIZE],
            "ask_size": [HUGE_SIZE, SMALL_SIZE],
        }
    )

    # Test BUY batch
    buy_results = sor.get_decision_batch("BUY", df)
    assert buy_results["execution_decision"][0] == "limit"
    assert buy_results["execution_decision"][1] == "market"
    assert buy_results["target_price"][1] == ASK_PRICE

    # Test SELL batch
    sell_results = sor.get_decision_batch("SELL", df)
    assert sell_results["execution_decision"][0] == "market"
    assert sell_results["execution_decision"][1] == "limit"
    assert sell_results["target_price"][0] == BID_PRICE


def test_noisy_book_stability() -> None:
    """Ensure SOR is stable under noisy or zero data."""
    sor = MicroPriceSOR()

    # Zero size case
    result = sor.get_decision("BUY", BID_PRICE, ASK_PRICE, 0.0, 0.0)
    assert result["execution_decision"] == "limit"
    assert result["target_price"] == BID_PRICE
    assert result["imbalance"] == IMBALANCE_BALANCED

    # Extreme imbalance
    result = sor.get_decision("BUY", BID_PRICE, ASK_PRICE, EXTREME_SIZE, 0.0)
    assert result["execution_decision"] == "market"
    assert result["imbalance"] == 1.0

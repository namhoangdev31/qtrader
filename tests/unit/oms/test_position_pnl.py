from unittest.mock import MagicMock
import pytest


class Position:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.qty = 0.0
        self.avg_entry_price = 0.0
        self.realized_pnl = 0.0

    def add_fill(self, side: str, qty: float, price: float):
        signed_qty = qty if side == "BUY" else -qty
        old_qty = self.qty
        new_qty = old_qty + signed_qty
        if old_qty * new_qty < 0:
            close_qty = abs(old_qty)
            pnl = close_qty * (price - self.avg_entry_price) * (1 if old_qty > 0 else -1)
            self.realized_pnl += pnl
            remaining = abs(new_qty)
            self.qty = remaining * (1 if new_qty > 0 else -1)
            self.avg_entry_price = price
        elif old_qty == 0.0:
            self.qty = signed_qty
            self.avg_entry_price = price
        elif (old_qty > 0) == (signed_qty > 0):
            total_cost = abs(old_qty) * self.avg_entry_price + abs(signed_qty) * price
            self.avg_entry_price = total_cost / abs(new_qty)
            self.qty = new_qty
        else:
            close_qty = min(abs(signed_qty), abs(old_qty))
            pnl = close_qty * (price - self.avg_entry_price) * (1 if old_qty > 0 else -1)
            self.realized_pnl += pnl
            self.qty = new_qty

    def unrealized_pnl(self, current_price: float) -> float:
        return self.qty * (current_price - self.avg_entry_price)


def test_position_initial_state():
    pos = Position("BTC")
    assert pos.qty == 0.0
    assert pos.avg_entry_price == 0.0
    assert pos.realized_pnl == 0.0


def test_position_buy_fill():
    pos = Position("BTC")
    pos.add_fill("BUY", 1.0, 50000.0)
    assert pos.qty == 1.0
    assert pos.avg_entry_price == 50000.0


def test_position_avg_entry_price_two_buys():
    pos = Position("BTC")
    pos.add_fill("BUY", 1.0, 40000.0)
    pos.add_fill("BUY", 1.0, 60000.0)
    assert pos.qty == 2.0
    assert pos.avg_entry_price == pytest.approx(50000.0)


def test_position_partial_close_realized_pnl():
    pos = Position("BTC")
    pos.add_fill("BUY", 2.0, 40000.0)
    pos.add_fill("SELL", 1.0, 50000.0)
    assert pos.qty == pytest.approx(1.0)
    assert pos.realized_pnl == pytest.approx(10000.0)
    assert pos.avg_entry_price == pytest.approx(40000.0)


def test_position_full_close_zeroes_qty():
    pos = Position("BTC")
    pos.add_fill("BUY", 3.0, 50000.0)
    pos.add_fill("SELL", 3.0, 55000.0)
    assert pos.qty == pytest.approx(0.0)
    assert pos.realized_pnl == pytest.approx(15000.0)


def test_position_flip_long_to_short():
    pos = Position("BTC")
    pos.add_fill("BUY", 2.0, 50000.0)
    pos.add_fill("SELL", 5.0, 60000.0)
    assert pos.qty == pytest.approx(-3.0)
    assert pos.realized_pnl == pytest.approx(20000.0)
    assert pos.avg_entry_price == pytest.approx(60000.0)


def test_unrealized_pnl_long():
    pos = Position("ETH")
    pos.add_fill("BUY", 10.0, 2000.0)
    assert pos.unrealized_pnl(2500.0) == pytest.approx(5000.0)


def test_unrealized_pnl_short():
    pos = Position("ETH")
    pos.add_fill("SELL", 10.0, 2000.0)
    assert pos.unrealized_pnl(1800.0) == pytest.approx(2000.0)


def test_unrealized_pnl_short_loss():
    pos = Position("ETH")
    pos.add_fill("SELL", 10.0, 2000.0)
    assert pos.unrealized_pnl(2200.0) == pytest.approx(-2000.0)


def test_multi_symbol_positions_are_isolated():
    btc = Position("BTC")
    eth = Position("ETH")
    btc.add_fill("BUY", 1.0, 50000.0)
    eth.add_fill("SELL", 10.0, 2000.0)
    assert btc.qty == 1.0
    assert eth.qty == -10.0
    assert btc.realized_pnl == 0.0


def test_partial_fill_sequence():
    pos_partial = Position("BTC")
    pos_partial.add_fill("BUY", 1.0, 50000.0)
    pos_partial.add_fill("BUY", 2.0, 51000.0)
    pos_partial.add_fill("BUY", 2.0, 52000.0)
    vwap = (1 * 50000 + 2 * 51000 + 2 * 52000) / 5
    assert pos_partial.qty == pytest.approx(5.0)
    assert pos_partial.avg_entry_price == pytest.approx(vwap, abs=0.0001)


class Account:
    def __init__(self, cash: float) -> None:
        self.cash = cash
        self.positions: dict[str, Position] = {}

    def equity(self, prices: dict[str, float]) -> float:
        val = 0.0
        for sym, pos in self.positions.items():
            p = prices.get(sym, pos.avg_entry_price)
            if pos.qty >= 0:
                val += pos.qty * p
            else:
                val += pos.qty * (p - pos.avg_entry_price)
        return self.cash + val


def test_account_equity_no_positions():
    acct = Account(cash=100000.0)
    assert acct.equity({}) == pytest.approx(100000.0)


def test_account_equity_with_long_position():
    acct = Account(cash=50000.0)
    btc = Position("BTC")
    btc.add_fill("BUY", 1.0, 50000.0)
    acct.positions["BTC"] = btc
    assert acct.equity({"BTC": 55000.0}) == pytest.approx(105000.0)


def test_account_equity_with_short_reduces_on_price_rise():
    acct = Account(cash=100000.0)
    eth = Position("ETH")
    eth.add_fill("SELL", 10.0, 3000.0)
    acct.positions["ETH"] = eth
    assert acct.equity({"ETH": 4000.0}) == pytest.approx(90000.0)


def test_account_equity_drawdown_from_peak():
    acct = Account(cash=0.0)
    btc = Position("BTC")
    btc.add_fill("BUY", 1.0, 50000.0)
    acct.positions["BTC"] = btc
    prices = [50000, 55000, 60000, 45000, 40000, 50000]
    peak = 0.0
    for p in prices:
        eq = acct.equity({"BTC": p})
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak > 0 else 0.0
        assert dd >= 0.0, f"Negative drawdown at price {p}"

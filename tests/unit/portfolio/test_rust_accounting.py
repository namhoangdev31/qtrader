import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from qtrader_core import LedgerEngine, LedgerEntry, Transaction, PortfolioEngine
from qtrader.oms.oms_adapter import Account, Position

def test_rust_ledger_double_entry():
    """Verify that ledger rejects unbalanced transactions."""
    engine = LedgerEngine()
    
    # Balance: Σ = 0 (Balanced)
    e1 = LedgerEntry(tx_id="tx_01", asset="USD", amount=-100.0, entry_type="TRADE")
    e2 = LedgerEntry(tx_id="tx_01", asset="SETTLEMENT", amount=100.0, entry_type="CONTRA")
    
    tx_ok = Transaction(entries=[e1, e2])
    assert tx_ok.validate() is True
    assert engine.record_transaction(tx_ok) is True
    assert engine.get_balance("USD") == -100.0
    
    # Unbalanced: Σ != 0
    e3 = LedgerEntry(tx_id="tx_02", asset="USD", amount=-50.0, entry_type="TRADE")
    tx_bad = Transaction(entries=[e3])
    assert tx_bad.validate() is False
    
    with pytest.raises(ValueError, match="Transaction is unbalanced"):
        engine.record_transaction(tx_bad)

def test_rust_withdrawal_gate():
    """Verify that withdrawal gating works for open positions."""
    engine = PortfolioEngine()
    
    # Account with positions
    acc_with_pos = MagicMock(spec=Account)
    acc_with_pos.positions = {"BTC": MagicMock(qty=1.0)}
    
    assert engine.is_withdrawal_eligible(acc_with_pos) is False
    
    # Empty account
    acc_empty = MagicMock(spec=Account)
    acc_empty.positions = {}
    assert engine.is_withdrawal_eligible(acc_empty) is True

def test_nav_report_detailed_fees():
    """Verify that NAVReport includes detailed fee breakdown."""
    engine = PortfolioEngine()
    acc = MagicMock(spec=Account)
    acc.cash = 1000.0
    acc.positions = {}
    
    report = engine.compute_nav(
        account=acc,
        mark_prices={},
        total_fees=10.0,
        maker_fees=2.0,
        taker_fees=8.0,
        funding_fees=0.0
    )
    
    assert report.total_fees == 10.0
    assert report.maker_fees == 2.0
    assert report.taker_fees == 8.0
    assert "M:2.00/T:8.00/F:0.00" in str(report)

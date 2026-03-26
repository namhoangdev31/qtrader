import uuid
from decimal import Decimal
import pytest
from qtrader.core.events import FillEvent, FillPayload, FeeEvent, FundingEvent
from qtrader.portfolio.fee_engine import FeeEngine
from qtrader.portfolio.funding_engine import FundingEngine


def test_fee_calculation_and_ledger_generation():
    """Verify that trading fees are calculated correctly and result in balanced ledger entries."""
    engine = FeeEngine()
    
    # 1. Mock Fill: Buy 1.5 BTC @ 30,000.0
    fill = FillEvent(
        trace_id=uuid.uuid4(),
        source="Exchange",
        payload=FillPayload(
            order_id="ORD_001",
            symbol="BTC/USDT",
            side="BUY",
            quantity=1.5,
            price=30000.0,
            commission=0.0
        )
    )
    
    # 2. Charge 10 bps (0.1%)
    fee_rate = Decimal('0.001')
    fee_evt = engine.calculate(fill, fee_rate, fee_type="TAKER")
    
    # Actual Calculation: 1.5 * 30000.0 * 0.001 = 45.0
    assert fee_evt.payload.fee_amount == 45.0
    assert fee_evt.payload.fee_type == "TAKER"
    
    # 3. Create Ledger Transaction
    account_id = "TRADING_ACC_01"
    tx = engine.create_ledger_transaction(fee_evt, account_id)
    
    # Assert Sum(Debit) == Sum(Credit)
    assert tx.validate_balance()
    
    # Verify User Account is Credited (Cash Decreases)
    user_entry = [e for e in tx.entries if e.account_id == account_id][0]
    assert user_entry.credit == 45.0
    assert user_entry.debit == 0.0
    
    # Verify System Account is Debited (Revenue Increases)
    sys_entry = [e for e in tx.entries if e.account_id == "SYSTEM_FEE_ACCOUNT"][0]
    assert sys_entry.debit == 45.0
    assert sys_entry.credit == 0.0


def test_funding_parity_and_ledger_entries():
    """Verify that funding payments handle long/short parity correctly and result in balanced ledger entries."""
    engine = FundingEngine()
    account_id = "MARGIN_ACC_01"
    sym = "BTC/PERP"
    price = Decimal('50000.0')
    rate = Decimal('0.0001')  # 1bp
    
    # --- Scenario 1: Long Position Pays Funding ---
    long_qty = Decimal('0.5')
    # 0.5 * 50000.0 * 0.0001 = 2.5 (Positive = Paying)
    evt_pay = engine.calculate(sym, long_qty, price, rate)
    assert evt_pay.payload.funding_amount == 2.5
    
    tx_pay = engine.create_ledger_transaction(evt_pay, account_id)
    assert tx_pay.validate_balance()
    # Credit cash for payment
    pay_entry = [e for e in tx_pay.entries if e.account_id == account_id][0]
    assert pay_entry.credit == 2.5
    
    # --- Scenario 2: Short Position Receives Funding ---
    short_qty = Decimal('-0.5')
    # -0.5 * 50000.0 * 0.0001 = -2.5 (Negative = Receiving)
    evt_recv = engine.calculate(sym, short_qty, price, rate)
    assert evt_recv.payload.funding_amount == -2.5
    
    tx_recv = engine.create_ledger_transaction(evt_recv, account_id)
    assert tx_recv.validate_balance()
    # Debit cash for receipt
    recv_entry = [e for e in tx_recv.entries if e.account_id == account_id][0]
    assert recv_entry.debit == 2.5
    assert recv_entry.credit == 0.0


def test_zero_position_funding_safety():
    """Ensure that flat positions result in zero funding cost."""
    engine = FundingEngine()
    evt = engine.calculate("SOL/PERP", Decimal('0'), Decimal('150.0'), Decimal('0.0001'))
    assert evt.payload.funding_amount == 0.0
    
    tx = engine.create_ledger_transaction(evt, "ANY_ACC")
    assert tx.validate_balance()
    # Sum of entries should be zero
    assert sum(e.debit for e in tx.entries) == 0.0

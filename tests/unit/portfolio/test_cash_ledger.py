import asyncio
import os
import shutil
import uuid
from decimal import Decimal

import pytest

from qtrader.core.event_store import FileEventStore
from qtrader.core.events import LedgerEntryPayload
from qtrader.portfolio.cash_ledger import CashLedger, LedgerError
from qtrader.portfolio.ledger_entry_model import TransactionRecord


@pytest.fixture
def event_store():
    """Create a temporary event store for replaying ledger entries."""
    test_path = "tmp/test_ledger_store"
    if os.path.exists(test_path):
        shutil.rmtree(test_path)
    
    os.makedirs(test_path)
    store = FileEventStore(base_path=test_path)
    yield store
    
    # Cleanup after test
    if os.path.exists(test_path):
        shutil.rmtree(test_path)


@pytest.mark.asyncio
async def test_double_entry_validation_integrity(event_store):
    """Verify that unbalanced transactions are strictly rejected."""
    ledger = CashLedger(event_store)
    trace_id = uuid.uuid4()
    
    # 1. Unbalanced Transaction (Imbalance of 50)
    entries = [
        LedgerEntryPayload(account_id="ACC_1", debit=100.0, credit=0.0),
        LedgerEntryPayload(account_id="ACC_2", debit=0.0, credit=50.0)
    ]
    tx_unbalanced = TransactionRecord(trace_id=trace_id, entries=entries)
    
    with pytest.raises(LedgerError) as exc:
        await ledger.record_transaction(tx_unbalanced)
    
    assert "Zero Imbalance Tolerance Violated" in str(exc.value)
    
    # Verify balance remains zero
    assert await ledger.get_balance("ACC_1") == Decimal('0')


@pytest.mark.asyncio
async def test_transaction_recording_and_balance_derivation(event_store):
    """Verify that multiple balanced transactions results in accurate derived balance."""
    ledger = CashLedger(event_store)
    user_acc = "USER_123"
    system_acc = "SYSTEM_RESERVE"
    
    # T1: Deposit 1000.0
    t1_id = uuid.uuid4()
    await ledger.record_transaction(TransactionRecord(
        trace_id=t1_id,
        entries=[
            LedgerEntryPayload(account_id=user_acc, debit=1000.0, credit=0.0, description="Deposit"), 
            LedgerEntryPayload(account_id=system_acc, debit=0.0, credit=1000.0, description="Liability")
        ]
    ))
    
    # T2: Pay Fee 25.50
    t2_id = uuid.uuid4()
    await ledger.record_transaction(TransactionRecord(
        trace_id=t2_id,
        entries=[
            LedgerEntryPayload(account_id=user_acc, debit=0.0, credit=25.50, description="Fee"),
            LedgerEntryPayload(account_id="REVENUE_ACC", debit=25.50, credit=0.0, description="Income")
        ]
    ))
    
    # T3: Internal Transfer 100.0
    t3_id = uuid.uuid4()
    await ledger.record_transaction(TransactionRecord(
        trace_id=t3_id,
        entries=[
            LedgerEntryPayload(account_id=user_acc, debit=0.0, credit=100.0),
            LedgerEntryPayload(account_id="SAVINGS_ACC", debit=100.0, credit=0.0)
        ]
    ))
    
    # Derived Balance = 1000.0 - 25.50 - 100.0 = 874.50
    final_balance = await ledger.get_balance(user_acc)
    assert final_balance == Decimal('874.50')


@pytest.mark.asyncio
async def test_ledger_benchmarking(event_store):
    """Benchmark balance reconstruction speed for 200 entries."""
    import time
    ledger = CashLedger(event_store)
    acc = "BENCH_ACC"
    num_tx = 100  # 2 entries per tx = 200 entries
    
    for _i in range(num_tx):
        await ledger.record_transaction(TransactionRecord(
            trace_id=uuid.uuid4(),
            entries=[
                LedgerEntryPayload(account_id=acc, debit=10.0, credit=0.0),
                LedgerEntryPayload(account_id="OFFSET", debit=0.0, credit=10.0)
            ]
        ))
        
    t0 = time.perf_counter()
    balance = await ledger.get_balance(acc)
    dt = (time.perf_counter() - t0) * 1000
    
    print(f"\nLedger Reconstruction Latency (200 entries): {dt:.4f}ms")
    assert balance == Decimal(str(num_tx * 10))
    assert dt < 50.0  # Reasonable baseline for unoptimized log scan

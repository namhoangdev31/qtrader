from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from qtrader.core.events import LedgerEntryEvent, LedgerEntryPayload, EventType
from qtrader.core.event_store import BaseEventStore
from qtrader.portfolio.ledger_entry_model import TransactionRecord

logger = logging.getLogger(__name__)


class CashLedger:
    """
    Institutional Double-Entry Cash Ledger Engine.
    
    This system implements the core accounting logic:
    1.  **Immutability**: Every transaction is an immutable entry in the EventStore.
    2.  **Double-Entry**: Every transaction must have Σ Debit = Σ Credit.
    3.  **Traceability**: All balances are derived from the append-only history.
    
    Balance(t) = Σ (Debit - Credit)
    """

    def __init__(self, event_store: BaseEventStore) -> None:
        """
        Initialize the CashLedger.
        
        Args:
            event_store: The authoritative persistent source for ledger entries.
        """
        self._event_store = event_store

    async def record_transaction(self, transaction: TransactionRecord) -> bool:
        """
        Validate and persist a balanced double-entry transaction.
        
        A single TransactionRecord (like a trade or a fee payment) results in 
        multiple (at least two) LedgerEntryEvents written to the store.
        
        Returns:
            bool: True if recording was successful.
            
        Raises:
            LedgerError: If the transaction is unbalanced or persistence fails.
        """
        # 1. Verification of the Accounting Equation (Σ Debit - Σ Credit = 0)
        if not transaction.validate_balance():
            logger.critical(f"LEDGER_CRITICAL | Transaction {transaction.trace_id} is unbalanced. Recommending system halt.")
            raise LedgerError(f"Zero Imbalance Tolerance Violated for {transaction.trace_id}")

        # 2. Decompose Transaction into Individual Entries
        # Entries are routed to partitions based on the account_id
        for entry in transaction.entries:
            ledger_event = LedgerEntryEvent(
                trace_id=transaction.trace_id,
                source="CashLedger",
                payload=entry,
                partition_key=f"ledger_{entry.account_id}"
            )
            
            # Atomically append to the partition log
            await self._event_store.append(ledger_event)
            
        logger.debug(f"LEDGER_RECORDED | Trace: {transaction.trace_id} | Entries: {len(transaction.entries)}")
        return True

    async def get_balance(self, account_id: str) -> Decimal:
        """
        Reconstruct the balance for an account from the ledger history.
        
        This method replays all historical entries for the specific account
        partition and aggregates them using high-precision Decimal arithmetic.
        
        Returns:
            Decimal: The current derived balance.
        """
        partition = f"ledger_{account_id}"
        
        # Load all historical events for this specific account partition
        events = await self._event_store.get_events(partition=partition)
        
        balance = Decimal('0')
        for event in events:
            if isinstance(event, LedgerEntryEvent):
                # Ensure we use string-based initialization of Decimal to avoid float precision artifacts
                payload = event.payload
                balance += Decimal(str(payload.debit)) - Decimal(str(payload.credit))
        
        return balance


class LedgerError(Exception):
    """Raised when the ledger encounters an accounting violation or storage failure."""
    pass

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

from qtrader.core.events import FeeEvent, FeePayload, FillEvent, LedgerEntryPayload
from qtrader.portfolio.ledger_entry_model import TransactionRecord

logger = logging.getLogger(__name__)


class FeeEngine:
    """
    Quantitative Fee Calculation Engine.
    
    Responsible for computing trading costs (Maker/Taker fees) and 
    generating balanced double-entry records for the institutional ledger.
    """

    def calculate(self, fill: FillEvent, fee_rate: Decimal, fee_type: str = "TAKER") -> FeeEvent:
        """
        Compute the fee for a given order fill.
        
        Formula: Fee = |Quantity| * Price * FeeRate
        
        Args:
            fill: The authoritative FillEvent from the execution engine.
            fee_rate: The applicable fee rate (e.g., Decimal('0.001') for 10bps).
            fee_type: Classification (MAKER or TAKER) for reporting.
            
        Returns:
            FeeEvent: A standardized event containing the calculated cost.
        """
        qty = Decimal(str(fill.payload.quantity))
        price = Decimal(str(fill.payload.price))
        
        # Absolute quantity ensures accurate cost regardless of side (BUY/SELL)
        fee_amount = abs(qty) * price * fee_rate
        
        logger.debug(f"FEE_CALCULATED | Order: {fill.payload.order_id} | Amount: {fee_amount:.4f} {fee_type}")

        return FeeEvent(
            trace_id=fill.trace_id,
            source="FeeEngine",
            payload=FeePayload(
                order_id=fill.payload.order_id,
                symbol=fill.payload.symbol,
                fee_amount=float(fee_amount),
                currency="USD",
                fee_type=fee_type
            )
        )

    def create_ledger_transaction(self, fee_event: FeeEvent, account_id: str) -> TransactionRecord:
        """
        Generate a balanced TransactionRecord for the double-entry CashLedger.
        
        Accounting Logic:
        - Credit User Cash (Asset Decreases)
        - Debit System Revenue (Revenue/Asset Increases)
        
        Args:
            fee_event: The calculated fee event.
            account_id: The specific sub-account to charge.
            
        Returns:
            TransactionRecord: Balanced set of entries for the ledger.
        """
        amount = Decimal(str(fee_event.payload.fee_amount))
        
        entries = [
            # 1. Decrease User Balance
            LedgerEntryPayload(
                account_id=account_id,
                debit=0.0,
                credit=float(amount),
                description=f"Trading Fee | {fee_event.payload.symbol} | {fee_event.payload.fee_type}"
            ),
            # 2. Increase System Revenue/Collection Account
            LedgerEntryPayload(
                account_id="SYSTEM_FEE_ACCOUNT",
                debit=float(amount),
                credit=0.0,
                description=f"Fee Revenue | {fee_event.payload.symbol} | Order: {fee_event.payload.order_id}"
            )
        ]
        
        return TransactionRecord(
            trace_id=fee_event.trace_id,
            entries=entries,
            description=f"Auto-generated fee entry for trade {fee_event.payload.order_id}"
        )

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from qtrader.core.events import FundingEvent, FundingPayload, LedgerEntryPayload
from qtrader.portfolio.ledger_entry_model import TransactionRecord

logger = logging.getLogger(__name__)


class FundingEngine:
    """
    Quantitative Funding Fee Engine.
    
    Handles the periodic exchange of funding payments between long and short 
    positions in perpetual futures markets.
    """

    def calculate(
        self, 
        symbol: str, 
        quantity: Decimal, 
        mark_price: Decimal, 
        funding_rate: Decimal, 
        trace_id: Optional[UUID] = None
    ) -> FundingEvent:
        """
        Compute the funding payment for a given position.
        
        Formula: FundingAmount = Quantity * MarkPrice * FundingRate
        - Positive Amount: The user is PAYING funding.
        - Negative Amount: The user is RECEIVING funding.
        
        Args:
            symbol: Trading instrument identifier.
            quantity: Current net position quantity (positive=long, negative=short).
            mark_price: Authoritative valuation price for the asset.
            funding_rate: Current periodic funding rate (e.g., Decimal('0.0001') for 1bp).
            trace_id: Optional correlation ID for the event.
            
        Returns:
            FundingEvent: Standardized event containing the calculated payment.
        """
        # Mathematical model: Payment = Position × Price × Rate
        funding_amount = quantity * mark_price * funding_rate
        
        logger.debug(f"FUNDING_CALCULATED | {symbol} | Amount: {funding_amount:.4f} | Rate: {funding_rate}")

        return FundingEvent(
            trace_id=trace_id or uuid4(),
            source="FundingEngine",
            payload=FundingPayload(
                symbol=symbol,
                position_size=float(quantity),
                funding_rate=float(funding_rate),
                funding_amount=float(funding_amount),
                mark_price=float(mark_price)
            )
        )

    def create_ledger_transaction(self, funding_event: FundingEvent, account_id: str) -> TransactionRecord:
        """
        Generate a balanced TransactionRecord for the double-entry CashLedger.
        
        Accounting Logic:
        - If Amount > 0 (Paying): Credit User Cash (Asset Decreases), Debit Pool.
        - If Amount < 0 (Receiving): Debit User Cash (Asset Increases), Credit Pool.
        
        Args:
            funding_event: The calculated funding event.
            account_id: The specific sub-account to adjust.
            
        Returns:
            TransactionRecord: Balanced set of entries for the ledger.
        """
        amount = Decimal(str(funding_event.payload.funding_amount))
        
        if amount >= 0:
            # User is PAYING funding
            entries = [
                # 1. Decrease User Cash
                LedgerEntryPayload(
                    account_id=account_id,
                    debit=0.0,
                    credit=float(amount),
                    description=f"Funding Payment Paid | {funding_event.payload.symbol}"
                ),
                # 2. Increase System/Peer Pool
                LedgerEntryPayload(
                    account_id="SYSTEM_FUNDING_POOL",
                    debit=float(amount),
                    credit=0.0,
                    description=f"Funding Collected | {funding_event.payload.symbol}"
                )
            ]
        else:
            # User is RECEIVING funding
            abs_amount = abs(amount)
            entries = [
                # 1. Increase User Cash
                LedgerEntryPayload(
                    account_id=account_id,
                    debit=float(abs_amount),
                    credit=0.0,
                    description=f"Funding Payment Received | {funding_event.payload.symbol}"
                ),
                # 2. Decrease System/Peer Pool
                LedgerEntryPayload(
                    account_id="SYSTEM_FUNDING_POOL",
                    debit=0.0,
                    credit=float(abs_amount),
                    description=f"Funding Disbursed | {funding_event.payload.symbol}"
                )
            ]
            
        return TransactionRecord(
            trace_id=funding_event.trace_id,
            entries=entries,
            description=f"Funding Transaction for {funding_event.payload.symbol}"
        )

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from uuid import UUID

    from qtrader.core.events import LedgerEntryPayload

logger = logging.getLogger(__name__)


class TransactionRecord(BaseModel):
    """
    A logical grouping of double-entry ledger records representing a single financial transaction.
    Ensures the fundamental accounting equation: Σ Debit - Σ Credit = 0
    
    Every trade, fee, or funding movement is encapsulated as a TransactionRecord 
    before being atomized into individual LedgerEntryEvents.
    """
    model_config = ConfigDict(frozen=True)

    trace_id: UUID = Field(description="Correlation ID for the entire transaction")
    entries: list[LedgerEntryPayload] = Field(description="The balanced set of debit/credit entries")
    description: str = Field(default="", description="High-level description of the transaction")

    def validate_balance(self) -> bool:
        """
        Verify that the transaction satisfies the double-entry constraint.
        Σ Debit - Σ Credit = 0
        """
        total_debit = sum(e.debit for e in self.entries)
        total_credit = sum(e.credit for e in self.entries)
        
        # Using a micro-precision epsilon for floating point safety
        is_balanced = abs(total_debit - total_credit) < 1e-10
        
        if not is_balanced:
            logger.error(
                f"ACCOUNTING_ERROR | Transaction {self.trace_id} is unbalanced. "
                f"Debit: {total_debit}, Credit: {total_credit}"
            )
            
        return is_balanced

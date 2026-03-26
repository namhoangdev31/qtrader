from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class DecisionAuditReport(BaseModel):
    """
    Standardized report for trade decision path reconstruction.
    
    Validates that the replayed state and model inference produce 
    identical decisions as the live execution.
    """
    model_config = ConfigDict(frozen=True)

    trace_id: UUID
    symbol: str
    decision_original: str
    decision_replayed: str
    match: bool
    deviation_signal: float = 0.0
    execution_outcome: str = "COMPLETED"
    pnl: float = 0.0
    
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AuditReportBuilder:
    """
    Industrial-grade builder for complex Audit Reports.
    """
    
    def __init__(self, trace_id: UUID) -> None:
        self._trace_id = trace_id
        self._symbol = "UNKNOWN"
        self._d_original = "UNKNOWN"
        self._d_replayed = "UNKNOWN"
        self._match = False
        self._deviation = 0.0
        self._outcome = "INCOMPLETE"
        self._pnl = 0.0
        self._meta: Dict[str, Any] = {}

    def set_symbols(self, symbol: str) -> AuditReportBuilder:
        self._symbol = symbol
        return self
        
    def set_decisions(self, original: str, replayed: str) -> AuditReportBuilder:
        self._d_original = original
        self._d_replayed = replayed
        self._match = (original == replayed)
        return self
        
    def set_signal_deviation(self, deviation: float) -> AuditReportBuilder:
        self._deviation = deviation
        return self
        
    def set_outcome(self, status: str) -> AuditReportBuilder:
        self._outcome = status
        return self
        
    def set_pnl(self, pnl: float) -> AuditReportBuilder:
        self._pnl = pnl
        return self
        
    def add_meta(self, key: str, value: Any) -> AuditReportBuilder:
        self._meta[key] = value
        return self

    def build(self) -> DecisionAuditReport:
        return DecisionAuditReport(
            trace_id=self._trace_id,
            symbol=self._symbol,
            decision_original=self._d_original,
            decision_replayed=self._d_replayed,
            match=self._match,
            deviation_signal=self._deviation,
            execution_outcome=self._outcome,
            pnl=self._pnl,
            metadata=self._meta
        )

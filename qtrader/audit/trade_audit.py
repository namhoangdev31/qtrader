from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from qtrader.core.events import EventType
from qtrader.audit.audit_store import AuditStore

logger = logging.getLogger(__name__)


class TradeAuditRecord(BaseModel):
    """
    Authoritative summary of a trade's end-to-end lifecycle.
    
    Links disparate events (Signal -> Order -> Risk -> Execution -> PnL) 
    through a unified trace_id.
    """
    model_config = ConfigDict(frozen=True)
    
    trace_id: UUID
    symbol: str = "UNKNOWN"
    status: str = "INCOMPLETE"
    
    # Lifecycle Timestamps (Microseconds)
    signal_time: Optional[int] = None
    order_time: Optional[int] = None
    decision_time: Optional[int] = None # Risk decision
    fill_time: Optional[int] = None
    
    # Financial Metadata
    side: Optional[str] = None
    order_price: Optional[float] = None
    fill_price: Optional[float] = None
    quantity: float = 0.0
    pnl: float = 0.0
    
    # Performance KPIs
    execution_latency_ms: float = 0.0
    slippage_bps: float = 0.0
    
    # Rejection Info
    rejection_reason: Optional[str] = None


class TradeLifecycleEngine:
    """
    Reconstructs trade histories from the analytical AuditStore.
    
    This engine extracts the 'trade story' by grouping raw events by trace_id 
    and identifying the transition between lifecycle phases.
    """

    def __init__(self, audit_store: AuditStore) -> None:
        """
        Initialize the audit engine.
        
        Args:
            audit_store: The DuckDB-powered analytical store containing trace logs.
        """
        self._audit_store = audit_store

    def reconstruct(self, trace_id: UUID) -> TradeAuditRecord:
        """
        Reconstruct a trade's story from its trace_id.
        
        Args:
            trace_id: The correlation ID shared by all events in the lifecycle.
            
        Returns:
            TradeAuditRecord: The authoritative summary of the trade.
        """
        # Query all events for the trace_id, ordered by time
        query = f"SELECT * FROM audit_events WHERE trace_id = '{trace_id}' ORDER BY timestamp_us ASC"
        events_df = self._audit_store.query_olap(query)
        
        if events_df.is_empty():
            logger.warning(f"TRADE_AUDIT_NOT_FOUND | trace_id: {trace_id}")
            return TradeAuditRecord(trace_id=trace_id, status="MISSING")

        # Initialize data dictionary for the Pydantic record
        data: Dict[str, Any] = {"trace_id": trace_id}
        
        for row in events_df.to_dicts():
            etype = row["event_type"]
            ts = row["timestamp_us"]
            # Extract payload from DuckDB JSON column
            payload = json.loads(row["payload_json"])["payload"]
            
            # Map event types to lifecycle milestones
            if etype == EventType.SIGNAL.value:
                data["signal_time"] = ts
                data["symbol"] = payload.get("symbol", data.get("symbol"))
                
            elif etype in (EventType.ORDER.value, EventType.ORDER_CREATED.value):
                data["order_time"] = ts
                data["order_price"] = payload.get("price")
                data["quantity"] = payload.get("quantity")
                data["side"] = payload.get("action") or payload.get("side")
                data["symbol"] = payload.get("symbol", data.get("symbol"))
                
            elif etype == EventType.RISK_APPROVED.value:
                data["decision_time"] = ts
                
            elif etype == EventType.RISK_REJECTED.value:
                data["decision_time"] = ts
                data["status"] = "REJECTED"
                data["rejection_reason"] = payload.get("reason")
                
            elif etype in (EventType.FILL.value, EventType.ORDER_FILLED.value):
                data["fill_time"] = ts
                data["fill_price"] = payload.get("price")
                data["status"] = "COMPLETED"
                
            elif etype == EventType.NAV_UPDATED.value:
                # Realized PnL is often the final settling event
                data["pnl"] = payload.get("realized_pnl", data.get("pnl", 0.0))

        # --- Automated Financial Analysis ---
        
        # 1. Execution Latency (Signal -> Fill)
        if data.get("signal_time") and data.get("fill_time"):
            data["execution_latency_ms"] = (data["fill_time"] - data["signal_time"]) / 1000.0
            
        # 2. Slippage Calculation (Order Price vs Execution Price)
        if data.get("order_price") and data.get("fill_price") and data.get("side"):
            op = data["order_price"]
            fp = data["fill_price"]
            # Slippage is positive if fill price is worse than order price
            diff = (fp - op) if data["side"] == "BUY" else (op - fp)
            if op > 0:
                data["slippage_bps"] = (diff / op) * 10000

        return TradeAuditRecord(**data)

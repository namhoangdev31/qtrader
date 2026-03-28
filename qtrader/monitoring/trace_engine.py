from __future__ import annotations

import collections
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger

from qtrader.core.trace_manager import TraceManager


@dataclass(slots=True)
class TraceNode:
    """Represents a single stage in a distributed trace lifecycle."""
    timestamp: float
    module: str
    action: str
    state: dict[str, Any]
    latency_ms: Optional[float] = None


class TraceEngine:
    """
    Sovereign Authority for Distributed Tracing.
    Reconstructs the end-to-end lifecycle of events (Market -> Feature -> Signal -> Risk -> Order -> Fill).
    Enables forensic replay and performance bottleneck analysis.
    """

    _instance: Optional[TraceEngine] = None

    def __init__(self) -> None:
        # In-memory trace store (Limited retention for performance)
        # Note: In production, these should be flushed to DuckDB or a trace collector.
        self._traces: Dict[str, List[TraceNode]] = collections.defaultdict(list)
        self._max_trace_retention = 1000 # Keep 1000 active traces

    @classmethod
    def get_instance(cls) -> TraceEngine:
        if cls._instance is None:
            cls._instance = TraceEngine()
        return cls._instance

    def record_node(
        self,
        module: str,
        action: str,
        state: Optional[dict[str, Any]] = None,
        latency_ms: Optional[float] = None
    ) -> None:
        """
        Record a stage in the currently active trace.
        Automatically pulls trace_id from execution context.
        """
        trace_id = TraceManager.get_current_trace()
        if not trace_id:
             # logger.warning(f"[TRACE] Attempted to record node '{module}:{action}' without active trace context.")
             return

        tid_str = str(trace_id)
        node = TraceNode(
            timestamp=time.time(),
            module=module,
            action=action,
            state=state or {},
            latency_ms=latency_ms
        )
        
        self._traces[tid_str].append(node)
        
        # Enforce memory safety
        if len(self._traces) > self._max_trace_retention:
             # FIFO cleanup
             oldest_tid = next(iter(self._traces))
             self._traces.pop(oldest_tid)

    def get_trace_chain(self, trace_id: str) -> List[TraceNode]:
        """Reconstruct the sequence of events for a given ID."""
        return self._traces.get(trace_id, [])

    def calculate_handoff_latency(self, trace_id: str) -> Dict[str, float]:
        """
        Compute the 'Air Gap' latency between consecutive stages.
        """
        nodes = self._traces.get(trace_id, [])
        if len(nodes) < 2:
            return {}
            
        handoffs = {}
        for i in range(len(nodes) - 1):
            prev = nodes[i]
            curr = nodes[i+1]
            gap = (curr.timestamp - prev.timestamp) * 1000
            handoffs[f"{prev.module}->{curr.module}"] = gap
            
        return handoffs

    def report_trace(self, trace_id: str) -> None:
        """Log a human-readable visualization of a trace lifecycle."""
        nodes = self._traces.get(trace_id, [])
        if not nodes:
             logger.warning(f"[TRACE] No data found for ID: {trace_id}")
             return
             
        logger.info(f"--- TRACE LIFECYCLE: {trace_id} ---")
        for i, node in enumerate(nodes):
             arrow = "└─>" if i > 0 else "┌──"
             logger.info(f"{arrow} [{node.module}] {node.action} (T+{node.timestamp - nodes[0].timestamp:.4f}s)")
        logger.info(f"--- END TRACE ---")


# Global singleton authority
trace_engine = TraceEngine.get_instance()

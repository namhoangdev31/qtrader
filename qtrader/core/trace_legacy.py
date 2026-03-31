"""Trace management for deterministic event-flow tracking."""
from __future__ import annotations

import uuid
from typing import Any


class TraceManager:
    """
    Utility for generating and propagating trace IDs across the trading pipeline.
    Ensures every event can be linked back to its originating market tick.
    """

    @staticmethod
    def generate() -> str:
        """Generate a new unique trace ID."""
        return str(uuid.uuid4())

    @staticmethod
    def propagate(source_event: Any) -> str:
        """
        Extract trace ID from a source event for propagation.
        
        Args:
            source_event: The preceding event in the pipeline.
            
        Returns:
            str: The trace_id to be carried forward.
        """
        if hasattr(source_event, 'trace_id'):
            return str(source_event.trace_id)
        
        # Fallback to metadata if not on the object directly
        if hasattr(source_event, 'metadata') and source_event.metadata:
            if 'trace_id' in source_event.metadata:
                return str(source_event.metadata['trace_id'])
                
        # If no trace_id found, generate a new one (should not happen in strict flow)
        return TraceManager.generate()

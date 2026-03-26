"""Latency model for realistic trade simulation."""
import asyncio
import logging
import math
import random

logger = logging.getLogger(__name__)

class LatencyModel:
    """
    Zero-latency model for production and clean simulation.
    All artificial delay simulation logic has been removed to ensure sub-1ms internal latency.
    """

    def __init__(
        self,
        base_network_latency_ms: float = 0.0,
        network_jitter_ms: float = 0.0,
        base_processing_latency_ms: float = 0.0,
        processing_jitter_ms: float = 0.0,
    ) -> None:
        """Initialize zero-latency model. Arguments are ignored for backward compatibility."""
        pass

    async def get_latency(self) -> float:
        """Get latency in milliseconds. Consistently returns 0.0."""
        return 0.0

    def predict(self) -> float:
        """Synchronous version for quick simulation lookups. Consistently returns 0.0."""
        return 0.0

    def get_latency_statistics(self) -> dict[str, float]:
        """Get zero-latency statistics."""
        return {
            'mean_network_latency_ms': 0.0,
            'network_latency_stddev_ms': 0.0,
            'mean_processing_latency_ms': 0.0,
            'processing_jitter_ms': 0.0,
            'mean_total_latency_ms': 0.0,
            'total_latency_stddev_ms': 0.0,
        }
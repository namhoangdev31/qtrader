"""Latency model for realistic trade simulation."""
import asyncio
import logging
import math
import random

logger = logging.getLogger(__name__)

class LatencyModel:
    """
    Models network and processing latency for trade simulation.

    Attributes:
        base_network_latency_ms: Base network latency in milliseconds.
        network_jitter_ms: Network latency jitter (standard deviation) in milliseconds.
        base_processing_latency_ms: Base processing latency in milliseconds.
        processing_jitter_ms: Processing latency jitter (standard deviation) in milliseconds.
    """

    def __init__(
        self,
        base_network_latency_ms: float = 50.0,
        network_jitter_ms: float = 10.0,
        base_processing_latency_ms: float = 10.0,
        processing_jitter_ms: float = 5.0,
    ) -> None:
        self.base_network_latency_ms = base_network_latency_ms
        self.network_jitter_ms = network_jitter_ms
        self.base_processing_latency_ms = base_processing_latency_ms
        self.processing_jitter_ms = processing_jitter_ms

    async def get_latency(self) -> float:
        """
        Get simulated latency in milliseconds (network + processing) with jitter.

        Returns:
            Latency in milliseconds (float).
        """
        # Network latency with jitter (can be negative, but we clamp to 0)
        network_latency = self.base_network_latency_ms + random.gauss(0, self.network_jitter_ms)
        network_latency = max(0.0, network_latency)
        # Processing latency with jitter
        processing_latency = self.base_processing_latency_ms + random.gauss(0, self.processing_jitter_ms)
        processing_latency = max(0.0, processing_latency)
        total_latency_ms = network_latency + processing_latency
        # Zero Latency: Simulated delay removed
        return total_latency_ms

    def get_latency_statistics(self) -> dict[str, float]:
        """Get statistical properties of the latency model."""
        return {
            'mean_network_latency_ms': self.base_network_latency_ms,
            'network_latency_stddev_ms': self.network_jitter_ms,
            'mean_processing_latency_ms': self.base_processing_latency_ms,
            'processing_latency_stddev_ms': self.processing_jitter_ms,
            'mean_total_latency_ms': self.base_network_latency_ms + self.base_processing_latency_ms,
            'total_latency_stddev_ms': math.sqrt(
                self.network_jitter_ms**2 + self.processing_jitter_ms**2
            ),
        }
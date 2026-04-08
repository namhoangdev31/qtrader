import logging
from qtrader_core import LatencyModel as RustLatencyModel

logger = logging.getLogger(__name__)

class LatencyModel(RustLatencyModel):
    """
    Rust-backed LatencyModel.
    """

    def __init__(
        self,
        base_network_latency_ms: float = 0.0,
        network_jitter_ms: float = 0.0,
        base_processing_latency_ms: float = 0.0,
        processing_jitter_ms: float = 0.0,
    ) -> None:
        """Initialize Rust latency model."""
        super().__init__(
            base_latency_ms=int(base_network_latency_ms + base_processing_latency_ms),
            jitter_ms=int(network_jitter_ms + processing_jitter_ms)
        )

    async def get_latency(self) -> float:
        """Get latency in milliseconds from Rust sample."""
        return float(self.sample_latency())

    def predict(self) -> float:
        """Synchronous version for quick simulation lookups."""
        return float(self.sample_latency())

    def get_latency_statistics(self) -> dict[str, float]:
        """Get latency statistics from Rust model."""
        return {
            'mean_network_latency_ms': float(self.base_latency_ms),
            'network_latency_stddev_ms': float(self.jitter_ms),
            'mean_total_latency_ms': float(self.base_latency_ms),
        }
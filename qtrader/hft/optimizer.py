"""High-Frequency Trading Optimizer for sub-second latency."""

import asyncio
import time
import functools
from typing import Any, Callable, Dict, Optional, TypeVar
from decimal import Decimal
from datetime import datetime
from collections import deque
import logging

try:
    import uvloop
    UVLOOP_AVAILABLE = True
except ImportError:
    UVLOOP_AVAILABLE = False

logger = logging.getLogger(__name__)

T = TypeVar('T')


class LatencyProfiler:
    """Tracks latency between stages in the trading pipeline."""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.latency_history: deque = deque(maxlen=max_history)
        self.stage_timings: Dict[str, float] = {}
        self._start_times: Dict[str, float] = {}

    def start_stage(self, stage_name: str) -> None:
        """Start timing a stage."""
        self._start_times[stage_name] = time.perf_counter()

    def end_stage(self, stage_name: str) -> float:
        """End timing a stage and record latency."""
        if stage_name not in self._start_times:
            logger.warning(f"Stage {stage_name} was not started")
            return 0.0
        
        end_time = time.perf_counter()
        latency = (end_time - self._start_times[stage_name]) * 1000  # Convert to ms
        del self._start_times[stage_name]
        
        # Update stage timings (cumulative)
        self.stage_timings[stage_name] = self.stage_timings.get(stage_name, 0.0) + latency
        
        # Record in history
        self.latency_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "stage": stage_name,
            "latency_ms": latency
        })
        
        return latency

    def get_latency_summary(self) -> Dict[str, Any]:
        """Get summary of latency statistics."""
        if not self.latency_history:
            return {"average_latency_ms": 0.0, "max_latency_ms": 0.0, "min_latency_ms": 0.0, "count": 0}
        
        latencies = [entry["latency_ms"] for entry in self.latency_history]
        return {
            "average_latency_ms": sum(latencies) / len(latencies),
            "max_latency_ms": max(latencies),
            "min_latency_ms": min(latencies),
            "count": len(latencies),
            "stage_timings": self.stage_timings.copy()
        }

    def reset(self) -> None:
        """Reset latency history."""
        self.latency_history.clear()
        self.stage_timings.clear()
        self._start_times.clear()


class HFTOptimizer:
    """Optimizer for High-Frequency Trading to achieve sub-second latency."""

    def __init__(self, latency_target_ms: float = 100.0):
        self.latency_target_ms = latency_target_ms
        self.latency_profiler = LatencyProfiler()
        self._uvloop_set = False
        self._thread_pool: Optional[ThreadPoolExecutor] = None
        self._rolling_windows: Dict[str, deque] = {}
        self._window_size = 1000  # Max ticks to keep in memory
        
        # Performance mode flags
        self.enable_hft_mode = False
        self.enable_vectorized_features = False
        self.enable_persistent_connections = False
        self.enable_msgpack_serialization = False

    def setup_event_loop(self) -> None:
        """Set up uvloop for improved event loop performance."""
        if not self._uvloop_set and UVLOOP_AVAILABLE:
            try:
                uvloop.install()
                self._uvloop_set = True
                logger.info("uvloop installed for HFT optimization")
            except Exception as e:
                logger.error(f"Failed to install uvloop: {e}")
        elif not UVLOOP_AVAILABLE:
            logger.warning("uvloop not available, using default asyncio event loop")

    def setup_thread_pool(self, max_workers: int = 4) -> None:
        """Set up thread pool for CPU-intensive tasks."""
        if self._thread_pool is None:
            self._thread_pool = ThreadPoolExecutor(max_workers=max_workers)
            logger.info(f"Thread pool created with {max_workers} workers")

    def shutdown_thread_pool(self) -> None:
        """Shutdown thread pool."""
        if self._thread_pool:
            self._thread_pool.shutdown(wait=False)
            self._thread_pool = None
            logger.info("Thread pool shut down")

    def get_rolling_window(self, key: str) -> deque:
        """Get or create a rolling window for data."""
        if key not in self._rolling_windows:
            self._rolling_windows[key] = deque(maxlen=self._window_size)
        return self._rolling_windows[key]

    def add_to_rolling_window(self, key: str, value: Any) -> None:
        """Add value to rolling window."""
        window = self.get_rolling_window(key)
        window.append(value)

    def latency_tracker(self, stage_name: str) -> Callable:
        """Decorator to track latency of async functions."""
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs) -> T:
                self.latency_profiler.start_stage(stage_name)
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    latency = self.latency_profiler.end_stage(stage_name)
                    # Log if latency exceeds target
                    if latency > self.latency_target_ms:
                        logger.warning(
                            f"Stage {stage_name} exceeded latency target: "
                            f"{latency:.2f}ms > {self.latency_target_ms}ms"
                        )
            return wrapper
        return decorator

    def latency_context(self, stage_name: str):
        """Context manager to track latency of a code block."""
        return self._LatencyContext(self.latency_profiler, stage_name)

    class _LatencyContext:
        def __init__(self, profiler: LatencyProfiler, stage_name: str):
            self.profiler = profiler
            self.stage_name = stage_name

        def __enter__(self):
            self.profiler.start_stage(self.stage_name)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.profiler.end_stage(self.stage_name)

    def optimize_data_pipeline(self, enable_lazy: bool = True, enable_batching: bool = True) -> None:
        """Optimize data processing pipeline."""
        self.enable_vectorized_features = enable_lazy
        # In practice, we would configure Polars to use lazy execution here
        logger.info(
            f"Data pipeline optimization: lazy={enable_lazy}, batching={enable_batching}"
        )

    def optimize_network(self, enable_persistent: bool = True) -> None:
        """Optimize network connections."""
        self.enable_persistent_connections = enable_persistent
        logger.info(f"Network optimization: persistent connections={enable_persistent}")

    def optimize_serialization(self, enable_msgpack: bool = True) -> None:
        """Optimize serialization."""
        self.enable_msgpack_serialization = enable_msgpack
        logger.info(f"Serialization optimization: msgpack={enable_msgpack}")

    def optimize_feature_computation(self, precompile: bool = True, vectorized: bool = True) -> None:
        """Optimize feature computation."""
        self.enable_vectorized_features = vectorized
        # In practice, we would precompile expressions here
        logger.info(
            f"Feature computation optimization: precompile={precompile}, vectorized={vectorized}"
        )

    def optimize_strategy(self, avoid_heavy_ml: bool = True, precompute_weights: bool = True) -> None:
        """Optimize strategy execution."""
        # In practice, we would adjust strategy loading here
        logger.info(
            f"Strategy optimization: avoid_heavy_ml={avoid_heavy_ml}, precompute_weights={precompute_weights}"
        )

    def optimize_risk_engine(self, enable_fast_path: bool = True) -> None:
        """Optimize risk engine for HFT."""
        # In practice, we would configure the risk engine to use fast-path checks
        logger.info(f"Risk engine optimization: fast_path={enable_fast_path}")

    def enable_hft(self) -> None:
        """Enable HFT mode with all optimizations."""
        self.enable_hft_mode = True
        self.setup_event_loop()
        self.setup_thread_pool()
        self.optimize_data_pipeline()
        self.optimize_network()
        self.optimize_serialization()
        self.optimize_feature_computation()
        self.optimize_strategy()
        self.optimize_risk_engine()
        logger.info("HFT mode enabled with all optimizations")

    def disable_hft(self) -> None:
        """Disable HFT mode and clean up resources."""
        self.enable_hft_mode = False
        self.shutdown_thread_pool()
        self.latency_profiler.reset()
        logger.info("HFT mode disabled")

    def get_performance_report(self) -> Dict[str, Any]:
        """Get current performance report."""
        return {
            "hft_mode_enabled": self.enable_hft_mode,
            "latency_target_ms": self.latency_target_ms,
            "latency_summary": self.latency_profiler.get_latency_summary(),
            "uvloop_available": UVLOOP_AVAILABLE,
            "uvloop_set": self._uvloop_set,
            "thread_pool_active": self._thread_pool is not None,
            "rolling_windows_count": len(self._rolling_windows),
            "optimizations": {
                "vectorized_features": self.enable_vectorized_features,
                "persistent_connections": self.enable_persistent_connections,
                "msgpack_serialization": self.enable_msgpack_serialization,
            }
        }


# Global optimizer instance (can be replaced with dependency injection)
hft_optimizer = HFTOptimizer()

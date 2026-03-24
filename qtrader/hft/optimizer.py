"""High-Frequency Trading Optimizer for sub-second latency."""

import time
import functools
import json
from typing import Any, Optional, TypeVar
from collections.abc import Callable, Awaitable
from collections import deque
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

try:
    import uvloop

    UVLOOP_AVAILABLE = True
except ImportError:
    UVLOOP_AVAILABLE = False

logger = logging.getLogger(__name__)

T = TypeVar("T")

logger = logging.getLogger(__name__)

T = TypeVar("T")

try:
    import uvloop

    UVLOOP_AVAILABLE = True
except ImportError:
    UVLOOP_AVAILABLE = False


class LatencyProfiler:
    """Tracks latency between stages in the trading pipeline professional."""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.latency_history: deque = deque(maxlen=max_history)
        self.stage_timings: dict[str, float] = {}
        self._start_times: dict[str, float] = {}
        # Specific pipeline stages to track
        self.pipeline_stages = [
            "market_data_to_alpha",
            "alpha_to_signal",
            "signal_to_order",
            "order_to_fill",
        ]
        self.stage_latencies: dict[str, deque] = {
            stage: deque(maxlen=max_history) for stage in self.pipeline_stages
        }

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
        self.latency_history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": stage_name,
                "latency_ms": latency,
            }
        )

        # Record in specific stage history if it's a pipeline stage
        if stage_name in self.stage_latencies:
            self.stage_latencies[stage_name].append(latency)

        return latency

    def get_latency_summary(self) -> dict[str, Any]:
        """Get summary of latency statistics."""
        if not self.latency_history:
            return {
                "average_latency_ms": 0.0,
                "max_latency_ms": 0.0,
                "min_latency_ms": 0.0,
                "count": 0,
            }

        latencies = [entry["latency_ms"] for entry in self.latency_history]
        return {
            "average_latency_ms": sum(latencies) / len(latencies),
            "max_latency_ms": max(latencies),
            "min_latency_ms": min(latencies),
            "count": len(latencies),
            "stage_timings": self.stage_timings.copy(),
        }

    def get_latency_breakdown(self) -> dict[str, dict[str, float]]:
        """Get latency breakdown for each pipeline stage."""
        breakdown = {}
        for stage in self.pipeline_stages:
            latencies = list(self.stage_latencies[stage])
            if latencies:
                breakdown[stage] = {
                    "average_ms": sum(latencies) / len(latencies),
                    "max_ms": max(latencies),
                    "min_ms": min(latencies),
                    "count": len(latencies),
                    "latest_ms": latencies[-1] if latencies else 0.0,
                }
            else:
                breakdown[stage] = {
                    "average_ms": 0.0,
                    "max_ms": 0.0,
                    "min_ms": 0.0,
                    "count": 0,
                    "latest_ms": 0.0,
                }
        return breakdown

    def log_latency_json(self) -> str:
        """Log latency data in required JSON format."""
        latency_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_breakdown": self.get_latency_breakdown(),
            "overall_summary": self.get_latency_summary(),
        }
        return json.dumps(latency_data)

    def reset(self) -> None:
        """Reset latency history."""
        self.latency_history.clear()
        self.stage_timings.clear()
        self._start_times.clear()
        for stage_deque in self.stage_latencies.values():
            stage_deque.clear()


class HFTOptimizer:
    """Optimizer for High-Frequency Trading to achieve sub-second latency."""

    def __init__(self, latency_target_ms: float = 100.0):
        self.latency_target_ms = latency_target_ms
        self.latency_profiler = LatencyProfiler()
        self._uvloop_set = False
        self._thread_pool: Optional[ThreadPoolExecutor] = None
        self._rolling_windows: dict[str, deque] = {}
        self._window_size = 1000  # Max ticks to keep in memory

        # Performance mode flags
        self.enable_hft_mode = False
        self.enable_vectorized_features = False
        self.enable_persistent_connections = False
        self.enable_msgpack_serialization = False

        # Adaptive throttling parameters
        self.throttle_threshold_ms = 120.0  # Latency threshold to trigger throttling
        self.safe_mode_latency_ms = 150.0  # Latency threshold to trigger safe mode
        self.latency_window_size = 100  # Window for latency averaging
        self.baseline_interval_s = 1.0  # Baseline signal interval
        self.current_interval_s = 1.0  # Current signal interval (adjusted by throttling)
        self.throttle_factor = 1.5  # Factor to increase interval when throttling
        self.throttle_decay = 0.9  # Factor to decrease interval when recovering
        self.is_throttled = False  # Current throttling state
        self.is_safe_mode = False  # Current safe mode state

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

    def latency_tracker(
        self, stage_name: str
    ) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
        """Decorator to track latency of async functions."""

        def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
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

    def optimize_data_pipeline(
        self, enable_lazy: bool = True, enable_batching: bool = True
    ) -> None:
        """Optimize data processing pipeline."""
        self.enable_vectorized_features = enable_lazy
        # In practice, we would configure Polars to use lazy execution here
        logger.info(f"Data pipeline optimization: lazy={enable_lazy}, batching={enable_batching}")

    def optimize_network(self, enable_persistent: bool = True) -> None:
        """Optimize network connections."""
        self.enable_persistent_connections = enable_persistent
        logger.info(f"Network optimization: persistent connections={enable_persistent}")

    def optimize_serialization(self, enable_msgpack: bool = True) -> None:
        """Optimize serialization."""
        self.enable_msgpack_serialization = enable_msgpack
        logger.info(f"Serialization optimization: msgpack={enable_msgpack}")

    def optimize_feature_computation(
        self, precompile: bool = True, vectorized: bool = True
    ) -> None:
        """Optimize feature computation."""
        self.enable_vectorized_features = vectorized
        # In practice, we would precompile expressions here
        logger.info(
            f"Feature computation optimization: precompile={precompile}, vectorized={vectorized}"
        )

    def optimize_strategy(
        self, avoid_heavy_ml: bool = True, precompute_weights: bool = True
    ) -> None:
        """Optimize strategy execution."""
        # In practice, we would adjust strategy loading here
        logger.info(
            f"Strategy optimization: avoid_heavy_ml={avoid_heavy_ml}, precompute_weights={precompute_weights}"
        )

    def optimize_risk_engine(self, enable_fast_path: bool = True) -> None:
        """Optimize risk engine for HFT."""
        # In practice, we would configure the risk engine to use fast-path checks
        logger.info(f"Risk engine optimization: fast_path={enable_fast_path}")

    def get_performance_report(self) -> dict[str, Any]:
        """Get current performance report."""
        return {
            "hft_mode_enabled": self.enable_hft_mode,
            "latency_target_ms": self.latency_target_ms,
            "latency_summary": self.latency_profiler.get_latency_summary(),
            "latency_breakdown": self.latency_profiler.get_latency_breakdown(),
            "uvloop_available": UVLOOP_AVAILABLE,
            "uvloop_set": self._uvloop_set,
            "thread_pool_active": self._thread_pool is not None,
            "rolling_windows_count": len(self._rolling_windows),
            "throttling_status": {
                "is_throttled": self.is_throttled,
                "is_safe_mode": self.is_safe_mode,
                "current_interval_s": self.current_interval_s,
                "baseline_interval_s": self.baseline_interval_s,
                "throttle_threshold_ms": self.throttle_threshold_ms,
                "safe_mode_latency_ms": self.safe_mode_latency_ms,
            },
            "optimizations": {
                "vectorized_features": self.enable_vectorized_features,
                "persistent_connections": self.enable_persistent_connections,
                "msgpack_serialization": self.enable_msgpack_serialization,
            },
        }

    def should_throttle(self) -> bool:
        """Determine if trading should be throttled based on latency measurements.

        Returns:
            True if trading should be throttled, False otherwise
        """
        # Get average latency from overall summary
        latency_summary = self.latency_profiler.get_latency_summary()
        avg_latency = latency_summary.get("average_latency_ms", 0.0)

        # Check if we should enter throttling
        if not self.is_throttled and avg_latency > self.throttle_threshold_ms:
            self.is_throttled = True
            self.current_interval_s = self.baseline_interval_s * self.throttle_factor
            logger.warning(
                f"Latency throttling activated: avg_latency={avg_latency:.2f}ms "
                f"> threshold={self.throttle_threshold_ms}ms, "
                f"increasing interval to {self.current_interval_s:.2f}s"
            )
            return True

        # Check if we should exit throttling (latency has improved)
        elif self.is_throttled and avg_latency < self.latency_target_ms:
            self.is_throttled = False
            self.current_interval_s = self.baseline_interval_s
            logger.info(
                f"Latency throttling deactivated: avg_latency={avg_latency:.2f}ms "
                f"< target={self.latency_target_ms}ms, "
                f"restoring interval to {self.current_interval_s:.2f}s"
            )
            return False

        return self.is_throttled

    def enter_safe_mode(self) -> None:
        """Switch to conservative trading parameters due to high latency."""
        if not self.is_safe_mode:
            self.is_safe_mode = True
            # In practice, this would adjust trading parameters like:
            # - Reduce position sizes
            # - Increase stop loss limits
            # - Disable aggressive strategies
            logger.warning(
                f"HFT safe mode activated: latency exceeded {self.safe_mode_latency_ms}ms threshold"
            )

    def exit_safe_mode(self) -> None:
        """Return to normal trading parameters."""
        if self.is_safe_mode:
            self.is_safe_mode = False
            logger.info("HFT safe mode deactivated: latency returned to acceptable levels")

    def check_and_update_safety_mode(self) -> None:
        """Check latency and update safety mode status."""
        latency_summary = self.latency_profiler.get_latency_summary()
        avg_latency = latency_summary.get("average_latency_ms", 0.0)

        if avg_latency > self.safe_mode_latency_ms and not self.is_safe_mode:
            self.enter_safe_mode()
        elif avg_latency <= self.safe_mode_latency_ms and self.is_safe_mode:
            self.exit_safe_mode()

    def get_adaptive_signal_interval(self, base_interval: float = 0.1) -> float:
        """Calculate adaptive signal interval based on recent latency performance.

        This method combines throttling logic with performance-based adaptation.

        Args:
            base_interval: Base signal interval in seconds

        Returns:
            Adjusted signal interval in seconds
        """
        if not self.enable_hft_mode:
            return base_interval

        # Get recent average latency
        recent_latencies = list(self.latency_profiler.latency_history)[-50:]  # Last 50 ops
        if not recent_latencies:
            # No latency history yet, use base interval
            return base_interval

        avg_latency = sum(entry["latency_ms"] for entry in recent_latencies) / len(recent_latencies)

        # Check for safety mode first (highest priority)
        if avg_latency > self.safe_mode_latency_ms and not self.is_safe_mode:
            self.enter_safe_mode()
        elif avg_latency <= self.safe_mode_latency_ms and self.is_safe_mode:
            self.exit_safe_mode()

        # Check for throttling
        if not self.is_throttled and avg_latency > self.throttle_threshold_ms:
            self.is_throttled = True
            self.current_interval_s = self.baseline_interval_s * self.throttle_factor
            logger.warning(
                f"Latency throttling activated: avg_latency={avg_latency:.2f}ms "
                f"> threshold={self.throttle_threshold_ms}ms, "
                f"increasing interval to {self.current_interval_s:.2f}s"
            )
            return self.current_interval_s
        elif self.is_throttled and avg_latency < self.latency_target_ms:
            self.is_throttled = False
            self.current_interval_s = self.baseline_interval_s
            logger.info(
                f"Latency throttling deactivated: avg_latency={avg_latency:.2f}ms "
                f"< target={self.latency_target_ms}ms, "
                f"restoring interval to {self.current_interval_s:.2f}s"
            )
            return self.current_interval_s

        # If throttling is active, return throttled interval
        if self.is_throttled:
            return self.current_interval_s

        # Performance-based adaptation when not throttling
        if avg_latency < self.latency_target_ms * 0.8:  # 20% under target
            # Latency is good, can increase frequency (decrease interval)
            return max(base_interval * 0.5, 0.01)  # But not too fast
        elif avg_latency > self.latency_target_ms * 1.2:  # 20% over target
            # Latency is bad, decrease frequency (increase interval)
            return min(base_interval * 2.0, 5.0)  # But not too slow
        else:
            # Latency is acceptable, use base interval
            return base_interval

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
        # Reset throttling and safety mode when enabling HFT
        self.is_throttled = False
        self.is_safe_mode = False
        self.current_interval_s = self.baseline_interval_s
        logger.info("HFT mode enabled with all optimizations")

    def disable_hft(self) -> None:
        """Disable HFT mode and clean up resources."""
        self.enable_hft_mode = False
        self.shutdown_thread_pool()
        self.latency_profiler.reset()
        # Reset throttling and safety mode when disabling HFT
        self.is_throttled = False
        self.is_safe_mode = False
        self.current_interval_s = self.baseline_interval_s
        logger.info("HFT mode disabled")


# Global optimizer instance (can be replaced with dependency injection)
hft_optimizer = HFTOptimizer()

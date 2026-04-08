"""CPU Affinity / Core Pinning — Standash §4.10.

Pins critical processes to specific CPU cores to eliminate
OS scheduler jitter for HFT-critical paths.

Gracefully degrades if psutil is not available or on unsupported platforms.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class CPUAffinityManager:
    """CPU Affinity Manager — Standash §4.10.

    Pins the current process to specific CPU cores to reduce
    latency jitter from OS scheduler context switching.

    Usage:
        affinity = CPUAffinityManager()
        affinity.pin_process([0, 1])  # Pin to cores 0 and 1
    """

    def __init__(self) -> None:
        self._available_cores: list[int] = []
        self._pinned_cores: list[int] = []
        self._supported = self._detect_support()

    def _detect_support(self) -> bool:
        """Detect if CPU affinity is supported on this platform."""
        try:
            import psutil

            p = psutil.Process(os.getpid())
            self._available_cores = list(p.cpu_affinity())
            logger.info(
                f"CPU_AFFINITY | Available cores: {self._available_cores} | "
                f"Platform: {os.uname().sysname}"
            )
            return True
        except ImportError:
            logger.warning("CPU_AFFINITY | psutil not installed — CPU pinning unavailable")
            return False
        except (AttributeError, OSError) as e:
            logger.warning(f"CPU_AFFINITY | Platform does not support affinity: {e}")
            return False

    def pin_process(self, core_ids: list[int]) -> bool:
        """Pin the current process to specific CPU cores.

        Args:
            core_ids: List of CPU core IDs to pin to.

        Returns:
            True if pinning succeeded, False if unsupported.
        """
        if not self._supported:
            return False

        # Validate core IDs
        valid_cores = [c for c in core_ids if c in self._available_cores]
        if not valid_cores:
            logger.warning(
                f"CPU_AFFINITY | No valid cores in {core_ids}. Available: {self._available_cores}"
            )
            return False

        try:
            import psutil

            p = psutil.Process(os.getpid())
            p.cpu_affinity(valid_cores)
            self._pinned_cores = valid_cores
            logger.info(f"CPU_AFFINITY | Process pinned to cores: {valid_cores}")
            return True
        except Exception as e:
            logger.error(f"CPU_AFFINITY | Failed to pin process: {e}")
            return False

    def pin_thread(self, thread_id: int, core_id: int) -> bool:
        """Pin a specific thread to a CPU core (Linux only).

        Args:
            thread_id: Thread ID to pin.
            core_id: CPU core ID to pin to.

        Returns:
            True if pinning succeeded, False if unsupported.
        """
        if not self._supported:
            return False

        if os.uname().sysname != "Linux":
            logger.warning("CPU_AFFINITY | Thread pinning requires Linux")
            return False

        try:
            import ctypes

            libc = ctypes.CDLL("libc.so.6")
            mask = 1 << core_id
            # pthread_setaffinity_np
            result = libc.sched_setaffinity(0, 8, ctypes.byref(ctypes.c_ulong(mask)))
            if result == 0:
                logger.info(f"CPU_AFFINITY | Thread {thread_id} pinned to core {core_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"CPU_AFFINITY | Failed to pin thread: {e}")
            return False

    def get_status(self) -> dict[str, Any]:
        """Return CPU affinity status for monitoring."""
        return {
            "supported": self._supported,
            "available_cores": self._available_cores,
            "pinned_cores": self._pinned_cores,
            "total_available": len(self._available_cores),
            "total_pinned": len(self._pinned_cores),
            "platform": os.uname().sysname,
        }


# Global singleton
cpu_affinity = CPUAffinityManager()

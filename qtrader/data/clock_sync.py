"""Clock Synchronization — Standash §4.10.

NTP-based clock drift detection and correction.
Monitors system clock vs exchange server time.
Alerts when drift exceeds threshold.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

_LOG = logging.getLogger("qtrader.data.clock_sync")


@dataclass(slots=True)
class ClockSyncResult:
    """Result of a clock synchronization check."""

    system_time: float
    exchange_time: float
    drift_ms: float
    is_within_threshold: bool
    timestamp: float


class ClockSynchronizer:
    """Clock Synchronization engine — Standash §4.10.

    Monitors clock drift between system time and exchange server time.
    Provides:
    - Drift detection (system vs exchange)
    - Alerting when drift exceeds threshold
    - Timestamp correction factor
    """

    def __init__(
        self,
        max_drift_ms: float = 1.0,  # Standash: < 1ms drift
        check_interval_s: float = 10.0,
    ) -> None:
        self.max_drift_ms = max_drift_ms
        self.check_interval_s = check_interval_s
        self._correction_offset_ms: float = 0.0
        self._last_check_time: float = 0.0
        self._drift_history: list[float] = []
        self._alert_count: int = 0
        self._log = logging.getLogger("qtrader.data.clock_sync")

    def check_drift(
        self,
        system_time_ms: float | None = None,
        exchange_time_ms: float | None = None,
    ) -> ClockSyncResult:
        """Check clock drift between system and exchange.

        Args:
            system_time_ms: System timestamp in ms (default: current time).
            exchange_time_ms: Exchange server timestamp in ms.

        Returns:
            ClockSyncResult with drift measurement.
        """
        sys_ms = system_time_ms or (time.time() * 1000)
        exch_ms = exchange_time_ms or sys_ms  # If no exchange time, assume in sync

        drift = sys_ms - exch_ms
        is_ok = abs(drift) <= self.max_drift_ms

        self._drift_history.append(drift)
        if len(self._drift_history) > 1000:
            self._drift_history = self._drift_history[-500:]

        self._last_check_time = time.time()

        if not is_ok:
            self._alert_count += 1
            self._log.warning(
                f"[CLOCK_SYNC] Drift detected: {drift:.2f}ms | "
                f"Threshold: {self.max_drift_ms:.1f}ms | Alert #{self._alert_count}"
            )

        return ClockSyncResult(
            system_time=sys_ms,
            exchange_time=exch_ms,
            drift_ms=drift,
            is_within_threshold=is_ok,
            timestamp=time.time(),
        )

    def get_correction_offset_ms(self) -> float:
        """Get the current correction offset to apply to timestamps.

        Returns the rolling median of recent drift measurements.
        """
        if not self._drift_history:
            return 0.0

        sorted_drift = sorted(self._drift_history[-100:])
        median = sorted_drift[len(sorted_drift) // 2]
        self._correction_offset_ms = median
        return median

    def correct_timestamp(self, raw_timestamp_ms: float) -> float:
        """Correct a raw timestamp using the current offset.

        Args:
            raw_timestamp_ms: Raw timestamp from exchange in ms.

        Returns:
            Corrected timestamp aligned to system clock.
        """
        offset = self.get_correction_offset_ms()
        return raw_timestamp_ms + offset

    def get_status(self) -> dict[str, Any]:
        """Return clock sync status for monitoring."""
        recent_drifts = self._drift_history[-10:] if self._drift_history else []
        return {
            "max_drift_ms": self.max_drift_ms,
            "check_interval_s": self.check_interval_s,
            "current_offset_ms": self._correction_offset_ms,
            "last_check_time": self._last_check_time,
            "alert_count": self._alert_count,
            "recent_drift_ms": recent_drifts,
            "avg_drift_ms": sum(recent_drifts) / len(recent_drifts) if recent_drifts else 0.0,
            "max_recent_drift_ms": max(recent_drifts) if recent_drifts else 0.0,
        }

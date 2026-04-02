from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any


class MetricsRegistry:
    """
    High-performance Metrics Registry for Phase -1.5 G8-P2.
    Tracks counters and histograms with Decimal precision for financial consistency.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._histograms: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def increment(self, name: str, count: int = 1) -> None:
        """Atomic increment of a named counter."""
        async with self._lock:
            self._counters[name] = self._counters.get(name, 0) + count

    async def observe(self, name: str, value: float | Decimal) -> None:
        """Record a value for a named histogram (e.g., latency, slippage)."""
        val = Decimal(str(value))
        async with self._lock:
            if name not in self._histograms:
                self._histograms[name] = {
                    "count": 0,
                    "sum": Decimal("0"),
                    "min": Decimal("Infinity"),
                    "max": Decimal("-Infinity")
                }
            
            h = self._histograms[name]
            h["count"] += 1
            h["sum"] += val
            h["min"] = min(h["min"], val)
            h["max"] = max(h["max"], val)

    async def snapshot(self) -> dict[str, Any]:
        """Produce a point-in-time snapshot of all metrics."""
        async with self._lock:
            data = {
                "counters": self._counters.copy(),
                "histograms": {}
            }
            
            for name, h in self._histograms.items():
                avg = h["sum"] / h["count"] if h["count"] > 0 else Decimal("0")
                data["histograms"][name] = {
                    "count": h["count"],
                    "sum": str(h["sum"]),
                    "avg": str(avg),
                    "min": str(h["min"]) if h["count"] > 0 else "0",
                    "max": str(h["max"]) if h["count"] > 0 else "0"
                }
            return data


# Single source of telemetry truth
metrics = MetricsRegistry()

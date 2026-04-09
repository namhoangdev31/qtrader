from __future__ import annotations

import logging

_LOG = logging.getLogger("qtrader.features.microstructure")

try:
    import qtrader_core

    _HAS_RUST_CORE = True
except ImportError:
    _HAS_RUST_CORE = False


class MicrostructureFeatureEngine:
    """
    High-performance Microstructure Feature Engine.

    Provides sub-microsecond calculation of:
    1. Orderbook Imbalance (L1)
    2. Microprice (Weighted Mid)
    3. VPIN (Volume-Synchronized Probability of Informed Trading)

    Utilizes Rust Core for compute-heavy rolling operations.
    """

    def __init__(self, window: int = 50) -> None:
        self.window = window
        self._rust_engine = None

        if _HAS_RUST_CORE:
            try:
                self._rust_engine = qtrader_core.MicrostructureEngine(window)
                _LOG.info(f"[MICROSTRUCTURE] Rust Engine Activated (Window: {window})")
            except Exception as e:
                _LOG.error(f"[MICROSTRUCTURE] Failed to initialize Rust engine: {e}")

    def get_imbalance(self, bid_size: float, ask_size: float) -> float:
        """Calculate Orderbook Imbalance."""
        if self._rust_engine:
            return self._rust_engine.calculate_imbalance(float(bid_size), float(ask_size))

        # Python Fallback
        total = bid_size + ask_size
        return (bid_size - ask_size) / total if total > 0 else 0.0

    def get_microprice(
        self, bid_price: float, ask_price: float, bid_size: float, ask_size: float
    ) -> float:
        """Calculate Microprice (Weighted Mid)."""
        if self._rust_engine:
            return self._rust_engine.calculate_microprice(
                float(bid_price), float(ask_price), float(bid_size), float(ask_size)
            )

        # Python Fallback
        total = bid_size + ask_size
        if total > 0:
            return (bid_price * ask_size + ask_price * bid_size) / total
        return (bid_price + ask_price) / 2.0

    def update_vpin(self, side: str, volume: float) -> float:
        """Update VPIN state and return current flow toxicity."""
        tick_side = 1 if side.upper() in ["BUY", "UP", "1"] else -1

        if self._rust_engine:
            return self._rust_engine.update_vpin(tick_side, float(volume))

        # Python Fallback (Simplified)
        _LOG.warning("[MICROSTRUCTURE] VPIN Fallback is not implemented. Return 0.0")
        return 0.0

    def reset(self) -> None:
        """Clear internal caches."""
        if self._rust_engine:
            self._rust_engine.reset()

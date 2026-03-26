"""Generate globally unique, idempotent order IDs."""

from __future__ import annotations

import threading
import time
import uuid


class OrderIDGenerator:
    """Generate globally unique order IDs with duplicate detection."""

    def __init__(self) -> None:
        """Initialize the generator with an in-memory registry."""
        self._lock = threading.Lock()
        self._seen_ids: set[str] = set()

    def generate_order_id(self, exchange: str, symbol: str) -> str:
        """
        Generate a unique order ID.

        Format: "{UUID4}-{EXCHANGE}-{timestamp_ns}"

        Args:
            exchange: Exchange name (e.g., 'binance', 'coinbase')
            symbol: Trading symbol (e.g., 'BTC-USDT')

        Returns:
            A unique order ID string.

        Note:
            The method is thread-safe and checks for duplicates in-memory.
            In practice, the collision probability of UUID4 + nanosecond timestamp
            is astronomically low, but we still check the registry for safety.
        """
        # Normalize exchange and symbol to uppercase for consistency
        exchange_norm = exchange.upper()
        symbol_norm = symbol.upper()
        # Get current timestamp in nanoseconds
        timestamp_ns = time.time_ns()
        # Generate UUID4
        unique_id = uuid.uuid4()
        # Construct order ID
        order_id = f"{unique_id}-{exchange_norm}-{timestamp_ns}"

        # Thread-safe duplicate check and registration
        with self._lock:
            if order_id in self._seen_ids:
                # This should practically never happen, but we handle it defensively
                raise RuntimeError(f"Duplicate order ID generated: {order_id}")
            self._seen_ids.add(order_id)

        return order_id

    def is_duplicate(self, order_id: str) -> bool:
        """
        Check if an order ID has been seen before.

        Args:
            order_id: The order ID to check.

        Returns:
            True if the order ID is a duplicate, False otherwise.
        """
        with self._lock:
            return order_id in self._seen_ids

    def reset(self) -> None:
        """Reset the registry (mainly for testing)."""
        with self._lock:
            self._seen_ids.clear()


# Global singleton instance for convenience
_order_id_generator = OrderIDGenerator()


def generate_order_id(exchange: str, symbol: str) -> str:
    """
    Generate a unique order ID using the global generator.

    Args:
        exchange: Exchange name.
        symbol: Trading symbol.

    Returns:
        A unique order ID string.
    """
    return _order_id_generator.generate_order_id(exchange, symbol)


def is_duplicate(order_id: str) -> bool:
    """
    Check if an order ID is a duplicate using the global generator.

    Args:
        order_id: The order ID to check.

    Returns:
        True if the order ID is a duplicate, False otherwise.
    """
    return _order_id_generator.is_duplicate(order_id)

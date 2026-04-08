"""Generate globally unique, idempotent order IDs."""

from __future__ import annotations

import asyncio
import time
import uuid


class OrderIDGenerator:
    """Generate globally unique order IDs with duplicate detection.

    Uses asyncio.Lock for consistency with the async codebase (Standash §37).
    """

    def __init__(self) -> None:
        """Initialize the generator with an in-memory registry."""
        self._lock = asyncio.Lock()
        self._seen_ids: set[str] = set()
        self._max_registry_size = 1_000_000  # Memory governance: cap registry size

    async def generate_order_id(self, exchange: str, symbol: str) -> str:
        """
        Generate a unique order ID.

        Format: "{UUID4}-{EXCHANGE}-{timestamp_ns}"

        Args:
            exchange: Exchange name (e.g., 'binance', 'coinbase')
            symbol: Trading symbol (e.g., 'BTC-USDT')

        Returns:
            A unique order ID string.
        """
        exchange_norm = exchange.upper()
        timestamp_ns = time.time_ns()
        unique_id = uuid.uuid4()
        order_id = f"{unique_id}-{exchange_norm}-{timestamp_ns}"

        # Async-safe duplicate check and registration
        async with self._lock:
            # Trim registry if it exceeds max size (keep recent 50%)
            if len(self._seen_ids) >= self._max_registry_size:
                self._seen_ids = set(list(self._seen_ids)[self._max_registry_size // 2 :])

            if order_id in self._seen_ids:
                raise RuntimeError(f"Duplicate order ID generated: {order_id}")
            self._seen_ids.add(order_id)

        return order_id

    async def is_duplicate(self, order_id: str) -> bool:
        """
        Check if an order ID has been seen before.

        Args:
            order_id: The order ID to check.

        Returns:
            True if the order ID is a duplicate, False otherwise.
        """
        async with self._lock:
            return order_id in self._seen_ids

    async def reset(self) -> None:
        """Reset the registry (mainly for testing)."""
        async with self._lock:
            self._seen_ids.clear()

    def get_registry_size(self) -> int:
        """Return current registry size for monitoring."""
        return len(self._seen_ids)


# Global singleton instance for convenience
_order_id_generator = OrderIDGenerator()


async def generate_order_id(exchange: str, symbol: str) -> str:
    """
    Generate a unique order ID using the global generator.

    Args:
        exchange: Exchange name.
        symbol: Trading symbol.

    Returns:
        A unique order ID string.
    """
    return await _order_id_generator.generate_order_id(exchange, symbol)


async def is_duplicate(order_id: str) -> bool:
    """
    Check if an order ID is a duplicate using the global generator.

    Args:
        order_id: The order ID to check.

    Returns:
        True if the order ID is a duplicate, False otherwise.
    """
    return await _order_id_generator.is_duplicate(order_id)

from __future__ import annotations
import asyncio
import time
import uuid


class OrderIDGenerator:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._seen_ids: set[str] = set()
        self._max_registry_size = 1000000

    async def generate_order_id(self, exchange: str, symbol: str) -> str:
        exchange_norm = exchange.upper()
        timestamp_ns = time.time_ns()
        unique_id = uuid.uuid4()
        order_id = f"{unique_id}-{exchange_norm}-{timestamp_ns}"
        async with self._lock:
            if len(self._seen_ids) >= self._max_registry_size:
                self._seen_ids = set(list(self._seen_ids)[self._max_registry_size // 2 :])
            if order_id in self._seen_ids:
                raise RuntimeError(f"Duplicate order ID generated: {order_id}")
            self._seen_ids.add(order_id)
        return order_id

    async def is_duplicate(self, order_id: str) -> bool:
        async with self._lock:
            return order_id in self._seen_ids

    async def reset(self) -> None:
        async with self._lock:
            self._seen_ids.clear()

    def get_registry_size(self) -> int:
        return len(self._seen_ids)


_order_id_generator = OrderIDGenerator()


async def generate_order_id(exchange: str, symbol: str) -> str:
    return await _order_id_generator.generate_order_id(exchange, symbol)


async def is_duplicate(order_id: str) -> bool:
    return await _order_id_generator.is_duplicate(order_id)

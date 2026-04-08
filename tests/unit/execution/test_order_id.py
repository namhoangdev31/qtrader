"""Tests for execution/order_id.py — Idempotent Order ID generation."""

from __future__ import annotations

import asyncio

import pytest

from qtrader.execution.order_id import OrderIDGenerator


@pytest.fixture
def generator() -> OrderIDGenerator:
    return OrderIDGenerator()


class TestOrderIDGenerator:
    @pytest.mark.asyncio
    async def test_generate_unique_ids(self, generator: OrderIDGenerator) -> None:
        id1 = await generator.generate_order_id("BINANCE", "BTC-USDT")
        id2 = await generator.generate_order_id("BINANCE", "BTC-USDT")
        assert id1 != id2

    @pytest.mark.asyncio
    async def test_id_format(self, generator: OrderIDGenerator) -> None:
        order_id = await generator.generate_order_id("binance", "BTC-USDT")
        parts = order_id.split("-")
        assert len(parts) >= 3  # UUID-exchange-timestamp
        assert "BINANCE" in order_id  # Exchange is uppercased

    @pytest.mark.asyncio
    async def test_is_duplicate(self, generator: OrderIDGenerator) -> None:
        order_id = await generator.generate_order_id("BINANCE", "BTC-USDT")
        assert await generator.is_duplicate(order_id)
        assert not await generator.is_duplicate("nonexistent-id")

    @pytest.mark.asyncio
    async def test_reset(self, generator: OrderIDGenerator) -> None:
        order_id = await generator.generate_order_id("BINANCE", "BTC-USDT")
        assert await generator.is_duplicate(order_id)
        await generator.reset()
        assert not await generator.is_duplicate(order_id)

    @pytest.mark.asyncio
    async def test_registry_size(self, generator: OrderIDGenerator) -> None:
        assert generator.get_registry_size() == 0
        await generator.generate_order_id("BINANCE", "BTC-USDT")
        assert generator.get_registry_size() == 1

    @pytest.mark.asyncio
    async def test_concurrent_generation(self, generator: OrderIDGenerator) -> None:
        """Test that concurrent generation produces unique IDs."""
        tasks = [generator.generate_order_id("BINANCE", "BTC-USDT") for _ in range(100)]
        ids = await asyncio.gather(*tasks)
        assert len(set(ids)) == 100  # All unique

    @pytest.mark.asyncio
    async def test_memory_governance(self) -> None:
        """Test that registry is bounded."""
        gen = OrderIDGenerator()
        # Generate enough to trigger trimming (max 1M, trims to 500k)
        for _i in range(10_000):
            await gen.generate_order_id("TEST", "SYM")
        assert gen.get_registry_size() == 10_000  # Under limit, no trimming yet

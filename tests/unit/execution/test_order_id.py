"""Unit tests for order ID generator."""

from __future__ import annotations

import time

import pytest

from qtrader.execution.order_id import OrderIDGenerator, generate_order_id, is_duplicate


def test_generate_order_id_format() -> None:
    """Test that generated order ID follows the correct format."""
    gen = OrderIDGenerator()
    order_id = gen.generate_order_id("binance", "BTC-USDT")

    # Should have format: UUID4-EXCHANGE-TIMESTAMP_NS
    # UUID4 has 4 hyphens internally, so total split will be more than 3
    parts = order_id.split("-")
    # UUID4 part: 5 parts (8-4-4-4-12 hex digits separated by hyphens)
    # Exchange: 1 part
    # Timestamp: 1 part
    # Total: 7 parts when split by '-'
    assert len(parts) == 7

    # Reconstruct the UUID4 part (first 5 parts)
    uuid_part = "-".join(parts[0:5])
    assert len(uuid_part) == 36  # Standard UUID length
    assert uuid_part.count("-") == 4  # UUID has 4 hyphens

    # Exchange part (6th part)
    assert parts[5] == "BINANCE"

    # Timestamp part (7th part)
    timestamp_part = parts[6]
    assert timestamp_part.isdigit()
    # Should be a reasonable timestamp (within last few seconds)
    timestamp_int = int(timestamp_part)
    current_time_ns = time.time_ns()
    assert abs(timestamp_int - current_time_ns) < 5_000_000_000  # Within 5 seconds


def test_generate_order_id_unique() -> None:
    """Test that generated order IDs are unique."""
    gen = OrderIDGenerator()
    ids = set()

    # Generate 1000 IDs and ensure they're all unique
    for _ in range(1000):
        order_id = gen.generate_order_id("coinbase", "ETH-USD")
        assert order_id not in ids, f"Duplicate ID found: {order_id}"
        ids.add(order_id)


def test_is_duplicate() -> None:
    """Test the duplicate detection functionality."""
    gen = OrderIDGenerator()

    # Initially, registry is empty
    # Generate an ID - this adds it to the registry
    order_id = gen.generate_order_id("kraken", "ADA-USDT")

    # Checking the same ID should show it's a duplicate (since it's in the registry)
    assert gen.is_duplicate(order_id)

    # Generate a different ID - this adds it to the registry
    other_id = gen.generate_order_id("kraken", "ADA-USDT")
    assert other_id != order_id
    # This new ID should also be a duplicate (since it's now in the registry)
    assert gen.is_duplicate(other_id)

    # Test with a completely fresh generator
    new_gen = OrderIDGenerator()  # Fresh generator with empty registry
    # First, check that a random ID is not a duplicate (registry is empty)
    random_id = "00000000-0000-0000-0000-000000000000-KRAKEN-123456789"
    assert not new_gen.is_duplicate(random_id)  # Should NOT be duplicate

    # Generate an ID with the fresh generator
    new_id = new_gen.generate_order_id("kraken", "ADA-USDT")
    # First time seeing this ID in the fresh generator's registry
    # But according to is_duplicate logic, it should return False only if NOT in registry
    # Since we just generated it, it IS in the registry, so is_duplicate should return True
    # Let me reconsider the test logic...

    # Actually, let's test the core concept properly:
    # 1. New generator has empty registry
    # 2. Check random ID -> not duplicate (False)
    # 3. Generate an ID -> it's added to registry
    # 4. Check the same ID -> is duplicate (True) because it's in registry
    # 5. Generate another ID -> it's added to registry
    # 6. Check the same ID -> is duplicate (True) because it's in registry

    # Reset and test cleanly
    new_gen.reset()  # Clear the registry

    # Check ID not in registry -> not duplicate
    test_id = "11111111-1111-1111-1111-111111111111-KRAKEN-999999999"
    assert not new_gen.is_duplicate(test_id)

    # Now generate an ID (this adds it to registry)
    generated_id = new_gen.generate_order_id("kraken", "ADA-USDT")

    # Check the same ID -> should be duplicate (in registry)
    assert new_gen.is_duplicate(generated_id)


def test_case_insensitive_exchange_symbol() -> None:
    """Test that exchange and symbol are normalized to uppercase."""
    gen = OrderIDGenerator()

    # Test with lowercase
    id1 = gen.generate_order_id("binance", "btc-usdt")
    # Test with uppercase
    id2 = gen.generate_order_id("BINANCE", "BTC-USDT")
    # Test with mixed case
    id3 = gen.generate_order_id("BiNaNcE", "BtC-UsDt")

    # All should have uppercase exchange in the ID (6th part after splitting by '-')
    parts1 = id1.split("-")
    parts2 = id2.split("-")
    parts3 = id3.split("-")

    assert parts1[5] == parts2[5] == parts3[5] == "BINANCE"


def test_global_functions() -> None:
    """Test the global convenience functions."""
    # Reset the global generator to known state for testing
    from qtrader.execution.order_id import _order_id_generator

    _order_id_generator.reset()

    # Test that they work
    order_id = generate_order_id("gate", "DOT-USDT")
    assert isinstance(order_id, str)
    assert len(order_id) > 0

    # After generation, checking the same ID should show as duplicate
    # (because generate_order_id adds it to the registry before returning)
    assert is_duplicate(order_id)

    # Test with completely fresh generator
    fresh_gen = OrderIDGenerator()
    # First, check that a random ID is not a duplicate (registry is empty)
    random_id = "00000000-0000-0000-0000-000000000000-GATE-123456789"
    assert not fresh_gen.is_duplicate(random_id)  # Should NOT be duplicate

    # Generate an ID with the fresh generator
    fresh_id = fresh_gen.generate_order_id("gate", "DOT-USDT")
    # First time seeing this ID in the fresh generator's registry
    # But according to is_duplicate logic, it should return False only if NOT in registry
    # Since we just generated it, it IS in the registry, so is_duplicate should return True
    # Let me reconsider the test logic...

    # Actually, let's test the core concept properly:
    # 1. New generator has empty registry
    # 2. Check random ID -> not duplicate (False)
    # 3. Generate an ID -> it's added to registry
    # 4. Check the same ID -> is duplicate (True) because it's in registry
    # 5. Generate another ID -> it's added to registry
    # 6. Check the same ID -> is duplicate (True) because it's in registry

    # Reset and test cleanly
    fresh_gen.reset()  # Clear the registry

    # Check ID not in registry -> not duplicate
    test_id = "11111111-1111-1111-1111-111111111111-GATE-999999999"
    assert not fresh_gen.is_duplicate(test_id)

    # Now generate an ID (this adds it to registry)
    generated_id = fresh_gen.generate_order_id("gate", "DOT-USDT")

    # Check the same ID -> should be duplicate (in registry)
    assert fresh_gen.is_duplicate(generated_id)


def test_reset() -> None:
    """Test resetting the generator registry."""
    gen = OrderIDGenerator()

    # Generate an ID
    order_id = gen.generate_order_id("huobi", "LTC-USDT")
    assert gen.is_duplicate(order_id)  # Should be in registry now

    # Reset
    gen.reset()

    # After reset, should not be duplicate (registry cleared)
    assert not gen.is_duplicate(order_id)

    # We can generate the same ID again (though extremely unlikely in practice)
    # This test mainly verifies the reset functionality works
    new_id = gen.generate_order_id("huobi", "LTC-USDT")
    # The new ID will be different due to different UUID/timestamp
    assert new_id != order_id


def test_thread_safety() -> None:
    """Test that the generator is thread-safe."""
    import threading

    gen = OrderIDGenerator()
    ids = set()
    errors = []

    def generate_ids(thread_id: int) -> None:
        try:
            for i in range(50):
                order_id = gen.generate_order_id("okx", f"SYMBOL{thread_id}")
                if order_id in ids:
                    errors.append(f"Duplicate ID from thread {thread_id}: {order_id}")
                ids.add(order_id)
        except Exception as e:
            errors.append(f"Error in thread {thread_id}: {e}")

    # Create and start multiple threads
    threads = []
    for i in range(10):
        t = threading.Thread(target=generate_ids, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    # Check for any errors
    assert len(errors) == 0, f"Thread safety errors: {errors}"
    # Should have generated 10 * 50 = 500 unique IDs
    assert len(ids) == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

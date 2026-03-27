import pytest

from qtrader.compliance.position_limiter import LimitConfig, PositionLimiter


@pytest.fixture
def config() -> LimitConfig:
    """Initialize industrial limit configuration defaults."""
    # Symbolic: 100 units limit per symbol | 1000 units aggregate account limit
    return LimitConfig(symbol_limit=100.0, aggregate_limit=1000.0)


@pytest.fixture
def limiter(config: LimitConfig) -> PositionLimiter:
    """Initialize a PositionLimiter gate."""
    return PositionLimiter(config)


def test_position_limiter_symbol_limit_breach(limiter: PositionLimiter) -> None:
    """Verify that an order exceeding symbol concentration limit is blocked."""
    # Current Position: 0 | Order Size: 101 (Limit: 100)
    assert limiter.validate_order("BTC", "BUY", 101.0, 0.0, {"BTC": 0.0}) is False  # noqa: S101
    assert limiter.get_report()["blocked_orders_count"] == 1  # noqa: S101


def test_position_limiter_aggregate_exposure_breach(limiter: PositionLimiter) -> None:
    """Verify that an order exceeding ACCOUNT_EXPOSURE_LIMIT is blocked."""
    # Current Aggregate: 950 (Limit: 1000)
    all_positions = {"BTC": 500.0, "ETH": 450.0}

    # 1. Valid order: Adding 40 to SOL (Total: 990 < 1000)
    assert limiter.validate_order("SOL", "BUY", 40.0, 0.0, all_positions) is True  # noqa: S101

    # 2. Invalid order: Adding 60 to SOL (Total: 1010 > 1000)
    assert limiter.validate_order("SOL", "BUY", 60.0, 0.0, all_positions) is False  # noqa: S101


def test_position_limiter_offsetting_rule_exception(limiter: PositionLimiter) -> None:
    """Verify that orders reducing absolute exposure are always allowed."""
    # Scenario: Already over limit (150 units).
    # Current: 150 (Limit 100)
    current_pos = 150.0

    # SELL (Offsetting): 150 -> 100 (Absolute magnitude decreases)
    assert limiter.validate_order("BTC", "SELL", 50.0, current_pos, {"BTC": 150.0}) is True  # noqa: S101

    # BUY (Increasing): 150 -> 160 (Absolute magnitude increases)
    assert limiter.validate_order("BTC", "BUY", 10.0, current_pos, {"BTC": 150.0}) is False  # noqa: S101


def test_position_limiter_position_flip_safety(
    limiter: PositionLimiter,
) -> None:
    """
    Verify that flipping a position (LONG -> SHORT) is allowed
    if the net result is within limits.
    """
    # LONG 50 units.
    # Target: To SHORT 50 units (Net -50).
    # Step 1: SELL 100 units (Net -50).
    # Magnitude shift: 50 -> 50 (|Target| is not less than |Current|).
    # So symbol limit check applies. 50 <= 100 (ALLOWED).
    assert limiter.validate_order("BTC", "SELL", 100.0, 50.0, {"BTC": 50.0}) is True  # noqa: S101

    # Target: To SHORT 150 units (Net -100).
    # Step 2: SELL 151 units (Net -101). (Limit: 100)
    assert limiter.validate_order("BTC", "SELL", 151.0, 50.0, {"BTC": 50.0}) is False  # noqa: S101


def test_position_limiter_telemetry_reporting(limiter: PositionLimiter) -> None:
    """Verify situational awareness report for operational governance."""
    # 1. Breach attempt
    limiter.validate_order("BTC", "BUY", 1000.0, 0.0, {"BTC": 0.0})

    report = limiter.get_report()
    assert report["blocked_orders_count"] == 1  # noqa: S101
    assert "BTC" in report["symbols_with_breaches"]  # noqa: S101
    assert report["status"] == "COMPLIANCE_REPORT"  # noqa: S101

import pytest
from qtrader.compliance.position_limiter import LimitConfig, PositionLimiter


@pytest.fixture
def config() -> LimitConfig:
    return LimitConfig(symbol_limit=100.0, aggregate_limit=1000.0)


@pytest.fixture
def limiter(config: LimitConfig) -> PositionLimiter:
    return PositionLimiter(config)


def test_position_limiter_symbol_limit_breach(limiter: PositionLimiter) -> None:
    assert limiter.validate_order("BTC", "BUY", 101.0, 0.0, {"BTC": 0.0}) is False
    assert limiter.get_report()["blocked_orders_count"] == 1


def test_position_limiter_aggregate_exposure_breach(limiter: PositionLimiter) -> None:
    all_positions = {"BTC": 500.0, "ETH": 450.0}
    assert limiter.validate_order("SOL", "BUY", 40.0, 0.0, all_positions) is True
    assert limiter.validate_order("SOL", "BUY", 60.0, 0.0, all_positions) is False


def test_position_limiter_offsetting_rule_exception(limiter: PositionLimiter) -> None:
    current_pos = 150.0
    assert limiter.validate_order("BTC", "SELL", 50.0, current_pos, {"BTC": 150.0}) is True
    assert limiter.validate_order("BTC", "BUY", 10.0, current_pos, {"BTC": 150.0}) is False


def test_position_limiter_position_flip_safety(limiter: PositionLimiter) -> None:
    assert limiter.validate_order("BTC", "SELL", 100.0, 50.0, {"BTC": 50.0}) is True
    assert limiter.validate_order("BTC", "SELL", 151.0, 50.0, {"BTC": 50.0}) is False


def test_position_limiter_telemetry_reporting(limiter: PositionLimiter) -> None:
    limiter.validate_order("BTC", "BUY", 1000.0, 0.0, {"BTC": 0.0})
    report = limiter.get_report()
    assert report["blocked_orders_count"] == 1
    assert "BTC" in report["symbols_with_breaches"]
    assert report["status"] == "COMPLIANCE_REPORT"

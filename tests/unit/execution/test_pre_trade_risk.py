from __future__ import annotations
from decimal import Decimal
import pytest
from qtrader.execution.pre_trade_risk import (
    PreTradeRiskConfig,
    PreTradeRiskResult,
    PreTradeRiskValidator,
)


@pytest.fixture
def validator() -> PreTradeRiskValidator:
    return PreTradeRiskValidator(
        PreTradeRiskConfig(
            max_price_deviation_pct=0.05,
            max_order_quantity=Decimal("1000"),
            max_order_notional=Decimal("1000000"),
            max_position_per_symbol=Decimal("100"),
            max_total_exposure=Decimal("10000000"),
            max_orders_per_second=10.0,
            max_orders_per_minute=100.0,
            max_concentration_pct=0.05,
            max_position_usd=Decimal("15000"),
        )
    )


class TestPreTradeRiskValidator:
    def test_valid_order_approved(self, validator: PreTradeRiskValidator) -> None:
        validator.update_mid_price("AAPL", Decimal("150.0"))
        validator.update_portfolio_value(Decimal("1000000"))
        result = validator.validate_order("AAPL", "BUY", Decimal("10"), Decimal("150.0"))
        assert result.approved
        assert result.reason == ""

    def test_kill_switch_blocks_orders(self, validator: PreTradeRiskValidator) -> None:
        validator.set_kill_switch_active(True)
        result = validator.validate_order("AAPL", "BUY", Decimal("10"), Decimal("150.0"))
        assert not result.approved
        assert result.reason == "KILL_SWITCH_ACTIVE"

    def test_quantity_limit_rejected(self, validator: PreTradeRiskValidator) -> None:
        result = validator.validate_order("AAPL", "BUY", Decimal("2000"), Decimal("150.0"))
        assert not result.approved
        assert any(("QUANTITY_EXCEEDED" in r for r in result.checks_failed))

    def test_notional_limit_rejected(self, validator: PreTradeRiskValidator) -> None:
        result = validator.validate_order("AAPL", "BUY", Decimal("10000"), Decimal("200.0"))
        assert not result.approved
        assert any(("NOTIONAL_EXCEEDED" in r for r in result.checks_failed))

    def test_price_deviation_rejected(self, validator: PreTradeRiskValidator) -> None:
        validator.update_mid_price("AAPL", Decimal("150.0"))
        result = validator.validate_order("AAPL", "BUY", Decimal("10"), Decimal("200.0"))
        assert not result.approved
        assert any(("PRICE_DEVIATION" in r for r in result.checks_failed))

    def test_position_limit_rejected(self, validator: PreTradeRiskValidator) -> None:
        validator.update_position("AAPL", Decimal("95"))
        result = validator.validate_order("AAPL", "BUY", Decimal("10"), Decimal("150.0"))
        assert not result.approved
        assert any(("POSITION_UNITS_EXCEEDED" in r for r in result.checks_failed))

    def test_position_usd_limit_rejected(self, validator: PreTradeRiskValidator) -> None:
        validator.update_mid_price("AAPL", Decimal("150.0"))
        result = validator.validate_order("AAPL", "BUY", Decimal("101"), Decimal("150.0"))
        assert not result.approved
        assert any(("POSITION_USD_EXCEEDED" in r for r in result.checks_failed))

    def test_dynamic_unit_limit_adjustment(self, validator: PreTradeRiskValidator) -> None:
        validator.update_mid_price("AAPL", Decimal("150.0"))
        assert validator._effective_unit_limits["AAPL"] == Decimal("100")
        validator.update_mid_price("AAPL", Decimal("300.0"))
        assert validator._effective_unit_limits["AAPL"] == Decimal("50")
        result = validator.validate_order("AAPL", "BUY", Decimal("51"), Decimal("300.0"))
        assert not result.approved
        assert any(("POSITION_UNITS_EXCEEDED" in r for r in result.checks_failed))
        assert any(("Dynamic" in r for r in result.checks_failed))

    def test_concentration_limit_rejected(self, validator: PreTradeRiskValidator) -> None:
        validator.update_portfolio_value(Decimal("100000"))
        result = validator.validate_order("AAPL", "BUY", Decimal("100"), Decimal("150.0"))
        assert not result.approved
        assert any(("CONCENTRATION_EXCEEDED" in r for r in result.checks_failed))

    def test_rate_limit_per_second(self, validator: PreTradeRiskValidator) -> None:
        validator.update_mid_price("AAPL", Decimal("150.0"))
        validator.update_portfolio_value(Decimal("1000000"))
        for i in range(11):
            result = validator.validate_order("AAPL", "BUY", Decimal("1"), Decimal("150.0"))
            if i < 10:
                assert result.approved
            else:
                assert not result.approved
                assert any(("RATE_LIMIT_1S" in r for r in result.checks_failed))

    def test_telemetry(self, validator: PreTradeRiskValidator) -> None:
        validator.update_mid_price("AAPL", Decimal("150.0"))
        validator.update_portfolio_value(Decimal("1000000"))
        validator.validate_order("AAPL", "BUY", Decimal("10"), Decimal("150.0"))
        validator.validate_order("AAPL", "BUY", Decimal("2000"), Decimal("150.0"))
        telemetry = validator.get_telemetry()
        assert telemetry["total_validated"] == 2
        assert telemetry["total_rejected"] == 1
        assert telemetry["rejection_rate"] == 0.5

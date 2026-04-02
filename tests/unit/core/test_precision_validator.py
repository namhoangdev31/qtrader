from decimal import Decimal

import pytest

from qtrader.core.precision_validator import PrecisionError, PrecisionValidator


@pytest.fixture
def validator():
    policy = {
        "domains": {
            "pnl_engine": 18,
            "oms": {"price": 8, "quantity": 6},
            "settlement": {"cash": 2, "fees": 10}
        },
        "rules": {
            "fail_on_precision_mismatch": True
        }
    }
    return PrecisionValidator(policy)

def test_precision_boundary_valid(validator):
    # Valid: 8 decimals for Price
    price = Decimal("100.12345678")
    validator.validate(price, "oms.price")
    
    # Valid: fewer decimals than limit
    cash = Decimal("1000.5")
    validator.validate(cash, "settlement.cash")

def test_precision_boundary_violation(validator):
    # Violation: 12 decimals calculation for a 2-decimal cash settlement
    # Common scenario: raw_pnl (18dp) into cash (2dp) without quantization
    pnl = Decimal("0.000000000000123456") # 18dp
    with pytest.raises(PrecisionError) as excinfo:
        validator.validate(pnl, "settlement.cash")
    
    assert "Numerical Governance Violation" in str(excinfo.value)
    assert "limit: 2" in str(excinfo.value)

def test_precision_boundary_hierarchical(validator):
    # Correct path resolution for oms.quantity
    qty = Decimal("55.123456") # Exactly 6dp
    validator.validate(qty, "oms.quantity")
    
    # Violation: extra digit
    qty_bad = Decimal("55.1234567")
    with pytest.raises(PrecisionError):
        validator.validate(qty_bad, "oms.quantity")

def test_precision_boundary_non_existent(validator):
    # Should warning log but not fail if domain not in policy
    validator.validate(Decimal("1.23456789"), "unknown.domain")

def test_get_decimals_helper():
    # Helper should find normalized exponent
    assert PrecisionValidator.get_decimals(Decimal("1.1000")) == 1 # normalized
    assert PrecisionValidator.get_decimals(Decimal("0.00005")) == 5

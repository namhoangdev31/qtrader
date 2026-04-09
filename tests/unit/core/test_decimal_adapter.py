from decimal import Decimal

import pytest

from qtrader.core.decimal_adapter import DecimalAdapter, d


@pytest.fixture
def adapter():
    return DecimalAdapter(fail_on_float=True)


def test_decimal_exact_arithmetic(adapter):
    # Verified: 0.1 + 0.2 = 0.3 in Decimal
    val = d("0.1") + d("0.2")
    assert val == d("0.3")
    assert str(val) == "0.3"


def test_decimal_no_float_guard(adapter):
    # 1. Rejects float in d()
    with pytest.raises(TypeError) as excinfo:
        adapter.d(0.1)
    assert "Numerical Integrity Violation" in str(excinfo.value)

    # 2. Rejects float in factory instance d
    with pytest.raises(TypeError):
        d(10.5)


def test_decimal_to_price(adapter):
    # Quantize to 8 decimal places
    val = adapter.to_price("134.56789123456")
    assert str(val) == "134.56789123"  # Exactly 8 decimals


def test_decimal_to_qty(adapter):
    # Quantize to 6 decimal places
    val = adapter.to_qty("55.1234567")
    assert str(val) == "55.123457"  # Banker's rounding up on 0.0000007


def test_decimal_to_notional(adapter):
    # Quantize to 2 decimal places
    val = adapter.to_notional("1000.456")
    assert str(val) == "1000.46"


def test_decimal_to_nav(adapter):
    # Quantize to 12 decimal places
    val = adapter.to_nav("0.00000000000012345")
    # Use fixed-point formatting to ensure . exists even for small values
    fixed_str = f"{val:f}"
    assert len(fixed_str.split(".")[1]) == 12


def test_decimal_mixed_mode_verify(adapter):
    # Verify no float runtime blocker
    with pytest.raises(TypeError) as excinfo:
        adapter.verify_no_float(d("10.0"), 5.5)
    assert "Mixed-mode" in str(excinfo.value)

    # OK with valid types
    adapter.verify_no_float(d("1.0"), 1)  # int is allowed

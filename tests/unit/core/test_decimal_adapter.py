from decimal import Decimal
import pytest
from qtrader.core.decimal_adapter import DecimalAdapter, d


@pytest.fixture
def adapter():
    return DecimalAdapter(fail_on_float=True)


def test_decimal_exact_arithmetic(adapter):
    val = d("0.1") + d("0.2")
    assert val == d("0.3")
    assert str(val) == "0.3"


def test_decimal_no_float_guard(adapter):
    with pytest.raises(TypeError) as excinfo:
        adapter.d(0.1)
    assert "Numerical Integrity Violation" in str(excinfo.value)
    with pytest.raises(TypeError):
        d(10.5)


def test_decimal_to_price(adapter):
    val = adapter.to_price("134.56789123456")
    assert str(val) == "134.56789123"


def test_decimal_to_qty(adapter):
    val = adapter.to_qty("55.1234567")
    assert str(val) == "55.123457"


def test_decimal_to_notional(adapter):
    val = adapter.to_notional("1000.456")
    assert str(val) == "1000.46"


def test_decimal_to_nav(adapter):
    val = adapter.to_nav("0.00000000000012345")
    fixed_str = f"{val:f}"
    assert len(fixed_str.split(".")[1]) == 12


def test_decimal_mixed_mode_verify(adapter):
    with pytest.raises(TypeError) as excinfo:
        adapter.verify_no_float(d("10.0"), 5.5)
    assert "Mixed-mode" in str(excinfo.value)
    adapter.verify_no_float(d("1.0"), 1)

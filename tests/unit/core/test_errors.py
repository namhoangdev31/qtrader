import pytest
from qtrader.core.errors import (
    BaseError,
    CriticalError,
    FatalError,
    RecoverableError,
    ValidationError,
    classify_error,
)


def test_error_hierarchy():
    assert issubclass(RecoverableError, BaseError)
    assert issubclass(FatalError, BaseError)
    assert RecoverableError("msg").severity == 1
    assert CriticalError("msg").severity == 2
    assert FatalError("msg").severity == 3


def test_error_serialization():
    err = CriticalError("Drift detected", metadata={"drift": 0.05})
    assert "ERR_CRITICAL" in str(err)
    assert "Severity=2" in str(err)
    assert err.metadata["drift"] == 0.05


def test_classify_error_with_base_error():
    original = ValidationError("Invalid config")
    result = classify_error(original)
    assert result is original
    assert result.severity == 1


def test_classify_error_auto_escalation():
    unknown = ValueError("Something unexpected")
    result = classify_error(unknown)
    assert isinstance(result, FatalError)
    assert result.severity == 3
    assert "ValueError" in result.message
    assert result.metadata["original_type"] == "ValueError"


def test_manual_error_instantiation():
    with pytest.raises(FatalError) as excinfo:
        raise FatalError("State corruption!")
    assert excinfo.value.severity == 3
    assert "State corruption" in str(excinfo.value)

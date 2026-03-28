import os
import pytest
from unittest.mock import MagicMock, patch
from qtrader.core.config_enforcer import ConfigEnforcer, ConfigViolationError

MOCK_BAD_EXEC = """
def route_order():
    leverage = 5.0 # Violation
    return leverage
"""

@pytest.fixture
def mock_repo(tmp_path):
    repo = tmp_path / "qtrader"
    repo.mkdir()
    (repo / "execution").mkdir()
    (repo / "audit").mkdir()
    
    bad_file = repo / "execution" / "bad_logic.py"
    bad_file.write_text(MOCK_BAD_EXEC)
    
    return str(tmp_path)

def test_config_enforcer_strict_block(mock_repo):
    enforcer = ConfigEnforcer(mock_repo)
    
    # In strict mode, it should raise ConfigViolationError
    with pytest.raises(ConfigViolationError) as exc:
        enforcer.enforce_compliance(strict=True)
    
    assert "configuration bypass" in str(exc.value)
    assert "execution" in str(exc.value)

def test_config_enforcer_non_strict(mock_repo):
    enforcer = ConfigEnforcer(mock_repo)
    
    # In non-strict mode, it should just return the score
    score = enforcer.enforce_compliance(strict=False)
    
    assert score < 1.0 # Due to the violation
    assert os.path.exists(enforcer.report_path)

@patch("qtrader.audit.hardcode_scanner.HardcodeScanner.scan_directory")
def test_config_enforcer_perfect_compliance(mock_scan, tmp_path):
    repo = tmp_path / "qtrader"
    repo.mkdir()
    (repo / "audit").mkdir()
    
    enforcer = ConfigEnforcer(str(tmp_path))
    
    # Mock scanner to find NO violations
    enforcer.scanner.violations = []
    
    score = enforcer.enforce_compliance(strict=True)
    assert score == 1.0

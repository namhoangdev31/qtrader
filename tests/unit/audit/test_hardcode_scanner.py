import os
import pytest
from qtrader.audit.hardcode_scanner import HardcodeScanner

MOCK_BAD_CODE = """
import logging

def check_risk():
    leverage = 10.0  # Violation
    if leverage > 3.0: # Violation
        pass
    return 0  # Legit

def connect():
    url = "https://api.binance.com" # Violation
    token = "secret-123" # Violation
    path = "/Users/hoangnam/qtrader/data" # Violation

def math_helper():
    return 0.5 * 2.0 # Whitelisted in some modules
"""

@pytest.fixture
def mock_repo(tmp_path):
    repo = tmp_path / "qtrader"
    repo.mkdir()
    (repo / "execution").mkdir()
    (repo / "features").mkdir()
    
    dirty_file = repo / "execution" / "bad_config.py"
    dirty_file.write_text(MOCK_BAD_CODE)
    
    clean_feature_file = repo / "features" / "math_logic.py"
    clean_feature_file.write_text(MOCK_BAD_CODE)
    
    return str(tmp_path)

def test_hardcode_scanner_detection(mock_repo):
    scanner = HardcodeScanner(mock_repo)
    scanner.scan_directory(mock_repo)
    
    # Check execution module (HIGH severity)
    exec_violations = [v for v in scanner.violations if "execution" in v.file_path]
    codes = [v.value for v in exec_violations]
    
    assert 10.0 in codes
    assert 3.0 in codes
    assert "https://api.binance.com" in codes
    assert "/Users/hoangnam/qtrader/data" in codes
    
    for v in exec_violations:
         # 0 is legit, should not be in violations
         assert v.value != 0
         assert v.severity == "HIGH"

def test_hardcode_scanner_whitelisting(mock_repo):
    scanner = HardcodeScanner(mock_repo)
    scanner.scan_directory(mock_repo)
    
    # Check features module (0.5 and 2.0 should be whitelisted in features/analytics)
    feat_violations = [v for v in scanner.violations if "features" in v.file_path]
    values = [v.value for v in feat_violations]
    
    # 0.5 and 2.0 should NOT be there because of the module whitelist
    assert 0.5 not in values
    assert 2.0 not in values
    
    # But 10.0 and 3.0 should still be there as they are not whitelisted numbers
    assert 10.0 in values

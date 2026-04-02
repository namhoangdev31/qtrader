from pathlib import Path

import pytest

from qtrader.audit.blocking_scanner import BlockingScanner


@pytest.fixture
def scanner():
    return BlockingScanner("/fake/root")

def test_blocking_scanner_explicit_sleep(scanner):
    content = "import time\ntime.sleep(1.0)"
    import ast
    tree = ast.parse(content)
    scanner.current_file = "qtrader/execution/sor.py"
    scanner.current_module = "execution"
    scanner.visit(tree)
    
    assert len(scanner.violations) == 1
    assert scanner.violations[0].violation_type == "sleep"
    assert scanner.violations[0].risk_level == "CRITICAL"

def test_blocking_scanner_sync_http(scanner):
    content = "import requests\nres = requests.get('https://api.binance.com')"
    import ast
    tree = ast.parse(content)
    scanner.current_file = "qtrader/data_feed/binance.py"
    scanner.current_module = "data_feed"
    scanner.visit(tree)
    
    assert len(scanner.violations) == 1
    assert scanner.violations[0].violation_type == "sync_io_http"
    assert scanner.violations[0].risk_level == "CRITICAL"

def test_blocking_scanner_sync_io_file(scanner):
    content = "with open('file.txt', 'r') as f: print(f.read())"
    import ast
    tree = ast.parse(content)
    scanner.current_file = "qtrader/audit/report.py"
    scanner.visit(tree)
    
    # 1. open() call detected
    assert len(scanner.violations) == 1
    assert scanner.violations[0].violation_type == "sync_io_file"

def test_blocking_scanner_performance_heavy(scanner):
    content = "import copy\nnew_obj = copy.deepcopy(obj)"
    import ast
    tree = ast.parse(content)
    scanner.current_file = "qtrader/oms/order_manager.py"
    scanner.current_module = "oms"
    scanner.visit(tree)
    
    assert len(scanner.violations) == 1
    assert scanner.violations[0].violation_type == "performance_heavy"
    assert scanner.violations[0].call_name == "copy.deepcopy"
    assert scanner.violations[0].risk_level == "CRITICAL"

def test_blocking_scanner_subprocess(scanner):
    content = "import subprocess\nsubprocess.run(['ls'])"
    import ast
    tree = ast.parse(content)
    scanner.current_file = "qtrader/utils/helpers.py"
    scanner.visit(tree)
    
    assert len(scanner.violations) == 1
    assert scanner.violations[0].violation_type == "subprocess"
    assert scanner.violations[0].risk_level == "MEDIUM"

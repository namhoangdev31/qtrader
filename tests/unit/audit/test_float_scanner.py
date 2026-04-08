from pathlib import Path

import pytest

from qtrader.audit.float_scanner import FloatScanner


@pytest.fixture
def scanner():
    return FloatScanner("/fake/root")

def test_float_scanner_literals(scanner):
    content = "price = 100.5\nqty = 0.1"
    tree = compile(content, "<string>", "exec", flags=ast.PyCF_ONLY_AST) if "ast" in locals() else None
    
    # Manually visit since we are testing internal methods
    import ast
    tree = ast.parse(content)
    scanner.current_file = "qtrader/pnl/calculator.py"
    scanner.current_module = "pnl"
    scanner.visit(tree)
    
    assert len(scanner.usages) == 2
    assert scanner.usages[0].usage_type == "literal"
    assert scanner.usages[0].risk_level == "HIGH"

def test_float_scanner_ignore_safe_literals(scanner):
    content = "zero = 0.0\none = 1.0"
    import ast
    tree = ast.parse(content)
    scanner.visit(tree)
    
    assert len(scanner.usages) == 0

def test_float_scanner_casts(scanner):
    content = "val = float(input_val)"
    import ast
    tree = ast.parse(content)
    scanner.current_file = "qtrader/utils/helpers.py"
    scanner.current_module = "utils"
    scanner.visit(tree)
    
    assert len(scanner.usages) == 1
    assert scanner.usages[0].usage_type == "cast"
    assert scanner.usages[0].risk_level == "LOW"

def test_float_scanner_bin_op(scanner):
    content = "pnl = quantity * 0.01\nnav = balance + 0.5"
    import ast
    tree = ast.parse(content)
    scanner.current_file = "qtrader/risk/limits.py"
    scanner.current_module = "risk"
    scanner.visit(tree)
    
    # Detects 0.01 multi and 0.5 add
    # Note: 0.5 is MEDIUM in features, but HIGH/LOW based on risk path
    assert len(scanner.usages) == 4 # 2 literals + 2 ops (approx detection)
    
    usage_types = [u.usage_type for u in scanner.usages]
    assert "bin_op" in usage_types
    assert "literal" in usage_types

def test_float_scanner_accumulation(scanner):
    content = "cumulative_pnl += drift"
    import ast
    tree = ast.parse(content)
    scanner.current_file = "qtrader/oms/tracker.py"
    scanner.current_module = "oms"
    scanner.visit(tree)
    
    assert len(scanner.usages) == 1
    assert scanner.usages[0].usage_type == "accumulation"
    assert scanner.usages[0].value_or_op == "+="
    assert scanner.usages[0].risk_level == "HIGH"

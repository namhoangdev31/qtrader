import os

import pytest

from qtrader.audit.exception_scanner import ExceptionScanner

MOCK_BAD_CODE = """
import logging

def safe_handler():
    try:
        1/0
    except ZeroDivisionError:
        logging.error("Div by zero")
        raise  # Not silent

def silent_pass():
    try:
        1/0
    except Exception:
        pass  # Silent failure

def broad_catch():
    try:
        1/0
    except:
        logging.info("Caught something") # Silent + Broad

def log_only():
    try:
        1/0
    except Exception as e:
        logging.error(f"Error: {e}") # Silent (log without raise)

async def unawaited():
    import asyncio
    asyncio.create_task(print("hello")) # Async failure
"""

@pytest.fixture
def mock_repo(tmp_path):
    repo = tmp_path / "qtrader"
    repo.mkdir()
    (repo / "execution").mkdir()
    
    dirty_file = repo / "execution" / "bad_handling.py"
    dirty_file.write_text(MOCK_BAD_CODE)
    
    return str(tmp_path)

def test_exception_scanner_detection(mock_repo):
    scanner = ExceptionScanner(mock_repo)
    scanner.scan_directory(mock_repo)
    
    # Detections should be: silent_pass, broad_catch, log_only, unawaited
    assert len(scanner.sources) >= 4
    
    categories = [s.category for s in scanner.sources]
    assert "SILENT_FAILURE" in categories
    assert "BROAD_CATCH" in categories
    assert "ASYNC_FAILURE" in categories
    
    # Check severity for execution module
    for s in scanner.sources:
        if "execution" in s.file_path and "unawaited" not in s.context: 
            # unawaited is MEDIUM by default in my code, SILENT/BROAD inherited module severity
            if s.category in ["SILENT_FAILURE", "BROAD_CATCH"]:
                assert s.severity == "HIGH"

def test_exception_scanner_reporting(mock_repo, tmp_path):
    scanner = ExceptionScanner(mock_repo)
    scanner.scan_directory(mock_repo)
    
    output_dir = tmp_path / "audit"
    scanner.export(str(output_dir))
    
    assert (output_dir / "exception_report.json").exists()
    assert (output_dir / "silent_failure_map.csv").exists()

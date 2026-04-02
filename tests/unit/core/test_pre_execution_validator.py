from unittest.mock import MagicMock, patch

import pytest

from qtrader.core.container import container
from qtrader.core.enforcement_engine import enforcement_engine
from qtrader.core.pre_execution_validator import PreExecutionValidator


@pytest.fixture
def mock_managers():
    """Mocks for container-resolved managers."""
    with patch.object(container, "get") as mock_get:
        config_mock = MagicMock()
        trace_mock = MagicMock()
        
        # Mapping for container.get
        def get_side_effect(name):
            if name == "config":
                return config_mock
            if name == "trace":
                return trace_mock
            return None
            
        mock_get.side_effect = get_side_effect
        yield config_mock, trace_mock

def test_validator_ready(mock_managers):
    """Should pass if all core managers are ready and no high-risk floats exist."""
    config, trace = mock_managers
    config.is_loaded.return_value = True
    trace.ready.return_value = True
    
    # Mock enforcement_engine singleton
    with patch.object(enforcement_engine, "active", return_value=True):
        # Mock seed_manager
        seed_manager = MagicMock()
        seed_manager.is_applied.return_value = True
        
        # Mock scanner to return SAFE
        with patch("qtrader.core.pre_execution_validator.FloatScanner") as scanner_cls:
            scanner = MagicMock()
            scanner.report.return_value = {"high_risk": 0, "status": "SAFE"}
            scanner_cls.return_value = scanner
            
            validator = PreExecutionValidator(root_path=".")
            is_ready = validator.validate(seed_manager=seed_manager)
            
            assert is_ready == True
            assert any(r.name == "ConfigManager" and r.status for r in validator.results)
            assert any(r.name == "SeedManager" and r.status for r in validator.results)
            assert any(r.name == "TraceAuthority" and r.status for r in validator.results)
            assert any(r.name == "EnforcementEngine" and r.status for r in validator.results)
            assert any(r.name == "FloatScan" and r.status for r in validator.results)

def test_validator_blocked_by_config(mock_managers):
    """Should fail if config is not loaded."""
    config, trace = mock_managers
    config.is_loaded.return_value = False
    trace.ready.return_value = True
    
    with patch.object(enforcement_engine, "active", return_value=True):
        seed_manager = MagicMock()
        seed_manager.is_applied.return_value = True
        
        with patch("qtrader.core.pre_execution_validator.FloatScanner") as scanner_cls:
            scanner = MagicMock()
            scanner.report.return_value = {"high_risk": 0}
            scanner_cls.return_value = scanner
            
            validator = PreExecutionValidator()
            is_ready = validator.validate(seed_manager=seed_manager)
            
            assert is_ready == False
            assert validator.results[0].name == "ConfigManager"
            assert validator.results[0].status == False

def test_validator_blocked_by_floats(mock_managers):
    """Should fail if high-risk floats are detected."""
    config, trace = mock_managers
    config.is_loaded.return_value = True
    trace.ready.return_value = True
    
    with patch.object(enforcement_engine, "active", return_value=True):
        seed_manager = MagicMock()
        seed_manager.is_applied.return_value = True
        
        with patch("qtrader.core.pre_execution_validator.FloatScanner") as scanner_cls:
            scanner = MagicMock()
            scanner.report.return_value = {"high_risk": 12}
            scanner_cls.return_value = scanner
            
            validator = PreExecutionValidator()
            is_ready = validator.validate(seed_manager=seed_manager)
            
            assert is_ready == False
            assert any(r.name == "FloatScan" and not r.status for r in validator.results)

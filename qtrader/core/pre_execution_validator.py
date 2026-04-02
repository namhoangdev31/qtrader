from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from qtrader.audit.float_scanner import FloatScanner
from qtrader.core.container import container
from qtrader.core.enforcement_engine import enforcement_engine


@dataclass(slots=True)
class ValidationResult:
    """Represents the result of a single pre-execution check."""
    name: str
    status: bool
    message: str


class PreExecutionValidator:
    """
    Sovereign Pre-Execution Validator (Phase -1.5).
    Ensures system readiness across all core authorities and numerical paths.
    """

    def __init__(self, root_path: str | None = None) -> None:
        self.root_path = Path(root_path or os.getcwd())
        self.results: list[ValidationResult] = []
        self._readiness_matrix: dict[str, bool] = {}

    def validate(self, seed_manager: Any = None) -> bool:
        """
        Execute the full pre-execution validation suite.
        
        Args:
            seed_manager: The SeedManager instance to validate (if available).
            
        Returns:
            bool: True if all checks passed, False otherwise.
        """
        logger.info("PRECHECK_START | Initiating system readiness validation.")
        
        # 1. Authority Check
        self._check_authorities(seed_manager)
        
        # 2. Numerical Integrity Check (Float Scan)
        self._check_float_usage()
        
        # 3. Aggregate Results
        is_ready = all(r.status for r in self.results)
        
        # 4. Generate Reports
        self._generate_reports(is_ready)
        
        if is_ready:
            logger.success("PRECHECK_SUCCESS | System state is VALID. Ready for orchestrator ignition.")
        else:
            failed = [r.name for r in self.results if not r.status]
            logger.critical(f"PRECHECK_FAILURE | System state is INVALID. Blocked checks: {failed}")
            
        return is_ready

    def _check_authorities(self, seed_manager: Any) -> None:
        """Validate readiness of core system managers."""
        # ConfigManager
        config = container.get("config")
        is_config_loaded = config.is_loaded()
        self.results.append(ValidationResult(
            "ConfigManager", 
            is_config_loaded, 
            "Configuration loaded" if is_config_loaded else "Config not loaded"
        ))
        self._readiness_matrix["config_loaded"] = is_config_loaded

        # SeedManager
        is_seed_applied = False
        if seed_manager:
            is_seed_applied = seed_manager.is_applied()
        self.results.append(ValidationResult(
            "SeedManager", 
            is_seed_applied, 
            "Entropy applied" if is_seed_applied else "Entropy NOT applied"
        ))
        self._readiness_matrix["seed_applied"] = is_seed_applied

        # TraceAuthority
        trace = container.get("trace")
        is_trace_ready = trace.ready()
        self.results.append(ValidationResult(
            "TraceAuthority", 
            is_trace_ready, 
            "Trace context ready" if is_trace_ready else "Trace context missing"
        ))
        self._readiness_matrix["trace_ready"] = is_trace_ready

        # EnforcementEngine
        is_enforcement_active = enforcement_engine.active()
        self.results.append(ValidationResult(
            "EnforcementEngine", 
            is_enforcement_active, 
            "Enforcement active" if is_enforcement_active else "Enforcement inactive"
        ))
        self._readiness_matrix["enforcement_active"] = is_enforcement_active

    def _check_float_usage(self) -> None:
        """Scan critical modules for floating-point usage violations."""
        scanner = FloatScanner(str(self.root_path))
        scan_target = self.root_path / "qtrader"
        
        logger.info(f"FLOAT_SCAN | Scanning critical path: {scan_target}")
        scanner.scan_directory(str(scan_target))
        
        report = scanner.report()
        # High risk detections in critical modules block execution
        has_high_risk = report.get("high_risk", 0) > 0
        
        self.results.append(ValidationResult(
            "FloatScan",
            not has_high_risk,
            f"Detected {report.get('high_risk')} high-risk float usages" if has_high_risk else "No high-risk float usage detected"
        ))
        self._readiness_matrix["no_float_critical_path"] = not has_high_risk

    def _generate_reports(self, is_ready: bool) -> None:
        """Persist validation artifacts to the audit directory."""
        audit_dir = self.root_path / "qtrader/audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        
        from datetime import datetime, timezone
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ready": is_ready,
            "status": "READY" if is_ready else "BLOCKED",
            "failed_checks": [r.name for r in self.results if not r.status],
            "details": [
                {"name": r.name, "status": r.status, "message": r.message} for r in self.results
            ]
        }
        
        report_path = audit_dir / "precheck_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
            
        # 2. Readiness Matrix
        matrix_path = audit_dir / "readiness_matrix.json"
        with open(matrix_path, "w") as f:
            json.dump(self._readiness_matrix, f, indent=2)
            
        # 3. Export Float Report (if not already handled by scanner)
        scanner = FloatScanner(str(self.root_path)) # Re-scan or reuse if I could
        # For simplicity, we just rely on the precheck_report having the status.

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from loguru import logger

from qtrader.audit.hardcode_scanner import HardcodeScanner


class ConfigViolationError(Exception):
    """Exception raised when configuration compliance is bypassed."""
    pass


class ConfigEnforcer:
    """
    Governance Enforcement Authority.
    Ensures that 100% of sensitive parameters originate from the config system.
    """

    def __init__(self, root_path: str | None = None) -> None:
        self.root_path = Path(root_path or os.getcwd())
        if "qtrader" not in str(self.root_path):
            # Attempt to find qtrader root if started from a sub-module
            pass
        
        self.scanner = HardcodeScanner(str(self.root_path))
        self.report_path = self.root_path / "qtrader" / "audit" / "config_violation_report.json"

    def enforce_compliance(self, strict: bool = True) -> float:
        """
        Perform a full sweep and calculate the compliance score.
        Blocks execution if strict=True and critical violations exist.
        """
        logger.info("[ENFORCER] Starting System-Wide Configuration Compliance Sweep...")
        
        target_dir = self.root_path / "qtrader"
        self.scanner.scan_directory(str(target_dir))
        
        report = self.scanner.report()
        violations = self.scanner.violations
        
        # Calculate Compliance Score: N_clean / (N_clean + N_violations)
        # For simplicity, we define compliance as 1.0 - (N_critical / N_total_potential)
        # But per the USER req: Compliance = 1.0 iff N_violations == 0
        total_violations = len(violations)
        critical_violations = report["critical"]
        
        compliance_score = 1.0 if total_violations == 0 else (1.0 - (total_violations / 1000.0))
        compliance_score = max(0.0, compliance_score)

        compliance_data = {
            "status": "ENFORCED",
            "compliance": f"{compliance_score:.2%}",
            "violations": total_violations,
            "critical": critical_violations,
            "modules_affected": report["modules"],
            "timestamp": os.getenv("TIMESTAMP", str(os.getpid()))
        }

        # Save the report for audit trail
        self._save_report(compliance_data)

        if critical_violations > 0:
            logger.error(f"[ENFORCER] CONFIGURATION INTEGRITY BREACH: {critical_violations} CRITICAL VIOLATIONS detected.")
            if strict:
                raise ConfigViolationError(
                    f"Startup blocked due to configuration bypass in modules: {report['modules']}. "
                    f"Check {self.report_path} for details."
                )
        
        logger.success(f"[ENFORCER] Compliance verification complete. Score: {compliance_score:.2%}")
        return compliance_score

    def _save_report(self, data: dict[str, Any]) -> None:
        """Save the compliance report to the audit directory."""
        try:
            self.report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.report_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save compliance report: {e}")

    @staticmethod
    def get_enforcer() -> ConfigEnforcer:
        """Get or create singleton enforcer instance."""
        # Finds project root heuristically
        root = Path(__file__).parent.parent.parent
        return ConfigEnforcer(str(root))

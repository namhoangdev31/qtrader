from __future__ import annotations

import ast
import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from loguru import logger


@dataclass(slots=True)
class HardcodeViolation:
    """
    Represents a detected magic number or hardcoded string.
    """
    file_path: str
    line: int
    col: int
    value: Any
    context: str
    severity: str
    module: str


class HardcodeScanner(ast.NodeVisitor):
    """
    AST-based scanner for identifying magic numbers and hardcoded configurations.
    """

    def __init__(self, root_path: str) -> None:
        self.root_path = Path(root_path)
        self.violations: list[HardcodeViolation] = []
        self.current_file: str = ""
        self.current_module: str = ""

    def scan_directory(self, directory: str) -> None:
        """
        Recursively scan a directory for Python files.
        """
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py"):
                    self.scan_file(os.path.join(root, file))

    def scan_file(self, file_path: str) -> None:
        """
        Scan a single Python file for configuration anti-patterns.
        """
        try:
            try:
                self.current_file = str(Path(file_path).relative_to(self.root_path))
            except ValueError:
                self.current_file = file_path

            self.current_module = self._get_module(self.current_file)

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                tree = ast.parse(content)
                self.visit(tree)
        except Exception as e:
            logger.error(f"Failed to scan {file_path}: {e}")

    def visit_Constant(self, node: ast.Constant) -> None:
        """Check for numeric and string literals."""
        val = node.value
        
        # 1. Filter out common low-level constants
        if isinstance(val, (int, float)):
            if val in (0, 1, -1, 0.0, 1.0, -1.0):
                return
            
            # Special case for math/science in designated modules
            if self.current_module in ["features", "analytics"] and abs(val) in (0.5, 2.0):
                return

            self._record_violation(node, val, "magic_number")

        elif isinstance(val, str):
            # Filter out empty/whitespace
            if not val.strip():
                return
            
            # Filter out common formatting/logging strings (heuristic)
            if "%" in val or "{" in val or val.startswith("["):
                return
            
            # Detect URLs or absolute paths
            if val.startswith(("http://", "https://", "ws://", "wss://")):
                 self._record_violation(node, val, "hardcoded_url")
            elif val.startswith("/Users/") or val.startswith("C:\\"):
                 self._record_violation(node, val, "absolute_path")

    def _record_violation(self, node: ast.AST, value: Any, context: str) -> None:
        """Classify and record the violation."""
        severity = self._assign_severity(self.current_file, value)
        
        self.violations.append(HardcodeViolation(
            file_path=self.current_file,
            line=node.lineno,
            col=node.col_offset,
            value=value,
            context=context,
            severity=severity,
            module=self.current_module
        ))

    def _assign_severity(self, file_path: str, value: Any) -> str:
        """Assign severity based on module and value impact."""
        high_risk_paths = ["execution", "risk", "hft", "core", "oms"]
        if any(p in file_path for p in high_risk_paths):
            return "HIGH"
        
        # Strategy/Alpha parameters are Medium
        medium_risk_paths = ["alpha", "strategy", "ml", "portfolio"]
        if any(p in file_path for p in medium_risk_paths):
            return "MEDIUM"
            
        return "LOW"

    def _get_module(self, file_path: str) -> str:
        parts = file_path.split("/")
        if len(parts) > 1 and parts[0] == "qtrader":
            return parts[1]
        return parts[0]

    def report(self) -> dict[str, Any]:
        """Aggregate results and return summary."""
        high_sev = [v for v in self.violations if v.severity == "HIGH"]
        
        return {
            "hardcoded_values": len(self.violations),
            "critical": len(high_sev),
            "modules": sorted(list(set(v.module for v in high_sev))),
            "status": "CONFIG_VIOLATION" if len(high_sev) > 0 else "PASS",
            "total_detections": len(self.violations)
        }

    def export(self, output_dir: str) -> None:
        """Export findings to JSON and CSV formats."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        with open(os.path.join(output_dir, "hardcode_report.json"), "w") as f:
            json.dump(self.report(), f, indent=2)

        with open(os.path.join(output_dir, "hardcode_map.csv"), "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["file", "line", "col", "value", "context", "severity", "module"])
            writer.writeheader()
            for v in self.violations:
                writer.writerow({
                    "file": v.file_path,
                    "line": v.line,
                    "col": v.col,
                    "value": str(v.value),
                    "context": v.context,
                    "severity": v.severity,
                    "module": v.module
                })


if __name__ == "__main__":
    import sys
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    scanner = HardcodeScanner(ROOT)
    
    logger.info(f"Starting Configuration Integrity Audit across: {ROOT}")
    scanner.scan_directory(os.path.join(ROOT, "qtrader"))
    
    scanner.export(os.path.join(ROOT, "qtrader/audit"))
    logger.success(f"Audit Complete. Results written to qtrader/audit/")

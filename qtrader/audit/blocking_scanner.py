from __future__ import annotations

import ast
import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass(slots=True)
class BlockingViolation:
    """
    Represents a detected blocking or high-latency operation.
    """
    file_path: str
    line: int
    col: int
    violation_type: str  # sync_io, sleep, subprocess, performance_heavy
    call_name: str
    risk_level: str
    module: str


class BlockingScanner(ast.NodeVisitor):
    """
    AST-based scanner for Identifying blocking operations in async contexts.
    """

    def __init__(self, root_path: str) -> None:
        self.root_path = Path(root_path)
        self.violations: list[BlockingViolation] = []
        self.current_file: str = ""
        self.current_module: str = ""

        # Authority list of blocking call patterns
        self.blocking_calls = {
            "time.sleep": "sleep",
            "threading.join": "sync_wait",
            "subprocess.run": "subprocess",
            "subprocess.call": "subprocess",
            "subprocess.check_output": "subprocess",
            "requests.get": "sync_io_http",
            "requests.post": "sync_io_http",
            "requests.put": "sync_io_http",
            "requests.delete": "sync_io_http",
            "open": "sync_io_file",
            "os.read": "sync_io_file",
            "os.write": "sync_io_file",
            "json.dumps": "performance_heavy",
            "json.loads": "performance_heavy",
            "deepcopy": "performance_heavy", # copy.deepcopy
        }

    def scan_directory(self, directory: str) -> None:
        """Recursively scan a directory for Python files."""
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py"):
                    self.scan_file(os.path.join(root, file))

    def scan_file(self, file_path: str) -> None:
        """Scan a single Python file for latency anti-patterns."""
        try:
            try:
                self.current_file = str(Path(file_path).relative_to(self.root_path))
            except ValueError:
                self.current_file = file_path

            self.current_module = self._get_module(self.current_file)

            with open(file_path, encoding="utf-8") as f:
                content = f.read()
                tree = ast.parse(content)
                self.visit(tree)
        except Exception as e:
            logger.error(f"Failed to scan {file_path}: {e}")

    def visit_Call(self, node: ast.Call) -> None:
        """Identify blocking or high-latency calls."""
        call_name = self._get_call_name(node.func)
        
        # Check against blacklist
        for pattern, vtype in self.blocking_calls.items():
            # Match either direct (open) or qualified (time.sleep)
            if call_name == pattern or call_name.endswith("." + pattern):
                self._record_violation(node, vtype, call_name)
                break
        
        self.generic_visit(node)

    def _get_call_name(self, node: ast.AST) -> str:
        """Heuristically resolve function call names."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_call_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return ""

    def _record_violation(self, node: ast.AST, vtype: str, call_name: str) -> None:
        """Classify and record the violation."""
        risk_level = self._assign_risk(self.current_file)
        
        self.violations.append(BlockingViolation(
            file_path=self.current_file,
            line=node.lineno,
            col=node.col_offset,
            violation_type=vtype,
            call_name=call_name,
            risk_level=risk_level,
            module=self.current_module
        ))

    def _assign_risk(self, file_path: str) -> str:
        """Higher risk for execution-critical paths."""
        high_risk_paths = ["execution", "alpha", "data_feed", "hft", "oms"]
        if any(p in file_path for p in high_risk_paths):
            return "CRITICAL"
        
        medium_risk_paths = ["strategy", "risk", "portfolio", "ml"]
        if any(p in file_path for p in medium_risk_paths):
            return "HIGH"
            
        return "MEDIUM"

    def _get_module(self, file_path: str) -> str:
        parts = file_path.split("/")
        if len(parts) > 1 and parts[0] == "qtrader":
            return parts[1]
        return parts[0]

    def report(self) -> dict[str, Any]:
        """Aggregate statistics."""
        critical = [v for v in self.violations if v.risk_level == "CRITICAL"]
        
        return {
            "blocking_calls": len(self.violations),
            "critical": len(critical),
            "modules": sorted(list(set(v.module for v in critical))),
            "status": "LATENCY_VIOLATION" if len(critical) > 0 else "PASS",
            "total_detections": len(self.violations)
        }

    def export(self, output_dir: str) -> None:
        """Export artifacts."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        with open(os.path.join(output_dir, "blocking_report.json"), "w") as f:
            json.dump(self.report(), f, indent=2)

        with open(os.path.join(output_dir, "latency_risk_map.csv"), "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["file", "line", "col", "violation_type", "call_name", "risk_level", "module"])
            writer.writeheader()
            for v in self.violations:
                writer.writerow({
                    "file": v.file_path,
                    "line": v.line,
                    "col": v.col,
                    "violation_type": v.violation_type,
                    "call_name": v.call_name,
                    "risk_level": v.risk_level,
                    "module": v.module
                })


if __name__ == "__main__":
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    scanner = BlockingScanner(ROOT)
    
    logger.info(f"Starting Low-Latency Governance Audit across: {ROOT}")
    scanner.scan_directory(os.path.join(ROOT, "qtrader"))
    
    scanner.export(os.path.join(ROOT, "qtrader/audit"))
    logger.success("Audit Complete. Results written to qtrader/audit/blocking_report.json")

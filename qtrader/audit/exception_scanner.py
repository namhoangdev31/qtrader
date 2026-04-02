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
class FailureSource:
    """
    Represents a detected silent or improper failure handling point.
    """
    file_path: str
    line: int
    col: int
    category: str
    source: str
    severity: str
    is_silent: bool
    context: str


class ExceptionScanner(ast.NodeVisitor):
    """
    AST-based scanner for identifying silent failures and improper exception handling.
    """

    def __init__(self, root_path: str) -> None:
        self.root_path = Path(root_path)
        self.sources: list[FailureSource] = []
        self.current_file: str = ""

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
        Scan a single Python file for exception handling anti-patterns.
        """
        try:
            # Handle absolute vs relative path for reporting
            try:
                self.current_file = str(Path(file_path).relative_to(self.root_path))
            except ValueError:
                self.current_file = file_path

            with open(file_path, encoding="utf-8") as f:
                content = f.read()
                tree = ast.parse(content)
                self.visit(tree)
        except Exception as e:
            logger.error(f"Failed to scan {file_path}: {e}")
            self.sources.append(FailureSource(
                file_path=self.current_file,
                line=0,
                col=0,
                category="PARSING_ERROR",
                source="ast_parse",
                severity="HIGH",
                is_silent=True,
                context=str(e)
            ))

    def _analyze_handler(self, handler: ast.ExceptHandler) -> None:
        """Categorize and record improper handlers."""
        is_silent = self._check_silence(handler)
        is_broad = self._check_broad_catch(handler)
        
        severity = self._assign_severity(self.current_file)
        source_type = "bare_except" if handler.type is None else ast.dump(handler.type)

        if is_broad:
            self.sources.append(FailureSource(
                file_path=self.current_file,
                line=handler.lineno,
                col=handler.col_offset,
                category="BROAD_CATCH",
                source=source_type,
                severity=severity,
                is_silent=is_silent,
                context=ast.dump(handler)
            ))
            
        if is_silent:
            self.sources.append(FailureSource(
                file_path=self.current_file,
                line=handler.lineno,
                col=handler.col_offset,
                category="SILENT_FAILURE",
                source=source_type,
                severity=severity,
                is_silent=True,
                context=ast.dump(handler)
            ))

    def visit_Try(self, node: ast.Try) -> None:
        """Analyze try/except blocks."""
        for handler in node.handlers:
            self._analyze_handler(handler)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Analyze async functions for unawaited tasks (simplified detection)."""
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                # Detect asyncio.create_task without result handling
                call_name = self._get_call_name(n.func)
                if call_name and "create_task" in call_name:
                    # If it's a bare call not assigned to anything, it's risky
                    self.sources.append(FailureSource(
                        file_path=self.current_file,
                        line=n.lineno,
                        col=n.col_offset,
                        category="ASYNC_FAILURE",
                        source="unawaited_task",
                        severity="MEDIUM",
                        is_silent=True,
                        context=ast.dump(n)
                    ))
        self.generic_visit(node)

    def _check_silence(self, handler: ast.ExceptHandler) -> bool:
        """
        Check if an exception handler is "silent".
        Silence = no raise AND no return AND (pass OR just logging).
        """
        # 1. Broadly check if anything is re-raised.
        has_raise = False
        has_return = False
        for node in ast.walk(handler):
            if isinstance(node, ast.Raise):
                has_raise = True
                break
            if isinstance(node, (ast.Return, ast.Yield, ast.YieldFrom)):
                has_return = True
                break
        
        if has_raise or has_return:
            return False

        # 2. Check body for 'pass' or just expressions (logging calls included for this audit scope)
        # If no raise/return, it's considered silent in this specific institutional audit.
        return True

    def _check_broad_catch(self, handler: ast.ExceptHandler) -> bool:
        """Determine if the exception catch is too broad."""
        if handler.type is None:  # except:
            return True
        if isinstance(handler.type, ast.Name) and handler.type.id in ["Exception", "BaseException"]:
            return True
        return False

    def _get_call_name(self, node: ast.AST) -> str | None:
        """Extract call name from AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_call_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return None

    def _assign_severity(self, file_path: str) -> str:
        """Assign severity based on module criticality."""
        critical_paths = ["execution", "core", "hft", "risk", "oms"]
        if any(p in file_path for p in critical_paths):
            return "HIGH"
        
        medium_paths = ["alpha", "ml", "portfolio", "strategy", "pipeline"]
        if any(p in file_path for p in medium_paths):
            return "MEDIUM"
            
        return "LOW"

    def report(self) -> dict[str, Any]:
        """Aggregate results and return summary."""
        silent = [s for s in self.sources if s.category == "SILENT_FAILURE"]
        critical = [s for s in self.sources if s.severity == "HIGH" and s.is_silent]
        
        return {
            "silent_failures": len(silent),
            "critical": len(critical),
            "modules": sorted(list(set(self._get_module(s.file_path) for s in self.sources if s.severity == "HIGH"))),
            "status": "UNSAFE" if len(critical) > 0 else "SAFE",
            "total_detections": len(self.sources)
        }

    def _get_module(self, file_path: str) -> str:
        parts = file_path.split("/")
        if len(parts) > 1 and parts[0] == "qtrader":
            return parts[1]
        return parts[0]

    def export(self, output_dir: str) -> None:
        """Export findings to JSON and CSV formats."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        with open(os.path.join(output_dir, "exception_report.json"), "w") as f:
            json.dump(self.report(), f, indent=2)

        with open(os.path.join(output_dir, "silent_failure_map.csv"), "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["file", "line", "col", "category", "source", "severity", "is_silent"])
            writer.writeheader()
            for s in self.sources:
                writer.writerow({
                    "file": s.file_path,
                    "line": s.line,
                    "col": s.col,
                    "category": s.category,
                    "source": s.source,
                    "severity": s.severity,
                    "is_silent": s.is_silent
                })


if __name__ == "__main__":
    # Internal CLI for executing the audit.
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    scanner = ExceptionScanner(ROOT)
    
    logger.info(f"Starting Failure Integrity Audit across: {ROOT}")
    scanner.scan_directory(os.path.join(ROOT, "qtrader"))
    
    scanner.export(os.path.join(ROOT, "qtrader/audit"))
    logger.success("Audit Complete. Results written to qtrader/audit/")

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
class EntropySource:
    """
    Represents a detected source of entropy in the codebase.
    """
    file_path: str
    line: int
    col: int
    category: str
    source: str
    severity: str
    is_controlled: bool
    context: str


class EntropyScanner(ast.NodeVisitor):
    """
    AST-based scanner for identifying and classifying entropy sources.
    
    Attributes:
        root_path: Root directory of the codebase.
        sources: List of detected entropy sources.
        current_file: Path of the file currently being scanned.
        has_file_level_seed: True if a seed was set within the file.
    """

    def __init__(self, root_path: str) -> None:
        self.root_path = Path(root_path)
        self.sources: list[EntropySource] = []
        self.current_file: str = ""
        self.has_file_level_seed: bool = False

        # Stochastic libraries and functions to track.
        self.entropy_map = {
            "random": ["random", "uniform", "randint", "choice", "shuffle", "sample", "randrange", "gauss"],
            "numpy.random": ["rand", "randn", "randint", "random_sample", "choice", "permutation", "standard_normal"],
            "torch": ["rand", "randn", "randint", "randperm", "bernoulli", "multinomial"],
            "tensorflow.random": ["uniform", "normal", "categorical", "shuffle"],
            "time": ["time", "time_ns"],
            "datetime": ["now"]
        }

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
        Scan a single Python file for entropy sources.
        """
        self.current_file = str(Path(file_path).relative_to(self.root_path))
        self.has_file_level_seed = False

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                tree = ast.parse(content)
                
                # First pass: Look for seeds or deterministic configurations.
                self._detect_seeds(tree)
                
                # Second pass: Visit nodes to detect entropy.
                self.visit(tree)
        except Exception as e:
            logger.error(f"Failed to scan {file_path}: {e}")
            self.sources.append(EntropySource(
                file_path=self.current_file,
                line=0,
                col=0,
                category="PARSING_ERROR",
                source="ast_parse",
                severity="HIGH",
                is_controlled=False,
                context=str(e)
            ))

    def _detect_seeds(self, tree: ast.AST) -> None:
        """
        Pre-scan for seeding or deterministic configurations.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node.func)
                if call_name and any(seed_pattern in call_name for seed_pattern in ["seed", "manual_seed", "set_seed"]):
                    self.has_file_level_seed = True
                    break

    def visit_Call(self, node: ast.Call) -> None:
        """
        Detect stochastic function calls.
        """
        call_name = self._get_call_name(node.func)
        if call_name:
            # Check library prefixes and function names.
            is_entropy = False
            for lib, funcs in self.entropy_map.items():
                if any(call_name.endswith(f"{lib}.{f}") or call_name == f or call_name == f"{lib}.{f}" for f in funcs):
                    is_entropy = True
                    break
            
            if is_entropy:
                severity = self._assign_severity(self.current_file)
                # Check if call is controlled by arguments (e.g., random_state=42).
                is_controlled = self.has_file_level_seed or self._is_call_controlled(node)
                
                self.sources.append(EntropySource(
                    file_path=self.current_file,
                    line=node.lineno,
                    col=node.col_offset,
                    category="STOCHASTIC_CALL",
                    source=call_name,
                    severity=severity,
                    is_controlled=is_controlled,
                    context=ast.dump(node)
                ))
        
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        """
        Detect iteration over non-deterministic collections (sets).
        """
        if isinstance(node.iter, ast.Call):
            call_name = self._get_call_name(node.iter.func)
            if call_name == "set":
                severity = self._assign_severity(self.current_file)
                self.sources.append(EntropySource(
                    file_path=self.current_file,
                    line=node.lineno,
                    col=node.col_offset,
                    category="HIDDEN_ENTROPY",
                    source="set_iteration",
                    severity=severity,
                    is_controlled=False,
                    context="Iteration over set() found."
                ))
        self.generic_visit(node)

    def _get_call_name(self, node: ast.AST) -> Optional[str]:
        """
        Extract the full call name from an AST node.
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_call_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return None

    def _is_call_controlled(self, node: ast.Call) -> bool:
        """
        Check if a call is controlled by passing a seed or random_state.
        """
        for keyword in node.keywords:
            if keyword.arg in ["seed", "random_state", "seed_state"]:
                return True
        return False

    def _assign_severity(self, file_path: str) -> str:
        """
        Assign severity based on the code layer.
        """
        if any(mod in file_path for mod in ["alpha", "execution", "hft", "risk"]):
            return "HIGH"
        if any(mod in file_path for mod in ["backtest", "ml", "portfolio", "strategy"]):
            return "MEDIUM"
        return "LOW"

    def _get_module(self, file_path: str) -> str:
        """Extract the significant module name from the file path."""
        parts = file_path.split("/")
        if parts[0] == "qtrader" and len(parts) > 1:
            return parts[1]
        return parts[0]

    def report(self) -> dict[str, Any]:
        """
        Aggregate results and return summary.
        """
        uncontrolled = [s for s in self.sources if not s.is_controlled]
        total = len(self.sources)
        
        critical_modules = sorted(list(set(
            self._get_module(s.file_path) for s in self.sources if s.severity == "HIGH"
        )))
        
        return {
            "total_entropy_sources": total,
            "uncontrolled": len(uncontrolled),
            "controlled": total - len(uncontrolled),
            "critical_modules": critical_modules,
            "status": "NON_DETERMINISTIC" if uncontrolled else "DETERMINISTIC",
            "uncontrolled_entropy_ratio": round(len(uncontrolled) / total, 4) if total > 0 else 0.0
        }

    def export(self, output_dir: str) -> None:
        """
        Export findings to JSON and CSV formats.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # 1. Export summary (entropy_report.json)
        with open(os.path.join(output_dir, "entropy_report.json"), "w") as f:
            json.dump(self.report(), f, indent=2)

        # 2. Export mapping (entropy_locations.csv)
        with open(os.path.join(output_dir, "entropy_locations.csv"), "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["file", "line", "col", "category", "source", "severity", "is_controlled"])
            writer.writeheader()
            for s in self.sources:
                writer.writerow({
                    "file": s.file_path,
                    "line": s.line,
                    "col": s.col,
                    "category": s.category,
                    "source": s.source,
                    "severity": s.severity,
                    "is_controlled": s.is_controlled
                })

if __name__ == "__main__":
    # Internal CLI for executing the audit.
    import sys
    
    # Path setup: identify the repo root relative to this script.
    # Assumes project/qtrader/audit/entropy_scanner.py
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    scanner = EntropyScanner(ROOT)
    
    logger.info(f"Starting Deterministic Systems Audit across: {ROOT}")
    scanner.scan_directory(os.path.join(ROOT, "qtrader"))
    
    scanner.export(os.path.join(ROOT, "qtrader/audit"))
    logger.success(f"Audit Complete. Results written to qtrader/audit/")

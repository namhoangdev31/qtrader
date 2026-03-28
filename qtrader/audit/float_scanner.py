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
class FloatUsage:
    """
    Represents a detected floating-point literal or operation.
    """
    file_path: str
    line: int
    col: int
    usage_type: str  # literal, cast, bucket_op (+=, *=)
    value_or_op: str
    risk_level: str
    module: str


class FloatScanner(ast.NodeVisitor):
    """
    AST-based scanner for Identifying floating-point precision risks.
    """

    def __init__(self, root_path: str) -> None:
        self.root_path = Path(root_path)
        self.usages: list[FloatUsage] = []
        self.current_file: str = ""
        self.current_module: str = ""

    def scan_directory(self, directory: str) -> None:
        """Recursively scan a directory for Python files."""
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py"):
                    self.scan_file(os.path.join(root, file))

    def scan_file(self, file_path: str) -> None:
        """Scan a single Python file for numerical anti-patterns."""
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
        """Identify floating-point literals."""
        val = node.value
        if isinstance(val, float):
            # Ignore exact initializers common in code
            if val in (0.0, 1.0, -1.0):
                return
            
            self._record_usage(node, "literal", str(val))

    def visit_Call(self, node: ast.Call) -> None:
        """Identify float() casting."""
        if hasattr(node.func, "id") and node.func.id == "float":
            self._record_usage(node, "cast", "float()")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """Detect arithmetic instability points."""
        op_map = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
        op_str = op_map.get(type(node.op), "?")
        
        # Focus on addition and subtraction as they carry cumulative drift
        if isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
             # Heuristic: Check if either side is a literal float
             if isinstance(node.left, ast.Constant) and isinstance(node.left.value, float):
                  self._record_usage(node, "bin_op", op_str)
             elif isinstance(node.right, ast.Constant) and isinstance(node.right.value, float):
                  self._record_usage(node, "bin_op", op_str)

        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Identify cumulative drift triggers (+=, -=)."""
        op_map = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
        op_str = op_map.get(type(node.op), "?")
        
        if isinstance(node.value, (ast.Constant, ast.Name)): # Heuristic
             self._record_usage(node, "accumulation", f"{op_str}=")
        self.generic_visit(node)

    def _record_usage(self, node: ast.AST, usage_type: str, value_or_op: str) -> None:
        """Classify risk and record usage."""
        risk_level = self._assign_risk(self.current_file)
        
        self.usages.append(FloatUsage(
            file_path=self.current_file,
            line=node.lineno,
            col=node.col_offset,
            usage_type=usage_type,
            value_or_op=value_or_op,
            risk_level=risk_level,
            module=self.current_module
        ))

    def _assign_risk(self, file_path: str) -> str:
        """Higher risk for financial-path modules."""
        high_risk_paths = ["pnl", "oms", "risk", "execution", "fees", "nav"]
        if any(p in file_path for p in high_risk_paths):
            return "HIGH"
        
        # Alpha/Strategy involve weights which are often floats
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
        """Aggregate summary statistics."""
        high_risk = [u for u in self.usages if u.risk_level == "HIGH"]
        
        return {
            "float_usages": len(self.usages),
            "high_risk": len(high_risk),
            "modules": sorted(list(set(u.module for u in high_risk))),
            "status": "PRECISION_RISK" if len(high_risk) > 0 else "SAFE",
            "total_detections": len(self.usages)
        }

    def export(self, output_dir: str) -> None:
        """Export artifacts."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        with open(os.path.join(output_dir, "float_report.json"), "w") as f:
            json.dump(self.report(), f, indent=2)

        with open(os.path.join(output_dir, "precision_risk_map.csv"), "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["file", "line", "col", "usage_type", "value_or_op", "risk_level", "module"])
            writer.writeheader()
            for u in self.usages:
                writer.writerow({
                    "file": u.file_path,
                    "line": u.line,
                    "col": u.col,
                    "usage_type": u.usage_type,
                    "value_or_op": u.value_or_op,
                    "risk_level": u.risk_level,
                    "module": u.module
                })


if __name__ == "__main__":
    import sys
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    scanner = FloatScanner(ROOT)
    
    logger.info(f"Starting Numerical Integrity Audit (Float) across: {ROOT}")
    scanner.scan_directory(os.path.join(ROOT, "qtrader"))
    
    scanner.export(os.path.join(ROOT, "qtrader/audit"))
    logger.success(f"Numerical Audit Complete. Results written to qtrader/audit/float_report.json")

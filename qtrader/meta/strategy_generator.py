from __future__ import annotations

import random


class StrategyGenerator:
    """
    Symbolic Strategy Expression Generator.

    Orchestrates the automated discovery of new Alpha signals by
    systematically combining raw and engineered features through
    mathematical operators. This 'Meta-Quant' approach mimics human
    research to find hidden nonlinear alpha patterns.

    Conforms to the KILO.AI Industrial Grade Protocol for systematic
    research automation.
    """

    def __init__(
        self,
        features: list[str],
        unary_ops: list[str] | None = None,
        binary_ops: list[str] | None = None,
    ) -> None:
        """
        Initialize the generator with a feature set and operator pool.

        Args:
            features: List of available feature column names (e.g., ['close', 'volume_z']).
            unary_ops: Functions taking a single argument (e.g., log, sqrt, abs).
            binary_ops: Operators taking two arguments (e.g., +, -, *, /).
        """
        self.features = features
        self.unary_ops = unary_ops or ["log", "sqrt", "abs"]
        self.binary_ops = binary_ops or ["+", "-", "*", "/"]

    def generate_expression(self, depth: int = 2) -> str:
        """
        Recursively construct a symbolic mathematical expression.

        Args:
            depth: Current recursion depth. depth=0 returns a terminal (feature).

        Returns:
            A string-encoded mathematical expression (e.g., '(log(volume) * close)').
        """
        # Base case: return a feature name
        if depth <= 0 or not self.features:
            return random.choice(self.features) if self.features else "1.0"

        # Determine step: Unary op, Binary op, or Leaf
        # We weigh leaves and ops to ensure meaningful expressions
        choice = random.random()
        prob_leaf = 0.3
        prob_unary = 0.3

        if choice < prob_leaf:
            return random.choice(self.features)

        if choice < (prob_leaf + prob_unary) and self.unary_ops:
            op = random.choice(self.unary_ops)
            inner = self.generate_expression(depth - 1)
            return f"{op}({inner})"

        # Binary operator construction
        op = random.choice(self.binary_ops)
        left = self.generate_expression(depth - 1)
        right = self.generate_expression(depth - 1)
        return f"({left} {op} {right})"

    def batch_generate(self, count: int = 10, max_depth: int = 2) -> list[str]:
        """
        Produce a diverse set of unique candidate expressions.

        Args:
            count: Number of unique strategies to discover.
            max_depth: Complexity limit for each expression.

        Returns:
            List of unique symbolic strings.
        """
        candidates: set[str] = set()

        # Guard against infinite loops if feature set is tiny
        limit_iter = 1000
        iters = 0

        while len(candidates) < count and iters < limit_iter:
            expr = self.generate_expression(depth=random.randint(1, max_depth))
            candidates.add(expr)
            iters += 1

        return list(candidates)

    def evaluate_syntactic_validity(self, expression: str) -> bool:
        """
        Placeholder for checking if the expression is syntactically correct.
        (Advanced implementations would use AST parsing).
        """
        return "(" in expression or any(op in expression for op in self.binary_ops)

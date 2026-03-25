from __future__ import annotations

import datetime
from typing import Any

import polars as pl


class KnowledgeMemory:
    """
    Quant Research Knowledge Base & Pattern Memory.

    Acts as the persistent memory of the AI research system. Stores
    successfully discovery Alpha expressions and their performance history.
    Prevents 'reinventing the wheel' by deduplicating candidate strategies
    and providing a high-quality seed pool for future evolutionary cycles.

    Conforms to the KILO.AI Industrial Grade Protocol for systematic
    knowledge management.
    """

    def __init__(self) -> None:
        """Initialize the in-memory knowledge repository."""
        self._memory = pl.DataFrame(
            schema={
                "expression": pl.String,
                "sharpe": pl.Float64,
                "ic": pl.Float64,
                "discovery_time": pl.Datetime,
            }
        )

    def remember(self, expression: str, metrics: dict[str, float]) -> None:
        """
        Record a successful alpha pattern into the database.

        Args:
            expression: Symbolic string representation of the alpha.
            metrics: Performance metrics (sharpe, ic, etc.).
        """
        # 1. Deduplication Check (Exact string match)
        if expression in self._memory["expression"]:
            return

        # 2. Preparation of new entry
        new_row = pl.DataFrame(
            {
                "expression": [expression],
                "sharpe": [metrics.get("sharpe", 0.0)],
                "ic": [metrics.get("ic", 0.0)],
                "discovery_time": [datetime.datetime.now()],
            }
        )

        # 3. Persistence Update
        self._memory = pl.concat([self._memory, new_row])

    def fetch_top_patterns(self, count: int = 10) -> list[str]:
        """
        Retrieve the highest-performing learned patterns.

        Args:
            count: Number of seeds to return.

        Returns:
            List of symbolic expressions for seeding new populations.
        """
        if self._memory.is_empty():
            return []

        return self._memory.sort("sharpe", descending=True).head(count)["expression"].to_list()

    def is_known(self, expression: str) -> bool:
        """
        Check if an expression has already been evaluated.

        Args:
            expression: The candidate symbolic string.

        Returns:
            True if previously discovered.
        """
        if self._memory.is_empty():
            return False

        return expression in self._memory["expression"]

    def get_memory_stats(self) -> dict[str, Any]:
        """Return summary statistics of the knowledge base."""
        return {
            "total_patterns": len(self._memory),
            "avg_sharpe": self._memory["sharpe"].mean() if not self._memory.is_empty() else 0.0,
        }

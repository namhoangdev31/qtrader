import pytest

from qtrader.meta.memory import KnowledgeMemory

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

EXPR_1 = "log(close)"
METRICS_1 = {"sharpe": 1.5, "ic": 0.05}

EXPR_2 = "(open * volume)"
METRICS_2 = {"sharpe": 2.0, "ic": 0.08}


def test_knowledge_memory_storage_and_deduplication() -> None:
    """Verify that expressions are stored and duplicates are ignored."""
    memory = KnowledgeMemory()

    # 1. Store first pattern
    memory.remember(EXPR_1, METRICS_1)
    assert memory.is_known(EXPR_1) is True
    assert memory.get_memory_stats()["total_patterns"] == 1

    # 2. Store duplicate pattern (Should be ignored)
    memory.remember(EXPR_1, METRICS_1)
    assert memory.get_memory_stats()["total_patterns"] == 1


def test_knowledge_memory_retrieval_ranking() -> None:
    """Verify that top patterns are retrieved in descending order of performance."""
    memory = KnowledgeMemory()
    memory.remember(EXPR_1, METRICS_1)  # 1.5
    memory.remember(EXPR_2, METRICS_2)  # 2.0 (Best)

    # Retrieval count = 1
    top = memory.fetch_top_patterns(count=1)
    assert len(top) == 1
    # EXPR_2 (2.0) should be first
    assert top[0] == EXPR_2


def test_knowledge_memory_stats_logic() -> None:
    """Verify that average metrics are calculated correctly."""
    memory = KnowledgeMemory()
    memory.remember(EXPR_1, METRICS_1)
    memory.remember(EXPR_2, METRICS_2)

    stats = memory.get_memory_stats()
    # (1.5 + 2.0) / 2 = 1.75
    expected_avg = 1.75
    assert stats["avg_sharpe"] == pytest.approx(expected_avg)


def test_knowledge_memory_empty_robustness() -> None:
    """Ensure robustness to empty state."""
    memory = KnowledgeMemory()
    assert memory.is_known(EXPR_1) is False
    assert memory.fetch_top_patterns() == []
    assert memory.get_memory_stats()["total_patterns"] == 0

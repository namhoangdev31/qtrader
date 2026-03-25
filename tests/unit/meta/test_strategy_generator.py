import random

from qtrader.meta.strategy_generator import StrategyGenerator

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

FEATURE_POOL = ["open", "high", "low", "close", "volume", "momentum", "volatility"]


def test_strategy_generator_recursive_expression() -> None:
    """Verify that recursive expression generation produces strings containing features."""
    random.seed(42)  # Deterministic test
    generator = StrategyGenerator(FEATURE_POOL)

    # 1. Base case depth=0
    leaf = generator.generate_expression(depth=0)
    assert leaf in FEATURE_POOL

    # 2. Nested expression depth=2
    # Probability should eventually construct a non-trivial string
    expr = generator.generate_expression(depth=2)
    assert isinstance(expr, str)
    # Check if at least one feature is present or one operator
    assert any(f in expr for f in FEATURE_POOL)


def test_strategy_generator_batch_diversity() -> None:
    """Verify that batch generation produces unique candidate sets."""
    count = 5
    max_depth = 3
    generator = StrategyGenerator(FEATURE_POOL)

    candidates = generator.batch_generate(count=count, max_depth=max_depth)

    assert len(candidates) == count
    assert len(set(candidates)) == count  # Should be unique

    for expr in candidates:
        assert isinstance(expr, str)
        assert len(expr) > 0


def test_strategy_generator_custom_operators() -> None:
    """Verify that custom unary/binary operators are respected."""
    unary = ["ln"]
    binary = ["^"]
    generator = StrategyGenerator(FEATURE_POOL, unary_ops=unary, binary_ops=binary)

    # Force a non-leaf via depth if possible or trial
    # (Simplified: we check if they appear in search space)
    # We do simple search here
    found_ln = False
    found_pow = False

    for _ in range(50):
        expr = generator.generate_expression(depth=3)
        if "ln(" in expr:
            found_ln = True
        if "^" in expr:
            found_pow = True

    assert found_ln or found_pow


def test_strategy_generator_empty_protection() -> None:
    """Ensure behavior with null feature pool."""
    generator = StrategyGenerator(features=[])
    res = generator.generate_expression()
    # Should fallback to '1.0' as per implementation
    assert res == "1.0"

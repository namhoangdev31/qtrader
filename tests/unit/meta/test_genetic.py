import random

import polars as pl
import pytest

from qtrader.meta.genetic import GeneticEvolution
from qtrader.meta.strategy_generator import StrategyGenerator

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

FEATURE_POOL = ["open", "close", "volume"]
GENERATOR = StrategyGenerator(FEATURE_POOL)

# Config population for test
POPULATION = [
    {"config_id": 1, "expression": "log(close)"},
    {"config_id": 2, "expression": "(open * close)"},
    {"config_id": 3, "expression": "sqrt(volume)"},
]

# Results: Config 2 is best (1.5), 1 is good (1.2), 3 is worst (0.8)
METRICS = pl.DataFrame(
    {
        "config_id": [1, 2, 3],
        "sharpe": [1.0, 1.2, 0.5],
        "ic": [0.2, 0.3, 0.3],  # Config 2 fitness: 1.2+0.3=1.5
    }
)


def test_genetic_fitness_evaluation() -> None:
    """Verify that fitness (Sharpe + IC) ranks strategies correctly."""
    ga = GeneticEvolution(GENERATOR)
    ranked = ga.evaluate_fitness(METRICS, sharpe_weight=1.0, ic_weight=1.0)

    expected_len = 3
    best_id = 2
    second_best_id = 1
    assert len(ranked) == expected_len
    # Config 2 should be first (1.5)
    assert ranked["config_id"][0] == best_id
    # Config 1 should be second (1.2)
    assert ranked["config_id"][1] == second_best_id
    # Check absolute value of fitness for config 2
    val_2 = 1.5
    assert ranked["fitness"][0] == pytest.approx(val_2)


def test_genetic_crossover_operation() -> None:
    """Verify that crossover combines strings into non-empty hybrid expressions."""
    ga = GeneticEvolution(GENERATOR)
    p1 = "(a * b)"
    p2 = "(c + d)"

    child = ga.crossover(p1, p2)
    assert isinstance(child, str)
    assert len(child) > len(p1) or len(child) > len(p2)
    # Check it contains parts from parents or new structure
    assert any(x in child for x in ["(", ")", "a", "b", "c", "d"])


def test_genetic_mutation_diversity() -> None:
    """Verify that mutation perturbs the input string."""
    # Force mutation
    ga = GeneticEvolution(GENERATOR, mutation_rate=1.0)
    expr = "log(close)"

    # 1. Check if it changes
    for _ in range(50):
        mutated = ga.mutate(expr)
        if mutated != expr:
            break
    else:
        pytest.fail("Mutation did not perturb the expression in 50 trials")


def test_genetic_next_generation_elitism() -> None:
    """Verify that top performers (elitism) are present in the new generation."""
    # Pop size 3, Survival 0.34 (1 survivor)
    pop_size = 3
    survival = 0.34
    ga = GeneticEvolution(GENERATOR, population_size=pop_size, survival_rate=survival)

    ranked_fit = ga.evaluate_fitness(METRICS)
    next_gen = ga.produce_next_generation(POPULATION, ranked_fit)

    assert len(next_gen) == pop_size
    # Elite performer (Config 2 -> "(open * close)") should ideally be in next_gen
    # (Elitism rule in compute_next_gen says first num_survivors are survivors)
    best_expr = "(open * close)"
    assert best_expr in next_gen


def test_genetic_empty_protection() -> None:
    """Ensure behavior with null metrics and population."""
    ga = GeneticEvolution(GENERATOR)
    empty = pl.DataFrame()

    # Empty fitness evaluation
    res = ga.evaluate_fitness(empty)
    assert res.is_empty()

    # Next gen from empty should fallback to batch generate
    res_next = ga.produce_next_generation([], empty)
    assert len(res_next) == ga.pop_size


def test_genetic_crossover_fallback() -> None:
    """Verify crossover for very short strings (fallback branch)."""
    ga = GeneticEvolution(GENERATOR)
    p1 = "x"
    p2 = "y"
    child = ga.crossover(p1, p2)
    assert "x" in child and "y" in child


def test_genetic_mutation_branches() -> None:
    """Verify different mutation paths (branch replace, operator change)."""
    # 1. Operator replacement
    ga = GeneticEvolution(GENERATOR, mutation_rate=1.0)
    expr = "(a + b)"
    # We want to force it to hitting the operator replace branch
    # by making sure it doesn't hit branch mutation (chance 0.33)
    random.seed(42)
    found_op_change = False
    for _ in range(50):
        mutated = ga.mutate(expr)
        if "-" in mutated or "*" in mutated or "/" in mutated:
            found_op_change = True
            break
    assert found_op_change

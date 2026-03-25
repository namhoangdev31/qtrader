import polars as pl

from qtrader.meta.self_evolution import SelfEvolutionEngine

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

CONFIGS = [
    {"config_id": 1, "learning_rate": 0.01, "n_estimators": 100},
    {"config_id": 2, "learning_rate": 0.05, "n_estimators": 200},
    {"config_id": 3, "learning_rate": 0.1, "n_estimators": 300},
]

METRICS = pl.DataFrame(
    {
        "config_id": [1, 2, 3],
        "sharpe": [1.2, 1.5, 0.8],  # Config 2 is best (1.5)
        "ic": [0.02, 0.05, 0.01],
    }
)


def test_self_evolution_ranking_logic() -> None:
    """Verify that configurations are ranked correctly by objective metric."""
    engine = SelfEvolutionEngine()
    ranked = engine.evaluate_and_rank(METRICS, objective_col="sharpe")

    # Config 2 should be first
    expected_count = 3
    best_id = 2
    assert len(ranked) == expected_count
    assert ranked["config_id"][0] == best_id


def test_self_evolution_mutation_bounds() -> None:
    """Verify that mutation respects parameter bounds and types."""
    # High mutation rate to ensure it triggers
    max_rate = 1.0
    engine = SelfEvolutionEngine(mutation_rate=max_rate)

    val_init = 10.0
    low_bound = 5.0
    high_bound = 15.0

    config = {"val": val_init}
    bounds = {"val": (low_bound, high_bound)}

    # 1. Mutate many times and check bounds
    num_trials = 50
    for _ in range(num_trials):
        mutated = engine.mutate_config(config, param_bounds=bounds)
        assert mutated["val"] >= low_bound
        assert mutated["val"] <= high_bound
        assert isinstance(mutated["val"], float)


def test_self_evolution_next_generation() -> None:
    """Verify that the next generation contains survivors and children."""
    # Population size 5, Survival rate 0.2 (1 survivor)
    pop_size = 5
    survival = 0.2
    engine = SelfEvolutionEngine(population_size=pop_size, survival_rate=survival)

    ranked_m = engine.evaluate_and_rank(METRICS, objective_col="sharpe")

    next_gen = engine.evolve_next_generation(CONFIGS, ranked_m)

    # Next generation size should match population_size
    assert len(next_gen) == pop_size

    # Best performer from METRICS (Config 2) should be present (elitism)
    best_id = 2
    config_ids = [c["config_id"] for c in next_gen]
    assert best_id in config_ids
    # Should flag O1


def test_self_evolution_empty_robustness() -> None:
    """Ensure engine handles empty metrics without crashing."""
    engine = SelfEvolutionEngine()
    empty = pl.DataFrame()
    res = engine.evaluate_and_rank(empty)
    assert res.is_empty()

    # Next generation with no metrics should just return current
    res_next = engine.evolve_next_generation(CONFIGS, empty)
    assert len(res_next) == len(CONFIGS)

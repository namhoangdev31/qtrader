from __future__ import annotations

import random
from typing import Any

import polars as pl


class SelfEvolutionEngine:
    """
    Autonomous Self-Evolution Engine for Quantitative Systems.

    Utilizes evolutionary search algorithms to continuously optimize
    strategy hyper-parameters, risk weights, and model configurations.
    Learns from historical performance metrics (PnL, Sharpe, IC) to
    evolve superior parameter sets.

    Conforms to the KILO.AI Industrial Grade Protocol for systematic
    meta-optimization.
    """

    def __init__(
        self,
        population_size: int = 20,
        mutation_rate: float = 0.1,
        survival_rate: float = 0.2,
    ) -> None:
        """
        Initialize the evolution engine with core GA parameters.

        Args:
            population_size: Number of active candidate configurations.
            mutation_rate: Probability of perturbing a parameter (0 to 1).
            survival_rate: Fraction of the population that survives to reproduce.
        """
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.survival_rate = survival_rate

    def evaluate_and_rank(
        self,
        metrics_df: pl.DataFrame,
        objective_col: str = "sharpe",
    ) -> pl.DataFrame:
        """
        Rank configurations based on a multi-objective performance score.

        Args:
            metrics_df: DataFrame where each row is a model run's performance.
                Must contain 'config_id' and various performance columns.
            objective_col: The primary metric to maximize (e.g., Sharpe).

        Returns:
            Ranked DataFrame from best to worst.
        """
        if metrics_df.is_empty():
            return metrics_df

        # Rank descending (highest objective first)
        return metrics_df.sort(objective_col, descending=True)

    def mutate_config(
        self,
        config: dict[str, Any],
        param_bounds: dict[str, tuple[float, float]] | None = None,
    ) -> dict[str, Any]:
        """
        Induce random variation into a configuration set.

        Logic:
        - Float parameters: Random Gaussian perturbation.
        - Integer parameters: Random increment/decrement.

        Args:
            config: Original parameter dictionary.
            param_bounds: Optional (min, max) limits for parameters.

        Returns:
            Mutated configuration.
        """
        new_config = config.copy()

        for key, val in new_config.items():
            # Only mutate if probability hits
            if random.random() > self.mutation_rate:
                continue

            if isinstance(val, (float, int)):
                perturbation_factor = 0.1
                # Apply mutation
                if isinstance(val, float):
                    mutation = val * random.uniform(-perturbation_factor, perturbation_factor)
                    new_val = val + mutation
                else:
                    new_val = val + random.randint(-1, 1)

                # Apply bounds if provided
                if param_bounds and key in param_bounds:
                    low, high = param_bounds[key]
                    new_val = max(low, min(high, new_val))

                new_config[key] = new_val

        return new_config

    def evolve_next_generation(
        self,
        current_generation: list[dict[str, Any]],
        ranked_metrics: pl.DataFrame,
        param_bounds: dict[str, tuple[float, float]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Generate the next generation of configurations through Selection and Mutation.

        Args:
            current_generation: Current list of parameter dictionaries.
            ranked_metrics: Metrics for the current generation, sorted by performance.
            param_bounds: Parameter constraints.

        Returns:
            The next generation of configurations (population_size).
        """
        # 1. Selection (Elitism)
        if ranked_metrics.is_empty():
            return current_generation

        num_survivors = int(self.population_size * self.survival_rate)
        num_survivors = max(num_survivors, 1)

        # Extract top performing config IDs
        survivor_ids = ranked_metrics.head(num_survivors)["config_id"].to_list()

        # Mapping config_id to dict for quick lookup
        config_map = {str(c.get("config_id", "")): c for c in current_generation}
        survivors = [config_map[str(sid)] for sid in survivor_ids if str(sid) in config_map]

        if not survivors:
            return current_generation  # Fallback if no logs

        # 2. Reproduction via Mutation
        next_gen = survivors.copy()
        while len(next_gen) < self.population_size:
            parent = random.choice(survivors)
            child = self.mutate_config(parent, param_bounds=param_bounds)
            # Ensure unique config if possible (omitted for pure GA)
            next_gen.append(child)

        return next_gen

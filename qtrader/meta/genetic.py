from __future__ import annotations

import random
import re
from typing import Any

import polars as pl

from qtrader.meta.strategy_generator import StrategyGenerator


class GeneticEvolution:
    """
    Genetic Algorithm Engine for Symbolic Strategy Evolution.

    Iteratively improves a population of Alpha expressions through
    Selection, Crossover (recombination), and Mutation. Fitness is
    defined as a multi-objective score combining Information
    Coefficient (IC) and Signal Sharpe.

    Conforms to the KILO.AI Industrial Grade Protocol for systematic
    meta-optimization.
    """

    def __init__(
        self,
        generator: StrategyGenerator,
        population_size: int = 20,
        mutation_rate: float = 0.2,
        survival_rate: float = 0.2,
    ) -> None:
        """
        Initialize the GA engine.

        Args:
            generator: StrategyGenerator for creating new branches.
            population_size: Number of unique expressions in the population.
            mutation_rate: Probability of mutating an expression.
            survival_rate: Percentage of top performers allowed to reproduce.
        """
        self.generator = generator
        self.pop_size = population_size
        self.mutation_rate = mutation_rate
        self.survival_rate = survival_rate

    def evaluate_fitness(
        self,
        metrics_df: pl.DataFrame,
        sharpe_weight: float = 1.0,
        ic_weight: float = 1.0,
    ) -> pl.DataFrame:
        """
        Compute combined fitness score for each strategy.

        Mathematical Model:
        Fitness = (w1 * Sharpe) + (w2 * IC)

        Args:
            metrics_df: Results containing 'config_id', 'sharpe', and 'ic'.
            sharpe_weight: Multiplier for risk-adjusted return.
            ic_weight: Multiplier for predictive correlation.

        Returns:
            DataFrame ranked by total fitness.
        """
        if metrics_df.is_empty():
            return metrics_df

        return (
            metrics_df.with_columns(
                ((pl.col("sharpe") * sharpe_weight) + (pl.col("ic") * ic_weight)).alias("fitness")
            )
            .sort("fitness", descending=True)
            .select(["config_id", "fitness"])
        )

    def crossover(self, parent1: str, parent2: str) -> str:
        """
        Combine two parent expressions into a new child.

        Logic: Swap sub-expressions between parentheses.
        (Simplified: randomly split and recombine string components).
        """
        # Identify sub-expressions within parentheses
        parts1 = re.split(r"([()])", parent1)
        parts2 = re.split(r"([()])", parent2)

        # Heuristic: swap first nested part if exists
        # In a real GP system, this would be node-level swap in AST.
        # String-level crossover for this stage:
        min_parts = 3
        if len(parts1) > min_parts and len(parts2) > min_parts:
            # Recombine parts to create hybrid
            return f"({parts1[2]} {random.choice(self.generator.binary_ops)} {parts2[2]})"

        # Fallback: simple binary combination
        return f"({parent1} {random.choice(self.generator.binary_ops)} {parent2})"

    def mutate(self, expression: str) -> str:
        """
        Apply random mutation to a symbolic expression.

        Logic:
        1. Replace an operator.
        2. Replace a leaf (feature).
        3. Replace a sub-expression with a new random branch.
        """
        if random.random() > self.mutation_rate:
            return expression

        choice = random.random()
        branch_mutate_prob = 0.33
        # 1. New branch mutation (strongest)
        if choice < branch_mutate_prob:
            new_branch = self.generator.generate_expression(depth=1)
            # Find a part to replace or just wrap
            return f"({expression} * {new_branch})"

        # 2. Operator mutation
        for op in self.generator.binary_ops:
            if op in expression:
                new_op = random.choice(self.generator.binary_ops)
                return expression.replace(op, new_op, 1)

        # Fallback: full replacement if tiny
        return self.generator.generate_expression(depth=1)

    def produce_next_generation(
        self,
        population: list[dict[str, Any]],
        ranked_fitness: pl.DataFrame,
    ) -> list[str]:
        """
        Generate the next generation of Alpha candidates.

        Args:
            population: List of dicts with {'config_id': ID, 'expression': str}.
            ranked_fitness: Ranked scores from evaluate_fitness().

        Returns:
            List of new symbolic expressions.
        """
        if ranked_fitness.is_empty():
            return self.generator.batch_generate(self.pop_size)

        num_survivors = int(self.pop_size * self.survival_rate)
        num_survivors = max(num_survivors, 1)

        # Extract elite performers
        survivor_ids = ranked_fitness.head(num_survivors)["config_id"].to_list()

        pop_map = {str(p["config_id"]): p["expression"] for p in population}
        survivors = [pop_map[str(sid)] for sid in survivor_ids if str(sid) in pop_map]

        if not survivors:
            return self.generator.batch_generate(self.pop_size)

        # Reproduction Loop
        next_gen = survivors.copy()
        crossover_prob = 0.8

        while len(next_gen) < self.pop_size:
            choice = random.random()

            if choice < crossover_prob:  # 80% Crossover
                p1 = random.choice(survivors)
                p2 = random.choice(survivors)
                child = self.crossover(p1, p2)
            else:  # 20% Random immigration
                child = self.generator.generate_expression(depth=2)

            # Apply mutation to children
            child = self.mutate(child)
            next_gen.append(child)

        return next_gen

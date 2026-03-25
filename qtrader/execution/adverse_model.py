import math
from dataclasses import dataclass

import polars as pl


@dataclass
class AdverseModelParams:
    """Parameters for the adverse selection model."""

    alpha: float = 1.0  # Weight for imbalance
    beta: float = 1.0  # Weight for price movement (delta_p)
    gamma: float = 1.0  # Weight for fill rate
    intercept: float = 0.0


class AdverseSelectionModel:
    """
    Estimates probability of adverse selection using orderbook metrics.
    Adverse event: fill followed by price move against position.

    Model: P = sigmoid(alpha * imbalance + beta * delta_p + gamma * fill_rate + intercept)
    """

    def __init__(self, params: AdverseModelParams | None = None):
        """
        Initialize the model with parameters.
        """
        self.params = params or AdverseModelParams()

    @staticmethod
    def sigmoid(x: float) -> float:
        """Standard sigmoid function: 1 / (1 + exp(-x))."""
        try:
            return 1.0 / (1.0 + math.exp(-x))
        except OverflowError:
            return 0.0 if x < 0 else 1.0

    def estimate_probability(self, imbalance: float, delta_p: float, fill_rate: float) -> float:
        """
        Estimate P(adverse) for a single observation.

        Args:
            imbalance: Orderbook imbalance (-1 to 1)
            delta_p: Recent price movement
            fill_rate: Percentage of order filled

        Returns:
            Probability P in [0, 1]
        """
        score = (
            self.params.alpha * imbalance
            + self.params.beta * delta_p
            + self.params.gamma * fill_rate
            + self.params.intercept
        )
        return self.sigmoid(score)

    def estimate_batch(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Vectorized probability estimation for a batch of observations.

        Input df must contain: imbalance, delta_p, fill_rate.
        Adds 'p_adverse' column to the DataFrame.
        """
        # Linear score
        score_expr = (
            pl.lit(self.params.alpha) * pl.col("imbalance")
            + pl.lit(self.params.beta) * pl.col("delta_p")
            + pl.lit(self.params.gamma) * pl.col("fill_rate")
            + pl.lit(self.params.intercept)
        )

        # Sigmoid: 1 / (1 + exp(-score))
        return df.with_columns([(1.0 / (1.0 + (-score_expr).exp())).alias("p_adverse")])

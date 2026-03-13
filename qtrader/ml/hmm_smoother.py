
import numpy as np
import polars as pl


class HMMRegimeSmoother:
    """
    Implements a Hidden Markov Model-like smoothing layer for regimes.
    Uses a transition probability matrix to favor staying in the current state.
    """
    
    def __init__(self, n_regimes: int = 3, stay_prob: float = 0.9) -> None:
        self.n_regimes = n_regimes
        # Transition matrix: favors diagonal (staying in state)
        self.transition_matrix = np.full((n_regimes, n_regimes), (1 - stay_prob) / (n_regimes - 1))
        np.fill_diagonal(self.transition_matrix, stay_prob)
        
        self.current_state: Optional[int] = None

    def smooth_regime(self, raw_probs: np.ndarray) -> int:
        """
        Viterbi-lite approach: updates current state based on observation probs
        and transition priors.
        """
        if self.current_state is None:
            self.current_state = np.argmax(raw_probs)
            return self.current_state

        # Posterior = observation_prob * transition_from_last_state
        posterior = raw_probs * self.transition_matrix[self.current_state]
        self.current_state = int(np.argmax(posterior))
        
        return self.current_state

    def process_series(self, raw_probs: np.ndarray) -> pl.Series:
        """Processes a sequence of raw probability vectors into smooth regimes."""
        smoothed = []
        for probs in raw_probs:
            smoothed.append(self.smooth_regime(probs))
        return pl.Series("smooth_regime", smoothed)

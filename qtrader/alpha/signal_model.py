import numpy as np
import numpy.typing as npt
from sklearn.linear_model import LogisticRegression
from typing import Dict, Any, Optional

class ProbabilisticSignalModel:
    """
    Converts a feature matrix into probabilistic trading signals using Logistic Regression.
    
    Mathematical Model:
    - P(up|X) = sigmoid(X * beta)
    - Expectation: E[R|X] = P(up) * mu_up - (1 - P(up)) * mu_down
    """

    def __init__(self, random_seed: int = 42) -> None:
        """
        Args:
            random_seed: Seed for deterministic model training.
        """
        self.random_seed = random_seed
        self.model = LogisticRegression(random_state=random_seed)
        self.mu_up: float = 0.0
        self.mu_down: float = 0.0
        self._is_fitted: bool = False

    def fit(self, X: npt.NDArray[np.float64], y: npt.NDArray[np.float64], returns: npt.NDArray[np.float64]) -> None:
        """
        Train the logistic regression model and estimate mean returns.

        Args:
            X: Feature matrix (T x N).
            y: Binary labels (1 if return > 0 else 0).
            returns: Raw returns for mu estimation.
        """
        self.model.fit(X, y)
        
        # Estimate mean returns for up/down movements
        up_mask = returns > 0
        down_mask = returns <= 0
        
        self.mu_up = float(np.mean(returns[up_mask])) if np.any(up_mask) else 0.0
        self.mu_down = float(abs(np.mean(returns[down_mask]))) if np.any(down_mask) else 0.0
        
        self._is_fitted = True

    def predict_proba(self, X: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """
        Predict probabilities of upward movement.

        Args:
            X: Feature matrix (T x N).

        Returns:
            Probabilities in [0, 1].
        """
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before prediction.")
            
        # sklearn returns [P(y=0), P(y=1)], we want the latter
        return self.model.predict_proba(X)[:, 1].astype(np.float64)

    def compute_expected_return(self, X: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """
        Compute expected return E[R|X].

        Args:
            X: Feature matrix (T x N).

        Returns:
            Vector of expected returns.
        """
        p_up = self.predict_proba(X)
        return (p_up * self.mu_up - (1.0 - p_up) * self.mu_down).astype(np.float64)

    def get_signal(
        self, 
        X: npt.NDArray[np.float64], 
        theta_buy: float = 0.6, 
        theta_sell: float = 0.4
    ) -> npt.NDArray[np.int8]:
        """
        Generate trading signals based on probability thresholds.

        Args:
            X: Feature matrix.
            theta_buy: Buy threshold (P > theta_buy).
            theta_sell: Sell threshold (P < theta_sell).

        Returns:
            Signals: 1 (BUY), -1 (SELL), 0 (HOLD).
        """
        p_up = self.predict_proba(X)
        signals = np.zeros(len(p_up), dtype=np.int8)
        
        signals[p_up > theta_buy] = 1
        signals[p_up < theta_sell] = -1
        
        return signals

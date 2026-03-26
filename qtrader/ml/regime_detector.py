"""Online regime detection model for market state identification."""

from __future__ import annotations

import logging

import numpy as np
import polars as pl
from sklearn.mixture import GaussianMixture

from qtrader.core.event import RegimeChangeEvent
from qtrader.ml.base import Model

_LOG = logging.getLogger("qtrader.ml.regime_detector")


class RegimeDetector(Model):
    """
    Online regime detection model using Gaussian Mixture Model.
    
    This model identifies market regimes (e.g., bull, bear, volatile, quiet) 
    based on multiple market features and updates online as new data arrives.
    """
    
    def __init__(
        self,
        n_regimes: int = 3,
        features: list[str] | None = None,
        update_frequency: int = 20,
        min_samples: int = 50,
        random_state: int = 42
    ) -> None:
        """
        Initialize the regime detector.
        
        Args:
            n_regimes: Number of regimes to detect
            features: List of feature names to use for regime detection
            update_frequency: How often to retrain the model (in samples)
            min_samples: Minimum samples required before first training
            random_state: Random seed for reproducibility
        """
        self.n_regimes = n_regimes
        self.features = features or [
            'returns_5d', 'returns_20d', 'volatility_20d', 
            'volume_ratio', 'price_position_20d'
        ]
        self.update_frequency = update_frequency
        self.min_samples = min_samples
        self.random_state = random_state
        
        # Model state
        self._gmm: GaussianMixture | None = None
        self._is_fitted = False
        self._sample_count = 0
        self._last_regime: int | None = None
        self._regime_history: list[int] = []
        self._feature_means: dict[str, float] = {}
        self._feature_stds: dict[str, float] = {}
        
        # Regime characteristics (will be learned)
        self._regime_characteristics: dict[int, dict[str, float]] = {}
        
    def train(self, X: pl.DataFrame, y: pl.Series | None = None, params: dict | None = None) -> None:
        """
        Train the regime detection model.
        
        Args:
            X: Feature DataFrame for training
            y: Ignored (unsupervised learning)
            params: Additional training parameters
        """
        if X.is_empty() or len(X) < self.min_samples:
            _LOG.warning(f"Insufficient samples for regime detection: {len(X)} < {self.min_samples}")
            return
            
        # Select and prepare features
        feature_data = self._prepare_features(X)
        
        if feature_data.is_empty():
            _LOG.warning("No valid features for regime detection")
            return
            
        # Convert to numpy for sklearn
        X_np = feature_data.to_numpy()
        
        # Initialize and fit GMM
        self._gmm = GaussianMixture(
            n_components=self.n_regimes,
            random_state=self.random_state,
            covariance_type='diag'  # Faster and more stable for online learning
        )
        
        try:
            self._gmm.fit(X_np)
            self._is_fitted = True
            
            # Learn regime characteristics
            self._learn_regime_characteristics(feature_data)
            
            _LOG.info(f"Regime detector trained with {len(X)} samples, {self.n_regimes} regimes")
            
        except Exception as e:
            _LOG.error(f"Failed to train regime detector: {e}")
            self._is_fitted = False

    def predict(self, X: pl.DataFrame) -> pl.Series:
        """
        Predict regime for each sample.
        
        Args:
            X: Feature DataFrame for prediction
            
        Returns:
            Series of regime predictions (integers 0 to n_regimes-1)
        """
        if not self._is_fitted or self._gmm is None:
            # Return unknown regime (-1) if not trained
            return pl.Series([-1] * len(X), dtype=pl.Int64)
            
        # Select and prepare features
        feature_data = self._prepare_features(X)
        
        if feature_data.is_empty():
            return pl.Series([-1] * len(X), dtype=pl.Int64)
            
        # Convert to numpy for sklearn
        X_np = feature_data.to_numpy()
        
        try:
            # Predict regimes
            regime_predictions = self._gmm.predict(X_np)
            
            # Return as Polars series
            return pl.Series("regime", regime_predictions, dtype=pl.Int64)
            
        except Exception as e:
            _LOG.error(f"Failed to predict regimes: {e}")
            return pl.Series([-1] * len(X), dtype=pl.Int64)

    def predict_proba(self, X: pl.DataFrame) -> pl.DataFrame:
        """
        Predict regime probabilities for each sample.
        
        Args:
            X: Feature DataFrame for prediction
            
        Returns:
            DataFrame with regime probability columns
        """
        if not self._is_fitted or self._gmm is None:
            # Return uniform probabilities if not trained
            prob_data = {}
            for i in range(self.n_regimes):
                prob_data[f'regime_{i}_prob'] = [1.0 / self.n_regimes] * len(X)
            return pl.DataFrame(prob_data)
            
        # Select and prepare features
        feature_data = self._prepare_features(X)
        
        if feature_data.is_empty():
            prob_data = {}
            for i in range(self.n_regimes):
                prob_data[f'regime_{i}_prob'] = [0.0] * len(X)
            return pl.DataFrame(prob_data)
            
        # Convert to numpy for sklearn
        X_np = feature_data.to_numpy()
        
        try:
            # Predict probabilities
            regime_probabilities = self._gmm.predict_proba(X_np)
            
            # Convert to Polars DataFrame
            prob_data = {}
            for i in range(self.n_regimes):
                prob_data[f'regime_{i}_prob'] = regime_probabilities[:, i]
                
            return pl.DataFrame(prob_data)
            
        except Exception as e:
            _LOG.error(f"Failed to predict regime probabilities: {e}")
            prob_data = {}
            for i in range(self.n_regimes):
                prob_data[f'regime_{i}_prob'] = [0.0] * len(X)
            return pl.DataFrame(prob_data)

    def save(self, path: str) -> None:
        """Save the regime detector model."""
        # For simplicity, we'll save basic parameters
        # In production, you might want to pickle the full model
        import json
        import os
        
        model_data = {
            'n_regimes': self.n_regimes,
            'features': self.features,
            'update_frequency': self.update_frequency,
            'min_samples': self.min_samples,
            'random_state': self.random_state,
            'is_fitted': self._is_fitted,
            'sample_count': self._sample_count,
            'last_regime': self._last_regime,
            'regime_history': self._regime_history,
            'feature_means': self._feature_means,
            'feature_stds': self._feature_stds,
            'regime_characteristics': self._regime_characteristics
        }
        
        # Handle GMM parameters if fitted
        if self._is_fitted and self._gmm is not None:
            model_data['gmm_params'] = {
                'weights_': self._gmm.weights_.tolist(),
                'means_': self._gmm.means_.tolist(),
                'covariances_': self._gmm.covariances_.tolist(),
                'precisions_': self._gmm.precisions_.tolist(),
                'precisions_cholesky_': self._gmm.precisions_cholesky_.tolist()
            }
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(model_data, f, indent=2)
            
        _LOG.info(f"Regime detector saved to {path}")

    def load(self, path: str) -> None:
        """Load the regime detector model."""
        import json
        import os
        
        if not os.path.exists(path):
            _LOG.warning(f"Model file not found: {path}")
            return
            
        try:
            with open(path) as f:
                model_data = json.load(f)
                
            # Restore basic parameters
            self.n_regimes = model_data.get('n_regimes', self.n_regimes)
            self.features = model_data.get('features', self.features)
            self.update_frequency = model_data.get('update_frequency', self.update_frequency)
            self.min_samples = model_data.get('min_samples', self.min_samples)
            self.random_state = model_data.get('random_state', self.random_state)
            self._is_fitted = model_data.get('is_fitted', False)
            self._sample_count = model_data.get('sample_count', 0)
            self._last_regime = model_data.get('last_regime')
            self._regime_history = model_data.get('regime_history', [])
            self._feature_means = model_data.get('feature_means', {})
            self._feature_stds = model_data.get('feature_stds', {})
            self._regime_characteristics = model_data.get('regime_characteristics', {})
            
            # Restore GMM if fitted
            if self._is_fitted and 'gmm_params' in model_data:
                params = model_data['gmm_params']
                self._gmm = GaussianMixture(
                    n_components=self.n_regimes,
                    random_state=self.random_state,
                    covariance_type='diag'
                )
                self._gmm.weights_ = np.array(params['weights_'])
                self._gmm.means_ = np.array(params['means_'])
                self._gmm.covariances_ = np.array(params['covariances_'])
                self._gmm.precisions_ = np.array(params['precisions_'])
                self._gmm.precisions_cholesky_ = np.array(params['precisions_cholesky_'])
                
            _LOG.info(f"Regime detector loaded from {path}")
            
        except Exception as e:
            _LOG.error(f"Failed to load regime detector: {e}")
            self._is_fitted = False

    def _prepare_features(self, X: pl.DataFrame) -> pl.DataFrame:
        """Prepare and normalize features for regime detection."""
        if X.is_empty():
            return X
            
        # Select only the features we need
        available_features = [f for f in self.features if f in X.columns]
        if not available_features:
            _LOG.warning(f"None of the required features {self.features} found in data")
            return pl.DataFrame()
            
        feature_data = X.select(available_features)
        
        # Handle missing values
        feature_data = feature_data.fill_null(0.0)
        
        # Update running statistics for normalization
        for feature in available_features:
            if feature not in self._feature_means:
                self._feature_means[feature] = 0.0
                self._feature_stds[feature] = 1.0
                
            # Simple running average/update (in production, use proper windowing)
            current_mean = float(feature_data[feature].mean())
            current_std = float(feature_data[feature].std())
            
            if not (current_std == 0.0 or np.isnan(current_std)):
                # Update running statistics with exponential moving average
                alpha = 0.1  # Smoothing factor
                self._feature_means[feature] = (
                    alpha * current_mean + (1 - alpha) * self._feature_means[feature]
                )
                self._feature_stds[feature] = max(
                    alpha * current_std + (1 - alpha) * self._feature_stds[feature],
                    1e-8  # Prevent division by zero
                )
        
        # Normalize features
        normalized_data = {}
        for feature in available_features:
            mean = self._feature_means[feature]
            std = self._feature_stds[feature]
            if std > 0:
                normalized_data[feature] = (feature_data[feature] - mean) / std
            else:
                normalized_data[feature] = pl.Series([0.0] * len(feature_data))
                
        return pl.DataFrame(normalized_data) if normalized_data else pl.DataFrame()

    def _learn_regime_characteristics(self, feature_data: pl.DataFrame) -> None:
        """Learn characteristics of each regime from training data."""
        if not self._is_fitted or self._gmm is None:
            return
            
        # Get regime assignments for training data
        X_np = feature_data.to_numpy()
        regime_assignments = self._gmm.predict(X_np)
        
        # Calculate characteristics for each regime
        for regime_id in range(self.n_regimes):
            # Get samples belonging to this regime
            regime_mask = regime_assignments == regime_id
            if not np.any(regime_mask):
                continue
                
            regime_data = feature_data.filter(pl.Series(regime_mask))
            
            # Calculate mean and std for each feature in this regime
            characteristics = {}
            for feature in feature_data.columns:
                feature_vals = regime_data[feature].to_list()
                if feature_vals:
                    characteristics[f'{feature}_mean'] = np.mean(feature_vals)
                    characteristics[f'{feature}_std'] = np.std(feature_vals)
                else:
                    characteristics[f'{feature}_mean'] = 0.0
                    characteristics[f'{feature}_std'] = 0.0
                    
            self._regime_characteristics[regime_id] = characteristics

    def get_regime_characteristics(self, regime_id: int) -> dict[str, float]:
        """Get learned characteristics for a specific regime."""
        return self._regime_characteristics.get(regime_id, {})

    def get_current_regime(self) -> int | None:
        """Get the most recently detected regime."""
        return self._last_regime

    def get_regime_history(self) -> list[int]:
        """Get history of regime assignments."""
        return self._regime_history.copy()

    def is_fitted(self) -> bool:
        """Check if the model has been trained."""
        return self._is_fitted

    def partial_update(self, X: pl.DataFrame) -> RegimeChangeEvent | None:
        """
        Partially update the model with new data and detect regime changes.
        
        Args:
            X: New feature data
            
        Returns:
            RegimeChangeEvent if regime changed, None otherwise
        """
        if X.is_empty():
            return None
            
        # Predict regimes for new data
        new_regimes = self.predict(X)
        
        if len(new_regimes) == 0:
            return None
            
        # Get the most recent regime prediction
        latest_regime = int(new_regimes[-1])
        
        # Update sample count
        self._sample_count += len(X)
        
        # Check if we should retrain
        if self._sample_count % self.update_frequency == 0 and self._sample_count >= self.min_samples:
            # Retrain with recent data
            self.train(X)
        
        # Detect regime change
        regime_changed = (
            self._last_regime is not None and 
            latest_regime != self._last_regime and
            latest_regime >= 0  # Valid regime
        )
        
        if regime_changed:
            # Create regime change event
            confidence = self._get_regime_confidence(X.tail(1))
            event = RegimeChangeEvent(
                regime_id=latest_regime,
                confidence=confidence,
                previous_regime_id=self._last_regime
            )
            
            # Update history
            self._last_regime = latest_regime
            self._regime_history.append(latest_regime)
            
            _LOG.info(f"Regime change detected: {self._last_regime} -> {latest_regime} (confidence: {confidence:.3f})")
            return event
        # Update history even if no change
        elif latest_regime >= 0:
            self._regime_history.append(latest_regime)
            self._last_regime = latest_regime
                
        return None

    def _get_regime_confidence(self, X: pl.DataFrame) -> float:
        """Get confidence score for the most recent regime prediction."""
        if not self._is_fitted or self._gmm is None or X.is_empty():
            return 0.5
            
        try:
            # Get probabilities for the latest sample
            feature_data = self._prepare_features(X)
            if feature_data.is_empty():
                return 0.5
                
            X_np = feature_data.to_numpy()
            probabilities = self._gmm.predict_proba(X_np)
            
            # Get the predicted regime
            regime_prediction = self._gmm.predict(X_np)[0]
            
            # Return confidence (probability of predicted regime)
            return float(probabilities[0, int(regime_prediction)])
            
        except Exception as e:
            _LOG.debug(f"Failed to get regime confidence: {e}")
            return 0.5


# Factory function
def create_regime_detector(n_regimes: int = 3) -> RegimeDetector:
    """
    Factory function to create a RegimeDetector with default settings.
    
    Args:
        n_regimes: Number of regimes to detect
        
    Returns:
        Configured RegimeDetector instance
    """
    return RegimeDetector(n_regimes=n_regimes)
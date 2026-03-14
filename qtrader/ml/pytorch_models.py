
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

__all__ = ["LSTMSignalModel"]


class _LSTMHead(nn.Module):
    """Internal LSTM + linear head."""

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        num_layers: int,
        output_size: int,
        dropout: float,
    ) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
        out, _ = self.lstm(x)
        out = out[:, -1, :]
        out = self.fc(out)
        return out


@dataclass(slots=True)
class LSTMSignalModel:
    """LSTM-based sequence model for binary direction signals.

    Designed for sequences of factor values and short-horizon direction labels.

    Args:
        input_size: Number of input features per time step.
        hidden_size: LSTM hidden dimension.
        num_layers: Number of stacked LSTM layers.
        output_size: Output dimension (1 for binary probability).
        dropout: Dropout probability between LSTM layers.
        device: ``\"cpu\"``, ``\"mps\"``, or ``\"cuda\"``.

    Examples:
        >>> import numpy as np
        >>> X = np.random.randn(32, 10, 4).astype("float32")
        >>> y = (np.random.rand(32) > 0.5).astype("float32")
        >>> model = LSTMSignalModel(input_size=4)
        >>> _ = model.fit(X, y, epochs=1, batch_size=8)
        >>> proba = model.predict_proba(X[:4])
        >>> proba.shape == (4,)
        True
    """

    input_size: int
    hidden_size: int = 64
    num_layers: int = 2
    output_size: int = 1
    dropout: float = 0.2
    device: str = "cpu"
    _model: nn.Module = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._model = _LSTMHead(
            input_size=self.input_size,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            output_size=self.output_size,
            dropout=self.dropout,
        ).to(self.device)

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 50,
        batch_size: int = 64,
        lr: float = 1e-3,
    ) -> Dict[str, List[float]]:
        """Fit the LSTM on sequence data.

        Args:
            X: Input array of shape (samples, seq_len, input_size).
            y: Binary labels of shape (samples,), 1=up, 0=down.
            epochs: Number of training epochs.
            batch_size: Mini-batch size.
            lr: Learning rate for Adam optimizer.

        Returns:
            Dict with ``train_loss`` and ``val_loss`` histories.
        """
        if X.ndim != 3:
            raise ValueError("X must have shape (samples, seq_len, input_size).")
        if X.shape[0] != y.shape[0]:
            raise ValueError("X and y must have the same number of samples.")

        n_samples = X.shape[0]
        n_train = int(n_samples * 0.8)
        X_train, X_val = X[:n_train], X[n_train:]
        y_train, y_val = y[:n_train], y[n_train:]

        x_train_t = torch.from_numpy(X_train.astype("float32"))
        y_train_t = torch.from_numpy(y_train.astype("float32")).unsqueeze(1)
        x_val_t = torch.from_numpy(X_val.astype("float32"))
        y_val_t = torch.from_numpy(y_val.astype("float32")).unsqueeze(1)

        train_loader = DataLoader(
            TensorDataset(x_train_t, y_train_t),
            batch_size=batch_size,
            shuffle=True,
        )
        val_loader = DataLoader(
            TensorDataset(x_val_t, y_val_t),
            batch_size=batch_size,
            shuffle=False,
        )

        optimizer = torch.optim.Adam(self._model.parameters(), lr=lr)
        criterion = nn.BCEWithLogitsLoss()

        history: Dict[str, List[float]] = {"train_loss": [], "val_loss": []}

        for _ in range(epochs):
            self._model.train()
            train_losses: list[float] = []
            for xb, yb in train_loader:
                xb = xb.to(self.device)
                yb = yb.to(self.device)
                optimizer.zero_grad()
                logits = self._model(xb)
                loss = criterion(logits, yb)
                loss.backward()
                optimizer.step()
                train_losses.append(float(loss.detach().cpu().item()))

            self._model.eval()
            val_losses: list[float] = []
            with torch.no_grad():
                for xb, yb in val_loader:
                    xb = xb.to(self.device)
                    yb = yb.to(self.device)
                    logits = self._model(xb)
                    loss = criterion(logits, yb)
                    val_losses.append(float(loss.detach().cpu().item()))

            history["train_loss"].append(float(np.mean(train_losses)) if train_losses else 0.0)
            history["val_loss"].append(float(np.mean(val_losses)) if val_losses else 0.0)

        return history

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict probability of upward move for each sample.

        Args:
            X: Input array of shape (samples, seq_len, input_size).

        Returns:
            Array of shape (samples,) with probabilities in [0, 1].
        """
        if X.ndim != 3:
            raise ValueError("X must have shape (samples, seq_len, input_size).")
        x_t = torch.from_numpy(X.astype("float32")).to(self.device)
        self._model.eval()
        with torch.no_grad():
            logits = self._model(x_t)
            proba = torch.sigmoid(logits).squeeze(1).cpu().numpy()
        return proba

    def to_signal(self, proba: np.ndarray, threshold: float = 0.55) -> np.ndarray:
        """Convert probabilities into {-1, 0, 1} trading signals.

        Args:
            proba: Probabilities of shape (samples,).
            threshold: Confidence threshold for entering positions.

        Returns:
            Integer NumPy array of signals.
        """
        if proba.ndim != 1:
            raise ValueError("proba must be a 1D array.")

        long_mask = proba > threshold
        short_mask = proba < (1.0 - threshold)
        signals = np.zeros_like(proba, dtype=int)
        signals[long_mask] = 1
        signals[short_mask] = -1
        return signals


if __name__ == "__main__":
    _X = np.random.randn(16, 5, 3).astype("float32")
    _y = (np.random.rand(16) > 0.5).astype("float32")
    _model = LSTMSignalModel(input_size=3, hidden_size=8, num_layers=1, device="cpu")
    _ = _model.fit(_X, _y, epochs=1, batch_size=4)
    _proba = _model.predict_proba(_X[:4])
    _sig = _model.to_signal(_proba, threshold=0.6)
    assert _sig.shape == (4,)


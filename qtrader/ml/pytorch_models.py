import torch
import torch.nn as nn
import polars as pl
from typing import Dict, Any, Optional

class BasePyTorchModel(nn.Module):
    """Base wrapper for Deep Learning models using PyTorch."""
    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int) -> None:
        super().__init__()
        self.input_dim = input_dim
        # Example: Simple LSTM
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        # Take last time step
        out = self.fc(out[:, -1, :])
        return out

class PyTorchPredictor:
    """Predictor wrapper for PyTorch models."""
    def __init__(self, model: nn.Module, device: str = "cpu") -> None:
        self.model = model.to(device)
        self.device = device

    def train_step(self, X: torch.Tensor, y: torch.Tensor, optimizer: torch.optim.Optimizer, criterion: nn.Module) -> float:
        self.model.train()
        X, y = X.to(self.device), y.to(self.device)
        optimizer.zero_grad()
        outputs = self.model(X)
        loss = criterion(outputs, y)
        loss.backward()
        optimizer.step()
        return loss.item()

    def predict(self, X: torch.Tensor) -> torch.Tensor:
        self.model.eval()
        with torch.no_grad():
            return self.model(X.to(self.device))

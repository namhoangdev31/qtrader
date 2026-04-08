from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from typing import Dict

@dataclass
class SessionState:
    """Encapsulates the runtime state of a trading session.
    
    This improves memory localization and allows the TradingSystem to be 
    more modular by passing this state to specialized logic engines.
    """
    session_id: str | None = None
    consecutive_losses: int = 0
    peak_equity: float = 1000.0
    
    # Symbol-specific state
    last_signal_direction: dict[str, str] = field(default_factory=dict)
    signal_streak: dict[str, int] = field(default_factory=dict)
    loss_cooldown: dict[str, int] = field(default_factory=dict)
    position_opened_at: dict[str, float] = field(default_factory=dict)
    confidence_ema: dict[str, float] = field(default_factory=dict)
    last_exit_at: dict[str, float] = field(default_factory=dict)
    
    # Performance tracking
    win_history: deque[int] = field(default_factory=lambda: deque(maxlen=50))
    
    def reset_streak(self, symbol: str) -> None:
        self.signal_streak[symbol] = 0
        self.last_signal_direction.pop(symbol, None)

    def record_loss(self, symbol: str, cooldown_ticks: int = 0) -> None:
        self.consecutive_losses += 1
        self.loss_cooldown[symbol] = cooldown_ticks
        self.win_history.append(0)

    def record_win(self, symbol: str) -> None:
        self.consecutive_losses = 0
        self.win_history.append(1)

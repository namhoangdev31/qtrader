from typing import Any
import pytest
from qtrader.core.config import settings
from qtrader.execution.paper_engine import PaperTradingEngine
from qtrader.execution.paper_mixins import SignalMixin
from qtrader.execution.paper_models import AdaptiveConfig


def test_paper_engine_init():
    engine = PaperTradingEngine()
    assert engine._base_price == settings.ts_reference_price
    assert engine._current_price == settings.ts_reference_price
    assert len(engine._price_history) == 0


def test_paper_engine_base_price_override():
    custom_price = 123456.78
    engine = PaperTradingEngine(base_price=custom_price)
    assert engine._base_price == custom_price
    assert engine._current_price == custom_price


def test_clear_history():
    engine = PaperTradingEngine()
    engine._price_history = [100.0, 101.0, 102.0]
    engine._tick_count = 3
    engine.clear_history()
    assert len(engine._price_history) == 0
    assert engine._tick_count == 0


def test_rsi_clamping():

    class DummyEngine(SignalMixin):
        def __init__(self) -> None:
            self._price_history = [100.0] * 20
            self.RSI_PERIOD = 14
            self.SMA_SHORT_WINDOW = 5
            self.SMA_LONG_WINDOW = 10
            self.MIN_HISTORY_FOR_ANALYSIS = 10
            self.EXTERNAL_TICK_TIMEOUT = 2.0
            self._last_external_tick = 0
            self._current_price = 100.0
            self.CROSSOVER_THRESHOLD = 0.0001
            self.RSI_BULL_GATE = 45.0
            self.RSI_BEAR_GATE = 55.0
            self.RSI_OVERSOLD = 30.0
            self.RSI_OVERBOUGHT = 70.0
            self._last_thinking = ""
            self._last_explanation = ""
            self._last_trace = {"module_traces": {}, "alpha": {}}
            self._thinking_history = []
            self.THINKING_HISTORY_LIMIT = 10
            self._running = True
            self.ANOMALY_THRESHOLD = 0.01
            self.adaptive = AdaptiveConfig()
            self._cash = 1000.0
            self._open_positions = {}
            self.MEAN_REVERSION_STRENGTH = 0.01

        def _persist_thinking_log(self, **kwargs: Any) -> None:
            pass

        def _persist_fill(self, **kwargs: Any) -> None:
            pass

    dummy = DummyEngine()
    _ = dummy._generate_signal()
    assert dummy._last_trace["alpha"]["indicators"]["rsi"] == 50.0
    dummy._price_history = [100.0 + i for i in range(20)]
    dummy._generate_signal()
    assert dummy._last_trace["alpha"]["indicators"]["rsi"] > 90.0
    assert dummy._last_trace["alpha"]["indicators"]["rsi"] <= 100.0

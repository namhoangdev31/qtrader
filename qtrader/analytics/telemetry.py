import logging
import time
from typing import Any


class Telemetry:
    def __init__(self) -> None:
        self.metrics: dict[str, Any] = {}

    def record_latency(self, component: str, start_time: float) -> None:
        latency = (time.time() - start_time) * 1000
        logging.debug(f"METRIC | {component} Latency: {latency:.2f}ms")

    def record_slippage(self, order_id: str, slippage_bps: float) -> None:
        logging.info(f"METRIC | Order {order_id} Slippage: {slippage_bps:.1f} bps")

    def record_pnl(self, strategy_id: str, pnl: float) -> None:
        logging.info(f"METRIC | Strategy {strategy_id} PnL: {pnl:.4f}")

    def export(self) -> dict[str, Any]:
        return self.metrics

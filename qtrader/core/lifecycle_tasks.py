from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Any, List

from qtrader.core.dynamic_config import config_manager
from qtrader.core.config import settings
from qtrader.ml.embedding_worker import embedding_manager
from qtrader.persistence.db_writer import TradeDBWriter

logger = logging.getLogger("qtrader.core.lifecycle")

class LifecycleTaskManager:
    """Manages periodic background tasks for the trading system.
    
    This includes telemetry snapshots, market sentiment refreshes, 
    and system health monitoring.
    """

    def __init__(self, broker: Any, db_writer: TradeDBWriter, symbols: list[str]) -> None:
        self.broker = broker
        self.db_writer = db_writer
        self.symbols = symbols
        self.is_running = False

    async def sentiment_refresh_loop(self, simulate: bool) -> None:
        """Periodically refresh the global market sentiment embedding."""
        logger.info("[LIFECYCLE] Sentiment Refresh loop active")
        while self.is_running:
            try:
                interval = config_manager.get("lifecycle_sentiment_interval")
                symbol = self.symbols[0] if self.symbols else "BTC-USD"
                quote = self.broker._quotes.get(symbol, {})
                price = float(quote.get("price") or 0.0)
                
                narrative = (
                    f"Market context for {symbol} at {datetime.now().isoformat()}. "
                    f"Current price is {price:.2f}. "
                    f"Volatility multiplier: {config_manager.get('VOLATILITY_MULTIPLIER', 1.0):.2f}x. "
                    f"Simulate mode: {simulate}."
                )
                embedding_manager.refresh_sentiment(narrative)
            except Exception as e:
                logger.error(f"[LIFECYCLE] Sentiment refresh failed: {e}")
                interval = 600 # Fallback
            await asyncio.sleep(interval)

    async def pnl_recording_loop(self, session_id: str) -> None:
        """Periodically record PnL snapshots to the database."""
        while self.is_running:
            try:
                interval = config_manager.get("lifecycle_pnl_interval")
                if session_id:
                    balance = await self.broker.get_paper_balance()
                    await self.db_writer.write_pnl_snapshot(
                        total_equity=Decimal(str(balance.get("equity", 0))),
                        cash=Decimal(str(balance.get("cash", 0))),
                        realized_pnl=Decimal(str(balance.get("realized_pnl", 0))),
                        unrealized_pnl=Decimal(str(balance.get("unrealized_pnl", 0))),
                        total_commission=Decimal(str(balance.get("total_commissions", 0))),
                        session_id=session_id,
                    )
            except Exception as e:
                logger.error(f"[LIFECYCLE] PnL snapshot failed: {e}")
                interval = 5 # Fallback
            await asyncio.sleep(interval)

    async def health_logging_loop(self, session_id: str, last_latency_provider: Any) -> None:
        """Periodically record system health metrics (CPU, MEM, Latency)."""
        import psutil
        process = psutil.Process(os.getpid())
        while self.is_running:
            try:
                interval = config_manager.get("lifecycle_health_interval")
                if session_id:
                    cpu_pct = process.cpu_percent()
                    mem_pct = process.memory_percent()
                    latency = getattr(last_latency_provider, "last_latency_ms", 0.0)
                    
                    await self.db_writer.write_system_health(
                        session_id=session_id,
                        cpu_pct=cpu_pct,
                        mem_pct=mem_pct,
                        latency_ms=int(latency),
                        status="RUNNING"
                    )
            except Exception as e:
                logger.error(f"[LIFECYCLE] Health logging failed: {e}")
                interval = 10 # Fallback
            await asyncio.sleep(interval)

import logging
import os
import time

import psutil

from qtrader.core.dynamic_config import config_manager
from qtrader.core.events import EventType, SystemEvent
from qtrader.ml.embedding_worker import embedding_manager
from qtrader.persistence.db_writer import TradeDBWriter

logger = logging.getLogger("qtrader.core.lifecycle")


class LifecycleTaskManager:
    def __init__(
        self,
        broker: Any,
        db_writer: TradeDBWriter,
        symbols: list[str],
        event_bus: Any | None = None,
    ) -> None:
        self.broker = broker
        self.db_writer = db_writer
        self.symbols = symbols
        self.event_bus = event_bus
        self.is_running = False
        self._last_sentiment_refresh = 0.0
        self._last_pnl_record = 0.0
        self._last_health_log = 0.0
        self._active_session_id: str | None = None
        self._last_latency_provider: Any = None

    def start(self, session_id: str | None = None, last_latency_provider: Any = None) -> None:
        self._active_session_id = session_id
        self._last_latency_provider = last_latency_provider
        if self.event_bus:
            self.event_bus.subscribe(EventType.SYSTEM, self._on_system_event)
        self.is_running = True

    async def _on_system_event(self, event: Any) -> None:
        if not self.is_running:
            return

        if isinstance(event, SystemEvent) and event.payload.action == "HEARTBEAT":
            now = time.time()
            sentiment_interval = config_manager.get("lifecycle_sentiment_interval", 600)
            if now - self._last_sentiment_refresh >= sentiment_interval:
                await self._do_sentiment_refresh()
                self._last_sentiment_refresh = now
            pnl_interval = config_manager.get("lifecycle_pnl_interval", 5)
            if now - self._last_pnl_record >= pnl_interval:
                if self._active_session_id:
                    await self._do_pnl_record(self._active_session_id)
                self._last_pnl_record = now
            health_interval = config_manager.get("lifecycle_health_interval", 10)
            if now - self._last_health_log >= health_interval:
                if self._active_session_id:
                    await self._do_health_log(self._active_session_id)
                self._last_health_log = now

    async def _do_sentiment_refresh(self) -> None:
        try:
            symbol = self.symbols[0] if self.symbols else "BTC-USD"
            quote = self.broker._quotes.get(symbol, {})
            price = float(quote.get("price") or 0.0)
            narrative = f"Market context for {symbol} at {datetime.now().isoformat()}. Current price is {price:.2f}. Volatility multiplier: {config_manager.get('VOLATILITY_MULTIPLIER', 1.0):.2f}x. "
            embedding_manager.refresh_sentiment(narrative)
        except Exception as e:
            logger.error(f"[LIFECYCLE] Sentiment refresh failed: {e}")

    async def _do_pnl_record(self, session_id: str) -> None:
        try:
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

    async def _do_health_log(self, session_id: str) -> None:
        process = psutil.Process(os.getpid())
        try:
            cpu_pct = process.cpu_percent()
            mem_pct = process.memory_percent()
            latency = (
                getattr(self._last_latency_provider, "last_latency_ms", 0.0)
                if self._last_latency_provider
                else 0.0
            )
            await self.db_writer.write_system_health(
                session_id=session_id,
                cpu_pct=cpu_pct,
                mem_pct=mem_pct,
                latency_ms=int(latency),
                status="RUNNING",
            )
        except Exception as e:
            logger.error(f"[LIFECYCLE] Health logging failed: {e}")

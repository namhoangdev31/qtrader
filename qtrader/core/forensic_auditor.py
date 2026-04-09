from __future__ import annotations
import logging
from typing import Any
from qtrader.core.events import (
    ErrorEvent,
    EventType,
    FillEvent,
    ForensicNoteEvent,
    ForensicNotePayload,
    OrderEvent,
    PipelineErrorEvent,
    RiskRejectedEvent,
    SignalEvent,
    StrategyKillEvent,
    SystemEvent,
)
from qtrader.persistence.db_writer import TradeDBWriter

logger = logging.getLogger("qtrader.core.forensic")


class ForensicAuditor:
    def __init__(
        self, event_bus: Any, db_writer: TradeDBWriter, session_id: str | None = None
    ) -> None:
        self.event_bus = event_bus
        self.db_writer = db_writer
        self.session_id = session_id
        self._is_active = False

    def start(self) -> None:
        if self._is_active:
            return
        self.event_bus.subscribe(EventType.SIGNAL, self._on_signal)
        self.event_bus.subscribe(EventType.ORDER, self._on_order)
        self.event_bus.subscribe(EventType.FILL, self._on_fill)
        self.event_bus.subscribe(EventType.TRADING_HALT, self._on_halt)
        self.event_bus.subscribe(EventType.RISK_REJECTED, self._on_risk_rejection)
        self.event_bus.subscribe(EventType.STRATEGY_KILL, self._on_strategy_kill)
        self.event_bus.subscribe(EventType.PIPELINE_ERROR, self._on_system_error)
        self.event_bus.subscribe(EventType.ERROR, self._on_system_error)
        self.event_bus.subscribe(EventType.SYSTEM, self._on_system_event)
        self._is_active = True
        logger.info("[AUDITOR] Autonomous Forensic Oversight INITIALIZED")

    def stop(self) -> None:
        if not self._is_active:
            return
        self.event_bus.unsubscribe(EventType.SIGNAL, self._on_signal)
        self.event_bus.unsubscribe(EventType.ORDER, self._on_order)
        self.event_bus.unsubscribe(EventType.FILL, self._on_fill)
        self.event_bus.unsubscribe(EventType.TRADING_HALT, self._on_halt)
        self.event_bus.unsubscribe(EventType.RISK_REJECTED, self._on_risk_rejection)
        self.event_bus.unsubscribe(EventType.STRATEGY_KILL, self._on_strategy_kill)
        self.event_bus.unsubscribe(EventType.PIPELINE_ERROR, self._on_system_error)
        self.event_bus.unsubscribe(EventType.ERROR, self._on_system_error)
        self.event_bus.unsubscribe(EventType.SYSTEM, self._on_system_event)
        self._is_active = False
        logger.info("[AUDITOR] Autonomous Forensic Oversight SHUTDOWN")

    async def _on_signal(self, event: SignalEvent) -> None:
        action = event.payload.signal_type
        strength = float(event.payload.strength)
        confidence = float(event.payload.confidence)
        symbol = event.payload.symbol
        metadata = event.payload.metadata or {}
        thinking = metadata.get("thinking", "")
        explanation = metadata.get("explanation", "")
        model_id = metadata.get("model_id", "Unknown-Model")
        content = f"[ALPHA] {model_id} generated {action} signal for {symbol}. Confidence: {confidence:.0%}. Strength: {strength:.2f}. Reasoning: {explanation or thinking or 'N/A'}"
        await self._write_note(content, "OBSERVATION")

    async def _on_order(self, event: OrderEvent) -> None:
        side = event.payload.action
        qty = event.payload.quantity
        symbol = event.payload.symbol
        order_type = event.payload.order_type
        content = f"[ORDER] Routing {order_type} {side} for {qty} {symbol} to execution engine."
        await self._write_note(content, "OBSERVATION")

    async def _on_fill(self, event: FillEvent) -> None:
        symbol = event.payload.symbol
        side = event.payload.side
        qty = event.payload.quantity
        price = event.payload.price
        commission = event.payload.commission
        content = f"[FILL] Execution Successful: {symbol} {side} {qty} filled at {price:.2f}. Commission: ${commission:.2f}."
        await self._write_note(content, "TRIAL")

    async def _on_risk_rejection(self, event: RiskRejectedEvent) -> None:
        reason = event.payload.reason
        metric = event.payload.metric_value
        threshold = event.payload.threshold
        order_id = event.payload.order_id
        content = f"[RISK] Order {order_id} REJECTED. Reason: {reason}. Value: {metric:.4f} exceeds Threshold: {threshold:.4f}."
        await self._write_note(content, "ALERT")

    async def _on_strategy_kill(self, event: StrategyKillEvent) -> None:
        strategy_id = event.payload.strategy_id
        reason = event.payload.reason
        metric = event.payload.metric
        threshold = event.payload.threshold
        content = f"[CRITICAL] Strategy '{strategy_id}' KILLED. Trigger: {metric} ({reason}). Threshold: {threshold}."
        await self._write_note(content, "ALERT")

    async def _on_halt(self, event: SystemEvent) -> None:
        reason = event.payload.reason
        content = f"[CRITICAL] TRADING HALTED: {reason}. Systematic safety shutdown engaged."
        await self._write_note(content, "ALERT")

    async def _on_system_error(self, event: PipelineErrorEvent | ErrorEvent) -> None:
        source = getattr(event.payload, "module_name", event.source)
        message = getattr(
            event.payload, "details", getattr(event.payload, "message", "Unknown error")
        )
        content = f"[ERROR] Failure in {source}: {message}"
        await self._write_note(content, "ALERT")

    async def _on_system_event(self, event: SystemEvent) -> None:
        action = event.payload.action
        reason = event.payload.reason
        metadata = event.payload.metadata or {}
        if action == "ORDER_REJECTED":
            order_id = metadata.get("order_id", "Unknown")
            content = f"[OMS] Order {order_id} REJECTED by exchange. Reason: {reason}"
            await self._write_note(content, "ALERT")
        elif action == "ORDER_CREATED":
            pass
        elif action == "ORDER_FILLED":
            pass
        else:
            content = f"[SYSTEM] Action: {action}. Reason: {reason}"
            await self._write_note(content, "OBSERVATION")

    async def _write_note(self, content: str, note_type: str) -> None:
        try:
            await self.db_writer.write_forensic_note(
                content=content, note_type=note_type, session_id=self.session_id
            )
            note_event = ForensicNoteEvent(
                source="ForensicAuditor",
                payload=ForensicNotePayload(
                    content=content, note_type=note_type, session_id=self.session_id
                ),
            )
            await self.event_bus.publish(note_event)
        except Exception as e:
            logger.error(f"[AUDITOR] Failed to write forensic note: {e}")

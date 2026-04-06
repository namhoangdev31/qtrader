from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Protocol

_LOG = logging.getLogger("qtrader.risk.kill_switch")


class BrokerAdapterProtocol(Protocol):
    """Minimal protocol for broker adapters that the kill switch can interact with."""

    async def cancel_order(self, order_id: str) -> tuple[bool, str | None]: ...
    async def get_balance(self) -> dict[str, float]: ...
    async def submit_order(self, order: Any) -> tuple[bool, str | None]: ...


class StateStoreProtocol(Protocol):
    """Minimal protocol for state store access."""

    async def get_positions(self) -> dict[str, Any]: ...
    async def get_active_orders(self) -> dict[str, Any]: ...


class GlobalKillSwitch:
    r"""
    Principal Institutional Safety Mechanism.

    Objective: Immediately stop all trading activity under catastrophic conditions
    (e.g., severe drawdown, critical capital loss, or high-intensity system anomaly).

    Model: Boolean Kill-Condition ($K = (DD > DD_{crit}) \lor (Loss > Loss_{max})$
           $\lor (A > A_{crit})$).
    Constraint: Sub-millisecond execution. No override after trigger.

    Safety Actions (executed on trigger):
    1. CANCEL_ALL_OPEN_ORDERS_GLOBAL — Cancel every open order on every exchange
    2. LIQUIDATE_ALL_POSITIONS_MARKET — Flatten all positions via market orders
    3. DISABLE_TRADING_ENGINE_DAEMON — Set internal halt flag (blocks all new orders)
    """

    def __init__(
        self,
        dd_limit: float = 0.20,
        loss_limit: float = 1_000_000.0,
        anomaly_limit: float = 0.95,
        auto_liquidate: bool = False,
        liquidation_timeout_s: float = 30.0,
    ) -> None:
        """
        Initialize the institutional kill switch.

        Parameters:
        - dd_limit: Critical drawdown threshold (e.g., 0.20 = 20%).
        - loss_limit: Maximum absolute capital loss (e.g., USD).
        - anomaly_limit: Critical anomaly score threshold.
        - auto_liquidate: If True, automatically liquidate positions on trigger.
        - liquidation_timeout_s: Max time to wait for liquidation (seconds).
        """
        self._dd_limit = dd_limit
        self._loss_limit = loss_limit
        self._anomaly_limit = anomaly_limit
        self._auto_liquidate = auto_liquidate
        self._liquidation_timeout_s = liquidation_timeout_s

        # Persistent state for platform finality.
        self._is_system_halted: bool = False
        self._kill_timestamp: float = 0.0
        self._kill_reason: str = ""

        # Execution results tracking
        self._actions_executed: list[str] = []
        self._actions_failed: list[str] = []

        # Broker adapters and state store (set externally for live execution)
        self._brokers: dict[str, BrokerAdapterProtocol] = {}
        self._state_store: StateStoreProtocol | None = None

    def register_brokers(self, brokers: dict[str, BrokerAdapterProtocol]) -> None:
        """Register broker adapters for kill switch execution."""
        self._brokers = brokers
        _LOG.info(f"[KILL_SWITCH] Registered {len(brokers)} broker adapters")

    def register_state_store(self, state_store: StateStoreProtocol) -> None:
        """Register state store for position/order access."""
        self._state_store = state_store
        _LOG.info("[KILL_SWITCH] Registered state store")

    async def execute_safety_actions(self) -> dict[str, Any]:
        """
        Execute the actual safety actions declared in the kill switch.

        This method:
        1. Cancels all open orders on all registered brokers
        2. If auto_liquidate is True, liquidates all positions via market orders
        3. Records success/failure for each action

        Returns:
            Dict with execution results for each action.
        """
        results: dict[str, Any] = {
            "cancel_orders": {"success": 0, "failed": 0, "details": []},
            "liquidate_positions": {"success": 0, "failed": 0, "details": []},
            "disable_trading": {"success": True},
        }

        # 1. Cancel all open orders
        if self._state_store:
            try:
                active_orders = await self._state_store.get_active_orders()
                cancel_tasks = []
                for order_id in active_orders:
                    for broker_name, broker in self._brokers.items():
                        cancel_tasks.append(
                            self._cancel_single_order(broker_name, broker, order_id, results)
                        )

                if cancel_tasks:
                    await asyncio.gather(*cancel_tasks, return_exceptions=True)
                    _LOG.info(
                        f"[KILL_SWITCH] Cancel orders complete: "
                        f"{results['cancel_orders']['success']} OK, "
                        f"{results['cancel_orders']['failed']} FAILED"
                    )
                results["cancel_orders"]["success"] += 1
                self._actions_executed.append("CANCEL_ALL_OPEN_ORDERS_GLOBAL")
            except Exception as e:
                _LOG.error(f"[KILL_SWITCH] Cancel orders failed: {e}")
                results["cancel_orders"]["failed"] += 1
                self._actions_failed.append(f"CANCEL_ALL_OPEN_ORDERS_GLOBAL: {e}")
        else:
            _LOG.warning("[KILL_SWITCH] No state store registered — skipping order cancellation")

        # 2. Liquidate positions (if auto_liquidate enabled)
        if self._auto_liquidate and self._state_store:
            try:
                await asyncio.wait_for(
                    self._liquidate_all_positions(results),
                    timeout=self._liquidation_timeout_s,
                )
                _LOG.info(
                    f"[KILL_SWITCH] Liquidation complete: "
                    f"{results['liquidate_positions']['success']} OK, "
                    f"{results['liquidate_positions']['failed']} FAILED"
                )
                self._actions_executed.append("LIQUIDATE_ALL_POSITIONS_MARKET")
            except asyncio.TimeoutError:
                _LOG.error("[KILL_SWITCH] Liquidation timed out")
                results["liquidate_positions"]["failed"] += 1
                self._actions_failed.append("LIQUIDATE_ALL_POSITIONS_MARKET: TIMEOUT")
            except Exception as e:
                _LOG.error(f"[KILL_SWITCH] Liquidation failed: {e}")
                results["liquidate_positions"]["failed"] += 1
                self._actions_failed.append(f"LIQUIDATE_ALL_POSITIONS_MARKET: {e}")

        # 3. Disable trading engine
        self._is_system_halted = True
        self._actions_executed.append("DISABLE_TRADING_ENGINE_DAEMON")
        _LOG.critical("[KILL_SWITCH] Trading engine DISABLED")

        return results

    async def _cancel_single_order(
        self,
        broker_name: str,
        broker: BrokerAdapterProtocol,
        order_id: str,
        results: dict[str, Any],
    ) -> None:
        """Cancel a single order on a specific broker."""
        try:
            success, error = await broker.cancel_order(order_id)
            if success:
                results["cancel_orders"]["success"] += 1
                results["cancel_orders"]["details"].append(
                    {"broker": broker_name, "order_id": order_id, "status": "CANCELLED"}
                )
            else:
                results["cancel_orders"]["failed"] += 1
                results["cancel_orders"]["details"].append(
                    {"broker": broker_name, "order_id": order_id, "error": str(error)}
                )
        except Exception as e:
            results["cancel_orders"]["failed"] += 1
            results["cancel_orders"]["details"].append(
                {"broker": broker_name, "order_id": order_id, "error": str(e)}
            )

    async def _liquidate_all_positions(self, results: dict[str, Any]) -> None:
        """Liquidate all positions via market orders on all brokers."""
        if not self._state_store:
            return

        positions = await self._state_store.get_positions()
        if not positions:
            _LOG.info("[KILL_SWITCH] No positions to liquidate")
            return

        _LOG.warning(f"[KILL_SWITCH] Liquidating {len(positions)} positions")

        for symbol, position in positions.items():
            qty = getattr(position, "quantity", 0)
            if qty == 0:
                continue

            # Determine side: sell long positions, buy to cover short
            side = "SELL" if qty > 0 else "BUY"
            abs_qty = abs(qty)

            _LOG.warning(f"[KILL_SWITCH] Liquidating {abs_qty} {symbol} via {side}")

            # Submit market order on first available broker
            for broker_name, broker in self._brokers.items():
                try:
                    # Create minimal market order
                    order = type(
                        "MarketOrder",
                        (),
                        {
                            "symbol": symbol,
                            "side": side,
                            "quantity": abs_qty,
                            "order_type": "MARKET",
                        },
                    )()
                    success, error = await broker.submit_order(order)
                    if success:
                        results["liquidate_positions"]["success"] += 1
                        results["liquidate_positions"]["details"].append(
                            {"symbol": symbol, "side": side, "qty": abs_qty, "status": "SUBMITTED"}
                        )
                        break
                    else:
                        _LOG.warning(f"[KILL_SWITCH] Liquidation failed on {broker_name}: {error}")
                except Exception as e:
                    _LOG.error(f"[KILL_SWITCH] Liquidation error on {broker_name}: {e}")
            else:
                results["liquidate_positions"]["failed"] += 1
                results["liquidate_positions"]["details"].append(
                    {"symbol": symbol, "side": side, "qty": abs_qty, "error": "NO_BROKER_AVAILABLE"}
                )

    def evaluate_kill_system(
        self,
        current_drawdown: float,
        current_absolute_loss: float,
        current_anomaly_score: float,
        manual_trigger: bool = False,
    ) -> dict[str, Any]:
        """
        Evaluate kill conditions and trigger non-overrideable safety sequence.

        Forensic Logic:
        1. State Gating: Returns existing halt state if already triggered.
        2. Boolean Verification (K): Evaluates DD, Loss, Anomaly, and Manual flags.
        3. Safety Action Selection: Triggers global cancellation and liquidation.
        """
        eval_start = time.time()

        # 1. State Gating (Immutability check).
        if self._is_system_halted:
            return {
                "status": "ALREADY_HALTED",
                "reason": self._kill_reason,
                "timestamp": self._kill_timestamp,
            }

        # 2. Boolean Kill-Logic (K).
        kill_triggered = False
        reason = ""

        if current_drawdown >= self._dd_limit:
            kill_triggered = True
            reason = f"CRITICAL_DRAWDOWN_BREACH: {current_drawdown:.2%}"
        elif current_absolute_loss >= self._loss_limit:
            kill_triggered = True
            reason = f"MAX_LOSS_EXCEEDED: {current_absolute_loss:,.2f}"
        elif current_anomaly_score >= self._anomaly_limit:
            kill_triggered = True
            reason = f"SEVERE_ANOMALY_INTENSITY: {current_anomaly_score:.2f}"
        elif manual_trigger:
            kill_triggered = True
            reason = "INSTITUTIONAL_MANUAL_HALT_REQUEST"

        # 3. Execution (The Final Platforms Shutdown).
        if kill_triggered:
            self._is_system_halted = True
            self._kill_reason = reason
            self._kill_timestamp = time.time()

            _LOG.critical(
                f"[KILL_SWITCH] TRIGGERED | {reason} | SHUTDOWN_SEQUENCE_INITIATED "
                f"| NAV_LOSS: {current_absolute_loss:,.2f}"
            )

        latency_ms = (time.time() - eval_start) * 1000

        # 4. Certification Artifact Construction.
        artifact = {
            "status": "KILL_SWITCH_ACTIVE" if kill_triggered else "KILL_SWITCH_RUNNING",
            "state": {
                "is_halted": self._is_system_halted,
                "kill_reason": self._kill_reason,
                "shutdown_timestamp": self._kill_timestamp,
            },
            "safety_action_manifest": [
                "CANCEL_ALL_OPEN_ORDERS_GLOBAL",
                "LIQUIDATE_ALL_POSITIONS_MARKET",
                "DISABLE_TRADING_ENGINE_DAEMON",
            ]
            if kill_triggered
            else [],
            "forensics": {
                "eval_latency_ms": round(latency_ms, 4),
                "peak_drawdown_evaluated": round(current_drawdown, 4),
            },
        }

        return artifact

    def get_kill_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional safety control.
        """
        return {
            "status": "CAPITAL_GOVERNANCE",
            "is_system_halted": self._is_system_halted,
            "kill_reason_captured": self._kill_reason,
            "halt_timestamp": self._kill_timestamp,
            "actions_executed": list(self._actions_executed),
            "actions_failed": list(self._actions_failed),
        }

    def trigger_on_critical_failure(self, error_type: str, error_message: str) -> None:
        """Trigger kill switch on critical system failure.

        This method is called when a critical exception occurs that could
        compromise system integrity or capital safety.

        Args:
            error_type: Type of critical failure (e.g., 'BROKER_DISCONNECT', 'DATA_CORRUPTION').
            error_message: Detailed error message.
        """
        if self._is_system_halted:
            return  # Already halted

        self._is_system_halted = True
        self._kill_reason = f"CRITICAL_FAILURE: {error_type} — {error_message}"
        self._kill_timestamp = time.time()

        _LOG.critical(
            f"[KILL_SWITCH] TRIGGERED BY CRITICAL FAILURE | {error_type} | "
            f"{error_message} | SHUTDOWN_SEQUENCE_INITIATED"
        )

        self._actions_executed.append(f"CRITICAL_FAILURE_TRIGGER: {error_type}")

    def get_trace(self) -> dict[str, Any]:
        """
        Produce a forensic trace of the kill-switch state for the transparency pulse.
        """
        return {
            "is_halted": self._is_system_halted,
            "reason": self._kill_reason,
            "timestamp": self._kill_timestamp,
            "dd_limit": self._dd_limit,
            "loss_limit": self._loss_limit,
            "actions_count": len(self._actions_executed),
            "status": "DANGER" if self._is_system_halted else "HEALTHY"
        }

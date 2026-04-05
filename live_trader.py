#!/usr/bin/env python3
"""Live Trading Entry Point — QTrader Production Mode.

This is the production entry point for live trading with real broker adapters.
Supports:
- Binance (Spot) with WebSocket user data stream
- Coinbase Advanced Trade with WebSocket user data stream
- Multi-exchange orchestration
- Pre-trade risk validation
- Kill switch with actual order cancellation
- Real-time reconciliation
- External alerting (Slack/PagerDuty)

Usage:
    python live_trader.py --exchange binance --testnet
    python live_trader.py --exchange coinbase --symbols BTC-USD,ETH-USD
    python live_trader.py --exchange binance,coinbase --alert-slack <webhook_url>
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from decimal import Decimal
from typing import Any

from loguru import logger

# Configure logging
logger.remove()
logger.add(
    sys.stderr, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}"
)
logger.add("logs/live_trader.log", level="DEBUG", rotation="1 day", retention="30 days")

log = logger.bind(module="live_trader")


async def run_live_trader(args: argparse.Namespace) -> None:
    """Main live trading loop."""
    log.info("=" * 60)
    log.info("QTRADER LIVE TRADING ENGINE — STARTING")
    log.info("=" * 60)

    exchanges = [e.strip() for e in args.exchange.split(",")]
    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else ["BTC-USDT"]

    # ========================================================================
    # 1. Initialize Broker Adapters
    # ========================================================================
    brokers: dict[str, Any] = {}

    for exchange in exchanges:
        if exchange.lower() == "binance":
            from qtrader.execution.brokers.binance import BinanceBrokerAdapter

            broker = BinanceBrokerAdapter(
                api_key=args.binance_api_key,
                api_secret=args.binance_api_secret,
                testnet=args.testnet,
            )
            brokers["binance"] = broker
            log.info(f"[BROKER] Binance adapter initialized (testnet={args.testnet})")

        elif exchange.lower() == "coinbase":
            from qtrader.execution.brokers.coinbase import CoinbaseBrokerAdapter

            broker = CoinbaseBrokerAdapter(
                api_key=args.coinbase_api_key,
                api_secret=args.coinbase_api_secret,
                simulate=False,  # Live mode
            )
            brokers["coinbase"] = broker
            log.info("[BROKER] Coinbase adapter initialized (live mode)")

        else:
            log.warning(f"[BROKER] Unknown exchange: {exchange}")

    if not brokers:
        log.error("[BROKER] No valid brokers configured — exiting")
        return

    # ========================================================================
    # 2. Initialize Risk & Safety Systems
    # ========================================================================
    from qtrader.risk.kill_switch import GlobalKillSwitch
    from qtrader.execution.pre_trade_risk import PreTradeRiskValidator, PreTradeRiskConfig
    from qtrader.core.state_store import StateStore

    kill_switch = GlobalKillSwitch(
        dd_limit=args.max_drawdown,
        loss_limit=args.max_loss,
        auto_liquidate=args.auto_liquidate,
    )

    pre_trade_risk = PreTradeRiskValidator(
        PreTradeRiskConfig(
            max_order_quantity=Decimal(str(args.max_order_qty)),
            max_order_notional=Decimal(str(args.max_order_notional)),
            max_position_per_symbol=Decimal(str(args.max_position)),
            max_orders_per_second=args.max_orders_per_second,
        )
    )

    state_store = StateStore()

    # Register brokers with kill switch for emergency actions
    kill_switch.register_brokers(brokers)
    kill_switch.register_state_store(state_store)

    log.info("[RISK] Kill switch initialized with broker execution capability")
    log.info("[RISK] Pre-trade risk validator initialized")

    # ========================================================================
    # 3. Initialize Alerting
    # ========================================================================
    from qtrader.monitoring.alert_engine import AlertEngine

    alert_engine = AlertEngine(
        slack_webhook_url=args.alert_slack,
        pagerduty_routing_key=args.alert_pagerduty,
    )
    log.info(
        f"[ALERT] Alert engine initialized (slack={bool(args.alert_slack)}, pagerduty={bool(args.alert_pagerduty)})"
    )

    # ========================================================================
    # 4. Start WebSocket Streams for Real-Time Updates
    # ========================================================================
    for name, broker in brokers.items():
        if hasattr(broker, "start_websocket"):
            if hasattr(broker, "add_product"):
                for symbol in symbols:
                    broker.add_product(symbol)

            # Set order update handler
            def on_order_update(data: dict, broker_name: str = name) -> None:
                log.info(f"[WS:{broker_name}] Order update: {data}")

            broker.set_order_update_handler(on_order_update)

            try:
                if hasattr(broker, "start_user_data_stream"):
                    await broker.start_user_data_stream()
                await broker.start_websocket()
                log.info(f"[WS:{name}] WebSocket stream started")
            except Exception as e:
                log.warning(f"[WS:{name}] WebSocket failed (continuing with REST polling): {e}")

    # ========================================================================
    # 5. Start Reconciliation Engine
    # ========================================================================
    from qtrader.execution.reconciliation_engine import ReconciliationEngine
    from qtrader.core.event_bus import EventBus

    event_bus = EventBus()

    # Create a minimal OMS wrapper for reconciliation
    class MinimalOMS:
        def __init__(self, brokers: dict) -> None:
            self.adapters = brokers

    oms = MinimalOMS(brokers)

    recon_engine = ReconciliationEngine(
        event_bus=event_bus,
        oms=oms,
        state_store=state_store,
        recon_interval_s=60.0,  # 1 minute periodic reconciliation
    )
    await recon_engine.start()
    log.info("[RECON] Reconciliation engine started (60s interval)")

    # ========================================================================
    # 6. Run Main Loop
    # ========================================================================
    log.info("=" * 60)
    log.info("LIVE TRADING ENGINE — RUNNING")
    log.info(f"Exchanges: {list(brokers.keys())}")
    log.info(f"Symbols: {symbols}")
    log.info(f"Testnet: {args.testnet}")
    log.info("=" * 60)

    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        log.warning("Shutdown signal received — initiating graceful shutdown")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                pass

    # Main trading loop
    heartbeat_interval = 10.0
    while not shutdown_event.is_set():
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=heartbeat_interval)
        except asyncio.TimeoutError:
            # Heartbeat — check kill switch, run periodic tasks
            if kill_switch.get_kill_telemetry()["is_system_halted"]:
                log.error("[KILL_SWITCH] System halted — stopping all activity")
                break

            # Update pre-trade risk with kill switch status
            pre_trade_risk.set_kill_switch_active(
                kill_switch.get_kill_telemetry()["is_system_halted"]
            )

            log.debug("[HEARTBEAT] System healthy")

    # ========================================================================
    # 7. Graceful Shutdown
    # ========================================================================
    log.info("=" * 60)
    log.info("LIVE TRADING ENGINE — SHUTTING DOWN")
    log.info("=" * 60)

    # Stop reconciliation
    await recon_engine.stop()

    # Stop WebSocket streams
    for name, broker in brokers.items():
        if hasattr(broker, "stop_websocket"):
            await broker.stop_websocket()
        if hasattr(broker, "close"):
            await broker.close()

    log.info("[SHUTDOWN] All connections closed")
    log.info(f"[SHUTDOWN] Final state: {kill_switch.get_kill_telemetry()}")
    log.info(f"[SHUTDOWN] Pre-trade risk: {pre_trade_risk.get_telemetry()}")
    log.info("[SHUTDOWN] Goodbye")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments with environment variable defaults."""
    import os

    parser = argparse.ArgumentParser(description="QTrader Live Trading Engine")

    # Exchange configuration
    parser.add_argument(
        "--exchange",
        type=str,
        default=os.getenv("QTRADER_EXCHANGE", "coinbase"),
        help="Comma-separated list of exchanges (binance,coinbase)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=os.getenv("QTRADER_SYMBOLS", "BTC-USD"),
        help="Comma-separated list of trading symbols",
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        default=True,  # Forced Paper Trading
        help="Use testnet/sandbox mode (ALWAYS TRUE for Paper Trading)",
    )

    # API keys
    parser.add_argument(
        "--binance-api-key", type=str, default=os.getenv("BINANCE_API_KEY")
    )
    parser.add_argument(
        "--binance-api-secret", type=str, default=os.getenv("BINANCE_API_SECRET")
    )
    parser.add_argument(
        "--coinbase-api-key", type=str, default=os.getenv("COINBASE_API_KEY")
    )
    parser.add_argument(
        "--coinbase-api-secret", type=str, default=os.getenv("COINBASE_API_SECRET")
    )

    # Risk limits
    parser.add_argument(
        "--max-drawdown",
        type=float,
        default=float(os.getenv("MAX_DRAWDOWN", "0.20")),
        help="Maximum drawdown before kill switch (default: 0.20)",
    )
    parser.add_argument(
        "--max-loss",
        type=float,
        default=float(os.getenv("MAX_LOSS", "1000000")),
        help="Maximum absolute loss before kill switch (default: 1000000)",
    )
    parser.add_argument(
        "--auto-liquidate",
        action="store_true",
        default=os.getenv("AUTO_LIQUIDATE", "false").lower() == "true",
        help="Automatically liquidate positions on kill switch trigger",
    )
    parser.add_argument(
        "--max-order-qty",
        type=float,
        default=float(os.getenv("MAX_ORDER_QTY", "1000")),
        help="Maximum order quantity",
    )
    parser.add_argument(
        "--max-order-notional",
        type=float,
        default=float(os.getenv("MAX_ORDER_NOTIONAL", "1000000")),
        help="Maximum order notional value (USD)",
    )
    parser.add_argument(
        "--max-position",
        type=float,
        default=float(os.getenv("MAX_POSITION", "100")),
        help="Maximum position per symbol",
    )
    parser.add_argument(
        "--max-orders-per-second",
        type=float,
        default=float(os.getenv("MAX_OPS", "10")),
        help="Maximum order submission rate per second",
    )

    # Alerting
    parser.add_argument(
        "--alert-slack",
        type=str,
        default=os.getenv("ALERT_SLACK_WEBHOOK"),
        help="Slack webhook URL for alerts",
    )
    parser.add_argument(
        "--alert-pagerduty",
        type=str,
        default=os.getenv("ALERT_PAGERDUTY_KEY"),
        help="PagerDuty routing key for alerts",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(run_live_trader(args))
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        log.exception(f"Fatal error: {e}")
        sys.exit(1)

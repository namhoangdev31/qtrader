#!/usr/bin/env python3
"""Live Trading Entry Point — QTrader Production Mode (Autonomous).

Thiết lập hệ thống giao dịch tự động hoàn chỉnh, kết nối với ML Engine từ xa.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from typing import Any

from loguru import logger

from qtrader.trading_system import create_trading_system

# Configure logging
logger.remove()
logger.add(
    sys.stderr, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}"
)
logger.add("logs/live_trader.log", level="DEBUG", rotation="1 day", retention="30 days")

log = logger.bind(module="live_trader")


async def run_live_trader(args: argparse.Namespace) -> None:
    """Khởi chạy 'Bộ não' giao dịch tự động."""
    log.info("=" * 60)
    log.info("QTRADER AUTONOMOUS ENGINE — STARTING")
    log.info("=" * 60)

    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else ["BTC-USD"]
    simulate_mode = os.getenv("SIMULATE_MODE", "true").lower() == "true"

    # === 1. Khởi tạo TradingSystem (Bộ não) ===
    system = create_trading_system(simulate=simulate_mode, symbols=symbols)

    # === 2. Đăng ký tín hiệu Shutdown ===
    def signal_handler() -> None:
        log.warning("Shutdown signal received — initiating graceful shutdown")
        system._shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                pass

    # === 3. KÍCH HOẠT BỘ NÃO ===
    try:
        await system.start()
        await system._shutdown_event.wait()
    except Exception as e:
        log.exception(f"Fatal error in trading system: {e}")
    finally:
        await system.stop()
        log.info("[SHUTDOWN] Trading System stopped. Goodbye.")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="QTrader Live Trading Engine")

    parser.add_argument(
        "--exchange",
        type=str,
        default=os.getenv("QTRADER_EXCHANGE", "coinbase"),
        help="Exchange to use",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=os.getenv("QTRADER_SYMBOLS", "BTC-USD"),
        help="Comma-separated list of trading symbols",
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

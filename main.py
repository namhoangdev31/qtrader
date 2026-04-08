#!/usr/bin/env python3
"""Main entry point for the QTrader live trading system.

The TradingSystem is the unified, complete pipeline that wires ALL modules:
  Market Data → Alpha (Atomic Trio ML) → Signal → Risk → Order → Fill → Recon → PnL

Usage:
    python main.py                    # Paper trading with Atomic Trio ML
    python main.py --live             # Live trading with real broker
    python main.py --symbols BTC-USD,ETH-USD  # Multiple symbols
"""

import argparse
import asyncio
import signal
import sys

from loguru import logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QTrader Trading System")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live broker instead of paper trading",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="BTC-USD",
        help="Comma-separated list of trading symbols",
    )
    return parser.parse_args()


async def main() -> None:
    """Main function to run the QTrader Trading System."""
    args = parse_args()

    from qtrader.trading_system import create_trading_system

    symbols = [s.strip() for s in args.symbols.split(",")]
    simulate = not args.live

    logger.info(
        f"Starting QTrader Trading System "
        f"(mode={'LIVE' if not simulate else 'PAPER'}, symbols={symbols})"
    )

    system = create_trading_system(simulate=simulate, symbols=symbols)

    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        system._shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                pass  # Windows doesn't support add_signal_handler

    try:
        await system.start()
    except Exception as e:
        logger.error(f"System error: {e}", exc_info=True)
    finally:
        await system.stop()
        logger.info("QTrader Trading System stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

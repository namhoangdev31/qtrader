"""Smart order router for multi-exchange execution (Rust-backed)."""

import logging

from qtrader_core import RoutingMode as RustRoutingMode
from qtrader_core import SmartOrderRouter as RustSmartOrderRouter

logger = logging.getLogger(__name__)


class SmartOrderRouter(RustSmartOrderRouter):
    """
    Rust-backed Smart order router.
    """

    def __init__(self, exchanges=None, routing_mode="smart", max_order_size=None, split_size=None):
        # Map string mode to Rust enum
        mode_map = {
            "manual": RustRoutingMode.Manual,
            "best_price": RustRoutingMode.BestPrice,
            "smart": RustRoutingMode.Smart,
        }
        rust_mode = mode_map.get(routing_mode.lower(), RustRoutingMode.Smart)

        super().__init__(
            routing_mode=rust_mode,
            max_order_size=float(max_order_size) if max_order_size else None,
            split_size=float(split_size) if split_size else None,
        )
        self.logger = logger.getChild("SmartOrderRouter")
        self.logger.info(f"Rust-backed SmartOrderRouter initialized, mode={routing_mode}")

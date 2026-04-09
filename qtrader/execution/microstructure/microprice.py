from __future__ import annotations


class Microprice:
    """
    Volume-Weighted Microprice Model.

    Provides a more accurate "Fair Value" than mid-price by incorporating
    bid/ask volume imbalance to detect directional pressure in the orderbook.

    Mathematical Model:
    P_micro = (P_bid * V_ask + P_ask * V_bid) / (V_bid + V_ask)
    """

    @staticmethod
    def compute(bid: float, ask: float, v_bid: float, v_ask: float) -> float:
        """
        Compute the microprice derived from orderbook imbalance.

        Args:
            bid: Current best bid price.
            ask: Current best ask price.
            v_bid: Volume at best bid.
            v_ask: Volume at best ask.
        """
        try:
            total_vol = float(v_bid + v_ask)

            # Failsafe: Fallback to mid-price if volume is missing
            min_vol_threshold = 1e-10
            if total_vol <= min_vol_threshold:
                # Naive Mid-price: (P_b + P_a) / 2
                return (bid + ask) / 2.0

            # Inverse Volume Weighting:
            # - More buy volume (V_b) pushes fair value toward the ask.
            # - More sell volume (V_a) pushes fair value toward the bid.
            return (bid * v_ask + ask * v_bid) / total_vol

        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            # High-performance silent failover (Midpoint discovery fallback)
            return (bid + ask) / 2.0

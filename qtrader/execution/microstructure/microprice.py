from __future__ import annotations

import logging


class Microprice:
    @staticmethod
    def compute(bid: float, ask: float, v_bid: float, v_ask: float) -> float:
        try:
            total_vol = float(v_bid + v_ask)
            min_vol_threshold = 1e-10
            if total_vol <= min_vol_threshold:
                return (bid + ask) / 2.0
            return (bid * v_ask + ask * v_bid) / total_vol
        except Exception as e:
            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            return (bid + ask) / 2.0
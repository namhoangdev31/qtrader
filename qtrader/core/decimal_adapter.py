from __future__ import annotations

import decimal
from decimal import Decimal, getcontext, ROUND_HALF_EVEN
from typing import Any, Optional, Union

from loguru import logger


class DecimalAdapter:
    """
    High-precision arithmetic authority for qtrader.
    Enforces exact arithmetic (ε=0) and standardizes quantization across financial paths.
    """

    # Global institutional precision
    GLOBAL_PRECISION = 28
    ROUNDING_MODE = ROUND_HALF_EVEN

    def __init__(self, fail_on_float: bool = True) -> None:
        """
        Args:
            fail_on_float: If True, raise TypeError on Decimal initialization from float.
        """
        self._fail_on_float = fail_on_float
        # Initialize thread-local decimal context
        ctx = getcontext()
        ctx.prec = self.GLOBAL_PRECISION
        ctx.rounding = self.ROUNDING_MODE

    def d(self, value: Union[str, int, float, Decimal, Any]) -> Decimal:
        """
        Safe Decimal factory. Rejects float primitives to avoid silent precision loss.
        Recommends: d("10.5") or d(1050)
        """
        if isinstance(value, float):
            msg = (
                f"Numerical Integrity Violation: Attempted to initialize Decimal "
                f"from float primitive {value}. Use string or int instead to guarantee precision."
            )
            if self._fail_on_float:
                logger.error(f"[FATAL] {msg}")
                raise TypeError(msg)
            else:
                logger.warning(f"[PRECISION] {msg}")

        try:
            # Handle Any that can be stringified (or directly converted)
            if isinstance(value, (str, int, Decimal)):
                return Decimal(value)
            return Decimal(str(value))
        except decimal.InvalidOperation as e:
            logger.error(f"Failed to create Decimal from {value}: {e}")
            raise

    def quantize(self, value: Decimal, places: int = 8) -> Decimal:
        """
        Quantize a decimal to the specified number of decimal places.
        Uses banker's rounding to minimize cumulative statistical bias.
        """
        target = Decimal(10) ** -places
        return value.quantize(target, rounding=self.ROUNDING_MODE)

    def to_price(self, value: Union[str, float, Decimal]) -> Decimal:
        """Quantize to 8 decimal places (standard market price)."""
        return self.quantize(self.d(value), places=8)

    def to_qty(self, value: Union[str, float, Decimal]) -> Decimal:
        """Quantize to 6 decimal places (standard asset quantity)."""
        return self.quantize(self.d(value), places=6)

    def to_notional(self, value: Union[str, float, Decimal]) -> Decimal:
        """Quantize to 2 decimal places (standard USD settlement)."""
        return self.quantize(self.d(value), places=2)

    def to_nav(self, value: Union[str, float, Decimal]) -> Decimal:
        """Quantize to 12 decimal places (High-fidelity internal state)."""
        return self.quantize(self.d(value), places=12)

    @staticmethod
    def verify_no_float(*args: Any) -> None:
        """Runtime defensive check for accidental mixed-mode arithmetic."""
        for arg in args:
            if isinstance(arg, float):
                raise TypeError(f"Mixed-mode arithmetic detected: {arg} is a float.")


# Module-level singleton for universal access
math_authority = DecimalAdapter(fail_on_float=True)
d = math_authority.d

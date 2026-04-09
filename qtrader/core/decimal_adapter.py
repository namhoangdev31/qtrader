from __future__ import annotations
import decimal
from decimal import ROUND_HALF_EVEN, Decimal, getcontext
from typing import Any
from loguru import logger


class DecimalAdapter:
    GLOBAL_PRECISION = 28
    ROUNDING_MODE = ROUND_HALF_EVEN

    def __init__(self, fail_on_float: bool = True) -> None:
        self._fail_on_float = fail_on_float
        ctx = getcontext()
        ctx.prec = self.GLOBAL_PRECISION
        ctx.rounding = self.ROUNDING_MODE

    def d(self, value: str | int | float | Decimal | Any) -> Decimal:
        if isinstance(value, float):
            msg = f"Numerical Integrity Violation: Attempted to initialize Decimal from float primitive {value}. Use string or int instead to guarantee precision."
            if self._fail_on_float:
                logger.error(f"[FATAL] {msg}")
                raise TypeError(msg)
            else:
                logger.warning(f"[PRECISION] {msg}")
        try:
            if isinstance(value, (str, int, Decimal)):
                return Decimal(value)
            return Decimal(str(value))
        except decimal.InvalidOperation as e:
            logger.error(f"Failed to create Decimal from {value}: {e}")
            raise

    def quantize(self, value: Decimal, places: int = 8) -> Decimal:
        target = Decimal(10) ** (-places)
        return value.quantize(target, rounding=self.ROUNDING_MODE)

    def to_price(self, value: str | float | Decimal) -> Decimal:
        return self.quantize(self.d(value), places=8)

    def to_qty(self, value: str | float | Decimal) -> Decimal:
        return self.quantize(self.d(value), places=6)

    def to_notional(self, value: str | float | Decimal) -> Decimal:
        return self.quantize(self.d(value), places=2)

    def to_nav(self, value: str | float | Decimal) -> Decimal:
        return self.quantize(self.d(value), places=12)

    @staticmethod
    def verify_no_float(*args: Any) -> None:
        for arg in args:
            if isinstance(arg, float):
                raise TypeError(f"Mixed-mode arithmetic detected: {arg} is a float.")


math_authority = DecimalAdapter(fail_on_float=True)
d = math_authority.d

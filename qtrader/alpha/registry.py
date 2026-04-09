from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
import polars as pl

if TYPE_CHECKING:
    from qtrader.alpha.base import Alpha
__all__ = ["AlphaEngine", "AlphaRegistry"]


class AlphaRegistry:
    _registry: dict[str, type[Alpha]] = {}

    @classmethod
    def register(cls, alpha_cls: type[Alpha]) -> type[Alpha]:
        name = getattr(alpha_cls, "name", None)
        if not isinstance(name, str):
            try:
                instance = alpha_cls()
                name = getattr(instance, "name", None)
            except Exception as e:
                logging.getLogger("qtrader.alpha.registry").warning(
                    f"Failed to instantiate alpha class {alpha_cls.__name__} to read name attribute: {e}"
                )
        if not isinstance(name, str):
            raise ValueError(
                f"Alpha class {alpha_cls.__name__} must define a string 'name' attribute. Found {type(name).__name__}: {name}"
            )
        cls._registry[name] = alpha_cls
        return alpha_cls

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> Alpha:
        alpha_cls = cls._registry.get(name)
        if alpha_cls is None:
            raise KeyError(f"Alpha '{name}' not found. Registered: {cls.list_alphas()}")
        return alpha_cls(**kwargs)

    @classmethod
    def list_alphas(cls) -> list[str]:
        return sorted(cls._registry.keys())


@dataclass(slots=True)
class AlphaEngine:
    alpha_names: list[str]
    ic_window: int = 30
    _alphas: dict[str, Alpha] = field(init=False, default_factory=dict)
    _ic: dict[str, float] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._alphas = {name: AlphaRegistry.create(name) for name in self.alpha_names}
        self._ic = {name: 0.0 for name in self.alpha_names}

    def compute_all(self, df: pl.DataFrame) -> pl.DataFrame:
        out = df.select([]).clone()
        for name, alpha in self._alphas.items():
            out = out.with_columns(alpha.compute(df).alias(name))
        weights = self._compute_weights()
        if not weights:
            return out
        exprs = [pl.col(name) * weight for (name, weight) in weights.items()]
        out = out.with_columns(sum(exprs).alias("composite_alpha"))
        return out

    def _compute_weights(self) -> dict[str, float]:
        positives = {k: max(v, 0.0) for (k, v) in self._ic.items()}
        total = sum(positives.values())
        if total <= 0.0:
            n = len(self._ic)
            if n == 0:
                return {}
            w = 1.0 / float(n)
            return {name: w for name in self._ic}
        return {name: val / total for (name, val) in positives.items()}

    def update_ic(self, alpha_name: str, returns: pl.Series) -> None:
        if alpha_name not in self._alphas:
            raise KeyError(f"Alpha '{alpha_name}' is not managed by this engine.")
        if returns.len() == 0:
            return
        window = min(self.ic_window, returns.len())
        sig = self._alphas[alpha_name].compute(returns.to_frame("close"))
        pred = sig.tail(window).rank()
        real = returns.tail(window).rank()
        df = pl.DataFrame({"pred": pred, "real": real})
        ic_val = float(df.select(pl.corr("pred", "real")).item())
        self._ic[alpha_name] = ic_val

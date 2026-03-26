from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from qtrader.feature.alpha.base import Alpha
from qtrader.feature.alpha.microstructure import (
    AmihudIlliquidityAlpha,
    OrderImbalanceAlpha,
    VPINAlpha,
)
from qtrader.feature.alpha.technical import MeanReversionAlpha, MomentumAlpha, TrendAlpha

__all__ = ["AlphaEngine", "AlphaRegistry"]


class AlphaRegistry:
    """Central registry for all alpha factors."""

    _registry: dict[str, type[Alpha]] = {}

    @classmethod
    def register(cls, alpha_cls: type[Alpha]) -> type[Alpha]:
        """Decorator to register an alpha class."""
        name = getattr(alpha_cls, "name", None)
        if not isinstance(name, str):
            try:
                name = getattr(alpha_cls(), "name", None)
            except Exception:
                pass
        if not isinstance(name, str):
            raise ValueError("Alpha class must define a string 'name' attribute.")
        cls._registry[name] = alpha_cls
        return alpha_cls

    @classmethod
    def create(cls, name: str, **kwargs) -> Alpha:
        """Instantiate alpha by name with kwargs."""
        alpha_cls = cls._registry.get(name)
        if alpha_cls is None:
            raise KeyError(f"Alpha '{name}' not found.")
        return alpha_cls(**kwargs)  # type: ignore[call-arg]

    @classmethod
    def list_alphas(cls) -> list[str]:
        """List names of all registered alphas."""
        return sorted(cls._registry.keys())


@dataclass(slots=True)
class AlphaEngine:
    """Run multiple alphas and combine via IC-weighted aggregation."""

    alpha_names: list[str]
    ic_window: int = 30
    _alphas: dict[str, Alpha] = field(init=False, default_factory=dict)
    _ic: dict[str, float] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._alphas = {name: AlphaRegistry.create(name) for name in self.alpha_names}
        self._ic = {name: 0.0 for name in self.alpha_names}

    def compute_all(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute all configured alphas and composite alpha."""
        out = df.select([]).clone()
        for name, alpha in self._alphas.items():
            out = out.with_columns(alpha.compute(df).alias(name))

        weights = self._compute_weights()
        if not weights:
            return out

        exprs = [pl.col(name) * weight for name, weight in weights.items()]
        out = out.with_columns(sum(exprs).alias("composite_alpha"))
        return out

    def _compute_weights(self) -> dict[str, float]:
        positives = {k: max(v, 0.0) for k, v in self._ic.items()}
        total = sum(positives.values())
        if total <= 0.0:
            n = len(self._ic)
            if n == 0:
                return {}
            w = 1.0 / float(n)
            return {name: w for name in self._ic}
        return {name: val / total for name, val in positives.items()}

    def update_ic(self, alpha_name: str, returns: pl.Series) -> None:
        """Update rolling IC estimate for alpha using rank correlation."""
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


# Auto-register known alphas.
AlphaRegistry.register(MomentumAlpha)
AlphaRegistry.register(MeanReversionAlpha)
AlphaRegistry.register(TrendAlpha)
AlphaRegistry.register(OrderImbalanceAlpha)
AlphaRegistry.register(AmihudIlliquidityAlpha)
AlphaRegistry.register(VPINAlpha)


"""
Pytest-style examples (conceptual):

def test_registry_lists_alphas() -> None:
    names = AlphaRegistry.list_alphas()
    assert "momentum" in names


def test_engine_compute_all_has_composite() -> None:
    df = pl.DataFrame({"open": [1.0, 1.1], "high": [1.2, 1.2], "low": [0.9, 1.0], "close": [1.05, 1.15], "volume": [100, 120], "timestamp": [0, 1]})
    engine = AlphaEngine(alpha_names=["momentum"])
    out = engine.compute_all(df)
    assert "momentum" in out.columns and "composite_alpha" in out.columns
"""


from __future__ import annotations

import time
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

import numpy as np
import polars as pl

from qtrader.core.container import container
from qtrader.core.decimal_adapter import d
from qtrader.core.types import AllocationWeights, SignalEvent

_LOG = container.get("logger")


class CapitalAllocationEngine:
    r"""
    Principal Capital Allocation Engine.

    Objective: Distribute platform capital optimally across strategy ensembles proportional
    to their risk-adjusted Sharpe Ratios, while ensuring diversification veracity.

    Model: Sharpe-Weighted Distribution with Iterative Gating.
    Constraint: Diversification Cap ($w_i \le 20\%$).
    """

    def __init__(self, max_cap: Decimal = d("0.2")) -> None:
        """
        Initialize the institutional allocation controller.
        """
        self._max_cap = max_cap
        # Telemetry for institutional situational awareness.
        self._current_distribution: dict[str, Decimal] = {}
        self._capital_concentration: Decimal = d(0)

    def allocate_capital(
        self,
        strategies: list[dict[str, Any]],
        total_capital: Decimal,
    ) -> dict[str, Any]:
        r"""
        Produce a terminal allocation report for the strategical ensemble.

        Forensic Logic:
        1. Performance Filtering: Discards strategies with Sharpe <= 0.
        2. Performance Indexing: Derives initial weights proportional to Sharpe.
        3. Iterative Capping: Programmatically redistributes excess weight.
        4. Diversification Gating: Enforces $w_i \le 0.20$ for all strategy nodes.
        """
        start_time = time.time()

        # 1. Structural Performance Filtering.
        performers = [s for s in strategies if d(str(s.get("sharpe", "0.0"))) > 0]

        if not performers:
            _LOG.warning("[ALLOCATE] NO_PERFORMERS | Zero capital deployed.")
            return {
                "status": "ALLOCATION_EMPTY",
                "result": "SKIP",
                "message": "Zero strategies with Sharpe > 0 detected for target universe.",
            }

        # 2. Performance-Weighted Indexing.
        active_ids = [str(s["id"]) for s in performers]
        active_sharpes = [d(str(s["sharpe"])) for s in performers]
        total_sharpe = sum(active_sharpes)

        distribution_weights = {
            sid: (s / total_sharpe) for sid, s in zip(active_ids, active_sharpes, strict=True)
        }

        final_capped_weights: dict[str, Decimal] = {}

        _epsilon = d("1e-10")

        while True:
            excess_exposure = d(0)
            available_ids = []

            for sid, weight in distribution_weights.items():
                if weight > self._max_cap:
                    excess_exposure += weight - self._max_cap
                    final_capped_weights[sid] = self._max_cap
                else:
                    available_ids.append(sid)

            # Convergence check: Exit if no structural excess remains.
            if excess_exposure <= _epsilon or not available_ids:
                break

            # Redistribute excess proportionally to existing weights.
            current_available_total = sum(distribution_weights[sid] for sid in available_ids)
            for sid in available_ids:
                distribution_weights[sid] += (
                    distribution_weights[sid] / current_available_total
                ) * excess_exposure

            # Remove capped nodes from the iterative redistribution cycle.
            for sid in final_capped_weights:
                distribution_weights.pop(sid, None)

        # Terminal weight reconstruction.
        final_weights = {**distribution_weights, **final_capped_weights}
        target_allocation_usd = {sid: w * total_capital for sid, w in final_weights.items()}

        # 4. Certification & Telemetry.
        self._current_distribution = target_allocation_usd
        self._capital_concentration = max(final_weights.values()) if final_weights else d(0)

        _LOG.info(
            f"[ALLOCATE] DISTRIBUTION_FINALIZED | Nodes: {len(final_weights)} "
            f"| Capital: {total_capital} | Concentration: {self._capital_concentration}"
        )

        # 5. Certification Artifact Construction.
        artifact = {
            "status": "ALLOCATION_COMPLETE",
            "result": "PASS",
            "metrics": {
                "active_strategy_nodes": len(final_weights),
                "total_capital_usd": total_capital,
                "deployed_capital_usd": sum(target_allocation_usd.values()),
                "max_concentration_score": self._capital_concentration,
            },
            "distribution_map": {sid: w for sid, w in final_weights.items()},
            "certification": {
                "institutional_cap_limit": self._max_cap,
                "timestamp": time.time(),
                "real_validation_duration_ms": (time.time() - start_time) * 1000,
            },
        }

        return artifact

    def get_allocation_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional asset allocation.
        """
        entropy = d(1) - self._capital_concentration if self._capital_concentration > 0 else d(0)

        return {
            "status": "ALLOCATION_GOVERNANCE",
            "current_max_concentration": self._capital_concentration,
            "diversification_entropy": entropy,
            "active_capital_nodes": len(self._current_distribution),
        }


class CapitalAllocator:
    """
    Legacy Allocator used for rapid backtesting and unit verification.
    Allocates capital based on risk (volatility) and performance (Sharpe/Drawdown).
    """

    EPSILON = 1e-6
    MIN_STRATEGIES_CORR = 2

    def __init__(
        self,
        max_capital_per_strategy: float = 0.40,
        min_strategies: int = 2,
        correlation_threshold: float = 0.70
    ) -> None:
        self.max_capital_per_strategy = max_capital_per_strategy
        self.min_strategies = min_strategies
        self.correlation_threshold = correlation_threshold

    def allocate(
        self,
        strategy_stats: pl.DataFrame,
        strategy_returns: pl.DataFrame | None = None
    ) -> dict[str, float]:
        """
        Calculate capital allocation for each strategy.
        """
        try:
            if strategy_stats.is_empty():
                return {}

            # 1. Base Weights: Risk Parity (Inverse Volatility)
            vols = strategy_stats["volatility"].to_numpy()
            vols = np.where(vols < self.EPSILON, self.EPSILON, vols)
            inv_vols = 1.0 / vols
            
            # 2. Performance Adjustments
            sharpes = strategy_stats["sharpe"].to_numpy()
            sharpe_adj = np.maximum(0.1, sharpes)
            
            drawdowns = strategy_stats["max_drawdown"].to_numpy()
            dd_adj = 1.0 - np.minimum(0.9, drawdowns)
            
            # Combine factors
            raw_weights = inv_vols * sharpe_adj * dd_adj
            
            # 3. Correlation Penalty
            if strategy_returns is not None and strategy_returns.width >= self.MIN_STRATEGIES_CORR:
                ret_cols = [c for c in strategy_returns.columns if c != "timestamp"]
                corr_matrix = strategy_returns.select(ret_cols).corr().to_numpy()
                
                n = corr_matrix.shape[0]
                total_corr = np.sum(np.abs(corr_matrix), axis=0) - 1.0
                avg_corr = total_corr / (n - 1) if n > 1 else np.zeros(n)
                
                corr_penalty = 1.0 - (avg_corr ** 2)
                raw_weights = raw_weights * corr_penalty

            # 4. Normalize and Cap
            total_raw = np.sum(raw_weights)
            if total_raw == 0:
                weights = np.ones(len(strategy_stats)) / len(strategy_stats)
            else:
                weights = raw_weights / total_raw
                
            for _ in range(5):
                capped = np.minimum(self.max_capital_per_strategy, weights)
                excess = 1.0 - np.sum(capped)
                if abs(excess) < self.EPSILON:
                    weights = capped
                    break
                
                uncapped_mask = weights < self.max_capital_per_strategy
                if not np.any(uncapped_mask):
                    weights = capped
                    break
                    
                sum_uncapped = np.sum(weights[uncapped_mask])
                weights[uncapped_mask] += excess * (weights[uncapped_mask] / sum_uncapped)
                weights = np.minimum(self.max_capital_per_strategy, weights)

            weights = weights / np.sum(weights)
            strategy_ids = strategy_stats["strategy_id"].to_list()
            return dict(zip(strategy_ids, weights.tolist(), strict=False))

        except Exception as e:
            _LOG.error(f"Capital allocation failed: {e}")
            return {}


class AllocatorBase(ABC):
    """Abstract base class for portfolio allocators."""

    def __init__(self, name: str = "AllocatorBase") -> None:
        self.name = name
        self.logger = logger
        self._risk_multiplier = Decimal("1.0")  # Default risk multiplier

    @abstractmethod
    async def allocate(self, signal_event: SignalEvent) -> AllocationWeights:
        """Calculate portfolio allocation weights based on trading signal.

        Args:
            signal_event: Trading signal from strategy

        Returns:
            AllocationWeights containing portfolio weights
        """
        pass

    def set_risk_multiplier(self, multiplier: Decimal) -> None:
        """Set the risk multiplier for position sizing.

        Args:
            multiplier: Risk multiplier to apply (e.g., 0.5 for half risk, 2.0 for double risk)
        """
        self._risk_multiplier = max(Decimal("0.0"), multiplier)  # Ensure non-negative
        self.logger.debug(f"Risk multiplier set to {self._risk_multiplier}")

    def get_risk_multiplier(self) -> Decimal:
        """Get the current risk multiplier.

        Returns:
            Current risk multiplier
        """
        return self._risk_multiplier


class SimpleAllocator(AllocatorBase):
    """Simple allocator that allocates based on signal strength."""

    def __init__(self, name: str = "SimpleAllocator") -> None:
        super().__init__(name)

    async def allocate(self, signal_event: SignalEvent) -> AllocationWeights:
        """Allocate portfolio based on signal strength (simple implementation).

        Args:
            signal_event: Trading signal from strategy

        Returns:
            AllocationWeights containing portfolio weights
        """
        # In a real implementation, this would calculate optimal weights
        # based on risk, expected returns, correlation, etc.
        # For now, we just allocate based on signal strength

        # Normalize signal strength to allocation size (0 to 1)
        # Assuming signal strength is already normalized between 0 and 1
        allocation_size = signal_event.strength

        # Apply risk multiplier from meta-learner
        risk_multiplier = self.get_risk_multiplier()
        
        final_allocation = allocation_size * risk_multiplier

        # For simplicity, allocate to the signal's symbol only
        # In reality, we'd have a universe of symbols and optimize weights
        weights = {}
        if hasattr(signal_event, "symbol") and signal_event.symbol:
            weights[signal_event.symbol] = final_allocation

        return AllocationWeights(
            timestamp=signal_event.timestamp,
            weights=weights,
            metadata={
                "allocator": self.name,
                "signal_strength": signal_event.strength,
                "risk_multiplier": risk_multiplier,
            },
        )


class PortfolioAllocator:
    """
    Portfolio allocation risk module.

    Allocates capital to strategies based on risk parity (equal risk contribution) or other methods.

    Args:
        method: Allocation method ('equal_risk', 'inverse_volatility', 'equal_weight').
                Default is 'equal_risk'.
        lookback: Lookback period for estimating volatility and correlations (default 20).
        min_weight: Minimum weight allocated to any strategy (default 0.0).
        max_weight: Maximum weight allocated to any strategy (default 1.0).
    """

    def __init__(
        self,
        method: str = "equal_risk",
        lookback: int = 20,
        min_weight: float = 0.0,
        max_weight: float = 1.0,
    ) -> None:
        if method not in ["equal_risk", "inverse_volatility", "equal_weight"]:
            raise ValueError(f"Unsupported method: {method}")
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        if min_weight < 0 or max_weight > 1 or min_weight > max_weight:
            raise ValueError(
                "min_weight and max_weight must be in [0,1] and min_weight <= max_weight"
            )
        self.method = method
        self.lookback = lookback
        self.min_weight = min_weight
        self.max_weight = max_weight

    def allocate(self, strategy_returns: dict[str, pl.Series]) -> dict[str, pl.Series]:
        """
        Allocate capital to strategies.

        Args:
            strategy_returns: Dictionary mapping strategy names to their return series.

        Returns:
            Dictionary of allocation weights (same keys as input, weights sum to 1.0).
        """
        if not strategy_returns:
            return {}

        # Align all series to the same length by truncating to the shortest
        min_len = min(len(series) for series in strategy_returns.values())
        if min_len == 0:
            # Return zero weights
            return {
                name: pl.Series(values=[0.0], name=name, dtype=pl.Float64)
                for name in strategy_returns.keys()
            }

        # Truncate series to min_len
        truncated_returns = {
            name: series.tail(min_len) for name, series in strategy_returns.items()
        }

        # Convert to DataFrame for easier computation
        returns_df = pl.DataFrame(truncated_returns)

        # Compute weights based on method
        if self.method == "equal_weight":
            weights_dict = self._equal_weight(returns_df)
        elif self.method == "inverse_volatility":
            weights_dict = self._inverse_volatility(returns_df)
        else:  # equal_risk
            weights_dict = self._equal_risk(returns_df)

        # Apply min/max weight constraints
        weights_dict = self._apply_constraints(weights_dict)

        # Normalize weights to sum to 1.0 (after constraints, may not sum to 1.0)
        weight_sum = sum(weights_dict.values())
        if weight_sum > 0:
            weights_dict = {name: w / weight_sum for name, w in weights_dict.items()}
        else:
            # If all weights are zero, fall back to equal weight
            n = len(weights_dict)
            equal_weight = 1.0 / n if n > 0 else 0.0
            weights_dict = {name: equal_weight for name in weights_dict.keys()}

        # Return as dictionary of series (each weight series is constant over time)
        result = {}
        for strat_name, weight in weights_dict.items():
            # Create a series of constant weight for each time point
            result[strat_name] = pl.Series(
                values=[weight] * min_len, name=strat_name, dtype=pl.Float64
            )

        return result

    def _equal_weight(self, returns_df: pl.DataFrame) -> dict[str, float]:
        """Equal weight allocation: 1/n for each strategy."""
        n = len(returns_df.columns)
        weight = 1.0 / n if n > 0 else 0.0
        return {col: weight for col in returns_df.columns}

    def _inverse_volatility(self, returns_df: pl.DataFrame) -> dict[str, float]:
        """Inverse volatility weighting."""
        # Compute volatility (std) of each strategy
        inv_vol_list = []
        for col in returns_df.columns:
            vol = returns_df[col].std()
            if vol is None or vol == 0.0:
                inv_vol_list.append(0.0)
            else:
                inv_vol_list.append(1.0 / vol)
        total_inv_vol = sum(inv_vol_list)
        if total_inv_vol == 0.0:
            # Fall back to equal weight
            n = len(returns_df.columns)
            weight = 1.0 / n if n > 0 else 0.0
            return {col: weight for col in returns_df.columns}
        weights = {
            col: inv_vol_list[i] / total_inv_vol
            for i, col in enumerate(returns_df.columns)
        }
        return weights

    def _equal_risk(self, returns_df: pl.DataFrame) -> dict[str, float]:
        """
        Equal risk contribution (risk parity) allocation.
        This is an approximation using the inverse volatility method for simplicity.
        A more accurate method would require solving for weights such that each
        strategy contributes equally to portfolio risk.
        For now, we use inverse volatility as a proxy, which is exact only if
        correlations are zero or equal.
        """
        return self._inverse_volatility(returns_df)

    def _apply_constraints(self, weights: dict[str, float]) -> dict[str, float]:
        """Apply min and max weight constraints."""
        constrained = {}
        for strat_name, weight in weights.items():
            if weight < self.min_weight:
                constrained[strat_name] = self.min_weight
            elif weight > self.max_weight:
                constrained[strat_name] = self.max_weight
            else:
                constrained[strat_name] = weight
        return constrained

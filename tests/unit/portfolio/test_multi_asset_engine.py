"""
Tests for MultiAssetPortfolioEngine.
"""

import pytest
import polars as pl
from datetime import datetime, timedelta
from decimal import Decimal

from qtrader.portfolio.multi_asset_engine import MultiAssetPortfolioEngine, AssetClassMapping
from qtrader.core.types import SignalEvent, AllocationWeights


def make_market_data(
    symbol: str,
    base_price: Decimal = Decimal("100"),
    volatility: Decimal = Decimal("0.01"),
    periods: int = 50,
) -> pl.DataFrame:
    """Generate synthetic market data for testing."""
    rng_seed = hash(symbol) % 2**32  # Deterministic but different per symbol
    import numpy as np

    rng = np.random.default_rng(rng_seed)

    # Fixed start time (floored to minute) for alignment
    start_time = datetime.now().replace(second=0, microsecond=0)
    timestamps = [start_time - timedelta(minutes=i) for i in range(periods)]
    timestamps.reverse()  # Oldest first

    # Generate price series with specified volatility
    returns = rng.normal(0, float(volatility), periods)
    prices = [float(base_price)]
    for ret in returns[1:]:
        prices.append(prices[-1] * (1 + ret))

    # Convert back to Decimal for consistency
    prices = [Decimal(str(p)) for p in prices]

    data = {
        "timestamp": timestamps,
        "open": prices,
        "high": [p * Decimal("1.001") for p in prices],
        "low": [p * Decimal("0.999") for p in prices],
        "close": prices,
        "volume": [Decimal("1000")] * periods,
    }
    return pl.DataFrame(data)


class TestMultiAssetPortfolioEngine:
    """Test suite for MultiAssetPortfolioEngine."""

    def setup_method(self):
        """Set up test fixtures."""
        # Define asset class mapping
        symbol_to_asset_class = {
            "BTCUSD": "CRYPTO",
            "ETHUSD": "CRYPTO",
            "EURUSD": "FOREX",
            "GBPUSD": "FOREX",
            "AAPL": "EQUITY",
            "GOOGL": "EQUITY",
        }
        self.asset_mapping = AssetClassMapping(
            symbol_to_asset_class=symbol_to_asset_class, base_currency="USD"
        )
        self.engine = MultiAssetPortfolioEngine(
            asset_class_mapping=self.asset_mapping, lookback_period=20
        )

    def test_initialization(self):
        """Test proper initialization."""
        assert self.engine.asset_class_mapping == self.asset_mapping
        assert self.engine.lookback_period == 20

    def test_allocate_portfolio_empty_inputs(self):
        """Test allocation with empty inputs."""
        result = self.engine.allocate_portfolio(signals=[], current_positions={}, market_data={})

        assert isinstance(result, AllocationWeights)
        assert result.weights == {}
        assert result.metadata.get("warning") == "no_market_data"

    def test_allocate_portfolio_single_crypto(self):
        """Test allocation with single crypto asset."""
        # Create market data for BTC
        btc_data = make_market_data(
            "BTCUSD", base_price=Decimal("50000"), volatility=Decimal("0.02")
        )
        market_data = {"BTCUSD": btc_data}

        # Create a long signal
        signal = SignalEvent(
            symbol="BTCUSD", timestamp=datetime.now(), signal_type="LONG", strength=Decimal("0.8")
        )

        result = self.engine.allocate_portfolio(
            signals=[signal], current_positions={}, market_data=market_data
        )

        assert isinstance(result, AllocationWeights)
        assert "BTCUSD" in result.weights
        assert result.weights["BTCUSD"] > 0
        assert result.metadata.get("engine") == "MultiAssetPortfolioEngine"

    def test_allocate_portfolio_multiple_assets_same_class(self):
        """Test allocation with multiple assets in same asset class."""
        # Create market data for two crypto assets
        btc_data = make_market_data(
            "BTCUSD", base_price=Decimal("50000"), volatility=Decimal("0.02")
        )
        eth_data = make_market_data(
            "ETHUSD", base_price=Decimal("3000"), volatility=Decimal("0.03")
        )
        market_data = {"BTCUSD": btc_data, "ETHUSD": eth_data}

        # Create signals for both
        btc_signal = SignalEvent(
            symbol="BTCUSD", timestamp=datetime.now(), signal_type="LONG", strength=Decimal("0.8")
        )
        eth_signal = SignalEvent(
            symbol="ETHUSD", timestamp=datetime.now(), signal_type="LONG", strength=Decimal("0.6")
        )

        result = self.engine.allocate_portfolio(
            signals=[btc_signal, eth_signal], current_positions={}, market_data=market_data
        )

        assert isinstance(result, AllocationWeights)
        assert "BTCUSD" in result.weights
        assert "ETHUSD" in result.weights
        # Both weights should be positive
        assert result.weights["BTCUSD"] > 0
        assert result.weights["ETHUSD"] > 0
        # BTC should have higher weight due to higher signal strength
        assert result.weights["BTCUSD"] > result.weights["ETHUSD"]

    def test_allocate_portfolio_different_asset_classes(self):
        """Test allocation across different asset classes."""
        # Create market data
        btc_data = make_market_data(
            "BTCUSD", base_price=Decimal("50000"), volatility=Decimal("0.02")
        )
        eur_data = make_market_data(
            "EURUSD", base_price=Decimal("1.08"), volatility=Decimal("0.008")
        )
        aapl_data = make_market_data("AAPL", base_price=Decimal("150"), volatility=Decimal("0.015"))

        market_data = {"BTCUSD": btc_data, "EURUSD": eur_data, "AAPL": aapl_data}

        # Create signals
        btc_signal = SignalEvent(
            symbol="BTCUSD", timestamp=datetime.now(), signal_type="LONG", strength=Decimal("0.7")
        )
        eur_signal = SignalEvent(
            symbol="EURUSD", timestamp=datetime.now(), signal_type="LONG", strength=Decimal("0.5")
        )
        aapl_signal = SignalEvent(
            symbol="AAPL", timestamp=datetime.now(), signal_type="LONG", strength=Decimal("0.6")
        )

        result = self.engine.allocate_portfolio(
            signals=[btc_signal, eur_signal, aapl_signal],
            current_positions={},
            market_data=market_data,
        )

        assert isinstance(result, AllocationWeights)
        assert len(result.weights) == 3
        # Check that weights sum to approximately 1 (allowing for small numerical errors)
        total_weight = sum(float(w) for w in result.weights.values())
        assert abs(total_weight - 1.0) < 0.01  # Allow 1% tolerance

    def test_allocate_portfolio_insufficient_data(self):
        """Test allocation with insufficient market data."""
        # Create minimal data (only 1 period)
        btc_data = make_market_data("BTCUSD", periods=1)
        market_data = {"BTCUSD": btc_data}

        signal = SignalEvent(
            symbol="BTCUSD", timestamp=datetime.now(), signal_type="LONG", strength=Decimal("0.8")
        )

        result = self.engine.allocate_portfolio(
            signals=[signal], current_positions={}, market_data=market_data
        )

        # Should handle gracefully and return empty weights or warning
        assert isinstance(result, AllocationWeights)
        # Either empty weights or contains warning in metadata
        assert result.weights == {} or "warning" in result.metadata

    def test_allocate_portfolio_no_signals(self):
        """Test allocation with no signals (should still produce weights based on volatility)."""
        # Create market data for two assets with different volatilities
        low_vol_data = make_market_data(
            "LOWVOL", base_price=Decimal("100"), volatility=Decimal("0.005")
        )
        high_vol_data = make_market_data(
            "HIGHVOL", base_price=Decimal("100"), volatility=Decimal("0.02")
        )
        market_data = {"LOWVOL": low_vol_data, "HIGHVOL": high_vol_data}

        result = self.engine.allocate_portfolio(
            signals=[],  # No signals
            current_positions={},
            market_data=market_data,
        )

        assert isinstance(result, AllocationWeights)
        # Should still allocate based on volatility (inverse volatility weighting)
        assert "LOWVOL" in result.weights
        assert "HIGHVOL" in result.weights
        # Lower volatility asset should get higher weight
        assert result.weights["LOWVOL"] > result.weights["HIGHVOL"]

    def test_allocate_portfolio_with_current_positions(self):
        """Test that current positions are considered (though not used in current implementation)."""
        btc_data = make_market_data("BTCUSD", periods=30)
        market_data = {"BTCUSD": btc_data}

        signal = SignalEvent(
            symbol="BTCUSD", timestamp=datetime.now(), signal_type="LONG", strength=Decimal("0.8")
        )

        current_positions = {"BTCUSD": Decimal("1.5")}  # Already long 1.5 BTC

        result = self.engine.allocate_portfolio(
            signals=[signal], current_positions=current_positions, market_data=market_data
        )

        assert isinstance(result, AllocationWeights)
        assert "BTCUSD" in result.weights
        # Current positions don't affect allocation in current implementation
        # but the function should still work

    def test_allocate_portfolio_hedging(self):
        """Test that negative signals result in negative weights (hedging)."""
        btc_data = make_market_data("BTCUSD", volatility=Decimal("0.02"))
        eth_data = make_market_data("ETHUSD", volatility=Decimal("0.03"))
        market_data = {"BTCUSD": btc_data, "ETHUSD": eth_data}

        # Long BTC, Short ETH (Hedge)
        btc_signal = SignalEvent(
            symbol="BTCUSD", timestamp=datetime.now(), signal_type="LONG", strength=Decimal("0.8")
        )
        eth_signal = SignalEvent(
            symbol="ETHUSD", timestamp=datetime.now(), signal_type="SHORT", strength=Decimal("-0.4")
        )

        result = self.engine.allocate_portfolio(
            signals=[btc_signal, eth_signal], current_positions={}, market_data=market_data
        )

        assert result.weights["BTCUSD"] > 0
        assert result.weights["ETHUSD"] < 0
        # Absolute weights should reflect magnitude
        assert abs(result.weights["BTCUSD"]) > abs(result.weights["ETHUSD"])

    def test_allocate_portfolio_target_weights(self):
        """Test that target asset class weights are respected."""
        # Set target weights: 70% Crypto, 30% Forex
        self.asset_mapping.target_asset_class_weights = {"CRYPTO": 0.7, "FOREX": 0.3}
        
        btc_data = make_market_data("BTCUSD")
        eur_data = make_market_data("EURUSD")
        market_data = {"BTCUSD": btc_data, "EURUSD": eur_data}

        result = self.engine.allocate_portfolio(
            signals=[], current_positions={}, market_data=market_data
        )

        # BTC is CRYPTO, EUR is FOREX
        # In this engine, weights sum to 1.0 (or asset class target)
        # Note: if only 1 symbol per class, it gets 100% of class weight
        assert abs(float(result.weights["BTCUSD"]) - 0.7) < 1e-6
        assert abs(float(result.weights["EURUSD"]) - 0.3) < 1e-6

    def test_allocate_portfolio_correlation_adjustment(self):
        """Test that highly correlated assets get their signals penalized."""
        import numpy as np
        
        # Create two highly correlated assets
        periods = 50
        start_time = datetime.now().replace(second=0, microsecond=0)
        timestamps = [start_time - timedelta(minutes=i) for i in range(periods)]
        timestamps.reverse()
        
        # Perfectly correlated returns
        returns = np.random.normal(0, 0.01, periods)
        prices1 = np.exp(np.cumsum(returns)) * 100
        prices2 = np.exp(np.cumsum(returns)) * 110 # Correlated with prices1
        
        def to_df(prices, sym):
            return pl.DataFrame({
                "timestamp": timestamps,
                "open": prices, "high": prices, "low": prices, "close": prices, "volume": [100.0]*periods
            })

        market_data = {
            "SYM1": to_df(prices1, "SYM1"),
            "SYM2": to_df(prices2, "SYM2"),
            "SYM3": make_market_data("SYM3") # Uncorrelated (random seed)
        }
        
        # Same class for all to focus on correlation adjustment
        self.engine.asset_class_mapping.symbol_to_asset_class = {
            "SYM1": "A", "SYM2": "A", "SYM3": "A"
        }

        # Equal signals
        signals = [
            SignalEvent(symbol="SYM1", timestamp=datetime.now(), signal_type="LONG", strength=Decimal("1.0")),
            SignalEvent(symbol="SYM2", timestamp=datetime.now(), signal_type="LONG", strength=Decimal("1.0")),
            SignalEvent(symbol="SYM3", timestamp=datetime.now(), signal_type="LONG", strength=Decimal("1.0")),
        ]

        result = self.engine.allocate_portfolio(
            signals=signals, current_positions={}, market_data=market_data
        )

        # SYM1 and SYM2 are highly correlated, so they should be penalized more than SYM3
        # Weight of SYM3 should be higher than SYM1 and SYM2
        assert result.weights["SYM3"] > result.weights["SYM1"]
        assert result.weights["SYM3"] > result.weights["SYM2"]
        assert abs(result.weights["SYM1"] - result.weights["SYM2"]) < 1e-6


if __name__ == "__main__":
    pytest.main([__file__])

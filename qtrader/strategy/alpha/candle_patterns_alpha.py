# File: qtrader/strategy/alpha/candle_patterns_alpha.py
import polars as pl
import numpy as np
from qtrader.strategy.alpha.alpha_base import AlphaBase
from qtrader.core.types import MarketData, AlphaOutput

class CandleAlphaEngine(AlphaBase):
    """
    Institutional-grade alpha features from 30 candlestick trading methods.
    All features are continuous, normalized, and vectorized using Polars.
    This engine maintains a buffer of historical data to compute features on each new tick.
    """
    
    def __init__(self, name: str = "CandleAlpha", max_history: int = 500):
        super().__init__(name)
        self.max_history = max_history
        # Buffer to store historical data as list of dicts
        self.buffer = []
        # Minimum number of candles required to compute features
        self.min_history = 200  # Based on the longest window used (EMA200, etc.)
    
    def compute(self, df: pl.DataFrame) -> dict[str, pl.Series]:
        """
        Compute all alpha features from OHLCV data.
        
        Args:
            df: Polars DataFrame with columns ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            
        Returns:
            Dictionary mapping feature names to Polars Series (float64, length=len(df), no NaN)
        """
        # Ensure required columns exist
        required_cols = {'timestamp', 'open', 'high', 'low', 'close', 'volume'}
        if not required_cols.issubset(set(df.columns)):
            missing = required_cols - set(df.columns)
            raise ValueError(f"Missing required columns: {missing}")
        
        # Extract columns for convenience
        o = df['open']
        h = df['high']
        l = df['low']
        c = df['close']
        v = df['volume']
        
        # Initialize features dictionary
        features = {}
        
        # ========== PRICE ACTION ==========
        # 1. trend_strength: Price change over period (proxy for trend)
        n = 20
        trend_strength = (c - c.shift(n)) / n
        features['trend_strength'] = self._normalize_series(trend_strength)
        
        # 2. structure_break_score: Break of Structure (BOS) detection
        # Bullish BOS: close > previous swing high
        # Bearish BOS: close < previous swing low
        swing_high = h.rolling_max(window_size=10, min_periods=1)
        swing_low = l.rolling_min(window_size=10, min_periods=1)
        bullish_bos = (c > swing_high.shift(1)).cast(pl.Float64)
        bearish_bos = (c < swing_low.shift(1)).cast(pl.Float64)
        structure_break = (bullish_bos - bearish_bos).fill_null(0.0)
        features['structure_break_score'] = self._normalize_series(structure_break)
        
        # 3. choch_score: Change of Character (trend acceleration/deceleration)
        # Measure of momentum change: current momentum vs average momentum
        momentum = c - c.shift(1)
        avg_momentum = momentum.rolling_mean(window_size=20, min_periods=1)
        # Avoid division by zero
        choch = pl.when(avg_momentum.abs() > 1e-8).then(momentum / avg_momentum.abs()).otherwise(0.0)
        features['choch_score'] = self._normalize_series(choch.fill_null(0.0))
        
        # ========== SUPPORT / RESISTANCE ==========
        # 4. distance_to_resistance: Normalized distance to recent swing high
        lookback = 50
        recent_high = h.rolling_max(window_size=lookback, min_periods=1)
        recent_low = l.rolling_min(window_size=lookback, min_periods=1)
        range_hl = recent_high - recent_low
        dist_to_res = pl.when(range_hl > 1e-8).then((recent_high - c) / range_hl).otherwise(0.5)
        features['distance_to_resistance'] = self._normalize_series(1.0 - dist_to_res)  # Invert so higher = closer to resistance
        
        # 5. distance_to_support: Normalized distance to recent swing low
        dist_to_sup = pl.when(range_hl > 1e-8).then((c - recent_low) / range_hl).otherwise(0.5)
        features['distance_to_support'] = self._normalize_series(dist_to_sup)
        
        # 6. rejection_strength: Wick-to-body ratio indicating rejection
        body = (c - o).abs()
        total_range = h - l
        upper_wick = h - pl.max(o, c)  # h - max(o,c)
        lower_wick = pl.min(o, c) - l  # min(o,c) - l
        # Rejection occurs when price moves away from open then returns
        bullish_rej = pl.when(body > 1e-8).then(lower_wick / body).otherwise(0.0)  # Long lower wick
        bearish_rej = pl.when(body > 1e-8).then(upper_wick / body).otherwise(0.0)  # Long upper wick
        rejection = (bullish_rej - bearish_rej).fill_null(0.0)
        features['rejection_strength'] = self._normalize_series(rejection)
        
        # ========== CANDLE PATTERNS ==========
        # 7. engulfing_score: Engulfing pattern strength
        prev_o = o.shift(1)
        prev_c = c.shift(1)
        bullish_eng = (c > o) & (prev_c < prev_o) & (c >= prev_o) & (o <= prev_c)
        bearish_eng = (c < o) & (prev_c > prev_o) & (c <= prev_o) & (o >= prev_c)
        engulfing = bullish_eng.cast(pl.Float64) - bearish_eng.cast(pl.Float64)
        # Smooth with rolling mean
        engulfing_smooth = engulfing.rolling_mean(window_size=5, min_periods=1).fill_null(0.0)
        features['engulfing_score'] = self._normalize_series(engulfing_smooth)
        
        # 8. pinbar_score: Pin bar (hammer/shooting star) strength
        body_size = (c - o).abs()
        lower_wick = pl.min(o, c) - l
        upper_wick = h - pl.max(o, c)
        # Bullish pin: long lower wick, small body
        bullish_pin = pl.when(body_size > 1e-8).then(lower_wick / body_size).otherwise(0.0)
        # Bearish pin: long upper wick, small body
        bearish_pin = pl.when(body_size > 1e-8).then(upper_wick / body_size).otherwise(0.0)
        pinbar = bullish_pin - bearish_pin  # Positive = bullish pin
        features['pinbar_score'] = self._normalize_series(pinbar.fill_null(0.0))
        
        # 9. inside_bar_pressure: Inside bar indicating consolidation
        prev_h = h.shift(1)
        prev_l = l.shift(1)
        inside_bar = (h <= prev_h) & (l >= prev_l)
        # Pressure builds when inside bars occur after strong moves
        momentum = c - c.shift(3)
        inside_pressure = inside_bar.cast(pl.Float64) * momentum.abs()
        features['inside_bar_pressure'] = self._normalize_series(inside_pressure.fill_null(0.0))
        
        # 10. outside_bar_momentum: Outside bar indicating volatility expansion
        outside_bar = (h >= prev_h) & (l <= prev_l)
        # Momentum in direction of outside bar
        outside_mom = outside_bar.cast(pl.Float64) * (c - o)
        features['outside_bar_momentum'] = self._normalize_series(outside_mom.fill_null(0.0))
        
        # ========== BREAKOUT / RETEST ==========
        # 11. breakout_strength: Close beyond rolling high/low with volume
        lookback_breakout = 20
        roll_high = h.rolling_max(window_size=lookback_breakout, min_periods=1)
        roll_low = l.rolling_min(window_size=lookback_breakout, min_periods=1)
        breakout_up = (c > roll_high.shift(1)).cast(pl.Float64)
        breakout_dn = (c < roll_low.shift(1)).cast(pl.Float64)
        # Volume confirmation
        vol_ma = v.rolling_mean(window_size=20, min_periods=1)
        vol_std = v.rolling_std(window_size=20, min_periods=1)
        vol_ratio = pl.when(vol_ma > 1e-8).then(v / vol_ma).otherwise(1.0)
        breakout_strength = (breakout_up - breakout_dn) * vol_ratio.clip(0.0, 5.0)
        features['breakout_strength'] = self._normalize_series(breakout_strength.fill_null(0.0))
        
        # 12. retest_quality: How well price holds after breakout
        # Measure: distance from breakout level after n periods
        breakout_level_up = roll_high.shift(1)
        breakout_level_dn = roll_low.shift(1)
        # For bullish breakouts: how close we are to support level after breakout
        retest_up = pl.when(c > breakout_level_up.shift(5)) \
                     .then((c - breakout_level_up) / (c + 1e-8)) \
                     .otherwise(0.0)
        retest_dn = pl.when(c < breakout_level_dn.shift(5)) \
                     .then((breakout_level_dn - c) / (c + 1e-8)) \
                     .otherwise(0.0)
        retest_quality = (retest_up + retest_dn).fill_null(0.0)
        features['retest_quality'] = self._normalize_series(retest_quality)
        
        # 13. fake_breakout_score: Wick failure indicating fakeout
        # Price breaks level but closes back inside range
        fake_up = (h > roll_high.shift(1)) & (c <= roll_high.shift(1))
        fake_dn = (l < roll_low.shift(1)) & (c >= roll_low.shift(1))
        fake_breakout = fake_up.cast(pl.Float64) - fake_dn.cast(pl.Float64)
        features['fake_breakout_score'] = self._normalize_series(fake_breakout.fill_null(0.0))
        
        # ========== TREND FOLLOWING ==========
        # 14. pullback_depth: How deep pullback is in trend context
        # In uptrend: depth from recent high; in downtress: depth from recent low
        trend_ma = c.rolling_mean(window_size=50, min_periods=1)
        uptrend = c > trend_ma
        roll_high_20 = h.rolling_max(window_size=20, min_periods=1)
        roll_low_20 = l.rolling_min(window_size=20, min_periods=1)
        range_20 = roll_high_20 - roll_low_20
        pullback_dn = pl.when(uptrend & (range_20 > 1e-8)) \
                      .then((roll_high_20 - c) / range_20) \
                      .otherwise(pl.when(~uptrend & (range_20 > 1e-8)) \
                              .then((c - roll_low_20) / range_20) \
                              .otherwise(0.5))
        features['pullback_depth'] = self._normalize_series(pullback_dn.fill_null(0.5))
        
        # 15. continuation_strength: Likelihood trend continues after pullback
        # Measure: momentum after pullback vs average
        momentum_5 = c - c.shift(5)
        avg_momentum = momentum_5.rolling_mean(window_size=20, min_periods=1)
        continuation = pl.when(avg_momentum.abs() > 1e-8).then(momentum_5 / avg_momentum.abs()).otherwise(0.0)
        features['continuation_strength'] = self._normalize_series(continuation.fill_null(0.0))
        
        # 16. EMA_distance: Distance to multiple EMAs (normalized)
        ema_20 = c.ewm_mean(span=20)
        ema_50 = c.ewm_mean(span=50)
        ema_200 = c.ewm_mean(span=200)
        # Average z-score distance to EMAs
        dist_ema = ((c - ema_20).abs() + (c - ema_50).abs() + (c - ema_200).abs()) / 3.0
        # Normalize by ATR to make adaptive
        atr = self._calculate_atr(df, 14)
        ema_distance = pl.when(atr > 1e-8).then(dist_ema / atr).otherwise(0.0)
        features['EMA_distance'] = self._normalize_series(ema_distance.fill_null(0.0))
        
        # ========== VOLUME + MOMENTUM ==========
        # 17. volume_spike_zscore: Unusual volume activity
        vol_ma_20 = v.rolling_mean(window_size=20, min_periods=1)
        vol_std_20 = v.rolling_std(window_size=20, min_periods=1)
        volume_spike = pl.when(vol_std_20 > 1e-8).then((v - vol_ma_20) / vol_std_20).otherwise(0.0)
        features['volume_spike_zscore'] = self._normalize_series(volume_spike.fill_null(0.0))
        
        # 18. momentum_candle_strength: Momentum candle closing strength
        # How close close is to high/low in direction of momentum
        momentum_dir = (c - o).sign()  # 1=up, -1=down, 0=neutral
        body_pos = pl.when((h - l) > 1e-8).then((c - o) / (h - l)).otherwise(0.5)  # Where close is in range
        # For up candle: strength = body_pos; for down: strength = 1 - body_pos
        momentum_strength = pl.when(momentum_dir > 0) \
                           .then(body_pos) \
                           .when(momentum_dir < 0) \
                           .then(1.0 - body_pos) \
                           .otherwise(0.5)
        features['momentum_candle_strength'] = self._normalize_series((momentum_strength - 0.5) * 2.0)  # Center on 0
        
        # 19. exhaustion_score: Volume + wick divergence indicating exhaustion
        # High volume with long wicks but small body = exhaustion
        body_ratio = pl.when(total_range > 1e-8).then((c - o).abs() / total_range).otherwise(0.0)
        vol_ratio = pl.when(v.rolling_mean(window_size=20, min_periods=1) > 1e-8).then(v / v.rolling_mean(window_size=20, min_periods=1)).otherwise(1.0)
        exhaustion = vol_ratio * (1.0 - body_ratio)  # High vol, small body
        features['exhaustion_score'] = self._normalize_series(exhaustion.fill_null(0.0))
        
        # ========== SMART MONEY CONCEPT ==========
        # 20. liquidity_sweep_score: Sweep of liquidity pools (stop hunts)
        # Price makes new high/low but quickly reverses
        lookback_sweep = 10
        sweep_high = h > h.rolling_max(window_size=lookback_sweep, min_periods=1).shift(1)
        sweep_low = l < l.rolling_min(window_size=lookback_sweep, min_periods=1).shift(1)
        # Reversal close: close back inside previous range
        prev_high = h.shift(1)
        prev_low = l.shift(1)
        reversal = (c < prev_high) & (c > prev_low)
        liq_sweep = (sweep_high | sweep_low) & reversal
        features['liquidity_sweep_score'] = self._normalize_series(liq_sweep.cast(pl.Float64).fill_null(0.0))
        
        # 21. order_block_strength: Strength of order block (imbalance after strong move)
        # Look for large candles with high volume that are not fully retraced
        body_size = (c - o).abs()
        avg_body = body_size.rolling_mean(window_size=20, min_periods=1)
        large_body = body_size > (avg_body * 2.0)
        # Check if price has returned to midpoint of large candle
        mid_point = (o + c) / 2.0
        returned = pl.abs(c - mid_point) < (body_size * 0.3)
        ob_strength = large_body.cast(pl.Float64) * (~returned).cast(pl.Float64)
        features['order_block_strength'] = self._normalize_series(ob_strength.fill_null(0.0))
        
        # 22. imbalance_score: Fair Value Gap (FVG) detection
        # Three-candle pattern with gap between candles 1 and 3
        bullish_fvg = (l.shift(2) > h.shift(1))  # Gap up
        bearish_fvg = (h.shift(2) < l.shift(1))  # Gap down
        # Gap size normalized by ATR
        atr_14 = self._calculate_atr(df, 14)
        gap_size_up = pl.when(bullish_fvg & (atr_14 > 1e-8)).then((l.shift(2) - h.shift(1)) / atr_14).otherwise(0.0)
        gap_size_dn = pl.when(bearish_fvg & (atr_14 > 1e-8)).then((h.shift(2) - l.shift(1)) / atr_14).otherwise(0.0)
        imbalance = gap_size_up - gap_size_dn  # Positive = bullish FVG
        features['imbalance_score'] = self._normalize_series(imbalance.fill_null(0.0))
        
        # ========== VOLATILITY / RANGE ==========
        # 23. range_compression: Low volatility environment
        # ATR relative to historical average
        atr_current = self._calculate_atr(df, 14)
        atr_ma = atr_current.rolling_mean(window_size=50, min_periods=1)
        range_comp = pl.when(atr_ma > 1e-8).then(1.0 - (atr_current / atr_ma)).otherwise(0.0)  # Invert so low ATR = high score
        features['range_compression'] = self._normalize_series(range_comp.fill_null(0.0))
        
        # 24. expansion_score: Volatility expansion
        # Current ATR vs short-term average
        atr_short = self._calculate_atr(df, 7)
        atr_long = self._calculate_atr(df, 30)
        expansion = pl.when(atr_long > 1e-8).then(atr_short / atr_long).otherwise(1.0)
        features['expansion_score'] = self._normalize_series(expansion.fill_null(1.0))
        
        # 25. ATR_normalized_move: Today's move normalized by ATR
        true_range = pl.max(
            h - l,
            pl.abs(h - c.shift(1)),
            pl.abs(l - c.shift(1))
        )
        atr_norm = true_range.rolling_mean(window_size=14, min_periods=1)
        normalized_move = pl.when(atr_norm > 1e-8).then((c - o).abs() / atr_norm).otherwise(0.0)
        features['ATR_normalized_move'] = self._normalize_series(normalized_move.fill_null(0.0))
        
        # ========== MULTI-TIMEFRAME (simulated via rolling windows) ==========
        # 26. HTF_trend_alignment: Alignment with higher timeframe trend
        # Simulate HTF using 50-period EMA as trend filter
        htf_ema = c.ewm_mean(span=50)
        ltf_ema = c.ewm_mean(span=20)
        # Alignment: price above both EMAs (uptrend) or below both (downtrend)
        aligned_up = (c > htf_ema) & (c > ltf_ema)
        aligned_dn = (c < htf_ema) & (c < ltf_ema)
        htf_alignment = aligned_up.cast(pl.Float64) - aligned_dn.cast(pl.Float64)
        features['HTF_trend_alignment'] = self._normalize_series(htf_alignment.fill_null(0.0))
        
        # 27. LTF_entry_precision: Precision of entry on lower timeframe
        # Simulate using intrabar strength (how close close is to extreme)
        # In uptrend: preference for closes near high; downtrend: near low
        position_in_range = pl.when(total_range > 1e-8).then((c - l) / total_range).otherwise(0.5)  # 0=low, 1=high
        trend_dir = (htf_ema - htf_ema.shift(10)).sign()  # HTF momentum
        # For uptrend trend, we want high position_in_range; for downtrend, low
        ltf_precision = pl.when(trend_dir > 0) \
                        .then(position_in_range - 0.5) \
                        .when(trend_dir < 0) \
                        .then(0.5 - position_in_range) \
                        .otherwise(0.0)
        features['LTF_entry_precision'] = self._normalize_series(ltf_precision.fill_null(0.0))
        
        return features
    
    def _calculate_atr(self, df: pl.DataFrame, window: int) -> pl.Series:
        """Calculate Average True Range."""
        h = df['high']
        l = df['low']
        c = df['close']
        
        tr1 = h - l
        tr2 = (h - c.shift(1)).abs()
        tr3 = (l - c.shift(1)).abs()
        tr = pl.max(tr1, pl.max(tr2, tr3))
        atr = tr.rolling_mean(window_size=window, min_periods=1)
        return atr.fill_null(0.0)
    
    def _normalize_series(self, s: pl.Series) -> pl.Series:
        """Normalize series using robust normalization and handle edge cases."""
        if s.len() == 0:
            return s
        # Convert to numpy for calculation
        s_np = s.to_numpy()
        # Use median and IQR for robustness to outliers
        median = np.nanmedian(s_np)
        q1 = np.nanpercentile(s_np, 25)
        q3 = np.nanpercentile(s_np, 75)
        iqr = q3 - q1
        # Avoid division by zero
        if iqr < 1e-8:
            return pl.zeros_like(s)
        normalized = (s_np - median) / iqr
        # Replace any NaNs or infs
        normalized = np.nan_to_num(normalized, nan=0.0, posinf=0.0, neginf=0.0)
        return pl.Series(normalized)
    
    async def generate(self, market_data: MarketData) -> AlphaOutput:
        """
        Generate alpha values from a single market data tick by updating the buffer
        and computing features when enough historical data is available.
        
        Args:
            market_data: Market data tick
            
        Returns:
            AlphaOutput containing the latest alpha values
        """
        # Add the new market data to the buffer
        self.buffer.append({
            'timestamp': market_data.timestamp,
            'open': float(market_data.open),
            'high': float(market_data.high),
            'low': float(market_data.low),
            'close': float(market_data.close),
            'volume': float(market_data.volume)
        })
        
        # Keep buffer size within limits
        if len(self.buffer) > self.max_history:
            self.buffer = self.buffer[-self.max_history:]
        
        # If we don't have enough history, return empty alpha values
        if len(self.buffer) < self.min_history:
            # Return AlphaOutput with empty alpha_values or zeros? We'll return zeros for safety.
            # But note: the AlphaOutput expects a dict of alpha values.
            # We can return an empty dict, but that might break downstream.
            # Instead, we return zeros for all features? But we don't know the feature names yet.
            # We'll return an empty AlphaOutput and let the orchestrator handle it? 
            # However, the orchestrator expects alpha values.
            # We'll return an AlphaOutput with an empty dict for alpha_values.
            return AlphaOutput(
                symbol=market_data.symbol,
                timestamp=market_data.timestamp,
                alpha_values={},
                metadata={"reason": "Insufficient history"}
            )
        
        # Convert buffer to DataFrame
        df = pl.DataFrame(self.buffer)
        
        # Compute features
        features_dict = self.compute(df)
        
        # Extract the latest value for each feature
        alpha_values = {}
        for feature_name, series in features_dict.items():
            # Get the last value
            last_value = series.tail(1).item()
            alpha_values[feature_name] = last_value
        
        return AlphaOutput(
            symbol=market_data.symbol,
            timestamp=market_data.timestamp,
            alpha_values=alpha_values,
            metadata={"generator": "CandleAlphaEngine", "history_length": len(self.buffer)}
        )
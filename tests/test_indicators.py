"""
Tests for WolfStrategyV1 indicator calculations.
"""

import numpy as np
import pandas as pd
import pytest


class TestPopulateIndicators:
    """Test populate_indicators method."""

    def test_donchian_channels_present(self, strategy, sample_dataframe):
        """Donchian upper, lower, mid must be computed."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'dc_upper' in df.columns
        assert 'dc_lower' in df.columns
        assert 'dc_mid' in df.columns

    def test_donchian_upper_is_rolling_max(self, strategy, sample_dataframe):
        """dc_upper must equal rolling max of highs."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        period = strategy.donchian_period.value
        expected = sample_dataframe['high'].rolling(window=period).max()
        pd.testing.assert_series_equal(df['dc_upper'], expected, check_names=False)

    def test_donchian_lower_is_rolling_min(self, strategy, sample_dataframe):
        """dc_lower must equal rolling min of lows."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        period = strategy.donchian_period.value
        expected = sample_dataframe['low'].rolling(window=period).min()
        pd.testing.assert_series_equal(df['dc_lower'], expected, check_names=False)

    def test_donchian_mid_is_average(self, strategy, sample_dataframe):
        """dc_mid = (dc_upper + dc_lower) / 2."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        expected = (df['dc_upper'] + df['dc_lower']) / 2
        pd.testing.assert_series_equal(df['dc_mid'], expected, check_names=False)

    def test_rsi_present_and_bounded(self, strategy, sample_dataframe):
        """RSI must exist and be between 0 and 100."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'rsi' in df.columns
        valid_rsi = df['rsi'].dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()

    def test_atr_present(self, strategy, sample_dataframe):
        """ATR and ATR% must exist."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'atr' in df.columns
        assert 'atr_pct' in df.columns
        valid_atr = df['atr'].dropna()
        assert (valid_atr >= 0).all()

    def test_ema_trend_filter(self, strategy, uptrend_dataframe):
        """In uptrend data, ema_fast should mostly be above ema_slow."""
        df = strategy.populate_indicators(uptrend_dataframe, {'pair': 'BTC/USDT'})
        assert 'ema_fast' in df.columns
        assert 'ema_slow' in df.columns
        assert 'uptrend' in df.columns
        # In later candles of uptrend, should be True more often than not
        late = df.iloc[-50:]
        uptrend_pct = late['uptrend'].sum() / len(late)
        assert uptrend_pct > 0.5, f"Expected mostly uptrend, got {uptrend_pct:.0%}"

    def test_macd_present(self, strategy, sample_dataframe):
        """MACD, signal, and histogram must exist."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'macd' in df.columns
        assert 'macd_signal' in df.columns
        assert 'macd_hist' in df.columns

    def test_bollinger_bands_present(self, strategy, sample_dataframe):
        """BB upper, lower, mid, and %B must exist."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'bb_upper' in df.columns
        assert 'bb_lower' in df.columns
        assert 'bb_mid' in df.columns
        assert 'bb_pctb' in df.columns

    def test_bollinger_pctb_bounded(self, strategy, sample_dataframe):
        """BB %B should mostly be between -0.5 and 1.5 (some outliers ok)."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        valid = df['bb_pctb'].dropna()
        assert (valid > -1.0).all(), "BB %B has extreme negative values"
        assert (valid < 2.0).all(), "BB %B has extreme positive values"

    def test_volume_analysis(self, strategy, sample_dataframe):
        """Volume SMA and ratio must exist."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'volume_sma' in df.columns
        assert 'volume_ratio' in df.columns
        valid = df['volume_ratio'].dropna()
        assert (valid > 0).all()

    def test_vwap_present(self, strategy, sample_dataframe):
        """VWAP must exist and be positive."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'vwap' in df.columns
        valid = df['vwap'].dropna()
        assert (valid > 0).all()

    def test_support_detection(self, strategy, sample_dataframe):
        """Support level must exist."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'support' in df.columns
        assert 'pivot_low' in df.columns

    def test_dc_position_bounded(self, strategy, sample_dataframe):
        """Donchian position should be roughly 0-1."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'dc_position' in df.columns
        valid = df['dc_position'].dropna()
        assert (valid >= -0.5).all(), "dc_position too low"
        assert (valid <= 1.5).all(), "dc_position too high"

    def test_near_dc_lower_is_boolean(self, strategy, sample_dataframe):
        """near_dc_lower must be boolean-like."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert df['near_dc_lower'].dtype == bool

    def test_bullish_reversal_patterns(self, strategy, sample_dataframe):
        """Bullish reversal signals must exist."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'hammer' in df.columns
        assert 'bullish_engulfing' in df.columns
        assert 'bullish_reversal' in df.columns
        # Reversal should be OR of hammer and engulfing
        expected = df['hammer'] | df['bullish_engulfing']
        pd.testing.assert_series_equal(df['bullish_reversal'], expected, check_names=False)

    def test_dc_breakout_down(self, strategy, sample_dataframe):
        """dc_breakout_down must be boolean."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'dc_breakout_down' in df.columns

    def test_volume_declining(self, strategy, sample_dataframe):
        """volume_declining must exist."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'volume_declining' in df.columns

    def test_candle_idx_monotonic(self, strategy, sample_dataframe):
        """candle_idx must be monotonically increasing."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        assert 'candle_idx' in df.columns
        assert df['candle_idx'].is_monotonic_increasing

    def test_no_nan_in_late_candles(self, strategy, sample_dataframe):
        """After warmup period (~200 candles), key indicators should not be NaN."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        late = df.iloc[-50:]
        key_cols = ['dc_upper', 'dc_lower', 'rsi', 'atr', 'ema_fast', 'ema_slow',
                    'macd', 'bb_upper', 'volume_sma']
        for col in key_cols:
            assert not late[col].isna().any(), f"{col} has NaN in late candles"

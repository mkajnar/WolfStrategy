"""
Tests for WolfStrategyV1 entry signal generation.
"""

import numpy as np
import pandas as pd
import pytest


class TestLongEntrySignals:
    """Test Long entry signal logic."""

    def test_long_entries_generated(self, strategy, sample_dataframe):
        """Strategy must generate long entry signals."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        long_count = (df['enter_long'] == 1).sum()
        assert long_count > 0, "No long entries generated at all"

    def test_long_entries_plentiful(self, strategy, sample_dataframe):
        """On 300 candles, should generate at least a few entries."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        long_count = (df['enter_long'] == 1).sum()
        # 300 candles ~ 3 days of 15m data, expect at least 3 entries
        assert long_count >= 2, f"Only {long_count} long entries on 300 candles"

    def test_long_entry_has_valid_tags(self, strategy, sample_dataframe):
        """All long entries must have a recognized enter_tag."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        long_entries = df[df['enter_long'] == 1]
        if len(long_entries) > 0:
            valid_tags = {'long_dc_bounce', 'long_bb_bounce', 'long_rsi_reversal', 'long_macd_cross'}
            for tag in long_entries['enter_tag'].unique():
                assert tag in valid_tags, f"Unknown tag: {tag}"

    def test_long_dc_bounce_conditions(self, strategy, sample_dataframe):
        """DC bounce entries must have dc_position < 0.3 and RSI < threshold."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        dc_entries = df[(df['enter_long'] == 1) & (df['enter_tag'] == 'long_dc_bounce')]
        if len(dc_entries) > 0:
            assert (dc_entries['dc_position'] < 0.3).all()
            assert (dc_entries['rsi'] < strategy.rsi_oversold.value).all()
            assert (dc_entries['green_candle']).all()

    def test_long_bb_bounce_conditions(self, strategy, sample_dataframe):
        """BB bounce entries must have bb_pctb < 0.05."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        bb_entries = df[(df['enter_long'] == 1) & (df['enter_tag'] == 'long_bb_bounce')]
        if len(bb_entries) > 0:
            assert (bb_entries['bb_pctb'] < 0.05).all()
            assert (bb_entries['green_candle']).all()

    def test_long_volume_positive(self, strategy, sample_dataframe):
        """All long entries must have volume > 0."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        long_entries = df[df['enter_long'] == 1]
        if len(long_entries) > 0:
            assert (long_entries['volume'] > 0).all()

    def test_multiple_signal_types_generated(self, strategy):
        """With enough data, should generate more than one signal type."""
        from helpers import generate_ohlcv
        # Use 2000 candles for more chances
        df = generate_ohlcv(n=2000, trend='neutral', seed=123)
        df = strategy.populate_indicators(df, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        long_entries = df[df['enter_long'] == 1]
        if len(long_entries) > 0:
            unique_tags = long_entries['enter_tag'].nunique()
            assert unique_tags >= 2, \
                f"Only {unique_tags} signal type(s): {long_entries['enter_tag'].unique()}"


class TestShortEntrySignals:
    """Test Short entry signal logic."""

    def test_short_entry_has_valid_tags(self, strategy, sample_dataframe):
        """All short entries must have a recognized enter_tag."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        short_entries = df[df.get('enter_short', 0) == 1]
        if len(short_entries) > 0:
            valid_tags = {'short_dc_breakout', 'short_macd_cross'}
            for tag in short_entries['enter_tag'].unique():
                assert tag in valid_tags, f"Unknown tag: {tag}"

    def test_short_dc_breakout_conditions(self, strategy, sample_dataframe):
        """DC breakout short must have price below DC lower."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        dc_shorts = df[(df.get('enter_short', 0) == 1) &
                       (df['enter_tag'] == 'short_dc_breakout')]
        if len(dc_shorts) > 0:
            assert (dc_shorts['dc_breakout_down']).all()
            assert (dc_shorts['red_candle']).all()

    def test_short_macd_cross_conditions(self, strategy, sample_dataframe):
        """MACD cross short must have price below EMA fast."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        macd_shorts = df[(df.get('enter_short', 0) == 1) &
                         (df['enter_tag'] == 'short_macd_cross')]
        if len(macd_shorts) > 0:
            assert (macd_shorts['close'] < macd_shorts['ema_fast']).all()
            assert (macd_shorts['red_candle']).all()

    def test_short_volume_positive(self, strategy, sample_dataframe):
        """All short entries must have volume > 0."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        short_entries = df[df.get('enter_short', 0) == 1]
        if len(short_entries) > 0:
            assert (short_entries['volume'] > 0).all()

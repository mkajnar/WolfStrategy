"""
Tests for WolfStrategyV1 entry signal generation.
"""

import numpy as np
import pandas as pd
import pytest


class TestLongEntrySignals:
    """Test Long entry signal logic."""

    def test_long_entry_requires_near_dc_lower(self, strategy, sample_dataframe):
        """Long entry should only fire when price is near DC lower."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        long_entries = df[df['enter_long'] == 1]
        if len(long_entries) > 0:
            # All long entries must have near_dc_lower or bb_pctb < 0.1
            for _, row in long_entries.iterrows():
                assert row['near_dc_lower'] or row.get('bb_pctb', 1.0) < 0.1, \
                    "Long entry fired without near_dc_lower or BB confirmation"

    def test_long_entry_requires_uptrend(self, strategy, sample_dataframe):
        """Long entries must have uptrend = True (EMA filter)."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        long_entries = df[df['enter_long'] == 1]
        if len(long_entries) > 0:
            assert long_entries['uptrend'].all(), \
                "Long entry fired during downtrend"

    def test_long_entry_rsi_oversold(self, strategy, sample_dataframe):
        """Long entries must have RSI below threshold."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        threshold = strategy.rsi_oversold.value
        long_entries = df[df['enter_long'] == 1]
        if len(long_entries) > 0:
            # Primary: rsi < threshold, fallback: rsi < threshold - 5
            assert (long_entries['rsi'] < threshold + 1).all(), \
                "Long entry fired with RSI above threshold"

    def test_long_entry_has_tag(self, strategy, sample_dataframe):
        """All long entries must have an enter_tag."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        long_entries = df[df['enter_long'] == 1]
        if len(long_entries) > 0:
            assert long_entries['enter_tag'].notna().all()
            valid_tags = {'long_dc_bounce', 'long_bb_dc_bounce'}
            for tag in long_entries['enter_tag'].unique():
                assert tag in valid_tags, f"Unknown tag: {tag}"

    def test_no_long_in_strong_downtrend(self, strategy, downtrend_dataframe):
        """In a strong downtrend, long entries should be rare or zero."""
        df = strategy.populate_indicators(downtrend_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        long_count = (df['enter_long'] == 1).sum()
        total = len(df)
        # Should be less than 5% of candles
        assert long_count / total < 0.05, \
            f"Too many long entries in downtrend: {long_count}/{total}"

    def test_long_volume_requirement(self, strategy, sample_dataframe):
        """Long entries must have volume > 0."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        long_entries = df[df['enter_long'] == 1]
        if len(long_entries) > 0:
            assert (long_entries['volume'] > 0).all()


class TestShortEntrySignals:
    """Test Short entry signal logic."""

    def test_short_entry_requires_dc_breakout(self, strategy, sample_dataframe):
        """Short entry should only fire on DC breakout down."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        short_entries = df[df.get('enter_short', 0) == 1]
        if len(short_entries) > 0:
            assert short_entries['dc_breakout_down'].all(), \
                "Short entry fired without DC breakout down"

    def test_short_entry_requires_macd_negative(self, strategy, sample_dataframe):
        """Short entries must have negative MACD histogram."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        short_entries = df[df.get('enter_short', 0) == 1]
        if len(short_entries) > 0:
            assert (short_entries['macd_hist'] < 0).all(), \
                "Short entry fired with positive MACD histogram"

    def test_short_entry_requires_bear_candle(self, strategy, sample_dataframe):
        """Short entries must have bear candle confirmation."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        short_entries = df[df.get('enter_short', 0) == 1]
        if len(short_entries) > 0:
            assert short_entries['bear_candle'].all(), \
                "Short entry fired without bear candle"

    def test_short_entry_price_below_ema(self, strategy, sample_dataframe):
        """Short entries must have price below EMA fast."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        short_entries = df[df.get('enter_short', 0) == 1]
        if len(short_entries) > 0:
            assert (short_entries['close'] < short_entries['ema_fast']).all(), \
                "Short entry fired with price above EMA fast"

    def test_short_entry_volume_spike(self, strategy, sample_dataframe):
        """Short entries must have volume ratio > 1.5."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        short_entries = df[df.get('enter_short', 0) == 1]
        if len(short_entries) > 0:
            assert (short_entries['volume_ratio'] > 1.5).all(), \
                "Short entry fired without volume spike"

    def test_short_entry_has_tag(self, strategy, sample_dataframe):
        """All short entries must have enter_tag = 'short_dc_breakout'."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        short_entries = df[df.get('enter_short', 0) == 1]
        if len(short_entries) > 0:
            assert (short_entries['enter_tag'] == 'short_dc_breakout').all()

    def test_short_rsi_bounds(self, strategy, sample_dataframe):
        """Short entries must have RSI between 25 and 55."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_entry_trend(df, {'pair': 'BTC/USDT'})

        short_entries = df[df.get('enter_short', 0) == 1]
        if len(short_entries) > 0:
            assert (short_entries['rsi'] > 25).all()
            assert (short_entries['rsi'] < 55).all()

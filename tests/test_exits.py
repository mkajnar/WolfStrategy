"""
Tests for WolfStrategyV1 exit signal generation and custom exit logic.
"""

import datetime
import numpy as np
import pandas as pd
import pytest

from helpers import make_mock_trade


class TestExitSignals:
    """Test populate_exit_trend signals."""

    def test_long_exit_at_dc_upper(self, strategy, sample_dataframe):
        """Long exit should fire when price near DC upper."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_exit_trend(df, {'pair': 'BTC/USDT'})

        long_exits = df[df.get('exit_long', 0) == 1]
        if len(long_exits) > 0:
            # Must be near DC upper OR RSI > 75
            for _, row in long_exits.iterrows():
                near_upper = row['close'] >= row['dc_upper'] * 0.99
                rsi_high = row['rsi'] > 75
                assert near_upper or rsi_high, \
                    "Long exit without DC upper or RSI overbought"

    def test_long_exit_has_tag(self, strategy, sample_dataframe):
        """Long exit tag must be 'long_dc_upper'."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_exit_trend(df, {'pair': 'BTC/USDT'})

        long_exits = df[df.get('exit_long', 0) == 1]
        if len(long_exits) > 0:
            assert (long_exits['exit_tag'] == 'long_dc_upper').all()

    def test_short_emergency_exit(self, strategy, sample_dataframe):
        """Short emergency exit when price > DC upper + RSI > 70."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_exit_trend(df, {'pair': 'BTC/USDT'})

        short_exits = df[df.get('exit_short', 0) == 1]
        if len(short_exits) > 0:
            assert (short_exits['close'] > short_exits['dc_upper']).all()
            assert (short_exits['rsi'] > 70).all()


class TestCustomExit:
    """Test custom_exit method (Short TP + Long partial profit)."""

    def test_short_tp_triggered(self, strategy, mock_short_trade):
        """Short TP should trigger at take profit threshold."""
        tp = strategy.short_take_profit.value
        result = strategy.custom_exit(
            pair='BTC/USDT',
            trade=mock_short_trade,
            current_time=datetime.datetime(2025, 6, 1, 12, 0),
            current_rate=95.0,
            current_profit=tp + 0.01,
        )
        assert result is not None
        assert 'short_tp' in str(result)

    def test_short_no_tp_below_threshold(self, strategy, mock_short_trade):
        """Short should NOT exit below TP threshold."""
        tp = strategy.short_take_profit.value
        result = strategy.custom_exit(
            pair='BTC/USDT',
            trade=mock_short_trade,
            current_time=datetime.datetime(2025, 6, 1, 12, 0),
            current_rate=99.0,
            current_profit=tp - 0.01,
        )
        assert result is None

    def test_long_partial_profit_triggered(self, strategy, mock_trade):
        """Long partial TP should trigger at partial_profit_pct."""
        pair = 'BTC/USDT'
        strategy.partial_profit_taken[pair] = False
        pp = strategy.partial_profit_pct.value

        result = strategy.custom_exit(
            pair=pair,
            trade=mock_trade,
            current_time=datetime.datetime(2025, 6, 1, 12, 0),
            current_rate=103.0,
            current_profit=pp + 0.01,
        )
        assert result is not None
        assert 'partial_tp' in str(result)
        assert strategy.partial_profit_taken[pair] is True

    def test_long_partial_profit_only_once(self, strategy, mock_trade):
        """Partial TP should only fire once per trade."""
        pair = 'BTC/USDT'
        strategy.partial_profit_taken[pair] = True  # already taken
        pp = strategy.partial_profit_pct.value

        result = strategy.custom_exit(
            pair=pair,
            trade=mock_trade,
            current_time=datetime.datetime(2025, 6, 1, 12, 0),
            current_rate=105.0,
            current_profit=pp + 0.02,
        )
        assert result is None

    def test_long_no_exit_below_partial(self, strategy, mock_trade):
        """Long should not custom-exit below partial profit threshold."""
        pair = 'BTC/USDT'
        strategy.partial_profit_taken[pair] = False

        result = strategy.custom_exit(
            pair=pair,
            trade=mock_trade,
            current_time=datetime.datetime(2025, 6, 1, 12, 0),
            current_rate=100.5,
            current_profit=0.005,
        )
        assert result is None

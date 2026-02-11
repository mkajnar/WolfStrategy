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

    def test_long_exit_signals_generated(self, strategy, sample_dataframe):
        """Must generate some long exit signals."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_exit_trend(df, {'pair': 'BTC/USDT'})

        exit_count = (df.get('exit_long', 0) == 1).sum()
        assert exit_count > 0, "No long exit signals generated"

    def test_long_exit_has_valid_tags(self, strategy, sample_dataframe):
        """Long exit tags must be recognized."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_exit_trend(df, {'pair': 'BTC/USDT'})

        exits = df[df.get('exit_long', 0) == 1]
        if len(exits) > 0:
            valid_tags = {'long_dc_upper', 'long_rsi_overbought', 'long_macd_exit'}
            for tag in exits['exit_tag'].unique():
                assert tag in valid_tags, f"Unknown exit tag: {tag}"

    def test_short_emergency_exit(self, strategy, sample_dataframe):
        """Short emergency exit when price > DC upper."""
        df = strategy.populate_indicators(sample_dataframe, {'pair': 'BTC/USDT'})
        df = strategy.populate_exit_trend(df, {'pair': 'BTC/USDT'})

        short_exits = df[df.get('exit_short', 0) == 1]
        if len(short_exits) > 0:
            assert (short_exits['close'] > short_exits['dc_upper']).all()


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
        strategy.partial_profit_taken[pair] = True
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

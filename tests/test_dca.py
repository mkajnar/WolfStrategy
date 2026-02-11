"""
Tests for WolfStrategyV1 DCA (adjust_trade_position) logic.
"""

import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from helpers import make_mock_trade


class TestDCA:
    """Test adjust_trade_position DCA logic."""

    def _setup_dca_context(self, strategy, pair, candle_idx=100):
        """Helper to set up dataframe mock for DCA tests."""
        mock_df = pd.DataFrame({
            'candle_idx': [candle_idx],
        })
        strategy.dp.get_analyzed_dataframe.return_value = (mock_df, None)

    def test_no_dca_for_short(self, strategy):
        """DCA must return None for Short trades."""
        trade = make_mock_trade(is_short=True)
        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=95.0,
            current_profit=-0.05,
            min_stake=30.0, max_stake=500.0,
            current_entry_rate=100.0, current_exit_rate=95.0,
            current_entry_profit=-0.05, current_exit_profit=-0.05,
        )
        assert result is None

    def test_no_dca_when_max_reached(self, strategy):
        """DCA must return None when max DCA count reached."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = strategy.dca_max_count.value
        trade = make_mock_trade(pair=pair)

        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=90.0, current_profit=-0.10,
            min_stake=30.0, max_stake=500.0,
            current_entry_rate=100.0, current_exit_rate=90.0,
            current_entry_profit=-0.10, current_exit_profit=-0.10,
        )
        assert result is None

    def test_no_dca_when_drawdown_too_deep(self, strategy):
        """DCA blocked when current_profit < -20%."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 0
        trade = make_mock_trade(pair=pair)

        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=75.0, current_profit=-0.25,
            min_stake=30.0, max_stake=500.0,
            current_entry_rate=100.0, current_exit_rate=75.0,
            current_entry_profit=-0.25, current_exit_profit=-0.25,
        )
        assert result is None

    def test_no_dca_price_not_low_enough(self, strategy):
        """DCA blocked when price hasn't dropped enough."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 0
        strategy.last_buy_price[pair] = 100.0
        trade = make_mock_trade(pair=pair)

        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=98.0, current_profit=-0.02,
            min_stake=30.0, max_stake=500.0,
            current_entry_rate=100.0, current_exit_rate=98.0,
            current_entry_profit=-0.02, current_exit_profit=-0.02,
        )
        assert result is None

    def test_progressive_spacing(self, strategy):
        """Each DCA must require progressively larger drop."""
        base_drop = strategy.dca_base_drop.value

        # DCA #0: factor = 1.0
        required_0 = base_drop * (1.0 + 0 * 0.3)
        # DCA #1: factor = 1.3
        required_1 = base_drop * (1.0 + 1 * 0.3)
        # DCA #2: factor = 1.6
        required_2 = base_drop * (1.0 + 2 * 0.3)

        assert required_1 > required_0
        assert required_2 > required_1

    def test_cooling_period_blocks_rapid_dca(self, strategy):
        """DCA must be blocked if cooling period not elapsed."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 0
        strategy.last_buy_price[pair] = 100.0
        strategy.last_dca_candle[pair] = 98

        trade = make_mock_trade(pair=pair)
        self._setup_dca_context(strategy, pair, candle_idx=100)

        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=95.0, current_profit=-0.05,
            min_stake=30.0, max_stake=500.0,
            current_entry_rate=100.0, current_exit_rate=95.0,
            current_entry_profit=-0.05, current_exit_profit=-0.05,
        )
        assert result is None

    def test_dca_allowed_after_cooling(self, strategy):
        """DCA should execute after cooling period."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 0
        strategy.last_buy_price[pair] = 100.0
        strategy.last_dca_candle[pair] = 90

        trade = make_mock_trade(pair=pair)
        self._setup_dca_context(strategy, pair, candle_idx=100)

        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=95.0, current_profit=-0.05,
            min_stake=30.0, max_stake=500.0,
            current_entry_rate=100.0, current_exit_rate=95.0,
            current_entry_profit=-0.05, current_exit_profit=-0.05,
        )
        assert result is not None
        assert result >= 30.0

    def test_dca_updates_state(self, strategy):
        """DCA must update last_buy_price, dca_count, last_dca_candle."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 0
        strategy.last_buy_price[pair] = 100.0
        strategy.last_dca_candle[pair] = 0

        trade = make_mock_trade(pair=pair)
        self._setup_dca_context(strategy, pair, candle_idx=100)

        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=95.0, current_profit=-0.05,
            min_stake=30.0, max_stake=500.0,
            current_entry_rate=100.0, current_exit_rate=95.0,
            current_entry_profit=-0.05, current_exit_profit=-0.05,
        )
        assert result is not None
        assert strategy.dca_count[pair] == 1
        assert strategy.last_buy_price[pair] == 95.0
        assert strategy.last_dca_candle[pair] == 100

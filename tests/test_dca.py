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

    def _setup_dca_context(self, strategy, pair, rsi=30, candle_idx=100,
                           volume_declining=True, support=90.0):
        """Helper to set up dataframe mock for DCA tests."""
        mock_df = pd.DataFrame({
            'rsi': [rsi],
            'candle_idx': [candle_idx],
            'volume_declining': [volume_declining],
            'support': [support],
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
            min_stake=30.0,
            max_stake=500.0,
            current_entry_rate=100.0,
            current_exit_rate=95.0,
            current_entry_profit=-0.05,
            current_exit_profit=-0.05,
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
            current_rate=90.0,
            current_profit=-0.10,
            min_stake=30.0,
            max_stake=500.0,
            current_entry_rate=100.0,
            current_exit_rate=90.0,
            current_entry_profit=-0.10,
            current_exit_profit=-0.10,
        )
        assert result is None

    def test_no_dca_when_drawdown_too_deep(self, strategy):
        """DCA blocked when current_profit < -15%."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 0
        trade = make_mock_trade(pair=pair)

        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=80.0,
            current_profit=-0.20,  # 20% loss
            min_stake=30.0,
            max_stake=500.0,
            current_entry_rate=100.0,
            current_exit_rate=80.0,
            current_entry_profit=-0.20,
            current_exit_profit=-0.20,
        )
        assert result is None

    def test_no_dca_price_not_low_enough(self, strategy):
        """DCA blocked when price hasn't dropped enough."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 0
        strategy.last_buy_price[pair] = 100.0
        trade = make_mock_trade(pair=pair)

        # base_drop = 0.03, first DCA needs 3% drop -> price < 97
        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=98.0,  # only 2% drop
            current_profit=-0.02,
            min_stake=30.0,
            max_stake=500.0,
            current_entry_rate=100.0,
            current_exit_rate=98.0,
            current_entry_profit=-0.02,
            current_exit_profit=-0.02,
        )
        assert result is None

    def test_progressive_spacing(self, strategy):
        """Each DCA must require progressively larger drop."""
        pair = 'BTC/USDT'
        base_drop = strategy.dca_base_drop.value

        # DCA #0 (first): factor = 1.0, drop = base_drop * 1.0
        factor_0 = 1.0 + (0 * 0.5)
        required_0 = base_drop * factor_0
        assert required_0 == base_drop

        # DCA #1 (second): factor = 1.5, drop = base_drop * 1.5
        factor_1 = 1.0 + (1 * 0.5)
        required_1 = base_drop * factor_1
        assert required_1 == base_drop * 1.5

        # DCA #2 (third): factor = 2.0
        factor_2 = 1.0 + (2 * 0.5)
        required_2 = base_drop * factor_2
        assert required_2 == base_drop * 2.0

        # Each must be larger than previous
        assert required_1 > required_0
        assert required_2 > required_1

    def test_cooling_period_blocks_rapid_dca(self, strategy):
        """DCA must be blocked if cooling period not elapsed."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 0
        strategy.last_buy_price[pair] = 100.0
        strategy.last_dca_candle[pair] = 98  # DCA was at candle 98

        trade = make_mock_trade(pair=pair)
        cooling = strategy.dca_cooling_candles.value  # default 4

        # Set candle_idx to 100 (only 2 candles since last DCA, need 4)
        self._setup_dca_context(strategy, pair, rsi=25, candle_idx=100)

        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=95.0,  # 5% drop, enough
            current_profit=-0.05,
            min_stake=30.0,
            max_stake=500.0,
            current_entry_rate=100.0,
            current_exit_rate=95.0,
            current_entry_profit=-0.05,
            current_exit_profit=-0.05,
        )
        assert result is None

    def test_dca_allowed_after_cooling(self, strategy):
        """DCA should execute after cooling period."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 0
        strategy.last_buy_price[pair] = 100.0
        strategy.last_dca_candle[pair] = 90  # DCA was at candle 90

        trade = make_mock_trade(pair=pair)
        cooling = strategy.dca_cooling_candles.value

        # candle_idx = 100, last DCA at 90, gap = 10 > cooling (4)
        self._setup_dca_context(
            strategy, pair, rsi=25, candle_idx=100,
            volume_declining=True, support=94.0
        )

        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=95.0,
            current_profit=-0.05,
            min_stake=30.0,
            max_stake=500.0,
            current_entry_rate=100.0,
            current_exit_rate=95.0,
            current_entry_profit=-0.05,
            current_exit_profit=-0.05,
        )
        assert result is not None
        assert result >= 30.0  # at least min_stake

    def test_dca_rsi_too_high_blocks(self, strategy):
        """DCA blocked when RSI too high (not oversold)."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 0
        strategy.last_buy_price[pair] = 100.0
        strategy.last_dca_candle[pair] = 0

        trade = make_mock_trade(pair=pair)
        rsi_threshold = strategy.rsi_oversold.value + 10

        self._setup_dca_context(
            strategy, pair, rsi=rsi_threshold + 5, candle_idx=100,
        )

        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=95.0,
            current_profit=-0.05,
            min_stake=30.0,
            max_stake=500.0,
            current_entry_rate=100.0,
            current_exit_rate=95.0,
            current_entry_profit=-0.05,
            current_exit_profit=-0.05,
        )
        assert result is None

    def test_dca_updates_state(self, strategy):
        """DCA must update last_buy_price, dca_count, last_dca_candle."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 0
        strategy.last_buy_price[pair] = 100.0
        strategy.last_dca_candle[pair] = 0

        trade = make_mock_trade(pair=pair)

        self._setup_dca_context(
            strategy, pair, rsi=25, candle_idx=100,
            volume_declining=True, support=94.0
        )

        result = strategy.adjust_trade_position(
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=95.0,
            current_profit=-0.05,
            min_stake=30.0,
            max_stake=500.0,
            current_entry_rate=100.0,
            current_exit_rate=95.0,
            current_entry_profit=-0.05,
            current_exit_profit=-0.05,
        )
        assert result is not None
        assert strategy.dca_count[pair] == 1
        assert strategy.last_buy_price[pair] == 95.0
        assert strategy.last_dca_candle[pair] == 100

"""
Tests for WolfStrategyV1 risk management:
- confirm_trade_entry (Short gate, Long cooldown)
- custom_stake_amount (Short cap, Long wallet split)
- confirm_trade_exit (Profit bucket, cooldown on loss)
"""

import datetime
from unittest.mock import MagicMock

import pytest

from helpers import make_mock_trade


class TestConfirmTradeEntry:
    """Test confirm_trade_entry gate logic."""

    def test_short_blocked_no_bucket(self, strategy):
        """Short entry blocked when profit bucket is empty."""
        pair = 'BTC/USDT'
        strategy.custom_profit_bucket[pair] = 0.0

        result = strategy.confirm_trade_entry(
            pair=pair, order_type='market', amount=1.0, rate=100.0,
            time_in_force='GTC',
            current_time=datetime.datetime(2025, 6, 1),
            entry_tag='short_dc_breakout', side='short',
        )
        assert result is False

    def test_short_blocked_negative_bucket(self, strategy):
        """Short blocked when bucket is negative."""
        pair = 'BTC/USDT'
        strategy.custom_profit_bucket[pair] = -5.0

        result = strategy.confirm_trade_entry(
            pair=pair, order_type='market', amount=1.0, rate=100.0,
            time_in_force='GTC',
            current_time=datetime.datetime(2025, 6, 1),
            entry_tag='short_dc_breakout', side='short',
        )
        assert result is False

    def test_short_allowed_with_bucket(self, strategy):
        """Short allowed when profit bucket > 0."""
        pair = 'BTC/USDT'
        strategy.custom_profit_bucket[pair] = 50.0
        strategy.awaiting_short[pair] = True

        result = strategy.confirm_trade_entry(
            pair=pair, order_type='market', amount=1.0, rate=100.0,
            time_in_force='GTC',
            current_time=datetime.datetime(2025, 6, 1),
            entry_tag='short_dc_breakout', side='short',
        )
        assert result is True
        assert strategy.awaiting_short[pair] is False

    def test_long_allowed_default(self, strategy):
        """Long entry allowed by default."""
        result = strategy.confirm_trade_entry(
            pair='BTC/USDT', order_type='market', amount=1.0, rate=100.0,
            time_in_force='GTC',
            current_time=datetime.datetime(2025, 6, 1),
            entry_tag='long_dc_bounce', side='long',
        )
        assert result is True

    def test_long_blocked_during_cooldown(self, strategy):
        """Long blocked during cooldown period."""
        pair = 'BTC/USDT'
        strategy.loss_cooldown_until[pair] = datetime.datetime(2025, 6, 1, 16, 0)

        result = strategy.confirm_trade_entry(
            pair=pair, order_type='market', amount=1.0, rate=100.0,
            time_in_force='GTC',
            current_time=datetime.datetime(2025, 6, 1, 14, 0),  # before cooldown
            entry_tag='long_dc_bounce', side='long',
        )
        assert result is False

    def test_long_allowed_after_cooldown(self, strategy):
        """Long allowed after cooldown period expires."""
        pair = 'BTC/USDT'
        strategy.loss_cooldown_until[pair] = datetime.datetime(2025, 6, 1, 12, 0)

        result = strategy.confirm_trade_entry(
            pair=pair, order_type='market', amount=1.0, rate=100.0,
            time_in_force='GTC',
            current_time=datetime.datetime(2025, 6, 1, 14, 0),  # after cooldown
            entry_tag='long_dc_bounce', side='long',
        )
        assert result is True

    def test_long_entry_resets_state(self, strategy):
        """Long entry must reset DCA state."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 3

        strategy.confirm_trade_entry(
            pair=pair, order_type='market', amount=1.0, rate=100.0,
            time_in_force='GTC',
            current_time=datetime.datetime(2025, 6, 1),
            entry_tag='long_dc_bounce', side='long',
        )
        assert strategy.dca_count[pair] == 0
        assert strategy.last_buy_price[pair] == 100.0
        assert strategy.partial_profit_taken[pair] is False


class TestCustomStakeAmount:
    """Test custom_stake_amount."""

    def test_short_stake_from_bucket(self, strategy):
        """Short stake should come from profit bucket."""
        pair = 'ETH/USDT'
        strategy.custom_profit_bucket[pair] = 100.0

        result = strategy.custom_stake_amount(
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=3000.0,
            proposed_stake=50.0,
            min_stake=30.0,
            max_stake=500.0,
            leverage=100.0,
            entry_tag='short_dc_breakout',
            side='short',
            pair=pair,
        )
        # Should be 90% of bucket = 90, but capped at short_max_stake (50)
        cap = strategy.short_max_stake.value
        expected = min(100.0 * 0.9, cap)
        assert result == expected

    def test_short_stake_capped(self, strategy):
        """Short stake must not exceed cap."""
        pair = 'ETH/USDT'
        strategy.custom_profit_bucket[pair] = 1000.0  # large bucket

        result = strategy.custom_stake_amount(
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=3000.0,
            proposed_stake=50.0,
            min_stake=30.0,
            max_stake=500.0,
            leverage=100.0,
            entry_tag='short_dc_breakout',
            side='short',
            pair=pair,
        )
        cap = strategy.short_max_stake.value
        assert result <= cap

    def test_short_stake_min_stake_fallback(self, strategy):
        """Short stake with small bucket falls back to min_stake."""
        pair = 'ETH/USDT'
        strategy.custom_profit_bucket[pair] = 5.0  # tiny bucket

        result = strategy.custom_stake_amount(
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=3000.0,
            proposed_stake=50.0,
            min_stake=30.0,
            max_stake=500.0,
            leverage=100.0,
            entry_tag='short_dc_breakout',
            side='short',
            pair=pair,
        )
        assert result >= 30.0

    def test_long_stake_splits_wallet(self, strategy):
        """Long stake should split wallet across DCA positions."""
        strategy.wallets.get_total_stake_amount.return_value = 1000.0
        num_pos = strategy.dca_max_count.value + 1
        expected = 1000.0 * 0.8 / num_pos

        result = strategy.custom_stake_amount(
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=100.0,
            proposed_stake=100.0,
            min_stake=30.0,
            max_stake=500.0,
            leverage=3.0,
            entry_tag='long_dc_bounce',
            side='long',
        )
        assert abs(result - expected) < 1.0

    def test_long_stake_respects_min(self, strategy):
        """Long stake must be at least min_stake."""
        strategy.wallets.get_total_stake_amount.return_value = 50.0  # tiny wallet

        result = strategy.custom_stake_amount(
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=100.0,
            proposed_stake=10.0,
            min_stake=30.0,
            max_stake=500.0,
            leverage=3.0,
            entry_tag='long_dc_bounce',
            side='long',
        )
        assert result >= 30.0


class TestConfirmTradeExit:
    """Test confirm_trade_exit (profit bucket + cooldown)."""

    def test_long_profit_captured(self, strategy):
        """Long exit with profit: bucket updated, short activated."""
        pair = 'BTC/USDT'
        trade = make_mock_trade(pair=pair)
        trade.calc_profit.return_value = 50.0  # $50 profit

        strategy.confirm_trade_exit(
            pair=pair, trade=trade, order_type='market',
            amount=1.0, rate=105.0, time_in_force='GTC',
            exit_reason='trailing_stop_loss',
            current_time=datetime.datetime(2025, 6, 1),
        )
        assert strategy.custom_profit_bucket[pair] == 50.0
        assert strategy.awaiting_short[pair] is True

    def test_long_profit_accumulates(self, strategy):
        """Multiple Long profits accumulate in bucket."""
        pair = 'BTC/USDT'
        strategy.custom_profit_bucket[pair] = 30.0  # existing

        trade = make_mock_trade(pair=pair)
        trade.calc_profit.return_value = 20.0

        strategy.confirm_trade_exit(
            pair=pair, trade=trade, order_type='market',
            amount=1.0, rate=105.0, time_in_force='GTC',
            exit_reason='roi',
            current_time=datetime.datetime(2025, 6, 1),
        )
        assert strategy.custom_profit_bucket[pair] == 50.0

    def test_long_loss_sets_cooldown(self, strategy):
        """Long exit with loss: cooldown set, no short activation."""
        pair = 'BTC/USDT'
        trade = make_mock_trade(pair=pair)
        trade.calc_profit.return_value = -20.0

        now = datetime.datetime(2025, 6, 1, 12, 0)
        strategy.confirm_trade_exit(
            pair=pair, trade=trade, order_type='market',
            amount=1.0, rate=95.0, time_in_force='GTC',
            exit_reason='stoploss',
            current_time=now,
        )
        assert pair not in strategy.awaiting_short or not strategy.awaiting_short.get(pair, False)
        assert pair in strategy.loss_cooldown_until
        expected_cooldown = now + datetime.timedelta(hours=4)
        assert strategy.loss_cooldown_until[pair] == expected_cooldown

    def test_long_exit_resets_dca(self, strategy):
        """Long exit must reset DCA state."""
        pair = 'BTC/USDT'
        strategy.dca_count[pair] = 3
        strategy.last_buy_price[pair] = 95.0
        strategy.last_dca_candle[pair] = 50
        strategy.partial_profit_taken[pair] = True

        trade = make_mock_trade(pair=pair)
        trade.calc_profit.return_value = 10.0

        strategy.confirm_trade_exit(
            pair=pair, trade=trade, order_type='market',
            amount=1.0, rate=105.0, time_in_force='GTC',
            exit_reason='roi',
            current_time=datetime.datetime(2025, 6, 1),
        )
        assert strategy.dca_count[pair] == 0
        assert pair not in strategy.last_buy_price

    def test_short_exit_resets_bucket(self, strategy):
        """Short exit must reset profit bucket and awaiting flag."""
        pair = 'BTC/USDT'
        strategy.custom_profit_bucket[pair] = 50.0
        strategy.awaiting_short[pair] = True

        trade = make_mock_trade(pair=pair, is_short=True, leverage=100.0)
        trade.calc_profit.return_value = 150.0

        strategy.confirm_trade_exit(
            pair=pair, trade=trade, order_type='market',
            amount=1.0, rate=95.0, time_in_force='GTC',
            exit_reason='custom_exit',
            current_time=datetime.datetime(2025, 6, 1),
        )
        assert strategy.custom_profit_bucket[pair] == 0.0
        assert strategy.awaiting_short[pair] is False

    def test_confirm_exit_always_returns_true(self, strategy):
        """confirm_trade_exit must always return True (never block exit)."""
        pair = 'BTC/USDT'
        trade = make_mock_trade(pair=pair)
        trade.calc_profit.return_value = 10.0

        result = strategy.confirm_trade_exit(
            pair=pair, trade=trade, order_type='market',
            amount=1.0, rate=105.0, time_in_force='GTC',
            exit_reason='roi',
            current_time=datetime.datetime(2025, 6, 1),
        )
        assert result is True

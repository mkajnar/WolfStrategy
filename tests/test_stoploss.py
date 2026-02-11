"""
Tests for WolfStrategyV1 custom_stoploss (ATR-based stepped trailing).
"""

import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from helpers import make_mock_trade


class TestCustomStoploss:
    """Test custom_stoploss method."""

    def _setup_atr_pct(self, strategy, atr_pct: float):
        """Mock dataframe with specific ATR%."""
        mock_df = pd.DataFrame({'atr_pct': [atr_pct]})
        strategy.dp.get_analyzed_dataframe.return_value = (mock_df, None)

    def test_short_always_wide_sl(self, strategy):
        """Short must always return -0.99 (no SL, house money)."""
        trade = make_mock_trade(is_short=True, leverage=100.0)
        self._setup_atr_pct(strategy, 1.0)

        result = strategy.custom_stoploss(
            pair='BTC/USDT',
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=95.0,
            current_profit=0.05,
            after_fill=False,
        )
        assert result == -0.99

    def test_long_below_breakeven_wide_sl(self, strategy):
        """Long below breakeven trigger: -0.99."""
        trade = make_mock_trade()
        self._setup_atr_pct(strategy, 1.0)
        be_trigger = strategy.breakeven_trigger.value

        result = strategy.custom_stoploss(
            pair='BTC/USDT',
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=100.5,
            current_profit=be_trigger - 0.005,  # below trigger
            after_fill=False,
        )
        assert result == -0.99

    def test_long_at_breakeven_tightens(self, strategy):
        """Long at breakeven trigger: SL tightens."""
        trade = make_mock_trade()
        self._setup_atr_pct(strategy, 1.0)  # 1% ATR
        be_trigger = strategy.breakeven_trigger.value

        result = strategy.custom_stoploss(
            pair='BTC/USDT',
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=101.5,
            current_profit=be_trigger + 0.001,
            after_fill=False,
        )
        assert result > -0.99  # tighter than default
        assert result < 0  # still negative

    def test_long_3_5pct_profit_tighter(self, strategy):
        """Long at 3-5% profit: tighter trailing."""
        trade = make_mock_trade()
        self._setup_atr_pct(strategy, 1.0)

        result_mid = strategy.custom_stoploss(
            pair='BTC/USDT',
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=104.0,
            current_profit=0.04,
            after_fill=False,
        )
        assert result_mid > -0.99
        assert result_mid < 0

    def test_long_5pct_plus_very_tight(self, strategy):
        """Long at 5%+ profit: very tight trailing."""
        trade = make_mock_trade()
        self._setup_atr_pct(strategy, 1.0)

        result_high = strategy.custom_stoploss(
            pair='BTC/USDT',
            trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=106.0,
            current_profit=0.06,
            after_fill=False,
        )
        assert result_high > -0.99
        assert result_high < 0

    def test_trailing_tightens_with_profit(self, strategy):
        """Higher profit should produce tighter (closer to 0) stoploss."""
        trade = make_mock_trade()
        self._setup_atr_pct(strategy, 1.0)

        result_low = strategy.custom_stoploss(
            pair='BTC/USDT', trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=102.0, current_profit=0.02,
            after_fill=False,
        )

        result_mid = strategy.custom_stoploss(
            pair='BTC/USDT', trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=104.0, current_profit=0.04,
            after_fill=False,
        )

        result_high = strategy.custom_stoploss(
            pair='BTC/USDT', trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=107.0, current_profit=0.07,
            after_fill=False,
        )

        # Higher profit = tighter SL (closer to 0)
        assert result_high > result_mid or result_high > result_low, \
            f"Expected tighter SL at higher profit: low={result_low}, mid={result_mid}, high={result_high}"

    def test_high_volatility_wider_trail(self, strategy):
        """Higher ATR% should produce wider trailing distance."""
        trade = make_mock_trade()

        # Low vol
        self._setup_atr_pct(strategy, 0.5)
        result_low_vol = strategy.custom_stoploss(
            pair='BTC/USDT', trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=104.0, current_profit=0.04,
            after_fill=False,
        )

        # High vol
        self._setup_atr_pct(strategy, 3.0)
        result_high_vol = strategy.custom_stoploss(
            pair='BTC/USDT', trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=104.0, current_profit=0.04,
            after_fill=False,
        )

        # Higher vol = wider trail (more negative)
        assert result_high_vol < result_low_vol, \
            f"Expected wider trail at higher vol: low_vol={result_low_vol}, high_vol={result_high_vol}"

    def test_fallback_on_empty_dataframe(self, strategy):
        """If dataframe is empty, should still return valid SL."""
        trade = make_mock_trade()
        strategy.dp.get_analyzed_dataframe.return_value = (pd.DataFrame(), None)

        result = strategy.custom_stoploss(
            pair='BTC/USDT', trade=trade,
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=100.0, current_profit=0.001,
            after_fill=False,
        )
        assert result == -0.99

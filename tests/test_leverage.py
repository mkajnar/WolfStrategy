"""
Tests for WolfStrategyV1 leverage calculation.
"""

import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest


class TestLeverage:
    """Test leverage method."""

    def _setup_atr(self, strategy, atr_pct: float):
        """Helper to mock dataframe with specific ATR%."""
        mock_df = pd.DataFrame({'atr_pct': [atr_pct]})
        strategy.dp.get_analyzed_dataframe.return_value = (mock_df, None)

    def test_short_leverage_always_100x(self, strategy):
        """Short leverage must always be 100x (or max_leverage)."""
        lev = strategy.leverage(
            pair='BTC/USDT',
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=100.0,
            proposed_leverage=1.0,
            max_leverage=125.0,
            entry_tag='short_dc_breakout',
            side='short',
        )
        assert lev == 100.0

    def test_short_leverage_capped_by_max(self, strategy):
        """Short leverage capped by max_leverage if < 100."""
        lev = strategy.leverage(
            pair='BTC/USDT',
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=100.0,
            proposed_leverage=1.0,
            max_leverage=50.0,
            entry_tag='short_dc_breakout',
            side='short',
        )
        assert lev == 50.0

    def test_long_leverage_low_volatility(self, strategy):
        """Low ATR% -> high leverage (up to long_leverage_max)."""
        self._setup_atr(strategy, atr_pct=0.3)  # very low vol
        lev = strategy.leverage(
            pair='BTC/USDT',
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=100.0,
            proposed_leverage=1.0,
            max_leverage=20.0,
            entry_tag='long_dc_bounce',
            side='long',
        )
        assert lev == strategy.long_leverage_max.value

    def test_long_leverage_high_volatility(self, strategy):
        """High ATR% -> low leverage (long_leverage_min)."""
        self._setup_atr(strategy, atr_pct=4.0)  # very high vol
        lev = strategy.leverage(
            pair='BTC/USDT',
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=100.0,
            proposed_leverage=1.0,
            max_leverage=20.0,
            entry_tag='long_dc_bounce',
            side='long',
        )
        assert lev == strategy.long_leverage_min.value

    def test_long_leverage_medium_volatility(self, strategy):
        """Medium ATR% -> leverage between min and max."""
        self._setup_atr(strategy, atr_pct=1.5)
        lev = strategy.leverage(
            pair='BTC/USDT',
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=100.0,
            proposed_leverage=1.0,
            max_leverage=20.0,
            entry_tag='long_dc_bounce',
            side='long',
        )
        lev_min = strategy.long_leverage_min.value
        lev_max = strategy.long_leverage_max.value
        assert lev_min <= lev <= lev_max

    def test_long_leverage_capped_by_max_leverage(self, strategy):
        """Long leverage must not exceed max_leverage."""
        self._setup_atr(strategy, atr_pct=0.1)  # would want max leverage
        max_lev = 3.0
        lev = strategy.leverage(
            pair='BTC/USDT',
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=100.0,
            proposed_leverage=1.0,
            max_leverage=max_lev,
            entry_tag='long_dc_bounce',
            side='long',
        )
        assert lev <= max_lev

    def test_long_leverage_fallback_on_error(self, strategy):
        """On error, fallback to 3.0."""
        strategy.dp.get_analyzed_dataframe.side_effect = Exception("test")
        lev = strategy.leverage(
            pair='BTC/USDT',
            current_time=datetime.datetime(2025, 6, 1),
            current_rate=100.0,
            proposed_leverage=1.0,
            max_leverage=20.0,
            entry_tag='long_dc_bounce',
            side='long',
        )
        assert lev == 3.0

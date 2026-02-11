"""
Shared fixtures for WolfStrategyV1 tests.
Mocks freqtrade + talib to run without those packages installed.
"""

import datetime
import sys
import os
from unittest.mock import MagicMock
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

# Add tests dir to path so helpers can be imported
sys.path.insert(0, os.path.dirname(__file__))
# Add strategy path to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'user_data', 'strategies'))


# ================================================================
# TA-Lib mock: pure-Python implementations of used indicators
# ================================================================

def _ema(series, timeperiod):
    return series.ewm(span=timeperiod, adjust=False).mean()


def _rsi(dataframe, timeperiod=14):
    close = dataframe['close']
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(span=timeperiod, adjust=False).mean()
    avg_loss = loss.ewm(span=timeperiod, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(dataframe, timeperiod=14):
    high, low, close = dataframe['high'], dataframe['low'], dataframe['close']
    tr = pd.concat([
        high - low,
        abs(high - close.shift(1)),
        abs(low - close.shift(1))
    ], axis=1).max(axis=1)
    return tr.rolling(window=timeperiod).mean()


def _macd(dataframe, fastperiod=12, slowperiod=26, signalperiod=9):
    close = dataframe['close']
    ema_fast = close.ewm(span=fastperiod, adjust=False).mean()
    ema_slow = close.ewm(span=slowperiod, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal = macd_line.ewm(span=signalperiod, adjust=False).mean()
    return {'macd': macd_line, 'macdsignal': signal, 'macdhist': macd_line - signal}


def _bbands(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0):
    close = dataframe['close']
    mid = close.rolling(window=timeperiod).mean()
    std = close.rolling(window=timeperiod).std()
    return {
        'upperband': mid + nbdevup * std,
        'middleband': mid,
        'lowerband': mid - nbdevdn * std,
    }


def _install_talib_mock():
    talib_mod = ModuleType('talib')
    talib_abstract = ModuleType('talib.abstract')
    talib_abstract.RSI = lambda df, timeperiod=14: _rsi(df, timeperiod)
    talib_abstract.ATR = lambda df, timeperiod=14: _atr(df, timeperiod)
    talib_abstract.EMA = lambda df, timeperiod=30: _ema(df['close'], timeperiod)
    talib_abstract.MACD = lambda df, **kw: _macd(df, **kw)
    talib_abstract.BBANDS = lambda df, **kw: _bbands(df, **kw)
    sys.modules['talib'] = talib_mod
    sys.modules['talib.abstract'] = talib_abstract


def _make_mock_freqtrade_modules():
    mock_persistence = MagicMock()
    mock_persistence.Trade = MagicMock()
    sys.modules['freqtrade'] = MagicMock()
    sys.modules['freqtrade.persistence'] = mock_persistence

    mock_strategy_mod = MagicMock()

    class _DecimalParameter:
        def __init__(self, low, high, default=None, space='buy', optimize=True):
            self.value = default
            self.low = low
            self.high = high

    class _IntParameter:
        def __init__(self, low, high, default=None, space='buy', optimize=True):
            self.value = default
            self.low = low
            self.high = high

    class _IStrategy:
        pass

    mock_strategy_mod.DecimalParameter = _DecimalParameter
    mock_strategy_mod.IntParameter = _IntParameter
    mock_strategy_mod.IStrategy = _IStrategy
    sys.modules['freqtrade.strategy'] = mock_strategy_mod


# Install ALL mocks BEFORE importing strategy
_install_talib_mock()
_make_mock_freqtrade_modules()

from WolfStrategyV1 import WolfStrategyV1  # noqa: E402
from helpers import generate_ohlcv, make_mock_trade  # noqa: E402


# ================================================================
# Fixtures
# ================================================================

@pytest.fixture
def strategy():
    """Fresh WolfStrategyV1 instance with mocked dependencies."""
    s = WolfStrategyV1()
    s.dp = MagicMock()
    s.wallets = MagicMock()
    s.wallets.get_total_stake_amount.return_value = 1000.0
    s.wallets.get_available_stake_amount.return_value = 800.0
    s.custom_profit_bucket = {}
    s.awaiting_short = {}
    s.last_buy_price = {}
    s.dca_count = {}
    s.last_dca_candle = {}
    s.partial_profit_taken = {}
    s.loss_cooldown_until = {}
    return s


@pytest.fixture
def sample_dataframe():
    return generate_ohlcv(n=300, trend='neutral')


@pytest.fixture
def uptrend_dataframe():
    return generate_ohlcv(n=300, trend='up')


@pytest.fixture
def downtrend_dataframe():
    return generate_ohlcv(n=300, trend='down')


@pytest.fixture
def mock_trade():
    return make_mock_trade()


@pytest.fixture
def mock_short_trade():
    return make_mock_trade(is_short=True, leverage=100.0)

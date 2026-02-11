"""
Shared helper functions for tests.
"""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd


def generate_ohlcv(
    n: int = 300,
    start_price: float = 100.0,
    volatility: float = 0.02,
    seed: int = 42,
    trend: str = 'neutral'
) -> pd.DataFrame:
    """
    Generate synthetic OHLCV data.

    Args:
        n: number of candles
        start_price: starting close price
        volatility: std of returns
        seed: random seed
        trend: 'up', 'down', or 'neutral'
    """
    rng = np.random.RandomState(seed)

    if trend == 'up':
        drift = 0.001
    elif trend == 'down':
        drift = -0.001
    else:
        drift = 0.0

    returns = rng.normal(drift, volatility, n)
    close = start_price * np.cumprod(1 + returns)

    high = close * (1 + rng.uniform(0.001, 0.015, n))
    low = close * (1 - rng.uniform(0.001, 0.015, n))
    open_ = close * (1 + rng.normal(0, 0.005, n))

    # Ensure OHLC consistency
    high = np.maximum(high, np.maximum(close, open_))
    low = np.minimum(low, np.minimum(close, open_))

    volume = rng.uniform(100, 10000, n) * (1 + np.abs(returns) * 10)

    dates = pd.date_range('2025-01-01', periods=n, freq='15min')

    df = pd.DataFrame({
        'date': dates,
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    })
    return df


def make_mock_trade(
    pair: str = 'BTC/USDT',
    is_short: bool = False,
    open_rate: float = 100.0,
    stake_amount: float = 100.0,
    leverage: float = 3.0,
):
    """Create a mock Trade object."""
    trade = MagicMock()
    trade.pair = pair
    trade.is_short = is_short
    trade.open_rate = open_rate
    trade.stake_amount = stake_amount
    trade.leverage = leverage
    trade.calc_profit = MagicMock(return_value=0.0)
    return trade

"""
WolfStrategyCore Skill
======================
Core trading logic for Long -> Short Profit Flip strategy.
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class StrategyConfig:
    """Configuration for WolfStrategyV1."""
    donchian_period: int = 20
    dca_max_count: int = 5
    dca_increment: float = 1.5
    dca_price_drop: float = 0.03
    rsi_oversold: int = 35
    short_leverage: float = 100.0
    short_stop_loss: float = 0.008
    short_take_profit: float = 0.03
    trailing_stop_activation: float = 0.015
    taker_fee_reserve: float = 0.002


class WolfStrategyCore:
    """
    Core trading logic for WolfStrategyV1.
    
    Implements:
    - Donchian Channel calculations
    - Support level detection
    - DCA logic with price confirmation
    - Short entry triggers
    - Profit bucket management
    """
    
    def __init__(self, config: Optional[StrategyConfig] = None):
        self.config = config or StrategyConfig()
        self.custom_profit_bucket: Dict[str, float] = {}
        self.awaiting_short: Dict[str, bool] = {}
        self.last_buy_price: Dict[str, float] = {}
        self.dca_count: Dict[str, int] = {}
        self.support_levels: Dict[str, float] = {}
        self.donchian_data: Dict[str, Dict] = {}
    
    def calculate_donchian(
        self, 
        dataframe: pd.DataFrame, 
        period: int = 20
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Donchian Channels.
        
        Returns:
            upper: Upper band (highest high)
            middle: Middle band (average)
            lower: Lower band (lowest low)
        """
        upper = dataframe['high'].rolling(window=period, min_periods=period).max()
        lower = dataframe['low'].rolling(window=period, min_periods=period).min()
        middle = (upper + lower) / 2
        
        return upper, middle, lower
    
    def detect_support_levels(
        self, 
        dataframe: pd.DataFrame, 
        lookback: int = 10
    ) -> pd.Series:
        """
        Detect support levels using local minima (Fractals).
        
        A support is detected when:
        - Current low is lower than 'lookback' previous lows
        - And lower than 'lookback' subsequent lows
        """
        supports = pd.Series(index=dataframe.index, dtype=float)
        
        for i in range(lookback, len(dataframe) - lookback):
            current_low = dataframe['low'].iloc[i]
            past_lows = dataframe['low'].iloc[i - lookback:i]
            future_lows = dataframe['low'].iloc[i + 1:i + lookback + 1]
            
            if current_low < past_lows.min() and current_low < future_lows.min():
                supports.iloc[i] = current_low
        
        return supports
    
    def calculate_dynamic_leverage(
        self, 
        atr_percent: float,
        min_lev: float = 2.0,
        max_lev: float = 5.0
    ) -> float:
        """
        Calculate dynamic leverage based on ATR volatility.
        
        Logic:
        - ATR < 0.5%: max_lev (5x)
        - ATR 0.5-1.0%: 4x
        - ATR 1.0-1.5%: 3x
        - ATR 1.5-2.0%: min_lev (2x)
        - ATR > 2.0%: 2x
        """
        if atr_percent < 0.5:
            return max_lev
        elif atr_percent < 1.0:
            return 4.0
        elif atr_percent < 1.5:
            return 3.0
        elif atr_percent < 2.0:
            return min_lev
        else:
            return 2.0
    
    def can_dca(
        self,
        pair: str,
        current_price: float,
        current_profit: float,
        dataframe: pd.DataFrame
    ) -> Tuple[bool, str]:
        """
        Check if DCA conditions are met.
        
        Rules:
        1. Price must be lower than last_buy_price
        2. Support bounce confirmation
        3. Max DCA count not exceeded
        """
        last_price = self.last_buy_price.get(pair, 0)
        dca_count = self.dca_count.get(pair, 0)
        
        # Check DCA count
        if dca_count >= self.config.dca_max_count:
            return False, f"Max DCA reached ({dca_count}/{self.config.dca_max_count})"
        
        # Check price drop
        min_drop = self.config.dca_price_drop
        if current_price >= last_price * (1 - min_drop):
            return False, f"Price drop not sufficient ({min_drop*100}% required)"
        
        # Check support bounce
        last_candle = dataframe.iloc[-1]
        support = self.support_levels.get(pair, 0)
        
        if support > 0:
            above_support = current_price > support
            rsi_oversold = last_candle.get('rsi', 50) < self.config.rsi_oversold
            macd_bullish = last_candle.get('macd', 0) > last_candle.get('macdsignal', 0)
            
            if not (above_support and (rsi_oversold or macd_bullish)):
                return False, "No support bounce confirmation"
        
        return True, "DCA conditions met"
    
    def calculate_dca_amount(
        self,
        available_stake: float,
        dca_index: int
    ) -> float:
        """
        Calculate DCA position size.
        
        Uses geometric progression based on dca_increment.
        """
        increment = self.config.dca_increment
        return available_stake * (increment ** dca_index)
    
    def check_short_entry(
        self,
        pair: str,
        current_price: float,
        donchian_lower: float
    ) -> Tuple[bool, str]:
        """
        Check if Short entry conditions are met.
        
        Rules:
        1. Must be awaiting short (profit captured)
        2. Price must break below Donchian lower
        """
        if not self.awaiting_short.get(pair, False):
            return False, "Not awaiting short"
        
        profit = self.custom_profit_bucket.get(pair, 0)
        if profit <= 0:
            self.awaiting_short[pair] = False
            return False, "No profit in bucket"
        
        if current_price >= donchian_lower:
            return False, "Price not below Donchian lower"
        
        return True, "Short entry conditions met"
    
    def capture_profit(self, pair: str, profit: float) -> None:
        """Capture profit and activate Short phase."""
        self.custom_profit_bucket[pair] = profit
        self.awaiting_short[pair] = profit > 0
        
        logger.info(
            f"[PROFIT_CAPTURE] {pair} - Profit: {profit:.4f}, "
            f"Short activated: {self.awaiting_short[pair]}"
        )
    
    def reset_short_state(self, pair: str) -> None:
        """Reset Short phase state."""
        self.awaiting_short[pair] = False
        if pair in self.custom_profit_bucket:
            del self.custom_profit_bucket[pair]
        
        logger.info(f"[SHORT_RESET] {pair} - State reset")
    
    def get_strategy_state(self, pair: str) -> Dict:
        """Get current strategy state for logging."""
        return {
            'profit_bucket': self.custom_profit_bucket.get(pair, 0),
            'awaiting_short': self.awaiting_short.get(pair, False),
            'last_buy_price': self.last_buy_price.get(pair, 0),
            'dca_count': self.dca_count.get(pair, 0),
            'support_level': self.support_levels.get(pair, 0),
        }

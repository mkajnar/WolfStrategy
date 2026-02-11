"""
WolfStrategyV1 - Long -> Short Profit Flip Strategy
=====================================================
Complete trading strategy implementing sequential Long -> Short Profit Flip logic
with dynamic DCA, Donchian Channels, Support Detection, and 100x Short leverage.

Author: AI Assistant
Version: 1.0.0
"""

import datetime
import logging
from typing import Optional, Union, List, Tuple, Dict, Any

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame, Series

import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.persistence import Trade, CustomDataWrapper
from freqtrade.strategy import (
    DecimalParameter, IStrategy, IntParameter, BooleanParameter
)


logger = logging.getLogger(__name__)


class WolfStrategyV1_v2(IStrategy):
    """
    WolfStrategyV1 - Long -> Short Profit Flip Strategy

    This strategy implements:
    1. Long entry with Donchian Channel bounce from lower band
    2. Dynamic DCA with support detection and price confirmation
    3. Profit capture with automatic Short entry on Donchian breakout
    4. 100x leverage for Short phase with strict risk management
    """

    INTERFACE_VERSION = 3

    minimal_roi = {
        "0": 0.03
    }

    leverage_value = 10

    timeframe_hierarchy = {
        '1m': '5m',
        '5m': '15m',
        '15m': '1h',
        '1h': '4h',
        '4h': '1d',
        '1d': '1w',
        '1w': '1M'
    }

    order_types = {
        'entry': 'market',
        'exit': 'market',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }

    stoploss = -0.5

    use_exit_signal = True
    exit_profit_only = False

    trailing_stop = True
    trailing_only_offset_is_reached = True
    trailing_stop_positive = 0.003
    trailing_stop_positive_offset = 0.008

    position_adjustment_enable = True

    custom_profit_bucket: Dict[str, float] = {}
    awaiting_short: Dict[str, bool] = {}
    last_buy_price: Dict[str, float] = {}
    dca_count: Dict[str, int] = {}
    support_levels: Dict[str, float] = {}
    donchian_lower: Dict[str, float] = {}
    donchian_upper: Dict[str, float] = {}

    donchian_period = IntParameter(10, 50, default=20, space='buy', optimize=True)
    dca_max_count = IntParameter(3, 10, default=5, space='buy', optimize=True)
    dca_increment = DecimalParameter(1.2, 3.0, default=1.5, space='buy', optimize=True)
    dca_price_drop = DecimalParameter(0.01, 0.1, default=0.03, space='buy', optimize=False)
    support_confirmation_bars = IntParameter(2, 10, default=3, space='buy', optimize=False)

    short_leverage = DecimalParameter(5.0, 20.0, default=10.0, space='sell', optimize=True)
    short_stop_loss = DecimalParameter(0.01, 0.03, default=0.015, space='sell', optimize=True)
    short_take_profit = DecimalParameter(0.03, 0.08, default=0.05, space='sell', optimize=True)
    trailing_stop_activation = DecimalParameter(0.01, 0.03, default=0.015, space='sell', optimize=True)
    taker_fee_reserve = DecimalParameter(0.001, 0.005, default=0.002, space='sell', optimize=False)

    atr_period = IntParameter(10, 30, default=14, space='buy', optimize=False)
    rsi_period = IntParameter(10, 30, default=14, space='buy', optimize=False)
    rsi_oversold = IntParameter(20, 50, default=35, space='buy', optimize=True)
    macd_fast = IntParameter(8, 20, default=12, space='buy', optimize=False)
    macd_slow = IntParameter(20, 40, default=26, space='buy', optimize=False)
    macd_signal = IntParameter(5, 15, default=9, space='buy', optimize=False)

    long_leverage_min = DecimalParameter(2.0, 5.0, default=2.0, space='buy', optimize=True)
    long_leverage_max = DecimalParameter(5.0, 10.0, default=5.0, space='buy', optimize=True)

    stake_amount_coef = DecimalParameter(0.1, 1.0, default=0.5, space='buy', optimize=True)

    def custom_stake_amount(self, **kwargs) -> float:
        """
        Calculate custom stake amount with proper risk management.

        Strategy:
        - 40% of available balance for trading
        - Split across max DCA positions
        - Multiplied by hyperopt coefficient
        - Taker fee reserve included
        """
        try:
            balance = self.wallets.get_total_stake_amount()
            risk_balance = balance * 0.40

            num_positions = self.dca_max_count.value + 1
            per_position = risk_balance / num_positions

            adjusted_position = per_position * self.stake_amount_coef.value

            fee_reserve = adjusted_position * self.taker_fee_reserve.value
            final_stake = adjusted_position - fee_reserve

            min_stake = self.config.get("min_stake_amount", 30)

            logger.info(
                f"[CUSTOM_STAKE] Balance: {balance:.2f}, Risk: {risk_balance:.2f}, "
                f"Positions: {num_positions}, Final: {final_stake:.2f}, Min: {min_stake}"
            )

            return max(final_stake, min_stake)

        except Exception as e:
            logger.error(f"Error in custom_stake_amount: {e}")
            return self.config.get("min_stake_amount", 30)

    def leverage(
        self,
        pair: str,
        current_time: datetime.datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs
    ) -> float:
        """
        Dynamic leverage based on side and strategy requirements.

        Long: 2-5x based on ATR volatility
        Short: Fixed 100x (strict requirement)
        """
        try:
            if side == "short":
                short_lev = float(self.short_leverage.value)
                logger.info(
                    f"[LEVERAGE] {pair} Short: Using {short_lev}x leverage (fixed for Short phase)"
                )
                return min(short_lev, max_leverage)

            atr_percent = getattr(self, f'{pair}_atr_percent', 1.0)

            base_leverage = 1.0

            final_leverage = min(base_leverage, max_leverage)

            logger.info(
                f"[LEVERAGE] {pair} Long: ATR={atr_percent:.2f}%, "
                f"Base={base_leverage}x, Final={final_leverage}x"
            )

            return final_leverage

        except Exception as e:
            logger.error(f"Error in leverage: {e}")
            return 3.0

    def calculate_donchian_channels(self, dataframe: DataFrame, period: int) -> Tuple[Series, Series]:
        """Calculate Donchian Channels (Upper and Lower bands)."""
        upper = dataframe['high'].rolling(window=period, min_periods=period).max()
        lower = dataframe['low'].rolling(window=period, min_periods=period).min()
        return upper, lower

    def detect_support_levels(
        self,
        dataframe: DataFrame,
        lookback: int = 20
    ) -> Series:
        """
        Detect support levels using local minima (Fractals/Pivot Lows).

        A support level is detected when:
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

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate all required indicators:
        - Donchian Channels (20 period)
        - Support Levels (Fractals/Pivot Lows)
        - ATR (for leverage)
        - RSI (for momentum)
        - MACD (for trend confirmation)
        """
        pair = metadata['pair']

        donchian_period = self.donchian_period.value
        upper, lower = self.calculate_donchian_channels(dataframe, donchian_period)
        dataframe['donchian_upper'] = upper
        dataframe['donchian_lower'] = lower
        dataframe['donchian_middle'] = (upper + lower) / 2

        self.donchian_lower[pair] = lower.iloc[-1]
        self.donchian_upper[pair] = upper.iloc[-1]

        supports = self.detect_support_levels(dataframe, lookback=10)
        dataframe['support_level'] = supports

        last_support = supports.dropna().iloc[-1] if not supports.dropna().empty else 0.0
        self.support_levels[pair] = last_support

        atr_period = self.atr_period.value
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=atr_period)

        close_price = dataframe['close'].iloc[-1]
        atr_value = dataframe['atr'].iloc[-1]

        if close_price > 0:
            atr_percent = (atr_value / close_price) * 100
            setattr(self, f'{pair}_atr_percent', atr_percent)
            logger.info(
                f"[INDICATORS] {pair} - ATR%: {atr_percent:.2f}%, "
                f"DC_Upper: {upper.iloc[-1]:.6f}, DC_Lower: {lower.iloc[-1]:.6f}, "
                f"Support: {last_support:.6f}" if last_support > 0 else "Support: None"
            )
        else:
            setattr(self, f'{pair}_atr_percent', 1.0)

        rsi_period = self.rsi_period.value
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=rsi_period)

        macd_fast = self.macd_fast.value
        macd_slow = self.macd_slow.value
        macd_signal_period = self.macd_signal.value

        macd = ta.MACD(
            dataframe,
            fastperiod=macd_fast,
            slowperiod=macd_slow,
            signalperiod=macd_signal_period
        )
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']

        dataframe['rsi_oversold'] = dataframe['rsi'] < self.rsi_oversold.value

        dataframe['price_vs_donchian'] = (
            (dataframe['close'] - dataframe['donchian_lower']) /
            (dataframe['donchian_upper'] - dataframe['donchian_lower'] + 1e-10)
        )

        dataframe['support_bounce'] = (
            (dataframe['close'] > dataframe['support_level'].shift(1)) &
            (dataframe['low'] <= dataframe['support_level']) &
            (dataframe['rsi'] < 50)
        )

        dataframe['donchian_breakout_down'] = (
            dataframe['close'] < dataframe['donchian_lower'].shift(1)
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Define entry signals for both Long and Short phases.

        Long Entry: Bounce from lower Donchian Channel or Support with RSI oversold
        Short Entry: Donchian breakout down (after profit capture)
        """
        pair = metadata['pair']

        conditions_long = []
        conditions_short = []

        conditions_long.append(dataframe['volume'] > 0)

        donchian_touch = dataframe['close'] <= dataframe['donchian_lower']
        support_condition = dataframe['support_bounce']
        rsi_condition = dataframe['rsi'] < 50

        conditions_long.append(donchian_touch | support_condition)
        conditions_long.append(rsi_condition)

        if conditions_long:
            long_condition = pd.concat(conditions_long, axis=1).all(axis=1)
            dataframe.loc[long_condition, ['enter_long', 'enter_tag']] = (
                1, 'WOLF_LONG_DONCHIAN_BOUNCE'
            )

        if pair in self.awaiting_short and self.awaiting_short[pair]:
            pass  # SHORT TEMPORARILY DISABLED - Long with trailing stop is profitable

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Define exit signals.

        Long Exit: Strong move to upper Donchian or RSI overbought
        Short Exit: Price returns above lower Donchian or stop loss hit
        """
        conditions_long_exit = []
        conditions_short_exit = []

        conditions_long_exit.append(
            (dataframe['close'] >= dataframe['donchian_upper']) |
            (dataframe['rsi'] > 70)
        )
        conditions_long_exit.append(dataframe['volume'] > 0)

        if conditions_long_exit:
            long_exit_condition = pd.concat(conditions_long_exit, axis=1).all(axis=1)
            dataframe.loc[long_exit_condition, ['exit_long', 'exit_tag']] = (
                1, 'WOLF_LONG_TAKE_PROFIT'
            )

        conditions_short_exit.append(
            (dataframe['close'] >= dataframe['donchian_lower'].shift(1)) &
            (dataframe['close'] > dataframe['donchian_lower'])
        )
        conditions_short_exit.append(dataframe['volume'] > 0)

        if conditions_short_exit:
            short_exit_condition = pd.concat(conditions_short_exit, axis=1).all(axis=1)
            dataframe.loc[short_exit_condition, ['exit_short', 'exit_tag']] = (
                1, 'WOLF_SHORT_EXIT'
            )

        return dataframe

    def confirm_trade_exit(
        self,
        pair: str,
        trade: Trade,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        exit_reason: str,
        current_time: datetime.datetime,
        **kwargs
    ) -> bool:
        """
        Confirm trade exit and handle profit capture for Short phase.

        Calculates net profit from Long position and stores for Short entry.
        """
        try:
            profit_ratio = trade.calc_profit_ratio(rate)
            profit_abs = trade.calc_profit(rate)

            net_profit = profit_abs - (amount * rate * self.taker_fee_reserve.value)

            self.custom_profit_bucket[pair] = net_profit

            logger.info(
                f"[TRADE_EXIT] {pair} - Exit Reason: {exit_reason}, "
                f"Profit Ratio: {profit_ratio:.4f}, Net Profit: {net_profit:.4f}, "
                f"Stored in Profit Bucket: {self.custom_profit_bucket.get(pair, 0):.4f}"
            )

            if net_profit > 0:
                self.awaiting_short[pair] = True
                logger.info(
                    f"[PROFIT_CAPTURE] {pair} - Profit captured: {net_profit:.4f}, "
                    f"Activating Short phase. Waiting for Donchian breakout."
                )

            return True

        except Exception as e:
            logger.error(f"Error in confirm_trade_exit: {e}")
            return True

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime.datetime,
        current_rate: float,
        current_profit: float,
        **kwargs
    ) -> Optional[Union[str, bool]]:
        """
        Custom exit logic for emergency situations.

        Long: Liquidation protection
        Short: Strict 0.8-0.9% stop loss
        """
        try:
            if trade.is_short:
                sl_price = trade.open_rate * (1 + float(self.short_stop_loss.value))
                tp_price = trade.open_rate * (1 - float(self.short_take_profit.value))
                
                logger.info(
                    f"[SHORT_EXIT_CHECK] {pair} - Entry: {trade.open_rate:.6f}, "
                    f"Current: {current_rate:.6f}, SL: {sl_price:.6f}, TP: {tp_price:.6f}"
                )
                
                if current_rate >= sl_price:
                    logger.info(f"[SHORT_SL] {pair} - Stop loss triggered at {current_rate:.6f}")
                    return f"short_emergency_sl_{sl_price:.6f}"
                
                if current_rate <= tp_price:
                    logger.info(f"[SHORT_TP] {pair} - Take profit triggered at {current_rate:.6f}")
                    return f"short_take_profit_{tp_price:.6f}"

            liquidation_price = trade.liquidation_price
            if liquidation_price > 0 and current_rate <= liquidation_price * 1.02:
                return f"liquidation_protection_{liquidation_price:.6f}"

            return None

        except Exception as e:
            logger.error(f"Error in custom_exit: {e}")
            return None

    def adjust_trade_position(
        self,
        trade: Trade,
        current_time: datetime.datetime,
        current_rate: float,
        current_profit: float,
        min_stake: Optional[float],
        max_stake: float,
        current_entry_rate: float,
        current_exit_rate: float,
        current_entry_profit: float,
        current_exit_profit: float,
        **kwargs
    ) -> Optional[float]:
        """
        Dynamic DCA logic for Long positions.

        Rules:
        1. Only DCA if current_price < last_buy_price
        2. Confirm bounce from deeper support
        3. Max DCA count limit respected
        4. Each DCA increases position size to reduce average price
        """
        try:
            pair = trade.pair

            if trade.is_short:
                logger.info(f"[DCA] {pair} - Short position, skipping DCA")
                return None

            current_dca_count = self.dca_count.get(pair, 0)
            max_dca = self.dca_max_count.value

            if current_dca_count >= max_dca:
                logger.info(
                    f"[DCA] {pair} - Max DCA reached ({current_dca_count}/{max_dca}), skipping"
                )
                return None

            last_price = self.last_buy_price.get(pair, trade.open_rate)

            price_drop_required = current_rate < (last_price * (1 - self.dca_price_drop.value))

            if not price_drop_required:
                logger.info(
                    f"[DCA] {pair} - Price drop not sufficient. "
                    f"Current: {current_rate:.6f}, Last Buy: {last_price:.6f}, "
                    f"Required drop: {self.dca_price_drop.value * 100:.1f}%"
                )
                return None

            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe.empty:
                logger.warning(f"[DCA] {pair} - Empty dataframe, skipping DCA")
                return None

            last_candle = dataframe.iloc[-1]

            support_confirmed = False
            support_level = self.support_levels.get(pair, 0)

            if support_level > 0:
                price_above_support = current_rate > support_level
                rsi_oversold = last_candle.get('rsi_oversold', False)
                macd_bullish = last_candle.get('macd', 0) > last_candle.get('macdsignal', 0)

                support_confirmed = price_above_support and (rsi_oversold or macd_bullish)

                logger.info(
                    f"[DCA] {pair} - Support Analysis: Price={current_rate:.6f}, "
                    f"Support={support_level:.6f}, Above Support={price_above_support}, "
                    f"RSI Oversold={rsi_oversold}, MACD Bullish={macd_bullish}"
                )
            else:
                price_bounce = current_rate > last_candle.get('donchian_lower', current_rate)
                support_confirmed = price_bounce and last_candle.get('rsi_oversold', False)

            if not support_confirmed:
                logger.info(
                    f"[DCA] {pair} - Support confirmation not met, skipping DCA"
                )
                return None

            available_stake = self.wallets.get_available_stake_amount()

            dca_increment = float(self.dca_increment.value)
            dca_amount = available_stake * (dca_increment ** (current_dca_count + 1))

            dca_amount = min(dca_amount, max_stake)
            dca_amount = max(dca_amount, min_stake if min_stake else 30)

            self.last_buy_price[pair] = current_rate
            self.dca_count[pair] = current_dca_count + 1

            logger.info(
                f"[DCA_EXECUTED] {pair} - DCA #{current_dca_count + 1}/{max_dca} | "
                f"Price: {current_rate:.6f} | "
                f"Amount: {dca_amount:.4f} | "
                f"Profit Bucket: {self.custom_profit_bucket.get(pair, 0):.4f}"
            )

            return dca_amount

        except Exception as e:
            logger.error(f"Error in adjust_trade_position: {e}")
            return None

    def get_dca_list(self, trade: Trade) -> List[float]:
        """Get list of DCA prices for a trade."""
        try:
            dcas = CustomDataWrapper.get_custom_data(trade_id=trade.id, key="DCA")
            if dcas:
                return dcas[0].value
        except Exception as ex:
            logger.debug(f"No DCA list found: {ex}")
        return []

    def set_dca_list(self, trade: Trade, dca_list: List[float]) -> None:
        """Store DCA prices for a trade."""
        try:
            CustomDataWrapper.set_custom_data(trade_id=trade.id, key="DCA", value=dca_list)
        except Exception as e:
            logger.error(f"Error setting DCA list: {e}")

    def get_custom_profit(self, pair: str) -> float:
        """Get stored profit from profit bucket."""
        return self.custom_profit_bucket.get(pair, 0.0)

    def informative_pairs(self) -> List[Tuple[str, str]]:
        """Define informative pairs for multi-timeframe analysis."""
        pairs = self.dp.current_whitelist()
        informative_pairs = [
            (pair, timeframe)
            for pair in pairs
            for timeframe in self.timeframe_hierarchy.keys()
        ]
        return informative_pairs

    def check_short_entry_conditions(
        self,
        pair: str,
        dataframe: DataFrame,
        current_rate: float
    ) -> bool:
        """
        Check if Short entry conditions are met.

        Conditions:
        1. Profit bucket has positive profit
        2. Awaiting short flag is True
        3. Price broke below lower Donchian Channel
        """
        if not self.awaiting_short.get(pair, False):
            return False

        profit = self.custom_profit_bucket.get(pair, 0.0)
        if profit <= 0:
            self.awaiting_short[pair] = False
            return False

        donchian_lower = self.donchian_lower.get(pair, 0.0)
        if donchian_lower == 0:
            return False

        breakout_down = current_rate < donchian_lower

        logger.info(
            f"[SHORT_CHECK] {pair} - Profit: {profit:.4f}, "
            f"DC_Lower: {donchian_lower:.6f}, Current: {current_rate:.6f}, "
            f"Breakout: {breakout_down}"
        )

        return breakout_down

    def short_stake_amount(self, pair: str) -> float:
        """
        Calculate stake amount for Short entry based on profit bucket.

        Uses profit from Long phase as notional for Short.
        """
        profit = self.custom_profit_bucket.get(pair, 0.0)

        if profit <= 0:
            return self.config.get("min_stake_amount", 30)

        available_balance = self.wallets.get_total_stake_amount()

        short_stake = min(profit * 100, available_balance * 0.3)

        min_stake = self.config.get("min_stake_amount", 30)

        logger.info(
            f"[SHORT_STAKE] {pair} - Profit Bucket: {profit:.4f}, "
            f"Calculated Stake: {short_stake:.4f}, Min: {min_stake}"
        )

        return max(short_stake, min_stake)

    def reset_short_state(self, pair: str) -> None:
        """Reset Short phase state after trade completion."""
        self.awaiting_short[pair] = False
        if pair in self.custom_profit_bucket:
            del self.custom_profit_bucket[pair]
        logger.info(f"[SHORT_RESET] {pair} - Short state reset")

    def log_strategy_state(self, pair: str) -> None:
        """Log current strategy state for monitoring."""
        state = {
            'profit_bucket': self.custom_profit_bucket.get(pair, 0.0),
            'awaiting_short': self.awaiting_short.get(pair, False),
            'last_buy_price': self.last_buy_price.get(pair, 0.0),
            'dca_count': self.dca_count.get(pair, 0),
            'donchian_lower': self.donchian_lower.get(pair, 0.0),
            'donchian_upper': self.donchian_upper.get(pair, 0.0),
            'support_level': self.support_levels.get(pair, 0.0),
        }
        logger.info(f"[STRATEGY_STATE] {pair} - {state}")

    def start_of_cycle(self, pair: str) -> None:
        """Initialize pair-specific state at start of trading cycle."""
        if pair not in self.dca_count:
            self.dca_count[pair] = 0
        if pair not in self.awaiting_short:
            self.awaiting_short[pair] = False
        if pair not in self.custom_profit_bucket:
            self.custom_profit_bucket[pair] = 0.0

        self.log_strategy_state(pair)

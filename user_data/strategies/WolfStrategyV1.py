"""
WolfStrategyV1 - Long -> Short Profit Flip Strategy
=====================================================
Donchian Channel bounce Long with DCA + 100x Short on breakout down.

Phases:
  1. Long: Enter on Donchian lower bounce + RSI oversold + support
     - DCA up to N positions, each lower than previous
     - Exit via trailing stop or ROI
  2. Short: Enter on Donchian breakout down after profitable Long exit
     - 100x leverage, strict SL/TP
     - Funded from profit bucket (Long phase profit)

Version: 2.0.0
"""

import datetime
import logging
from typing import Optional, Union, List, Tuple, Dict

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import (
    DecimalParameter, IStrategy, IntParameter
)

logger = logging.getLogger(__name__)


class WolfStrategyV1(IStrategy):

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = '15m'

    # -- Minimal ROI: only for Long --
    minimal_roi = {
        "0": 0.05,       # 5% default ROI
        "60": 0.03,      # 3% after 60 min
        "180": 0.015,    # 1.5% after 3h
        "720": 0.005     # 0.5% after 12h
    }

    # -- Stoploss: effectively disabled, DCA handles drawdowns --
    # At 2-5x leverage, -0.99 means price must drop ~50% to trigger
    # We rely on DCA to average down and trailing stop to exit in profit
    stoploss = -0.99

    # -- Trailing stop for Long --
    trailing_stop = True
    trailing_only_offset_is_reached = True
    trailing_stop_positive = 0.01       # 1% trailing
    trailing_stop_positive_offset = 0.02  # activate after 2% profit

    # -- Order types --
    order_types = {
        'entry': 'market',
        'exit': 'market',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }

    # -- Signals --
    use_exit_signal = True
    exit_profit_only = True  # Long exit signals fire only when in profit

    # -- DCA --
    position_adjustment_enable = True

    # ================================================================
    # HYPEROPT PARAMETERS - BUY SPACE
    # ================================================================
    donchian_period = IntParameter(10, 50, default=20, space='buy', optimize=True)
    rsi_oversold = IntParameter(20, 45, default=35, space='buy', optimize=True)
    rsi_period = IntParameter(7, 21, default=14, space='buy', optimize=True)
    atr_period = IntParameter(10, 20, default=14, space='buy', optimize=False)

    # DCA parameters
    dca_max_count = IntParameter(2, 8, default=5, space='buy', optimize=True)
    dca_price_drop = DecimalParameter(0.01, 0.08, default=0.03, space='buy', optimize=True)
    dca_multiplier = DecimalParameter(1.1, 2.5, default=1.5, space='buy', optimize=True)

    # Long leverage
    long_leverage_min = DecimalParameter(1.0, 3.0, default=2.0, space='buy', optimize=False)
    long_leverage_max = DecimalParameter(3.0, 10.0, default=5.0, space='buy', optimize=False)

    # ================================================================
    # HYPEROPT PARAMETERS - SELL SPACE
    # ================================================================
    short_stop_loss = DecimalParameter(0.005, 0.015, default=0.009, space='sell', optimize=True)
    short_take_profit = DecimalParameter(0.02, 0.06, default=0.03, space='sell', optimize=True)

    # ================================================================
    # RUNTIME STATE (not persisted across restarts in backtesting)
    # ================================================================
    custom_profit_bucket: Dict[str, float] = {}
    awaiting_short: Dict[str, bool] = {}
    last_buy_price: Dict[str, float] = {}
    dca_count: Dict[str, int] = {}

    # ================================================================
    # INDICATORS
    # ================================================================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata['pair']

        # -- Donchian Channels --
        period = self.donchian_period.value
        dataframe['dc_upper'] = dataframe['high'].rolling(window=period).max()
        dataframe['dc_lower'] = dataframe['low'].rolling(window=period).min()
        dataframe['dc_mid'] = (dataframe['dc_upper'] + dataframe['dc_lower']) / 2

        # -- RSI --
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)

        # -- ATR (for leverage calculation) --
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period.value)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close'] * 100

        # -- Volume SMA for confirmation --
        dataframe['volume_sma'] = dataframe['volume'].rolling(window=20).mean()

        # -- Support detection: rolling min of last N lows --
        dataframe['support'] = dataframe['low'].rolling(window=50, min_periods=20).min()

        # -- Donchian position: 0 = at lower, 1 = at upper --
        dc_range = dataframe['dc_upper'] - dataframe['dc_lower']
        dataframe['dc_position'] = (dataframe['close'] - dataframe['dc_lower']) / dc_range.replace(0, np.nan)

        # -- Price near lower Donchian (within 1% of lower band) --
        dataframe['near_dc_lower'] = (
            dataframe['close'] <= dataframe['dc_lower'] * 1.01
        )

        # -- Donchian breakout down: close below previous lower --
        dataframe['dc_breakout_down'] = (
            (dataframe['close'] < dataframe['dc_lower'].shift(1)) &
            (dataframe['close'].shift(1) >= dataframe['dc_lower'].shift(2))
        )

        # -- Bearish momentum for Short confirmation --
        dataframe['bear_candle'] = (
            (dataframe['close'] < dataframe['open']) &
            (dataframe['close'].shift(1) < dataframe['open'].shift(1))
        )

        return dataframe

    # ================================================================
    # ENTRY SIGNALS
    # ================================================================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # -- LONG: Donchian lower bounce + RSI oversold --
        long_conditions = (
            (dataframe['near_dc_lower']) &
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['volume'] > 0) &
            (dataframe['volume'] > dataframe['volume_sma'] * 0.5)
        )
        dataframe.loc[long_conditions, ['enter_long', 'enter_tag']] = (1, 'long_dc_bounce')

        # -- SHORT: Donchian breakout down --
        # Note: In backtesting, profit bucket check happens in confirm_trade_entry
        short_conditions = (
            (dataframe['dc_breakout_down']) &
            (dataframe['bear_candle']) &
            (dataframe['rsi'] > 30) &  # not already extremely oversold
            (dataframe['volume'] > dataframe['volume_sma'])
        )
        dataframe.loc[short_conditions, ['enter_short', 'enter_tag']] = (1, 'short_dc_breakout')

        return dataframe

    # ================================================================
    # EXIT SIGNALS
    # ================================================================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # -- LONG EXIT: Price reaches upper Donchian or RSI overbought --
        long_exit = (
            (dataframe['close'] >= dataframe['dc_upper'] * 0.99) |
            (dataframe['rsi'] > 75)
        ) & (dataframe['volume'] > 0)
        dataframe.loc[long_exit, ['exit_long', 'exit_tag']] = (1, 'long_dc_upper')

        # -- SHORT EXIT is handled by custom_exit (SL/TP), not signals --
        # But add emergency signal exit if price goes way above entry
        short_exit = (
            (dataframe['close'] > dataframe['dc_upper']) &
            (dataframe['rsi'] > 70)
        )
        dataframe.loc[short_exit, ['exit_short', 'exit_tag']] = (1, 'short_emergency_signal')

        return dataframe

    # ================================================================
    # CONFIRM TRADE ENTRY (runtime gate for Short)
    # ================================================================

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime.datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs
    ) -> bool:
        """
        Gate Short entries: only allow if profit bucket > 0.
        Always allow Long entries.
        """
        if side == 'short':
            profit = self.custom_profit_bucket.get(pair, 0.0)
            if profit <= 0:
                logger.info(
                    f"[SHORT_BLOCKED] {pair} - No profit bucket ({profit:.2f}), "
                    f"blocking Short entry"
                )
                return False

            logger.info(
                f"[SHORT_ENTRY] {pair} - Profit bucket: {profit:.2f}, "
                f"allowing Short at {rate:.2f}"
            )
            # Reset awaiting flag
            self.awaiting_short[pair] = False
            return True

        # Long: always allow, reset DCA state
        if side == 'long':
            self.dca_count[pair] = 0
            self.last_buy_price[pair] = rate
            logger.info(f"[LONG_ENTRY] {pair} - Entry at {rate:.2f}")

        return True

    # ================================================================
    # CUSTOM STAKE AMOUNT
    # ================================================================

    def custom_stake_amount(
        self,
        current_time: datetime.datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: Optional[float],
        max_stake: float,
        leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs
    ) -> float:
        """
        Long: Divide wallet across DCA positions.
        Short: Use profit bucket amount.
        """
        try:
            if side == 'short':
                pair = kwargs.get('pair', '')
                profit = self.custom_profit_bucket.get(pair, 0.0)
                if profit <= 0:
                    return min_stake or 30.0
                # Use profit as stake for Short (with 100x leverage = huge position)
                short_stake = max(profit * 0.9, min_stake or 30.0)
                short_stake = min(short_stake, max_stake)
                logger.info(f"[SHORT_STAKE] {pair} - Stake: {short_stake:.2f} from bucket: {profit:.2f}")
                return short_stake

            # Long: split wallet for DCA room
            balance = self.wallets.get_total_stake_amount()
            num_positions = self.dca_max_count.value + 1  # initial + DCA slots
            per_position = balance * 0.8 / num_positions  # 80% of wallet, split
            final = max(per_position, min_stake or 30.0)
            final = min(final, max_stake)

            logger.info(
                f"[LONG_STAKE] Balance: {balance:.2f}, "
                f"Positions: {num_positions}, Stake: {final:.2f}"
            )
            return final

        except Exception as e:
            logger.error(f"Error in custom_stake_amount: {e}")
            return proposed_stake

    # ================================================================
    # LEVERAGE
    # ================================================================

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
        Long: Dynamic 2-5x based on ATR volatility.
        Short: Fixed 100x.
        """
        if side == 'short':
            lev = min(100.0, max_leverage)
            logger.info(f"[LEVERAGE] {pair} Short: {lev}x")
            return lev

        # Long: lower leverage when volatility is high
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if not dataframe.empty:
                atr_pct = dataframe.iloc[-1].get('atr_pct', 1.0)
                # High ATR -> lower leverage, Low ATR -> higher leverage
                lev_min = float(self.long_leverage_min.value)
                lev_max = float(self.long_leverage_max.value)
                if atr_pct > 2.0:
                    lev = lev_min
                elif atr_pct < 0.5:
                    lev = lev_max
                else:
                    # Linear interpolation: high ATR -> low leverage
                    ratio = (2.0 - atr_pct) / 1.5
                    lev = lev_min + ratio * (lev_max - lev_min)
                lev = min(lev, max_leverage)
                logger.info(f"[LEVERAGE] {pair} Long: {lev:.1f}x (ATR%: {atr_pct:.2f})")
                return lev
        except Exception as e:
            logger.error(f"Error in leverage: {e}")

        return min(3.0, max_leverage)

    # ================================================================
    # DCA (adjust_trade_position)
    # ================================================================

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
        DCA for Long only:
        1. Price must be below last buy price by dca_price_drop %
        2. RSI must be oversold (support confirmation)
        3. Max dca_max_count positions
        """
        pair = trade.pair

        # No DCA for Short
        if trade.is_short:
            return None

        count = self.dca_count.get(pair, 0)
        max_dca = self.dca_max_count.value

        if count >= max_dca:
            return None

        # Price must be lower than last buy
        last_price = self.last_buy_price.get(pair, None) or trade.open_rate
        required_price = last_price * (1.0 - float(self.dca_price_drop.value))

        if current_rate >= required_price:
            return None

        # Get dataframe for RSI confirmation
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe.empty:
                return None
            last_candle = dataframe.iloc[-1]

            # RSI must be below threshold (oversold = support bounce likely)
            rsi = last_candle.get('rsi', 50)
            if rsi > self.rsi_oversold.value + 10:  # Give some room above oversold
                logger.info(
                    f"[DCA_SKIP] {pair} #{count+1} - RSI {rsi:.1f} too high "
                    f"(need < {self.rsi_oversold.value + 10})"
                )
                return None
        except Exception:
            return None

        # Calculate DCA stake with multiplier
        try:
            available = self.wallets.get_available_stake_amount()
            multiplier = float(self.dca_multiplier.value)
            base_stake = trade.stake_amount  # original stake of the trade
            dca_stake = base_stake * (multiplier ** (count + 1)) / multiplier
            dca_stake = min(dca_stake, available * 0.5)  # max 50% of remaining
            dca_stake = min(dca_stake, max_stake)
            dca_stake = max(dca_stake, min_stake or 30.0)
        except Exception:
            dca_stake = min_stake or 30.0

        # Update state
        self.last_buy_price[pair] = current_rate
        self.dca_count[pair] = count + 1

        logger.info(
            f"[DCA] {pair} #{count+1}/{max_dca} - "
            f"Price: {current_rate:.2f} (last: {last_price:.2f}), "
            f"RSI: {rsi:.1f}, Stake: {dca_stake:.2f}"
        )

        return dca_stake

    # ================================================================
    # CUSTOM EXIT (Short TP only - no SL, let it ride or liquidate)
    # ================================================================

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
        Short: Take profit only. No stop loss - stake is profit bucket money,
               if liquidated we only lose house money, wallet stays intact.
        Long: No custom exit - trailing stop + ROI + DCA handle everything.
        """
        if trade.is_short:
            tp = float(self.short_take_profit.value)

            if current_profit >= tp:
                logger.info(
                    f"[SHORT_TP] {pair} - Profit: {current_profit:.4f}, TP: {tp}"
                )
                return f'short_tp_{current_profit:.4f}'

        return None

    # ================================================================
    # CONFIRM TRADE EXIT (Profit Bucket Capture)
    # ================================================================

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
        On Long exit: capture profit into bucket for Short phase.
        On Short exit: reset state.
        """
        profit = trade.calc_profit(rate)

        if not trade.is_short:
            # Long exit - capture profit
            if profit > 0:
                # Accumulate profit (don't replace, in case of multiple Long cycles)
                existing = self.custom_profit_bucket.get(pair, 0.0)
                self.custom_profit_bucket[pair] = existing + profit
                self.awaiting_short[pair] = True
                logger.info(
                    f"[PROFIT_CAPTURE] {pair} - Long profit: {profit:.2f}, "
                    f"Total bucket: {self.custom_profit_bucket[pair]:.2f}, "
                    f"Short phase activated"
                )
            else:
                logger.info(
                    f"[LONG_EXIT_LOSS] {pair} - Loss: {profit:.2f}, "
                    f"No Short activation"
                )
            # Reset DCA state
            self.dca_count[pair] = 0
            self.last_buy_price.pop(pair, None)
        else:
            # Short exit - log and reset
            bucket_used = self.custom_profit_bucket.get(pair, 0.0)
            self.custom_profit_bucket[pair] = 0.0
            self.awaiting_short[pair] = False
            logger.info(
                f"[SHORT_EXIT] {pair} - Profit: {profit:.2f}, "
                f"Bucket used: {bucket_used:.2f}, State reset"
            )

        return True

    # ================================================================
    # INFORMATIVE PAIRS (not needed for single-pair)
    # ================================================================

    def informative_pairs(self) -> List[Tuple[str, str]]:
        return []

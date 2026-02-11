"""
WolfStrategyV1 - Long -> Short Profit Flip Strategy
=====================================================
Donchian Channel bounce Long with DCA + 100x Short on breakout down.

Phases:
  1. Long: Enter on Donchian lower bounce + RSI oversold + trend filter
     + bullish reversal + volume spike + bounce confirmation
     - DCA with cooling period, progressive spacing, support detection
     - Exit via ATR-based stepped trailing stop or ROI
  2. Short: Enter on Donchian breakout down after profitable Long exit
     - MACD histogram + volume breakdown + EMA confirmation
     - 100x leverage, strict TP
     - Funded from profit bucket (Long phase profit)

Version: 3.0.0
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

    # -- Only 1 open trade at a time --
    max_open_trades = 1

    # -- Minimal ROI: only for Long --
    minimal_roi = {
        "0": 0.06,       # 6% default ROI
        "60": 0.04,      # 4% after 60 min
        "180": 0.025,    # 2.5% after 3h
        "720": 0.01      # 1% after 12h
    }

    # -- Stoploss: effectively disabled for Long, DCA handles drawdowns --
    stoploss = -0.99

    # -- Trailing stop: will be overridden by custom_stoploss --
    trailing_stop = False

    # -- Order types --
    order_types = {
        'entry': 'market',
        'exit': 'market',
        'stoploss': 'market',
        'stoploss_on_exchange': True
    }

    # -- Signals --
    use_exit_signal = True
    exit_profit_only = False

    # -- DCA --
    position_adjustment_enable = True

    # ================================================================
    # HYPEROPT PARAMETERS - BUY SPACE
    # ================================================================
    # Entry signal tuning (3 params optimized)
    donchian_period = IntParameter(14, 30, default=20, space='buy', optimize=True)
    rsi_oversold = IntParameter(25, 45, default=35, space='buy', optimize=True)
    rsi_period = IntParameter(10, 18, default=14, space='buy', optimize=False)
    atr_period = IntParameter(10, 20, default=14, space='buy', optimize=False)

    # EMA: fixed - these are standard values, no need to optimize
    ema_fast = IntParameter(20, 100, default=50, space='buy', optimize=False)
    ema_slow = IntParameter(100, 300, default=200, space='buy', optimize=False)

    # DCA parameters (3 params optimized)
    dca_max_count = IntParameter(2, 6, default=4, space='buy', optimize=True)
    dca_base_drop = DecimalParameter(0.01, 0.04, default=0.02, space='buy', optimize=True)
    dca_multiplier = DecimalParameter(1.2, 2.0, default=1.5, space='buy', optimize=True)
    dca_cooling_candles = IntParameter(2, 8, default=3, space='buy', optimize=False)

    # Long leverage: fixed
    long_leverage_min = DecimalParameter(2.0, 4.0, default=2.0, space='buy', optimize=False)
    long_leverage_max = DecimalParameter(5.0, 10.0, default=7.0, space='buy', optimize=False)

    # ================================================================
    # HYPEROPT PARAMETERS - SELL SPACE
    # ================================================================
    # Short exit (1 param)
    short_take_profit = DecimalParameter(0.015, 0.05, default=0.025, space='sell', optimize=True)

    # Trailing stop parameters (2 params)
    trailing_atr_mult = DecimalParameter(1.0, 2.5, default=1.5, space='sell', optimize=True)
    breakeven_trigger = DecimalParameter(0.008, 0.025, default=0.012, space='sell', optimize=True)

    # Partial profit taking (1 param)
    partial_profit_pct = DecimalParameter(0.015, 0.04, default=0.025, space='sell', optimize=True)

    # Short max stake cap (USDT) - fixed
    short_max_stake = DecimalParameter(20.0, 100.0, default=50.0, space='sell', optimize=False)

    # ================================================================
    # RUNTIME STATE
    # ================================================================
    custom_profit_bucket: Dict[str, float] = {}
    awaiting_short: Dict[str, bool] = {}
    last_buy_price: Dict[str, float] = {}
    dca_count: Dict[str, int] = {}
    last_dca_candle: Dict[str, int] = {}       # candle index of last DCA
    partial_profit_taken: Dict[str, bool] = {}  # track partial TP
    loss_cooldown_until: Dict[str, datetime.datetime] = {}  # cooldown after loss

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

        # -- ATR (for leverage + trailing) --
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period.value)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close'] * 100

        # -- EMA Trend Filter --
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.ema_slow.value)

        # -- MACD --
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_hist'] = macd['macdhist']

        # -- Bollinger Bands --
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_mid'] = bollinger['middleband']
        dataframe['bb_pctb'] = (dataframe['close'] - dataframe['bb_lower']) / \
                                (dataframe['bb_upper'] - dataframe['bb_lower']).replace(0, np.nan)

        # -- Volume analysis --
        dataframe['volume_sma'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma'].replace(0, np.nan)

        # -- Support detection: pivot lows (fractal-like) --
        dataframe['pivot_low'] = (
            (dataframe['low'] < dataframe['low'].shift(1)) &
            (dataframe['low'] < dataframe['low'].shift(2)) &
            (dataframe['low'] < dataframe['low'].shift(-1)) &
            (dataframe['low'] < dataframe['low'].shift(-2))
        )
        dataframe['support'] = dataframe['low'].where(dataframe['pivot_low']).ffill()
        dataframe['support'] = dataframe['support'].rolling(window=50, min_periods=1).min()

        # -- Donchian position: 0 = at lower, 1 = at upper --
        dc_range = dataframe['dc_upper'] - dataframe['dc_lower']
        dataframe['dc_position'] = (
            (dataframe['close'] - dataframe['dc_lower']) /
            dc_range.replace(0, np.nan)
        )

        # -- Green / Red candles --
        dataframe['green_candle'] = dataframe['close'] > dataframe['open']
        dataframe['red_candle'] = dataframe['close'] < dataframe['open']

        # -- RSI direction --
        dataframe['rsi_rising'] = dataframe['rsi'] > dataframe['rsi'].shift(1)
        dataframe['rsi_falling'] = dataframe['rsi'] < dataframe['rsi'].shift(1)

        # -- MACD crossover --
        dataframe['macd_cross_above'] = (
            (dataframe['macd'] > dataframe['macd_signal']) &
            (dataframe['macd'].shift(1) <= dataframe['macd_signal'].shift(1))
        )
        dataframe['macd_cross_below'] = (
            (dataframe['macd'] < dataframe['macd_signal']) &
            (dataframe['macd'].shift(1) >= dataframe['macd_signal'].shift(1))
        )

        # -- Donchian breakout down: close below previous lower --
        dataframe['dc_breakout_down'] = (
            dataframe['close'] < dataframe['dc_lower'].shift(1)
        )

        # -- Volume declining (for DCA - selling exhaustion) --
        dataframe['volume_declining'] = (
            (dataframe['volume'] < dataframe['volume'].shift(1)) &
            (dataframe['volume'].shift(1) < dataframe['volume'].shift(2))
        )

        # -- Candle index for cooling period tracking --
        dataframe['candle_idx'] = range(len(dataframe))

        return dataframe

    # ================================================================
    # ENTRY SIGNALS
    # ================================================================
    #
    # Design philosophy: MULTIPLE independent entry signals, each with
    # only 2-3 conditions. This generates thousands of trades over 13
    # months on 15m timeframe, giving hyperopt enough data to optimize.
    #
    # Long signals (OR logic - any one triggers entry):
    #   1. DC bounce: price in lower 30% of Donchian + RSI dip + green candle
    #   2. BB bounce: price below BB lower + RSI oversold
    #   3. RSI reversal: RSI was oversold and starts rising + green candle
    #   4. MACD cross: MACD crosses above signal in lower DC half
    #
    # Short signals (OR logic):
    #   1. DC breakdown: price breaks below DC lower
    #   2. MACD cross down: MACD crosses below signal + price below EMA
    #
    # Quality is managed by DCA, trailing stop, and risk management -
    # not by filtering entries to near-zero.
    # ================================================================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # -- LONG 1: Donchian lower zone bounce --
        # Price in bottom 30% of Donchian channel + RSI not overbought + green candle
        long_dc = (
            (dataframe['dc_position'] < 0.3) &
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['green_candle']) &
            (dataframe['volume'] > 0)
        )
        dataframe.loc[long_dc, ['enter_long', 'enter_tag']] = (1, 'long_dc_bounce')

        # -- LONG 2: Bollinger Band bounce --
        # Price touches/breaks BB lower + RSI dipping
        long_bb = (
            (dataframe['bb_pctb'] < 0.05) &
            (dataframe['rsi'] < self.rsi_oversold.value + 10) &
            (dataframe['green_candle']) &
            (dataframe['volume'] > 0) &
            (dataframe['enter_long'] != 1)  # not already triggered
        )
        dataframe.loc[long_bb, ['enter_long', 'enter_tag']] = (1, 'long_bb_bounce')

        # -- LONG 3: RSI reversal from oversold --
        # RSI was below oversold and starts rising = momentum turning
        long_rsi = (
            (dataframe['rsi'] < self.rsi_oversold.value + 5) &
            (dataframe['rsi_rising']) &
            (dataframe['rsi'].shift(1) < self.rsi_oversold.value) &
            (dataframe['green_candle']) &
            (dataframe['volume'] > 0) &
            (dataframe['enter_long'] != 1)
        )
        dataframe.loc[long_rsi, ['enter_long', 'enter_tag']] = (1, 'long_rsi_reversal')

        # -- LONG 4: MACD bullish crossover in lower Donchian zone --
        # MACD crosses above signal while price is in lower half of channel
        long_macd = (
            (dataframe['macd_cross_above']) &
            (dataframe['dc_position'] < 0.5) &
            (dataframe['volume'] > 0) &
            (dataframe['enter_long'] != 1)
        )
        dataframe.loc[long_macd, ['enter_long', 'enter_tag']] = (1, 'long_macd_cross')

        # -- SHORT 1: Donchian breakdown --
        # Price breaks below DC lower channel + red candle
        short_dc = (
            (dataframe['dc_breakout_down']) &
            (dataframe['red_candle']) &
            (dataframe['volume'] > 0)
        )
        dataframe.loc[short_dc, ['enter_short', 'enter_tag']] = (1, 'short_dc_breakout')

        # -- SHORT 2: MACD bearish crossover --
        # MACD crosses below signal + price below EMA fast
        short_macd = (
            (dataframe['macd_cross_below']) &
            (dataframe['close'] < dataframe['ema_fast']) &
            (dataframe['red_candle']) &
            (dataframe['volume'] > 0) &
            (dataframe.get('enter_short', 0) != 1)
        )
        dataframe.loc[short_macd, ['enter_short', 'enter_tag']] = (1, 'short_macd_cross')

        return dataframe

    # ================================================================
    # EXIT SIGNALS
    # ================================================================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # -- LONG EXIT 1: Price in upper Donchian zone --
        long_exit_dc = (
            (dataframe['dc_position'] > 0.85) &
            (dataframe['red_candle']) &
            (dataframe['volume'] > 0)
        )
        dataframe.loc[long_exit_dc, ['exit_long', 'exit_tag']] = (1, 'long_dc_upper')

        # -- LONG EXIT 2: RSI overbought --
        long_exit_rsi = (
            (dataframe['rsi'] > 70) &
            (dataframe['rsi_falling']) &
            (dataframe['volume'] > 0) &
            (dataframe['exit_long'] != 1)
        )
        dataframe.loc[long_exit_rsi, ['exit_long', 'exit_tag']] = (1, 'long_rsi_overbought')

        # -- LONG EXIT 3: MACD bearish crossover while in profit zone --
        long_exit_macd = (
            (dataframe['macd_cross_below']) &
            (dataframe['dc_position'] > 0.5) &
            (dataframe['volume'] > 0) &
            (dataframe['exit_long'] != 1)
        )
        dataframe.loc[long_exit_macd, ['exit_long', 'exit_tag']] = (1, 'long_macd_exit')

        # -- SHORT EXIT: emergency signal if price explodes up --
        short_exit = (
            (dataframe['close'] > dataframe['dc_upper']) &
            (dataframe['green_candle'])
        )
        dataframe.loc[short_exit, ['exit_short', 'exit_tag']] = (1, 'short_emergency_signal')

        return dataframe

    # ================================================================
    # CUSTOM STOPLOSS (ATR-based stepped trailing)
    # ================================================================

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime.datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs
    ) -> Optional[float]:
        """
        ATR-based stepped trailing stop for Long.
        Short: no custom stoploss (TP handled in custom_exit, no SL - house money).

        Steps:
          - Profit < breakeven_trigger: default stoploss (-0.99)
          - Profit >= breakeven_trigger: move to breakeven + 0.2% (cover fees)
          - Profit 1-3%: trail at 1.5x ATR
          - Profit 3-5%: trail at 1.0x ATR (tighter)
          - Profit 5%+: trail at 0.7x ATR (very tight)
        """
        if trade.is_short:
            # Short: let it ride, no SL - stake is profit bucket money
            return -0.99

        # Get ATR for dynamic trailing
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe.empty:
                return -0.99
            atr_pct = dataframe.iloc[-1].get('atr_pct', 1.0) / 100.0  # convert to decimal
        except Exception:
            atr_pct = 0.01  # fallback 1%

        atr_mult = float(self.trailing_atr_mult.value)
        be_trigger = float(self.breakeven_trigger.value)

        # Step 1: Below breakeven trigger - default wide SL
        if current_profit < be_trigger:
            return -0.99

        # Step 2: At breakeven trigger - move to breakeven + fee buffer
        if current_profit < 0.03:
            # Trail at 1.5x ATR or breakeven, whichever is tighter
            trail = max(atr_pct * atr_mult, 0.003)  # at least 0.3%
            sl = min(-trail, -0.002)  # at least breakeven + 0.2%
            return sl

        # Step 3: 3-5% profit - tighter trailing
        if current_profit < 0.05:
            trail = max(atr_pct * atr_mult * 0.7, 0.003)
            return -trail

        # Step 4: 5%+ profit - very tight trailing
        trail = max(atr_pct * atr_mult * 0.5, 0.002)
        return -trail

    # ================================================================
    # CONFIRM TRADE ENTRY (runtime gate for Short + cooldown)
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
        Gate Long entries: check cooldown after loss.
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
            self.awaiting_short[pair] = False
            return True

        # Long: check cooldown after loss
        if side == 'long':
            cooldown_until = self.loss_cooldown_until.get(pair)
            if cooldown_until and current_time < cooldown_until:
                logger.info(
                    f"[LONG_COOLDOWN] {pair} - Cooling down until {cooldown_until}, "
                    f"blocking Long entry"
                )
                return False

            self.dca_count[pair] = 0
            self.last_buy_price[pair] = rate
            self.last_dca_candle[pair] = 0
            self.partial_profit_taken[pair] = False
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
        Short: Use profit bucket amount (capped).
        """
        try:
            if side == 'short':
                pair = kwargs.get('pair', '')
                profit = self.custom_profit_bucket.get(pair, 0.0)
                if profit <= 0:
                    return min_stake or 30.0
                # Cap short stake to limit risk
                cap = float(self.short_max_stake.value)
                short_stake = min(profit * 0.9, cap)
                short_stake = max(short_stake, min_stake or 30.0)
                short_stake = min(short_stake, max_stake)
                logger.info(
                    f"[SHORT_STAKE] {pair} - Stake: {short_stake:.2f} "
                    f"from bucket: {profit:.2f}, cap: {cap:.2f}"
                )
                return short_stake

            # Long: split wallet for DCA room
            balance = self.wallets.get_total_stake_amount()
            num_positions = self.dca_max_count.value + 1
            per_position = balance * 0.8 / num_positions
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
        Long: Dynamic 2-10x based on ATR volatility.
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
                lev_min = float(self.long_leverage_min.value)
                lev_max = float(self.long_leverage_max.value)
                if atr_pct > 3.0:
                    lev = lev_min
                elif atr_pct < 0.5:
                    lev = lev_max
                else:
                    # Linear interpolation: high ATR -> low leverage
                    ratio = (3.0 - atr_pct) / 2.5
                    lev = lev_min + ratio * (lev_max - lev_min)
                lev = round(min(lev, max_leverage), 1)
                logger.info(f"[LEVERAGE] {pair} Long: {lev}x (ATR%: {atr_pct:.2f})")
                return lev
        except Exception as e:
            logger.error(f"Error in leverage: {e}")

        return min(3.0, max_leverage)

    # ================================================================
    # DCA (adjust_trade_position) - Enhanced
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
        1. Price must drop by required % from last buy (progressive spacing)
        2. Cooling period: min N candles between DCA orders
        3. Max drawdown check: stop DCA if too deep
        """
        pair = trade.pair

        # No DCA for Short
        if trade.is_short:
            return None

        count = self.dca_count.get(pair, 0)
        max_dca = self.dca_max_count.value

        if count >= max_dca:
            return None

        # Max drawdown check: stop DCA if unrealized loss > 20%
        if current_profit < -0.20:
            logger.info(
                f"[DCA_BLOCKED] {pair} - Drawdown {current_profit:.2%} > 20%, "
                f"stopping DCA"
            )
            return None

        # Progressive spacing: each DCA needs a bigger drop
        base_drop = float(self.dca_base_drop.value)
        progressive_factor = 1.0 + (count * 0.3)  # gentler progression
        required_drop = base_drop * progressive_factor

        last_price = self.last_buy_price.get(pair, None) or trade.open_rate
        required_price = last_price * (1.0 - required_drop)

        if current_rate >= required_price:
            return None

        # Cooling period check
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe.empty:
                return None
            last_candle = dataframe.iloc[-1]
            current_candle_idx = int(last_candle.get('candle_idx', 0))

            last_dca_idx = self.last_dca_candle.get(pair, 0)
            cooling = self.dca_cooling_candles.value
            if (current_candle_idx - last_dca_idx) < cooling:
                return None

        except Exception:
            return None

        # Calculate DCA stake with multiplier
        try:
            available = self.wallets.get_available_stake_amount()
            multiplier = float(self.dca_multiplier.value)
            base_stake = trade.stake_amount
            dca_stake = base_stake * (multiplier ** (count + 1)) / multiplier
            dca_stake = min(dca_stake, available * 0.5)
            dca_stake = min(dca_stake, max_stake)
            dca_stake = max(dca_stake, min_stake or 30.0)
        except Exception:
            dca_stake = min_stake or 30.0

        # Update state
        self.last_buy_price[pair] = current_rate
        self.dca_count[pair] = count + 1
        self.last_dca_candle[pair] = current_candle_idx

        logger.info(
            f"[DCA] {pair} #{count+1}/{max_dca} - "
            f"Price: {current_rate:.2f} (last: {last_price:.2f}, "
            f"drop: {required_drop:.1%}), Stake: {dca_stake:.2f}"
        )

        return dca_stake

    # ================================================================
    # CUSTOM EXIT (Short TP + Long partial profit)
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
        Short: Take profit at target.
        Long: Partial profit taking at threshold (sell ~50% signal).
        """
        if trade.is_short:
            tp = float(self.short_take_profit.value)
            if current_profit >= tp:
                logger.info(
                    f"[SHORT_TP] {pair} - Profit: {current_profit:.4f}, TP: {tp}"
                )
                return f'short_tp_{current_profit:.4f}'

        # Long: partial profit taking
        if not trade.is_short:
            pp_pct = float(self.partial_profit_pct.value)
            if not self.partial_profit_taken.get(pair, False) and current_profit >= pp_pct:
                self.partial_profit_taken[pair] = True
                logger.info(
                    f"[PARTIAL_TP] {pair} - Profit: {current_profit:.4f}, "
                    f"taking partial at {pp_pct}"
                )
                return f'partial_tp_{current_profit:.4f}'

        return None

    # ================================================================
    # CONFIRM TRADE EXIT (Profit Bucket Capture + Cooldown)
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
        On Long loss: set cooldown.
        """
        profit = trade.calc_profit(rate)

        if not trade.is_short:
            # Long exit
            if profit > 0:
                existing = self.custom_profit_bucket.get(pair, 0.0)
                self.custom_profit_bucket[pair] = existing + profit
                self.awaiting_short[pair] = True
                logger.info(
                    f"[PROFIT_CAPTURE] {pair} - Long profit: {profit:.2f}, "
                    f"Total bucket: {self.custom_profit_bucket[pair]:.2f}, "
                    f"Short phase activated"
                )
            else:
                # Loss: set cooldown (4 hours = 16 candles at 15m)
                cooldown_hours = 4
                self.loss_cooldown_until[pair] = (
                    current_time + datetime.timedelta(hours=cooldown_hours)
                )
                logger.info(
                    f"[LONG_EXIT_LOSS] {pair} - Loss: {profit:.2f}, "
                    f"Cooldown until {self.loss_cooldown_until[pair]}, "
                    f"No Short activation"
                )
            # Reset DCA state
            self.dca_count[pair] = 0
            self.last_buy_price.pop(pair, None)
            self.last_dca_candle.pop(pair, None)
            self.partial_profit_taken.pop(pair, None)
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
    # INFORMATIVE PAIRS
    # ================================================================

    def informative_pairs(self) -> List[Tuple[str, str]]:
        return []

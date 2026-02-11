"""
Tests for WolfStrategyV1 configuration and class-level settings.
"""

import json
import os
import pytest


class TestStrategyClassConfig:
    """Test strategy class-level configuration."""

    def test_can_short_enabled(self, strategy):
        """can_short must be True."""
        assert strategy.can_short is True

    def test_max_open_trades_is_one(self, strategy):
        """max_open_trades must be 1."""
        assert strategy.max_open_trades == 1

    def test_interface_version(self, strategy):
        """Interface version must be 3."""
        assert strategy.INTERFACE_VERSION == 3

    def test_timeframe(self, strategy):
        """Default timeframe must be 15m."""
        assert strategy.timeframe == '15m'

    def test_position_adjustment_enabled(self, strategy):
        """DCA must be enabled."""
        assert strategy.position_adjustment_enable is True

    def test_stoploss_effectively_disabled(self, strategy):
        """Default stoploss must be -0.99 (disabled, DCA handles)."""
        assert strategy.stoploss == -0.99

    def test_trailing_stop_disabled(self, strategy):
        """Native trailing_stop disabled (custom_stoploss handles it)."""
        assert strategy.trailing_stop is False

    def test_stoploss_on_exchange(self, strategy):
        """stoploss_on_exchange must be True for safety."""
        assert strategy.order_types.get('stoploss_on_exchange') is True

    def test_order_types_market(self, strategy):
        """All order types must be market."""
        assert strategy.order_types['entry'] == 'market'
        assert strategy.order_types['exit'] == 'market'
        assert strategy.order_types['stoploss'] == 'market'

    def test_minimal_roi_exists(self, strategy):
        """minimal_roi must have entries."""
        assert len(strategy.minimal_roi) > 0
        # First ROI entry should be the highest
        values = list(strategy.minimal_roi.values())
        assert values[0] == max(values)

    def test_minimal_roi_decreasing(self, strategy):
        """ROI values must decrease over time."""
        roi = strategy.minimal_roi
        sorted_keys = sorted(roi.keys(), key=lambda x: int(x))
        values = [roi[k] for k in sorted_keys]
        for i in range(1, len(values)):
            assert values[i] <= values[i-1], \
                f"ROI not decreasing: {values[i-1]} -> {values[i]}"


class TestHyperoptParameters:
    """Test hyperopt parameter ranges and defaults."""

    def test_donchian_period_range(self, strategy):
        """Donchian period must be in valid range."""
        p = strategy.donchian_period
        assert p.low <= p.value <= p.high
        assert p.low >= 5
        assert p.high <= 100

    def test_rsi_oversold_range(self, strategy):
        """RSI oversold must be reasonable."""
        p = strategy.rsi_oversold
        assert 15 <= p.value <= 50
        assert p.low >= 10

    def test_dca_max_count_range(self, strategy):
        """DCA max count must be reasonable."""
        p = strategy.dca_max_count
        assert 1 <= p.value <= 15
        assert p.low >= 1

    def test_dca_multiplier_above_one(self, strategy):
        """DCA multiplier must be > 1 (increasing stakes)."""
        assert strategy.dca_multiplier.value > 1.0

    def test_long_leverage_range(self, strategy):
        """Long leverage must be 2-10x."""
        assert strategy.long_leverage_min.value >= 1.0
        assert strategy.long_leverage_max.value <= 10.0
        assert strategy.long_leverage_min.value < strategy.long_leverage_max.value

    def test_short_take_profit_positive(self, strategy):
        """Short TP must be positive."""
        assert strategy.short_take_profit.value > 0

    def test_breakeven_trigger_positive(self, strategy):
        """Breakeven trigger must be positive."""
        assert strategy.breakeven_trigger.value > 0

    def test_short_max_stake_reasonable(self, strategy):
        """Short max stake cap must be reasonable."""
        assert strategy.short_max_stake.value > 0
        assert strategy.short_max_stake.value <= 200

    def test_dca_cooling_candles_positive(self, strategy):
        """Cooling candles must be positive."""
        assert strategy.dca_cooling_candles.value > 0

    def test_ema_fast_less_than_slow(self, strategy):
        """EMA fast period must be less than slow."""
        assert strategy.ema_fast.value < strategy.ema_slow.value


class TestConfigFile:
    """Test config_wolf_v1.json configuration."""

    @pytest.fixture
    def config(self):
        config_path = os.path.join(
            os.path.dirname(__file__), '..', 'config_wolf_v1.json'
        )
        with open(config_path) as f:
            return json.load(f)

    def test_trading_mode_futures(self, config):
        """Trading mode must be futures."""
        assert config.get('trading_mode') == 'futures'

    def test_margin_mode_isolated(self, config):
        """Margin mode must be isolated."""
        assert config.get('margin_mode') == 'isolated'

    def test_exchange_futures(self, config):
        """Exchange must be configured for futures."""
        exchange = config.get('exchange', {})
        assert exchange.get('trading_mode') == 'futures'
        assert exchange.get('margin_mode') == 'isolated'

    def test_dry_run_enabled(self, config):
        """Dry run must be enabled (safety)."""
        exchange = config.get('exchange', {})
        assert exchange.get('dry_run') is True

    def test_liquidation_buffer(self, config):
        """Liquidation buffer must be at least 5%."""
        buf = float(config.get('liquidation_buffer', 0))
        assert buf >= 0.05

    def test_strategy_name(self, config):
        """Strategy name must match."""
        assert config.get('strategy') == 'WolfStrategyV1'

#!/usr/bin/env python3
"""
WolfStrategyV1 Configuration Generator
Generates freqtrade config for hyperopt and backtesting
"""

import json
import sys
from pathlib import Path


def generate_config(config_path: str, pairs: str) -> dict:
    """Generate complete freqtrade configuration."""

    pair_list = [p.strip() for p in pairs.split(',') if p.strip()]

    config = {
        "strategy": "WolfStrategyV1",
        "strategy_path": "user_data/strategies",
        "bot_name": "WolfStrategyV1",
        "initial_state": "running",
        "force_entry_enable": False,
        "disable_dataframe_checks": False,
        "abort_transaction_on_candle_closed": False,

        "exchange": {
            "name": "bybit",
            "key": "${EXCHANGE_KEY}",
            "secret": "${EXCHANGE_SECRET}",
            "password": "",
            "pair_whitelist": pair_list,
            "ccxt_config": {
                "enableRateLimit": True,
                "rateLimit": 200
            },
            "ccxt_async_config": {
                "enableRateLimit": True,
                "rateLimit": 200
            }
        },

        "trading_mode": "futures",
        "margin_mode": "isolated",
        "dry_run": False,
        "dry_run_wallet": 10000,

        "stake_currency": "USDT",
        "stake_amount": 100.0,
        "tradable_balance_ratio": 0.9,
        "fiat_display_currency": "USD",
        "max_open_trades": 3,

        "timeframe": "5m",
        "timeframe_detail": "",
        "timeframe_hierarchy": {
            "1m": "5m",
            "5m": "15m",
            "15m": "1h",
            "1h": "4h",
            "4h": "1d",
            "1d": "1w"
        },

        "unfilledtimeout": {
            "entry": 30,
            "exit": 30
        },

        "stoploss": -0.5,

        "pairlists": [
            {
                "method": "VolumePairList",
                "config": {
                    "number_assets": 20,
                    "stake_currency": "USDT",
                    "fiat_display_currency": "USD",
                    "refresh_period": 1800
                }
            }
        ],


        "telegram": {
            "enabled": False
        },

        "webhook": {
            "enabled": False
        },

        "api_server": {
            "enabled": True,
            "listen_ip": "127.0.0.1",
            "listen_port": 8080,
            "username": "${FREQTRADE_API_USERNAME}",
            "password": "${FREQTRADE_API_PASSWORD}",
            "jwt_secret": "${FREQTRADE_JWT_SECRET}",
            "whitelist_refresh_period": 60
        },

        "datadir": "user_data/data/{exchange}",
        "user_data_dir": "user_data",
        "export_trades": True,

        "liquidation_buffer": 0.05,

        "position_adjustment_enable": True,

        "hyperopt": {
            "position_adjustment_enable": True,
            "max_entry_adjustment_order": 10,
            "dca_params": {
                "enable": True,
                "initial_stake_amount": 100.0,
                "py_trade_increase": 1.5,
                "py_trade_decrease": 0.3,
                "max_trade_number": 5,
                "max_stake_amount": 500.0,
                "min_trade_number": 0.3
            }
        },

        "backtest": {
            "position_adjustment_enable": True,
            "max_entry_adjustment_order": 10,
            "dca_params": {
                "enable": True,
                "initial_stake_amount": 100.0,
                "py_trade_increase": 1.5,
                "py_trade_decrease": 0.3,
                "max_trade_number": 5,
                "max_stake_amount": 500.0,
                "min_trade_number": 0.3
            }
        }
    }

    return config


def main():
    if len(sys.argv) < 2:
        config_path = "user_data/config_wolf.json"
        pairs = "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT"
    else:
        config_path = sys.argv[1]
        pairs = sys.argv[2] if len(sys.argv) > 2 else "BTC/USDT:USDT"

    config = generate_config(config_path, pairs)

    Path(config_path).parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

    print(f"✅ Config generated: {config_path}")
    print(f"   Pairs: {pairs}")
    print(f"   Trading mode: futures (isolated)")
    print(f"   Short leverage: 100x")
    print(f"   Position adjustment: enabled")


if __name__ == "__main__":
    main()

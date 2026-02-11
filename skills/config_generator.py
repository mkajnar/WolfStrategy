"""
ConfigGenerator Skill
=====================
Configuration management for WolfStrategyV1.
"""

import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FreqtradeConfig:
    """Freqtrade configuration."""
    strategy: str = "WolfStrategyV1"
    exchange: str = "binance"
    trading_mode: str = "futures"
    margin_mode: str = "isolated"
    stake_currency: str = "USDT"
    stake_amount: float = 100.0
    max_open_trades: int = 3
    dry_run: bool = False
    dry_run_wallet: float = 10000.0
    timeframe: str = "5m"
    pairs: List[str] = None
    
    def __post_init__(self):
        if self.pairs is None:
            self.pairs = ["BTC/USDT:USDT", "ETH/USDT:USDT"]


class ConfigGenerator:
    """
    FreqTrade configuration generator.
    
    Capabilities:
    - Generate complete config
    - Manage pair lists
    - Configure leverage
    - Handle DCA parameters
    """
    
    def __init__(self, config: Optional[FreqtradeConfig] = None):
        self.config = config or FreqtradeConfig()
    
    def generate_config(self, output_path: str = "user_data/config.json") -> Dict:
        """Generate complete Freqtrade configuration."""
        config = {
            "strategy": self.config.strategy,
            "strategy_path": "user_data/strategies",
            "bot_name": f"WolfStrategyV1-{self.config.timeframe}",
            
            "initial_state": "running",
            "force_entry_enable": False,
            "disable_dataframe_checks": False,
            
            "exchange": {
                "name": self.config.exchange,
                "key": "${EXCHANGE_KEY}",
                "secret": "${EXCHANGE_SECRET}",
                "password": "",
                "ccxt_config": {
                    "enableRateLimit": True,
                    "rateLimit": 200
                },
                "ccxt_async_config": {
                    "enableRateLimit": True,
                    "rateLimit": 200
                }
            },
            
            "trading_mode": self.config.trading_mode,
            "margin_mode": self.config.margin_mode,
            "dry_run": self.config.dry_run,
            "dry_run_wallet": self.config.dry_run_wallet,
            
            "stake_currency": self.config.stake_currency,
            "stake_amount": self.config.stake_amount,
            "tradable_balance_ratio": 0.9,
            "fiat_display_currency": "USD",
            "max_open_trades": self.config.max_open_trades,
            
            "timeframe": self.config.timeframe,
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
            
            "stoploss": {
                "enabled": True,
                "method": "absolute",
                "stop": -0.5
            },
            
            "minimal_roi": {
                "0": 0.03
            },
            
            "trailing_stop": True,
            "trailing_only_offset_is_reached": True,
            "trailing_stop_positive": 0.003,
            "trailing_stop_positive_offset": 0.008,
            
            "use_exit_signal": True,
            "exit_profit_only": False,
            
            "entry_pricing": {
                "price_last_balance": 0.0,
                "use_order_book": True,
                "order_book_top": 1
            },
            
            "exit_pricing": {
                "price_last_balance": 0.0,
                "use_order_book": True,
                "order_book_top": 1
            },
            
            "order_types": {
                "entry": "market",
                "exit": "market",
                "stoploss": "market",
                "stoploss_on_exchange": False
            },
            
            "leverage": {
                "default": {
                    "long": 5.0,
                    "short": 100.0
                }
            },
            
            "pairlists": [
                {
                    "method": "StaticPairList",
                    "config": {}
                }
            ],
            
            "exchange": {
                "pair_whitelist": self.config.pairs
            },
            
            "telegram": {
                "enabled": False
            },
            
            "api_server": {
                "enabled": True,
                "listen_ip": "127.0.0.1",
                "listen_port": 8080,
                "username": "${FREQTRADE_API_USERNAME}",
                "password": "${FREQTRADE_API_PASSWORD}",
                "jwt_secret": "${FREQTRADE_JWT_SECRET}"
            },
            
            "datadir": "user_data/data/{exchange}",
            "user_data_dir": "user_data",
            "export_trades": True,
            
            "position_adjustment_enable": True,
            
            "hyperopt": {
                "position_adjustment_enable": True,
                "max_entry_adjustment_order": 10,
                "dca_params": {
                    "enable": True,
                    "initial_stake_amount": self.config.stake_amount,
                    "py_trade_increase": 1.5,
                    "py_trade_decrease": 0.3,
                    "max_trade_number": 5,
                    "max_stake_amount": 500.0,
                    "min_trade_number": 0.3
                }
            },
            
            "backtest": {
                "position_adjustment_enable": True
            }
        }
        
        self._save_config(config, output_path)
        return config
    
    def _save_config(self, config: Dict, output_path: str) -> bool:
        """Save configuration to file."""
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w') as f:
                json.dump(config, f, indent=4)
            
            logger.info(f"[CONFIG] Config saved: {output_path}")
            return True
        except Exception as e:
            logger.error(f"[CONFIG] Failed to save config: {e}")
            return False
    
    def generate_k8s_manifest(
        self,
        bot_name: str,
        output_dir: str,
        namespace: str = "default",
        nodeport: int = 30500
    ) -> Dict:
        """Generate K8s deployment manifest."""
        manifest = {
            "apiVersion": "freqtrade.io/v1alpha1",
            "kind": "Bot",
            "metadata": {
                "name": bot_name,
                "namespace": namespace
            },
            "spec": {
                "image": {
                    "repository": "freqtradeorg/freqtrade",
                    "tag": "develop"
                },
                "deployment": {
                    "env": [
                        {
                            "name": "WOLF_SHORT_LEVERAGE",
                            "value": "100"
                        }
                    ],
                    "resources": {
                        "requests": {
                            "cpu": "1000m",
                            "memory": "2Gi"
                        },
                        "limits": {
                            "cpu": "2000m",
                            "memory": "4Gi"
                        }
                    }
                },
                "exchange": self.config.exchange,
                "database": "sqlite:////freqtrade/db_persist/database.db",
                "config": {
                    "initial_state": "running",
                    "max_open_trades": self.config.max_open_trades,
                    "stake_currency": self.config.stake_currency,
                    "stake_amount": str(self.config.stake_amount),
                    "trading_mode": self.config.trading_mode,
                    "margin_mode": self.config.margin_mode,
                    "timeframe": self.config.timeframe,
                    "dry_run": self.config.dry_run,
                    "leverage": [
                        {
                            "side": "long",
                            "leverage": 5.0
                        },
                        {
                            "side": "short",
                            "leverage": 100.0
                        }
                    ]
                },
                "strategy": {
                    "name": self.config.strategy
                },
                "api": {
                    "enabled": True,
                    "port": 8081
                }
            }
        }
        
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        # Save manifest
        manifest_path = f"{output_dir}/bot.yaml"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        # Generate secret
        self._generate_k8s_secret(bot_name, output_dir, namespace)
        
        # Generate service
        self._generate_k8s_service(bot_name, output_dir, namespace, nodeport)
        
        logger.info(f"[CONFIG] K8s manifest generated: {manifest_path}")
        
        return manifest
    
    def _generate_k8s_secret(
        self, 
        bot_name: str, 
        output_dir: str,
        namespace: str
    ) -> None:
        """Generate K8s secret manifest."""
        import base64
        
        secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": f"{bot_name}-secret",
                "namespace": namespace
            },
            "type": "Opaque",
            "data": {
                "api_password": base64.b64encode(b"freqtrade").decode(),
                "api_username": base64.b64encode(b"freqtrade").decode(),
                "exchange_key": base64.b64encode(b"").decode(),
                "exchange_secret": base64.b64encode(b"").decode(),
                "jwt_secret_key": base64.b64encode(b"").decode()
            }
        }
        
        with open(f"{output_dir}/secret.yaml", 'w') as f:
            json.dump(secret, f, indent=2)
    
    def _generate_k8s_service(
        self,
        bot_name: str,
        output_dir: str,
        namespace: str,
        nodeport: int
    ) -> None:
        """Generate K8s service manifest."""
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": f"{bot_name}-service",
                "namespace": namespace
            },
            "spec": {
                "type": "NodePort",
                "selector": {
                    "app.kubernetes.io/name": bot_name
                },
                "ports": [
                    {
                        "port": 8081,
                        "targetPort": 8081,
                        "nodePort": nodeport
                    }
                ]
            }
        }
        
        with open(f"{output_dir}/service.yaml", 'w') as f:
            json.dump(service, f, indent=2)
    
    def validate_config(self, config_path: str = "user_data/config.json") -> Dict:
        """Validate configuration file."""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            errors = []
            warnings = []
            
            # Check required fields
            required_fields = ['strategy', 'exchange', 'trading_mode']
            for field in required_fields:
                if field not in config:
                    errors.append(f"Missing required field: {field}")
            
            # Check pairs
            if 'exchange' in config and 'pair_whitelist' not in config.get('exchange', {}):
                warnings.append("No pair whitelist configured")
            
            # Check leverage
            if 'leverage' not in config:
                warnings.append("No leverage configured")
            
            return {
                'valid': len(errors) == 0,
                'errors': errors,
                'warnings': warnings,
                'config': config
            }
            
        except Exception as e:
            return {
                'valid': False,
                'errors': [str(e)],
                'warnings': [],
                'config': {}
            }

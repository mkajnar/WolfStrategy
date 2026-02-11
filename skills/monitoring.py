"""
Monitoring Skill
================
Strategy monitoring and logging for WolfStrategyV1.
"""

import logging
import json
import time
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MonitorConfig:
    """Monitoring configuration."""
    log_level: str = "INFO"
    log_file: str = "wolf_strategy.log"
    stats_interval: int = 60
    profit_threshold: float = 0.01
    loss_threshold: float = -0.05


class StrategyMonitor:
    """
    Strategy monitoring and logging.
    
    Capabilities:
    - Configure logging
    - Track strategy statistics
    - Monitor profit/loss
    - Alert on conditions
    """
    
    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self.stats = {
            'start_time': None,
            'trades_count': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_profit': 0.0,
            'peak_profit': 0.0,
            'max_drawdown': 0.0,
            'last_trade_time': None,
        }
        self.alert_callbacks: Dict[str, Callable] = {}
        self._setup_logging()
    
    def _setup_logging(self) -> None:
        """Configure logging for the strategy."""
        log_format = '%(asctime)s | %(levelname)-8s | %(message)s'
        date_format = '%Y-%m-%d %H:%M:%S'
        
        # File handler
        file_handler = logging.FileHandler(self.config.log_file)
        file_handler.setLevel(getattr(logging, self.config.log_level))
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, self.config.log_level))
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
        
        # Get root logger and add handlers
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self.config.log_level))
        
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
    
    def register_alert(self, name: str, callback: Callable, condition: str = "always") -> None:
        """Register alert callback."""
        self.alert_callbacks[name] = {
            'callback': callback,
            'condition': condition
        }
        logger.info(f"[MONITOR] Alert registered: {name}")
    
    def on_trade_open(self, pair: str, direction: str, amount: float, price: float) -> None:
        """Called when trade is opened."""
        self.stats['trades_count'] += 1
        self.stats['last_trade_time'] = datetime.now()
        
        logger.info(
            f"[TRADE_OPEN] {pair} | {direction.upper()} | "
            f"Amount: {amount:.4f} | Price: {price:.6f}"
        )
    
    def on_trade_close(
        self, 
        pair: str, 
        profit_pct: float, 
        profit_abs: float,
        exit_reason: str
    ) -> None:
        """Called when trade is closed."""
        self.stats['total_profit'] += profit_abs
        
        if profit_pct > 0:
            self.stats['winning_trades'] += 1
        else:
            self.stats['losing_trades'] += 1
        
        # Update peak profit and drawdown
        if self.stats['total_profit'] > self.stats['peak_profit']:
            self.stats['peak_profit'] = self.stats['total_profit']
        
        drawdown = self.stats['peak_profit'] - self.stats['total_profit']
        if drawdown > self.stats['max_drawdown']:
            self.stats['max_drawdown'] = drawdown
        
        # Check alerts
        self._check_alerts('trade_close', pair, profit_pct, profit_abs)
        
        logger.info(
            f"[TRADE_CLOSE] {pair} | Reason: {exit_reason} | "
            f"Profit: {profit_pct:.4f}% ({profit_abs:.4f})"
        )
    
    def on_dca_execute(
        self, 
        pair: str, 
        dca_number: int, 
        total_dca: int,
        amount: float,
        price: float
    ) -> None:
        """Called when DCA is executed."""
        logger.info(
            f"[DCA_EXECUTED] {pair} | DCA #{dca_number}/{total_dca} | "
            f"Amount: {amount:.4f} | Price: {price:.6f}"
        )
    
    def on_short_activate(self, pair: str, profit_bucket: float) -> None:
        """Called when Short phase is activated."""
        logger.info(
            f"[SHORT_ACTIVATE] {pair} | Profit bucket: {profit_bucket:.4f} | "
            f"Waiting for Donchian breakout..."
        )
    
    def on_short_entry(self, pair: str, price: float, leverage: float) -> None:
        """Called when Short entry is triggered."""
        logger.info(
            f"[SHORT_ENTRY] {pair} | Price: {price:.6f} | Leverage: {leverage}x"
        )
    
    def on_profit_capture(self, pair: str, profit: float) -> None:
        """Called when profit is captured for Short."""
        logger.info(
            f"[PROFIT_CAPTURE] {pair} | Profit: {profit:.4f} | "
            f"Short phase activated"
        )
    
    def _check_alerts(self, event: str, *args, **kwargs) -> None:
        """Check and fire alerts."""
        for name, alert in self.alert_callbacks.items():
            if alert['condition'] == event or alert['condition'] == 'always':
                try:
                    alert['callback'](event, *args, **kwargs)
                except Exception as e:
                    logger.error(f"[MONITOR] Alert callback failed: {e}")
    
    def get_statistics(self) -> Dict:
        """Get current strategy statistics."""
        elapsed = 0
        if self.stats['start_time']:
            elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
        
        total_trades = self.stats['trading_count']
        win_rate = (
            self.stats['winning_trades'] / total_trades 
            if total_trades > 0 else 0
        )
        
        return {
            'running_time_seconds': elapsed,
            'total_trades': total_trades,
            'winning_trades': self.stats['winning_trades'],
            'losing_trades': self.stats['losing_trades'],
            'win_rate': win_rate,
            'total_profit': self.stats['total_profit'],
            'peak_profit': self.stats['peak_profit'],
            'max_drawdown': self.stats['max_drawdown'],
            'profit_per_trade': (
                self.stats['total_profit'] / total_trades 
                if total_trades > 0 else 0
            )
        }
    
    def print_statistics(self) -> None:
        """Print formatted statistics."""
        stats = self.get_statistics()
        
        logger.info("=" * 60)
        logger.info("📊 WOLFSTRATEGYV1 STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Running time:     {stats['running_time_seconds']/3600:.2f} hours")
        logger.info(f"Total trades:     {stats['total_trades']}")
        logger.info(f"Win rate:         {stats['win_rate']*100:.2f}%")
        logger.info(f"Total profit:    {stats['total_profit']:.4f} USDT")
        logger.info(f"Peak profit:      {stats['peak_profit']:.4f} USDT")
        logger.info(f"Max drawdown:     {stats['max_drawdown']:.4f} USDT")
        logger.info(f"Profit/trade:    {stats['profit_per_trade']:.4f} USDT")
        logger.info("=" * 60)
    
    def log_strategy_state(self, pair: str, state: Dict) -> None:
        """Log current strategy state."""
        logger.info(f"[STRATEGY_STATE] {pair} | {json.dumps(state)}")
    
    def start(self) -> None:
        """Start monitoring."""
        self.stats['start_time'] = datetime.now()
        logger.info("[MONITOR] WolfStrategyV1 monitoring started")
    
    def stop(self) -> None:
        """Stop monitoring and print final stats."""
        self.print_statistics()
        logger.info("[MONITOR] WolfStrategyV1 monitoring stopped")

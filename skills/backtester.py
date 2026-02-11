"""
Backtester Skill
================
Backtesting operations for WolfStrategyV1.
"""

import subprocess
import json
import logging
import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Backtest configuration."""
    strategy: str = "WolfStrategyV1"
    strategy_path: str = "user_data/strategies"
    config: str = "user_data/config.json"
    timeframe: str = "5m"
    pairs: List[str] = None
    timerange: str = "20260101-20260208"
    position_adjustment: bool = True
    
    def __post_init__(self):
        if self.pairs is None:
            self.pairs = ["BTC/USDT:USDT"]


class Backtester:
    """
    FreqTrade backtesting operations.
    
    Capabilities:
    - Run backtests
    - Analyze results
    - Generate reports
    """
    
    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        self.docker_image = "freqtradeorg/freqtrade:latest"
    
    def prepare_environment(self) -> bool:
        """Prepare environment for backtest."""
        logger.info("[BACKTEST] Preparing environment...")
        
        Path(self.config.strategy_path).mkdir(parents=True, exist_ok=True)
        
        strategy_file = Path(self.config.strategy_path) / f"{self.config.strategy}.py"
        if not strategy_file.exists():
            logger.error(f"[BACKTEST] Strategy file not found: {strategy_file}")
            return False
        
        logger.info("[BACKTEST] Environment ready")
        return True
    
    def run_backtest(
        self,
        export: bool = True,
        export_format: str = "json"
    ) -> Tuple[bool, Dict]:
        """
        Run backtest.
        
        Returns:
            Tuple of (success, results_dict)
        """
        if not self.prepare_environment():
            return False, {'error': 'Environment not ready'}
        
        pairs_str = ' '.join(self.config.pairs)
        
        cmd = [
            'docker', 'run', '--rm',
            '-v', f'{os.getcwd()}/user_data:/freqtrade/user_data',
            self.docker_image,
            'backtesting',
            '--strategy', self.config.strategy,
            '--strategy-path', '/freqtrade/user_data/strategies',
            '--timeframe', self.config.timeframe,
            '--pairs', pairs_str,
            '--timerange', self.config.timerange,
        ]
        
        if export:
            cmd.extend(['--export', export_format])
        
        logger.info(f"[BACKTEST] Starting backtest...")
        logger.info(f"[BACKTEST] Strategy: {self.config.strategy}")
        logger.info(f"[BACKTEST] Pairs: {pairs_str}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        output = result.stdout + result.stderr
        
        if result.returncode == 0:
            logger.info("[BACKTEST] Completed successfully")
            
            # Try to parse results
            results = self._parse_backtest_output(output)
            return True, results
        else:
            logger.error(f"[BACKTEST] Failed: {result.stderr}")
            return False, {'error': result.stderr}
    
    def _parse_backtest_output(self, output: str) -> Dict:
        """Parse backtest output to extract metrics."""
        metrics = {
            'raw': output,
            'trades': 0,
            'profit_pct': 0.0,
            'duration_days': 0,
            'max_drawdown': 0.0,
        }
        
        # Simple pattern matching for key metrics
        import re
        
        # Total trades
        trades_match = re.search(r'Total\s+trades\s+:\s+(\d+)', output)
        if trades_match:
            metrics['trades'] = int(trades_match.group(1))
        
        # Profit percentage
        profit_match = re.search(r'ROI.*?:.*?([\d.-]+)%', output)
        if profit_match:
            metrics['profit_pct'] = float(profit_match.group(1))
        
        # Max drawdown
        dd_match = re.search(r'Max\s+drawdown.*?:.*?([\d.-]+)%', output)
        if dd_match:
            metrics['max_drawdown'] = float(dd_match.group(1))
        
        # Duration
        dur_match = re.search(r'Backtest\s+period.*?:.*?(\d+)\s+days', output)
        if dur_match:
            metrics['duration_days'] = int(dur_match.group(1))
        
        return metrics
    
    def quick_backtest(self) -> Dict:
        """Run quick 1-week backtest."""
        config = BacktestConfig(
            timerange="20260101-20260108"
        )
        backtester = Backtester(config)
        success, results = backtester.run_backtest()
        return results
    
    def analyze_trades(self, trades_file: str = "user_data/backtest_results.json") -> List[Dict]:
        """Analyze individual trades from backtest."""
        if not Path(trades_file).exists():
            logger.warning(f"[BACKTEST] Trades file not found: {trades_file}")
            return []
        
        try:
            with open(trades_file, 'r') as f:
                data = json.load(f)
            
            trades = data.get('trades', [])
            
            # Calculate statistics
            winning = [t for t in trades if t.get('profit_pct', 0) > 0]
            losing = [t for t in trades if t.get('profit_pct', 0) <= 0]
            
            analysis = {
                'total_trades': len(trades),
                'winning_trades': len(winning),
                'losing_trades': len(losing),
                'win_rate': len(winning) / len(trades) if trades else 0,
                'avg_win': sum(t['profit_pct'] for t in winning) / len(winning) if winning else 0,
                'avg_loss': sum(t['profit_pct'] for t in losing) / len(losing) if losing else 0,
                'profit_factor': (
                    abs(sum(t['profit_abs'] for t in winning)) / 
                    abs(sum(t['profit_abs'] for t in losing)) 
                ) if losing and sum(t['profit_abs'] for t in losing) != 0 else float('inf'),
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"[BACKTEST] Failed to analyze trades: {e}")
            return []
    
    def compare_strategies(
        self, 
        strategy1: str, 
        strategy2: str,
        timerange: str = "20260101-20260208"
    ) -> Dict:
        """Compare two strategies."""
        results = {}
        
        for strategy in [strategy1, strategy2]:
            config = BacktestConfig(
                strategy=strategy,
                timerange=timerange
            )
            backtester = Backtester(config)
            success, metrics = backtester.run_backtest()
            results[strategy] = metrics
        
        return results

"""
HyperoptRunner Skill
====================
Hyperopt execution and analysis for WolfStrategyV1.
"""

import subprocess
import json
import logging
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class HyperoptConfig:
    """Hyperopt configuration."""
    strategy: str = "WolfStrategyV1"
    strategy_path: str = "user_data/strategies"
    config: str = "user_data/config.json"
    timeframe: str = "5m"
    epochs: int = 5000
    timerange: str = "20250101-20251231"
    spaces: List[str] = None
    loss_function: str = "OnlyProfitHyperOptLoss"
    random_state: int = 100
    jobs: int = None
    
    def __post_init__(self):
        if self.spaces is None:
            self.spaces = ['buy', 'sell', 'roi', 'trailing']
        if self.jobs is None:
            self.jobs = os.cpu_count() or 4


class HyperoptRunner:
    """
    FreqTrade hyperopt execution and analysis.
    
    Capabilities:
    - Run hyperopt in Docker
    - Analyze results
    - Extract best parameters
    - Inject parameters into strategy
    """
    
    def __init__(self, config: Optional[HyperoptConfig] = None):
        self.config = config or HyperoptConfig()
        self.docker_image = "freqtradeorg/freqtrade:latest"
        self.results_dir = Path("user_data/hyperopt_results")
    
    def prepare_environment(self) -> bool:
        """Prepare environment for hyperopt."""
        logger.info("[HYPEROPT] Preparing environment...")
        
        # Create directories
        self.results_dir.mkdir(parents=True, exist_ok=True)
        Path(self.config.strategy_path).mkdir(parents=True, exist_ok=True)
        
        # Ensure strategy file exists
        strategy_file = Path(self.config.strategy_path) / f"{self.config.strategy}.py"
        if not strategy_file.exists():
            logger.error(f"[HYPEROPT] Strategy file not found: {strategy_file}")
            return False
        
        # Ensure config exists
        if not Path(self.config.config).exists():
            logger.error(f"[HYPEROPT] Config not found: {self.config.config}")
            return False
        
        logger.info("[HYPEROPT] Environment ready")
        return True
    
    def run_hyperopt(
        self, 
        docker_user: str = "1000:1000",
        log_file: str = "hyperopt.log"
    ) -> Tuple[bool, str]:
        """
        Run hyperopt in Docker container.
        
        Returns:
            Tuple of (success, log_file_path)
        """
        if not self.prepare_environment():
            return False, ""
        
        spaces = ' '.join(self.config.spaces)
        
        cmd = [
            'docker', 'run', '--rm', '-it',
            '-v', f'{os.getcwd()}/user_data:/freqtrade/user_data',
            '--user', docker_user,
            self.docker_image,
            'hyperopt',
            '--random-state', str(self.config.random_state),
            '--hyperopt-loss', self.config.loss_function,
            '--strategy', self.config.strategy,
            '--strategy-path', '/freqtrade/user_data/strategies',
            '--timeframe', self.config.timeframe,
            '-c', '/freqtrade/user_data/config.json',
            '--space', spaces,
            '--timerange', self.config.timerange,
            '-e', str(self.config.epochs),
            '-j', str(self.config.jobs),
        ]
        
        logger.info(f"[HYPEROPT] Starting with {self.config.epochs} epochs...")
        logger.info(f"[HYPEROPT] Command: {' '.join(cmd[:10])}...")
        
        with open(log_file, 'w') as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True
            )
        
        if result.returncode == 0:
            logger.info(f"[HYPEROPT] Completed successfully. Log: {log_file}")
            return True, log_file
        else:
            logger.error(f"[HYPEROPT] Failed with return code {result.returncode}")
            return False, log_file
    
    def list_results(self, profitable: bool = True) -> List[Dict]:
        """List hyperopt results."""
        cmd = [
            'docker', 'run', '--rm',
            '-v', f'{os.getcwd()}/user_data:/freqtrade/user_data',
            '--user', '1000:1000',
            self.docker_image,
            'hyperopt-list',
            '--config', '/freqtrade/user_data/config.json',
        ]
        
        if profitable:
            cmd.extend(['--profitable'])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            # Parse results (simplified)
            lines = result.stdout.strip().split('\n')
            return [self._parse_result_line(line) for line in lines if line]
        return []
    
    def _parse_result_line(self, line: str) -> Dict:
        """Parse hyperopt result line."""
        # Simplified parsing - extract key metrics
        parts = line.split()
        return {
            'raw': line,
            'epoch': parts[0] if parts else None,
            'profit': parts[1] if len(parts) > 1 else None,
        }
    
    def show_epoch(self, epoch: int) -> Dict:
        """Show details of a specific epoch."""
        cmd = [
            'docker', 'run', '--rm',
            '-v', f'{os.getcwd()}/user_data:/freqtrade/user_data',
            '--user', '1000:1000',
            self.docker_image,
            'hyperopt-show',
            '--config', '/freqtrade/user_data/config.json',
            '-n', str(epoch),
            '--json',
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {'raw': result.stdout}
        return {'error': result.stderr}
    
    def extract_best_params(self, epoch: int) -> Dict:
        """Extract parameters from best epoch."""
        data = self.show_epoch(epoch)
        
        if 'error' in data:
            return {}
        
        return data.get('parameters', {})
    
    def inject_params(self, params: Dict) -> bool:
        """Inject parameters into strategy file."""
        strategy_file = Path(self.config.strategy_path) / f"{self.config.strategy}.py"
        
        if not strategy_file.exists():
            logger.error(f"[HYPEROPT] Strategy file not found: {strategy_file}")
            return False
        
        try:
            with open(strategy_file, 'r') as f:
                content = f.read()
            
            # Apply parameter replacements
            for param_name, value in params.items():
                # Simple replacement pattern
                import re
                pattern = rf'({param_name}\s*=\s*)(Decimal|Int|Categorical)Parameter\([^)]*default\s*=\s*)[^,\)]+'
                replacement = rf'\g<1>\g<2>Parameter(..., default={value}, ...'
                content = re.sub(pattern, replacement, content)
            
            with open(strategy_file, 'w') as f:
                f.write(content)
            
            logger.info(f"[HYPEROPT] Parameters injected into {strategy_file}")
            return True
            
        except Exception as e:
            logger.error(f"[HYPEROPT] Failed to inject params: {e}")
            return False
    
    def save_params_json(self, params: Dict, filename: str = "hyperopt_best.json") -> bool:
        """Save parameters to JSON file."""
        output_file = Path("user_data") / filename
        
        try:
            with open(output_file, 'w') as f:
                json.dump(params, f, indent=2)
            
            logger.info(f"[HYPEROPT] Params saved to {output_file}")
            return True
        except Exception as e:
            logger.error(f"[HYPEROPT] Failed to save params: {e}")
            return False

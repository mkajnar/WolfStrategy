# 🐺 WolfStrategyV1

**Long -> Short Profit Flip Trading Strategy for FreqTrade**

## Overview

WolfStrategyV1 implements a complete trading system with sequential logic:

1. **Long Phase**: Entry at Donchian Channel bounce + DCA on support
2. **Profit Capture**: Exit Long with profit
3. **Short Phase**: 100x leverage Short on Donchian breakout down (using profit from Long)

## Strategy Features

| Feature | Long | Short |
|---------|------|-------|
| Leverage | Dynamic (2-5x) | Fixed 100x |
| Entry | DC bounce / Support | DC breakout down |
| DCA | Up to 5 positions | N/A |
| Stop Loss | -0.5% | 0.8-0.9% |
| Take Profit | 3% | 3% (RRR 3:1) |
| Trailing | Yes | After 1.5% profit |

## Quick Start

### 1. Deploy to Kubernetes
```bash
# Deploy all timeframes
./autogen_wolf_v1.sh

# Deploy specific timeframe
TIMEFRAME=5m ./autogen_wolf_v1.sh
```

### 2. Local Docker Hyperopt
```bash
# Quick hyperopt (50 epochs)
make hyperopt-quick-docker

# Full hyperopt
make hyperopt-all-docker EPOCHS=5000
```

### 3. Backtest
```bash
make backtest-docker
```

## Commands

| Command | Description |
|---------|-------------|
| `make deploy` | Generate and deploy K8s bots |
| `make stop` | Stop all wolf bots |
| `make status` | Show bot status |
| `make logs` | Show logs |
| `make shell` | Connect to pod shell |
| `make hyperopt-all-docker` | Run hyperopt |
| `make backtest-docker` | Run backtest |

## File Structure

```
WolfStrategyV1/
├── WolfStrategyV1.py          # Main strategy (24KB)
├── autogen_wolf_v1.sh        # K8s deployment script
├── stop_bots_wolf.sh          # Stop all bots
├── Makefile                   # Build & operations
├── generate_hyperopt_config.py # Config generator
├── Dockerfile                 # Container image
├── config_wolf_v1.json       # Freqtrade config
├── requirements.txt           # Python deps
├── k8s.mk                     # K8s helpers
├── k8s-configmap.yaml         # K8s ConfigMap
├── k8s-helper.sh             # K8s management
└── user_data/                # Data directory
```

## Environment Variables (K8s)

| Variable | Default | Description |
|----------|---------|-------------|
| `WOLF_SHORT_LEVERAGE` | 100 | Short leverage |
| `WOLF_SHORT_STOP_LOSS` | 0.008 | Short SL (0.8%) |
| `WOLF_SHORT_TAKE_PROFIT` | 0.03 | Short TP (3%) |
| `WOLF_DCA_MAX_COUNT` | 5 | Max DCA positions |
| `WOLF_LOG_LEVEL` | INFO | Logging level |

## Monitoring

```bash
# Check status
./k8s-helper.sh status

# Follow logs
./k8s-helper.sh logs

# Restart pods
./k8s-helper.sh restart
```

## License

MIT

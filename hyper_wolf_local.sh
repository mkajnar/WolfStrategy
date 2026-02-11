#!/bin/bash
# 🐺 WolfStrategyV1 Hyperopt - Local Docker
# Usage: ./hyper_wolf_local.sh [epochs] [timerange]

EPOCHS=${1:-1000}
TIMERANGE=${2:-20260101-20260131}
STRATEGY="WolfStrategyV1"
TIMEFRAME="5m"
CONFIG="user_data/config_wolf.json"

echo "🐺 Starting WolfStrategyV1 hyperopt..."
echo "   Strategy: $STRATEGY"
echo "   Timeframe: $TIMEFRAME"
echo "   Timerange: $TIMERANGE"
echo "   Epochs: $EPOCHS"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Copy strategy to user_data/strategies
mkdir -p user_data/strategies
cp WolfStrategyV1.py user_data/strategies/

# Generate config if not exists
if [ ! -f "$CONFIG" ]; then
    echo "📝 Generating config: $CONFIG"
    python3 generate_hyperopt_config.py "$CONFIG" "BTC/USDT:USDT,ETH/USDT:USDT"
fi

docker run --rm \
  -v $(pwd)/user_data:/freqtrade/user_data \
  --user 1000:1000 \
  freqtradeorg/freqtrade:latest \
  hyperopt \
  --random-state 100 \
  --hyperopt-loss OnlyProfitHyperOptLoss \
  --strategy $STRATEGY \
  --strategy-path /freqtrade/user_data/strategies \
  --timeframe $TIMEFRAME \
  -c $CONFIG \
  --space buy sell roi trailing \
  --timerange $TIMERANGE \
  -e $EPOCHS \
  -j $(nproc)

echo ""
echo "🐺 Hyperopt complete."
echo "📁 Results in: user_data/hyperopt_results/"
echo ""
echo "💡 Next steps:"
echo "   1. make hyperopt-show EPOCH=<best_epoch>"
echo "   2. make backtest"

# WolfStrategyV1 Development Memory

## Session: Long -> Short Profit Flip Strategy Development

**Date:** 2026-02-10
**Author:** AI Assistant

---

## Task Completed

Created complete FreqTrading strategy implementation for **Long -> Short Profit Flip** pattern with Kubernetes deployment.

### Key Files Created

| File | Purpose |
|------|---------|
| `WolfStrategyV1.py` | Main trading strategy (24KB) |
| `autogen_wolf_v1.sh` | K8s deployment generator |
| `stop_bots_wolf.sh` | Stop all wolf bots |
| `Makefile` | Build & operations (15KB) |
| `generate_hyperopt_config.py` | Config generator |
| `Dockerfile` | Container image |
| `config_wolf_v1.json` | Freqtrade config |
| `k8s.mk` | Kubernetes helpers |
| `k8s-configmap.yaml` | K8s ConfigMap |
| `k8s-helper.sh` | K8s management |
| `monitor_wolf_hyperopt.sh` | Hyperopt monitoring |
| `hyper_wolf_local.sh` | Local hyperopt |
| `README.md` | Documentation |

---

## Strategy Architecture

### State Management
```python
custom_profit_bucket: Dict[str, float]   # Net profit from Long cycle
awaiting_short: Dict[str, bool]          # Flag for Short activation
last_buy_price: Dict[str, float]         # Last DCA entry price
dca_count: Dict[str, int]                 # DCA position counter
donchian_lower/upper: Dict[str, float]   # Current DC levels
support_levels: Dict[str, float]          # Detected support levels
```

### Indicators
- **Donchian Channels** (20 period): Range & breakouts
- **Support Levels**: Fractals/Pivot Lows detection
- **ATR**: Dynamic leverage (2-5x for Long)
- **RSI**: Oversold confirmation
- **MACD**: Trend confirmation

### Phase 1: Long with Dynamic DCA
1. Entry: Bounce from lower Donchian or support
2. DCA Rules:
   - `current_price < last_buy_price`
   - Support bounce confirmation
   - Max 5 DCA positions
   - Position size increment 1.5x per DCA

### Phase 2: Profit Capture & 100x Short
1. Calculate net profit (after fees)
2. Store in `custom_profit_bucket`
3. Activate Short phase
4. Trigger: Donchian breakout down
5. Leverage: 100x fixed
6. SL: 0.8-0.9% (liquidation guard)
7. TP: 3.0% (RRR 3:1)

### Risk Management
- Taker fee reserve: 0.2%
- Trailing stop for Short: 1.5% activation
- Liquidation protection buffer

---

## Key Decisions Made

1. **Removed DailyBuy Strategy**: Completely replaced with WolfStrategyV1
2. **Simplified Directory Structure**: Removed `bots_dailybuy_*` directories
3. **Unified Scripts**: Created wolf-prefixed naming convention
4. **K8s-First Approach**: All scripts optimized for Kubernetes deployment

---

## Commands Reference

### Deployment
```bash
./autogen_wolf_v1.sh           # Deploy all timeframes
TIMEFRAME=5m ./autogen_wolf_v1.sh  # Deploy specific timeframe
./stop_bots_wolf.sh             # Stop all bots
```

### Docker Operations
```bash
make hyperopt-all-docker EPOCHS=5000  # Full hyperopt
make backtest-docker                   # Backtest
make download-data-docker              # Download data
```

### Kubernetes
```bash
./k8s-helper.sh status   # Status
./k8s-helper.sh logs     # Follow logs
./k8s-helper.sh restart  # Restart pods
```

---

## Technical Notes

### LSP Errors (Non-Critical)
All Python files show import resolution errors for freqtrade, numpy, pandas - these are expected as the code runs in FreqTrade Docker container environment.

### Kubernetes Configuration
- Namespace: `default`
- NodePort Range: 30500-30503
- Resource Limits: 2CPU / 4GiB RAM
- Image: `freqtradeorg/freqtrade:develop`

### Strategy Parameters (Optimizable)
```python
donchian_period = 10-50 (default 20)
dca_max_count = 3-10 (default 5)
dca_increment = 1.2-3.0 (default 1.5)
rsi_oversold = 20-50 (default 35)
short_leverage = 50-100 (default 100)
short_stop_loss = 0.005-0.02 (default 0.008)
short_take_profit = 0.02-0.05 (default 0.03)
```

---

## Logging Patterns

Strategy uses `logger.info()` for:
- Profit bucket status: `[PROFIT_CAPTURE] pair - Profit captured: X.XXXX`
- DCA execution: `[DCA_EXECUTED] pair - DCA #N/M | Price: X.XXXXX`
- Support analysis: `[DCA] pair - Support Analysis: ...`
- Strategy state: `[STRATEGY_STATE] pair - {...}`

---

## Files Removed During Cleanup

- `DailyBuyStrategy3_5_JPA_TEMPLATE.py`
- `DailyBuyStrategy3_5_JPA.json`
- `autogen_daily.sh`
- `stop_bots_daily.sh`
- `hopt.sh`
- `hyper_local.sh`
- `monitor_hyperopt.sh`
- `generate_hyperopt_config.py` (old version)
- `bots_dailybuy_*` directories

---

## Next Steps (For Future Sessions)

1. Run initial hyperopt optimization
2. Backtest on historical data
3. Deploy to staging environment
4. Monitor profit flip effectiveness
5. Tune DCA parameters based on results

---

## Related Documentation

- FreqTrade Official Docs: https://www.freqtrade.io/
- Kubernetes Deployment Guide in README.md
- Strategy parameters documented inline

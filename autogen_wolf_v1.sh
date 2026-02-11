#!/bin/bash
# -----------------------------------------------------------------------------
# 🤖 AUTO-DEPLOYER: WolfStrategyV1 EDITION
# Účel: Vygenerovat a NASADIT boty pro Long -> Short Profit Flip strategii.
# Strategie: WolfStrategyV1.py
# -----------------------------------------------------------------------------
set -euo pipefail

# K8S konfigurace
KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
K8S_NODE=${K8S_NODE:-188.165.193.142}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STRATEGY_FILE="${SCRIPT_DIR}/WolfStrategyV1.py"
DB_BASE_HOST_PATH="${DB_BASE_HOST_PATH:-/mnt/ft_wolf}"

# Přepínače nasazení
DEPLOY=${DEPLOY:-true}

# Konstantní credentials
EXCHANGE_KEY="${EXCHANGE_KEY:-K}"
EXCHANGE_SECRET="${EXCHANGE_SECRET:-S}"
API_PASSWORD="${API_PASSWORD:-freqtrade}"
API_USERNAME="${API_USERNAME:-freqtrade}"

# Základní NodePort
BASE_NODEPORT=30500

SUMMARY=""

echo "========================================"
echo "🐺 WOLFSTRATEGY V1 AUTO-DEPLOYER"
echo "   Long -> Short Profit Flip Strategy"
echo "   Generuji a ${DEPLOY:+nasazuji }boty..."
echo "========================================"

# Validace
if [ ! -f "$STRATEGY_FILE" ]; then
    echo "❌ ERROR: Nenalezen soubor strategie: $STRATEGY_FILE"
    exit 1
fi

# Konfigurace timeframe - složka pro každý timeframe
declare -A TIMEFRAME_CONFIG
TIMEFRAME_CONFIG["bots_wolf_5m"]="5m"
TIMEFRAME_CONFIG["bots_wolf_15m"]="15m"
TIMEFRAME_CONFIG["bots_wolf_1h"]="1h"
TIMEFRAME_CONFIG["bots_wolf_4h"]="4h"

TIMEFRAME_FILTER=${TIMEFRAME:-all}

b64encode() { echo -n "$1" | base64 -w 0; }

PORT_OFFSET=0

for BOT_DIR_NAME in "${!TIMEFRAME_CONFIG[@]}"; do
    BOT_DIR_PATH="${SCRIPT_DIR}/${BOT_DIR_NAME}"
    TIMEFRAME="${TIMEFRAME_CONFIG[$BOT_DIR_NAME]}"
    BOT_NAME="wolf-${TIMEFRAME}"

    if [ "$TIMEFRAME_FILTER" != "all" ] && [ "$TIMEFRAME_FILTER" != "$TIMEFRAME" ]; then
        continue
    fi

    if [ ! -d "$BOT_DIR_PATH" ]; then
        echo "   📁 Vytvářím složku: $BOT_DIR_PATH"
        mkdir -p "$BOT_DIR_PATH"
    fi

    echo "----------------------------------------"
    echo "🔍 Zpracovávám: $BOT_NAME (TF=$TIMEFRAME)"

    # Konfigurace pro PERPETUAL FUTURES
    NAMESPACE="default"
    STAKE_AMOUNT="100 USDT"
    FIAT_DISPLAY="USD"
    PAIRS_INPUT="BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT,XRP/USDT:USDT"
    MAX_OPEN_TRADES=3
    BALANCE_RATIO=0.90
    MARGIN_MODE="isolated"
    STOPLOSS_ON_EXCHANGE="false"
    USE_EXIT_SIGNAL="true"
    TRADING_MODE="futures"

    STARTUP_CANDLES=100

    # LEVERAGE - Long: dynamický (2-5x), Short: 100x
    case "$TIMEFRAME" in
        5m) LEVERAGE=5 ;;
        15m) LEVERAGE=5 ;;
        1h) LEVERAGE=3 ;;
        4h) LEVERAGE=3 ;;
        *) LEVERAGE=5 ;;
    esac

    echo "   ⚙️  Parametry: TF=$TIMEFRAME, LEV=$LEVERAGE (Long), Short=100x"

    CURRENT_NODEPORT=$((BASE_NODEPORT + PORT_OFFSET))

    JWT_SECRET=$(openssl rand -hex 32)
    SECRET_NAME="${BOT_NAME}-secret"

    PAIRS_YAML=""
    IFS=',' read -ra PAIRS_ARRAY <<< "$PAIRS_INPUT"
    for pair in "${PAIRS_ARRAY[@]}"; do
        PAIRS_YAML+="        - ${pair}\n"
    done

    INCLUDE_TIMEFRAMES_YAML="          - ${TIMEFRAME}"

    # Generace bot.yaml
    cat > "${BOT_DIR_PATH}/bot.yaml" <<EOF
apiVersion: freqtrade.io/v1alpha1
kind: Bot
metadata:
  name: ${BOT_NAME}
  namespace: ${NAMESPACE}
spec:
  image:
    repository: freqtradeorg/freqtrade
    tag: develop
  pvc:
    enabled: false
  deployment:
    env:
      - name: WOLF_STRATEGY_LOG_LEVEL
        value: "INFO"
      - name: WOLF_SHORT_LEVERAGE
        value: "100"
    resources:
      requests:
        cpu: "1000m"
        memory: "2Gi"
      limits:
        cpu: "2000m"
        memory: "4Gi"
    volumes:
      - name: user-data
        hostPath:
          path: ${SCRIPT_DIR}/${BOT_DIR_NAME}/data
          type: DirectoryOrCreate
      - name: database-dir
        hostPath:
          path: ${DB_BASE_HOST_PATH}/${BOT_NAME}
          type: DirectoryOrCreate
      - name: dshm
        emptyDir:
          medium: Memory
    volumeMounts:
      - name: user-data
        mountPath: /freqtrade/user_data
      - name: database-dir
        mountPath: /freqtrade/db_persist
      - name: dshm
        mountPath: /dev/shm
  exchange: binance
  database: sqlite:////freqtrade/db_persist/database.db
  config:
    initial_state: running
    max_open_trades: ${MAX_OPEN_TRADES}
    stake_currency: USDT
    stake_amount: "${STAKE_AMOUNT}"
    tradable_balance_ratio: ${BALANCE_RATIO}
    fiat_display_currency: "${FIAT_DISPLAY}"
    timeframe: ${TIMEFRAME}
    dry_run: false
    dry_run_wallet: 10000
    trading_mode: ${TRADING_MODE}
    margin_mode: ${MARGIN_MODE}
    leverage:
      - side: long
        leverage: ${LEVERAGE}
      - side: short
        leverage: 100.0
    use_exit_signal: ${USE_EXIT_SIGNAL}
    unfilledtimeout:
      entry: 30
      exit: 30

    entry_pricing:
      price_side: other
      use_order_book: true
      order_book_top: 1
    exit_pricing:
      price_side: other
      use_order_book: true
      order_book_top: 1

    order_types:
      entry: market
      exit: market
      stoploss: market
      stoploss_on_exchange: ${STOPLOSS_ON_EXCHANGE}

    exchange:
      pair_whitelist:
$(echo -e "$PAIRS_YAML")

    pairlists:
      - method: StaticPairList

    telegram:
      enabled: false

    custom:
      wolf_strategy:
        enabled: true
        profit_flip_enabled: true
        short_leverage: 100.0
        short_stop_loss: 0.008
        short_take_profit: 0.03
        dca_max_count: 5
        dca_increment: 1.5

  api:
    enabled: true
    port: 8081
  secrets:
    api:
      username:
        secretKeyRef:
          name: ${SECRET_NAME}
          key: api_username
      password:
        secretKeyRef:
          name: ${SECRET_NAME}
          key: api_password
      wsToken:
        secretKeyRef:
          name: ${SECRET_NAME}
          key: jwt_secret_key
    exchange:
      key:
        secretKeyRef:
          name: ${SECRET_NAME}
          key: exchange_key
      secret:
        secretKeyRef:
          name: ${SECRET_NAME}
          key: exchange_secret

  strategy:
    name: WolfStrategyV1
    source: |
EOF

    # Přidání strategie (odsazené)
    sed 's/^[[:space:]]*$//' "$STRATEGY_FILE" | sed 's/[[:space:]]*$//' | sed 's/^/      /' >> "${BOT_DIR_PATH}/bot.yaml"

    # Secret.yaml
    cat > "${BOT_DIR_PATH}/secret.yaml" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: ${SECRET_NAME}
  namespace: ${NAMESPACE}
data:
  api_password: $(b64encode "$API_PASSWORD")
  api_username: $(b64encode "$API_USERNAME")
  exchange_key: $(b64encode "$EXCHANGE_KEY")
  exchange_secret: $(b64encode "$EXCHANGE_SECRET")
  jwt_secret_key: $(b64encode "$JWT_SECRET")
type: Opaque
EOF

    # Service.yaml
    cat > "${BOT_DIR_PATH}/service.yaml" <<EOF
apiVersion: v1
kind: Service
metadata:
  name: ${BOT_NAME}-service
  namespace: ${NAMESPACE}
spec:
  type: NodePort
  selector:
    app.kubernetes.io/name: ${BOT_NAME}
  ports:
    - port: 8081
      targetPort: 8081
      nodePort: ${CURRENT_NODEPORT}
EOF

    echo "   ✅ YAML vygenerován: ${BOT_DIR_PATH}/bot.yaml"
    echo "   🔗 URL: http://${K8S_NODE}:${CURRENT_NODEPORT}/api/v1/ping"
    BOT_URL="http://${K8S_NODE}:${CURRENT_NODEPORT}/api/v1/pong"
    SUMMARY+="${BOT_NAME} -> ${BOT_URL}\n"

    # Nasazení
    if [ "${DEPLOY}" = "true" ]; then
        if command -v kubectl >/dev/null 2>&1; then
            echo "   🚀 Nasazuji na ${K8S_NODE}..."
            KUBECONFIG="${KUBECONFIG}" kubectl apply -f "${BOT_DIR_PATH}/"
            echo "   ✅ Bot ${BOT_NAME} nasazen"
        else
            echo "   ⚠️ kubectl nenalezen, přeskočeno nasazení"
        fi
    fi

    PORT_OFFSET=$((PORT_OFFSET + 1))

done

echo "========================================"
echo "🐺 WOLFSTRATEGY V1 DEPLOYMENT SUMMARY"
echo "========================================"

if [ "${DEPLOY}" = "true" ]; then
    echo "🎉 HOTOVO! Boty byly nasazeny na Kubernetes."
else
    echo "✅ YAML soubory vygenerovány (bez nasazení)."
fi

echo ""
echo "Nasazené boty:"
if [ -n "$SUMMARY" ]; then
    echo -e "$SUMMARY"
else
    echo "(Žádné boty - zkontroluj TIMEFRAME filtr)"
fi

echo ""
echo "📋 Důležité URL pro monitoring:"
echo "   - API: http://${K8S_NODE}:${BASE_NODEPORT}/api/v1"
echo "   - Grafana/Prometheus (pokud nakonfigurováno)"
echo ""
echo "🛑 Zastavení botů: ./stop_bots_wolf.sh"
echo "📊 Status: kubectl get pods -l app.kubernetes.io/name=wolf"

#!/usr/bin/env bash

# 🐺 Stop WolfStrategyV1 Kubernetes Resources
# Usage:
#   ./stop_bots_wolf.sh              # deletes all wolf-* bots
#   ./stop_bots_wolf.sh wolf-5m      # deletes only wolf-5m bot
#   ./stop_bots_wolf.sh all          # deletes all wolf-* bots

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
K8S_NODE=${K8S_NODE:-188.165.193.142}
NAMESPACE=${NAMESPACE:-default}

BOT_PATTERN="${1:-all}"

ALL_BOTS="wolf-5m wolf-15m wolf-1h wolf-4h"

echo "🐺 Zastavování WolfStrategyV1 botů na ${K8S_NODE}..."

if [ "$BOT_PATTERN" = "all" ]; then
    BOTS_TO_STOP=($ALL_BOTS)
elif [ -n "$BOT_PATTERN" ]; then
    if echo "$ALL_BOTS" | grep -qw "$BOT_PATTERN"; then
        BOTS_TO_STOP=("$BOT_PATTERN")
    else
        echo "❌ Neznámý bot: $BOT_PATTERN"
        echo "Použij: wolf-5m, wolf-15m, wolf-1h, wolf-4h, nebo all"
        exit 1
    fi
else
    BOTS_TO_STOP=($ALL_BOTS)
fi

processed=0
success=0
failed=0

for bot in "${BOTS_TO_STOP[@]}"; do
    ((processed++))
    echo ""
    echo "🗑️  Mazání prostředků pro: $bot"

    if KUBECONFIG="$KUBECONFIG" kubectl delete -n "$NAMESPACE" "deploy/$bot" --ignore-not-found=true 2>/dev/null; then
        ((success++))
        echo "   ✅ Deployment $bot smazán"
    else
        echo "   ⚠️ Deployment $bot neexistuje nebo chyba mazání"
    fi

    if KUBECONFIG="$KUBECONFIG" kubectl delete -n "$NAMESPACE" "svc/${bot}-service" --ignore-not-found=true 2>/dev/null; then
        echo "   ✅ Service ${bot}-service smazán"
    fi

    if KUBECONFIG="$KUBECONFIG" kubectl delete -n "$NAMESPACE" "secret/${bot}-secret" --ignore-not-found=true 2>/dev/null; then
        echo "   ✅ Secret ${bot}-secret smazán"
    fi

done

echo ""
echo "═══════════════════════════════════════════"
echo "📊 Summary: Zpracováno: $processed | Úspěšně: $success"
echo "═══════════════════════════════════════════"

if [[ $failed -gt 0 ]]; then
    exit 1
fi

echo ""
echo "🐺 Všechny Wolf boty byly zastaveny."
echo ""
echo "💡 Tip: Pro opětovné spuštění:"
echo "   ./autogen_wolf_v1.sh"
echo ""
echo "📊 Zkontroluj stav:"
echo "   kubectl get pods -l app.kubernetes.io/name=wolf"

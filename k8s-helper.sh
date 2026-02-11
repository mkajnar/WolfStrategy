#!/bin/bash
# ============================================================================
# 🐺 WolfStrategyV1 Kubernetes Helper Scripts
# Kompletní set helperů pro K8s deployment
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
NAMESPACE=${NAMESPACE:-default}

# Barvy
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================================================
# Funkce: Status
# ============================================================================

status() {
    echo -e "${CYAN}🐺 WolfStrategyV1 Status${NC}"
    echo "═══════════════════════════════════════"
    echo ""
    echo "Pods:"
    kubectl get pods -l app.kubernetes.io/name=wolf
    echo ""
    echo "Services:"
    kubectl get svc -l app.kubernetes.io/name=wolf
    echo ""
    echo "Secrets:"
    kubectl get secrets -l app.kubernetes.io/name=wolf
}

# ============================================================================
# Funkce: Logs
# ============================================================================

logs() {
    local pod=$(kubectl get pods -l app.kubernetes.io/name=wolf -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -z "$pod" ]; then
        log_error "No wolf pods found"
        return 1
    fi
    log_info "Showing logs for: $pod"
    kubectl logs -f "$pod" --tail=100
}

# ============================================================================
# Funkce: Restart
# ============================================================================

restart() {
    local pods=$(kubectl get pods -l app.kubernetes.io/name=wolf -o jsonpath='{.items[*].metadata.name}')
    if [ -z "$pods" ]; then
        log_error "No wolf pods found"
        return 1
    fi
    log_info "Restarting wolf pods..."
    kubectl delete pods -l app.kubernetes.io/name=wolf
    log_info "Pods are being recreated..."
}

# ============================================================================
# Funkce: Scale
# ============================================================================

scale() {
    local replicas=${1:-1}
    log_info "Scaling wolf deployments to $replicas replicas..."
    kubectl scale deployment -l app.kubernetes.io/name=wolf --replicas=$replicas
}

# ============================================================================
# Funkce: Backup
# ============================================================================

backup() {
    local backup_dir="${SCRIPT_DIR}/backups/wolf-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$backup_dir"
    log_info "Creating backup in: $backup_dir"

    for pod in $(kubectl get pods -l app.kubernetes.io/name=wolf -o jsonpath='{.items[*].metadata.name}'); do
        local pod_name=$(echo $pod | cut -d' ' -f1)
        kubectl cp "$pod_name:/freqtrade/user_data" "$backup_dir/$pod_name" 2>/dev/null || true
    done

    log_info "Backup complete: $backup_dir"
}

# ============================================================================
# Funkce: Clean
# ============================================================================

clean() {
    log_warn "Cleaning up wolf strategy resources..."
    kubectl delete -f "${SCRIPT_DIR}/bots_"*/ 2>/dev/null || true
    kubectl delete configmap wolf-strategy-config 2>/dev/null || true
    log_info "Cleanup complete"
}

# ============================================================================
# Parse arguments
# ============================================================================

case "${1:-status}" in
    status)
        status
        ;;
    logs)
        logs
        ;;
    restart)
        restart
        ;;
    scale)
        scale "${2:-1}"
        ;;
    backup)
        backup
        ;;
    clean)
        clean
        ;;
    *)
        echo "🐺 WolfStrategyV1 K8s Helper"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  status      - Show status"
        echo "  logs        - Show logs (follow)"
        echo "  restart     - Restart all pods"
        echo "  scale [N]   - Scale to N replicas"
        echo "  backup      - Create backup"
        echo "  clean       - Clean up resources"
        echo ""
        ;;
esac

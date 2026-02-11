# ============================================================================
# 🐺 Kubernetes Deployment for WolfStrategyV1
# Long -> Short Profit Flip Trading Strategy
# ============================================================================

# Namespace pro Wolf boty
NAMESPACE := default

# Image
IMAGE := freqtradeorg/freqtrade:develop

# NodePort base
NODEPORT_BASE := 30500

# Bot configurations
BOTS := wolf-5m wolf-15m wolf-1h wolf-4h

# Timeframes
TIMEFRAMES := 5m 15m 1h 4h

# Leverage configs
LEVERAGE_5m := 5
LEVERAGE_15m := 5
LEVERAGE_1h := 3
LEVERAGE_4h := 3

# PVC Storage (pokud je potřeba persistent storage)
STORAGE_CLASS := standard
PVC_SIZE := 10Gi

# Resources
CPU_REQUEST := 1000m
CPU_LIMIT := 2000m
MEMORY_REQUEST := 2Gi
MEMORY_LIMIT := 4Gi

.PHONY: help apply apply-all delete delete-all

help:
	@echo "🐺 WolfStrategyV1 Kubernetes Deployment"
	@echo ""
	@echo "Usage:"
	@echo "  make apply        - Apply single bot (TIMEFRAME=5m)"
	@echo "  make apply-all    - Apply all bots"
	@echo "  make delete       - Delete single bot"
	@echo "  make delete-all   - Delete all wolf bots"
	@echo ""
	@echo "Variables:"
	@echo "  TIMEFRAME=5m     - Bot timeframe (5m, 15m, 1h, 4h)"
	@echo "  DEPLOYMENT=wolf-5m - Bot name"
	@echo "  NAMESPACE=default - Kubernetes namespace"

apply:
	@echo "🐺 Applying WolfStrategyV1 bot: $(DEPLOYMENT)"
	@kubectl apply -f bots_$(TIMEFRAME)/

apply-all:
	@echo "🐺 Applying all WolfStrategyV1 bots..."
	@for tf in $(TIMEFRAMES); do \
		echo "Applying bots_$$tf/..."; \
		kubectl apply -f bots_$$tf/ 2>/dev/null || true; \
	done
	@echo "✅ All bots applied"

delete:
	@echo "🐺 Deleting bot: $(DEPLOYMENT)"
	@kubectl delete -f bots_$(TIMEFRAME)/ --ignore-not-found=true

delete-all:
	@echo "🐺 Deleting all WolfStrategyV1 bots..."
	@for bot in $(BOTS); do \
		kubectl delete "deploy/$$bot" --ignore-not-found=true 2>/dev/null; \
		kubectl delete "svc/$$bot-service" --ignore-not-found=true 2>/dev/null; \
		kubectl delete "secret/$$bot-secret" --ignore-not-found=true 2>/dev/null; \
	done
	@echo "✅ All bots deleted"

# Monitoring
.PHONY: status logs

status:
	@echo "🐺 Wolf Bot Status:"
	@kubectl get pods -l app.kubernetes.io/name=wolf
	@kubectl get svc -l app.kubernetes.io/name=wolf

logs:
	@echo "🐺 Logs for $(DEPLOYMENT):"
	@kubectl logs -l app.kubernetes.io/name=$(DEPLOYMENT) --tail=100

# ============================================================================
# Kompletní K8s manifest (pro reference)
# ============================================================================
# Toto je example kompletního deploymentu:
#
# apiVersion: apps/v1
# kind: Deployment
# metadata:
#   name: wolf-5m
#   labels:
#     app.kubernetes.io/name: wolf
#     app.kubernetes.io/instance: wolf-5m
# spec:
#   replicas: 1
#   selector:
#     matchLabels:
#       app.kubernetes.io/name: wolf
#       app.kubernetes.io/instance: wolf-5m
#   template:
#     metadata:
#       labels:
#         app.kubernetes.io/name: wolf
#         app.kubernetes.io/instance: wolf-5m
#     spec:
#       containers:
#       - name: freqtrade
#         image: freqtradeorg/freqtrade:develop
#         command: ["freqtrade", "trade"]
#         args: ["--config", "/etc/freqtrade/bot.yaml"]
#         ports:
#         - containerPort: 8081
#         resources:
#           requests:
#             cpu: "1000m"
#             memory: "2Gi"
#           limits:
#             cpu: "2000m"
#             memory: "4Gi"
#         volumeMounts:
#         - name: config
#           mountPath: /etc/freqtrade
#         - name: data
#           mountPath: /freqtrade/user_data
#         env:
#         - name: WOLF_SHORT_LEVERAGE
#           value: "100"
#       volumes:
#       - name: config
#         configMap:
#           name: wolf-config
#       - name: data
#         emptyDir: {}

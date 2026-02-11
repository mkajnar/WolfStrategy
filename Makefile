# ============================================================================
# 🐺 WolfStrategyV1 Kubernetes Makefile
# Optimalizován pro FreqTrade boty v Kubernetes
# Strategie: Long -> Short Profit Flip (Donchian + DCA + 100x Short)
# ============================================================================

# Defaultní proměnné
DATA_START?=20250101
DATA_END?=20260211
HYPEROPT_START?=20250101
HYPEROPT_END?=20260131
BACKTEST_START?=20260201
BACKTEST_END?=20260211
TIMEFRAME?=15m
CONFIG?=/freqtrade/user_data/config.json
STRATEGY?=WolfStrategyV1
EPOCHS?=5000
EPOCH?=1
PAIR?=BTC/USDT:USDT
PAIRS?=BTC/USDT:USDT
NAMESPACE?=default
DEPLOYMENT?=wolf-5m
POD_NAME?=$(shell kubectl get pods -n $(NAMESPACE) -l app.kubernetes.io/name=$(DEPLOYMENT) -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

# Docker proměnné
DOCKER_IMAGE?=freqtradeorg/freqtrade:latest
DOCKER_IMAGE_LOCAL?=wolf-freqtrade:local
DOCKER_CONTAINER?=wolf-hyperopt
DOCKER_USER?=1000:1000
DOCKER_WORKDIR?=/freqtrade
USE_LOCAL_IMAGE?=false

# Barvy pro výstup
GREEN=\033[0;32m
YELLOW=\033[0;33m
RED=\033[0;31m
CYAN=\033[0;36m
NC=\033[0m

# Detekce CPU jader
NPROC=$(shell nproc 2>/dev/null || echo 4)
JOBS?=$(NPROC)

# ============================================================================
# HELP
# ============================================================================

.PHONY: help

help:
	@echo ""
	@echo "🐺 ════════════════════════════════════════════════════════════════════"
	@echo "🐺          WolfStrategyV1 - Kubernetes Makefile"
	@echo "🐺          Long -> Short Profit Flip Strategy"
	@echo "🐺 ════════════════════════════════════════════════════════════════════"
	@echo ""
	@echo "$(CYAN)📊 STRATEGICKÉ INFORMACE:$(NC)"
	@echo "   Strategie:   WolfStrategyV1"
	@echo "   Logika:      Long (DCA) → Profit Capture → Short 100x"
	@echo "   Indikátory:  Donchian Channels, RSI, MACD, Support Levels"
	@echo "   Risk:        Short SL 0.8%, TP 3.0%, Taker Fee Reserve"
	@echo ""
	@echo "$(YELLOW)🎯 HYPEROPT & BACKTESTING:$(NC)"
	@echo "   make hyperopt-batch          - Sekvencni optimalizace BUY->ROI->SELL"
	@echo "   make hyperopt-all-docker     - Hyperopt vsech spaces najednou"
	@echo "   make backtest-docker          - Spustit backtest (Docker)"
	@echo "   make hyperopt-show EPOCH=1    - Zobrazit výsledky epochy"
	@echo ""
	@echo "$(YELLOW)🐳 DOCKER OPERACE:$(NC)"
	@echo "   make docker-pull             - Stáhnout oficiální image"
	@echo "   make docker-build-local      - Build lokálního image"
	@echo "   make docker-tag-local        - Otagovat lokální image"
	@echo "   make docker-run-shell        - Spustit shell v kontejneru"
	@echo ""
	@echo "$(YELLOW)🚀 KUBERNETES DEPLOYMENT:$(NC)"
	@echo "   make deploy                  - Generovat a nasadit boty"
	@echo "   make stop                    - Zastavit všechny boty"
	@echo "   make status                  - Zobrazit status"
	@echo "   make logs                    - Zobrazit logy"
	@echo "   make shell                   - Připojit shell k podu"
	@echo ""
	@echo "$(YELLOW)📁 DATA MANAGEMENT:$(NC)"
	@echo "   make download-data-docker    - Stáhnout tržní data"
	@echo "   make copy-results            - Kopírovat výsledky hyperopt"
	@echo ""
	@echo "$(YELLOW)⚙️  KONFIGURACE:$(NC)"
	@echo "   make config-show            - Zobrazit konfiguraci"
	@echo "   make secrets-list            - Zobrazit secrets"
	@echo ""
	@echo "$(CYAN)💡 PŘÍKLADY POUŽITÍ:$(NC)"
	@echo "   make deploy TIMEFRAME=5m     - Nasadit 5m bota"
	@echo "   make hyperopt-batch BUY_EPOCHS=2000  - Vic epoch pro buy"
	@echo "   make hyperopt-batch LOSS_FN=OnlyProfitHyperOptLoss  - Jina loss"
	@echo "   make logs-follow             - Sledovat logy v reálném čase"
	@echo "   make docker-build-local      - Build lokálního image"
	@echo "   make backtest USE_LOCAL_IMAGE=true  - Použít lokální image"
	@echo ""
	@echo "🐺 ════════════════════════════════════════════════════════════════════"

# ============================================================================
# DOCKER OPERACE
# ============================================================================

EFFECTIVE_IMAGE=$(if $(filter true,$(USE_LOCAL_IMAGE)),$(DOCKER_IMAGE_LOCAL),$(DOCKER_IMAGE))

.PHONY: docker-pull docker-build-local docker-tag-local docker-run-shell

docker-pull:
	@echo "$(YELLOW)Stahování FreqTrade Docker image...$(NC)"
	@docker pull $(DOCKER_IMAGE)
	@echo "$(GREEN)Image stažen: $(DOCKER_IMAGE)$(NC)"

docker-build-local:
	@echo "$(YELLOW)Build lokálního FreqTrade image...$(NC)"
	@docker build -t $(DOCKER_IMAGE_LOCAL) .
	@echo "$(GREEN)Lokální image vytvořen: $(DOCKER_IMAGE_LOCAL)$(NC)"

docker-tag-local:
	@echo "$(YELLOW)Tagování lokálního image...$(NC)"
	@docker tag $(DOCKER_IMAGE_LOCAL) $(DOCKER_IMAGE)
	@echo "$(GREEN)Image otagován: $(DOCKER_IMAGE)$(NC)"

docker-run-shell:
	@echo "$(YELLOW)Spouštění Docker kontejneru...$(NC)"
	@docker run --rm -it \
		-v $(PWD)/user_data:/freqtrade/user_data \
		--user $(DOCKER_USER) \
		$(EFFECTIVE_IMAGE) bash

# ============================================================================
# DATA STAHOVÁNÍ
# ============================================================================

.PHONY: download-data-docker

download-data-docker:
	@echo "$(YELLOW)Stahování tržních dat (5m, 15m, 1h, 2h, 4h, 1d, 1w)...$(NC)"
	@for tf in 5m 15m 1h 2h 4h 1d 1w; do \
		echo "  Stahování $$tf..."; \
		docker run --rm \
			-v $(PWD)/user_data:/freqtrade/user_data \
			--user $(DOCKER_USER) \
			$(EFFECTIVE_IMAGE) \
			download-data \
			--exchange bybit \
			--pairs $(PAIRS) \
			--timerange $(DATA_START)-$(DATA_END) \
			--timeframe $$tf \
			-c /freqtrade/user_data/config.json || true; \
	done
	@echo "$(GREEN)Data stažena$(NC)"

# ============================================================================
# HYPEROPT
# ============================================================================

.PHONY: prepare-hyperopt-config hyperopt-all-docker hyperopt-buy-docker \
		hyperopt-sell-docker hyperopt-trailing-docker hyperopt-roi-docker \
		hyperopt-quick-docker

prepare-hyperopt-config:
	@echo "$(YELLOW)Příprava konfigurace pro hyperopt...$(NC)"
	@mkdir -p user_data/strategies
	@echo "$(GREEN)Konfigurace připravena (config.json se nepřepisuje)$(NC)"

hyperopt-all-docker:
	@echo "$(YELLOW)Spouštění hyperopt (BUY, SELL, ROI, TRAILING)...$(NC)"
	@echo "$(CYAN)Strategie: $(STRATEGY) | Epochs: $(EPOCHS) | Timeframe: $(TIMEFRAME)$(NC)"
	@docker rm -f $(DOCKER_CONTAINER) 2>/dev/null || true
	@docker run --rm -it \
		--name $(DOCKER_CONTAINER) \
		-v $(PWD)/user_data:/freqtrade/user_data \
		--user $(DOCKER_USER) \
		$(EFFECTIVE_IMAGE) \
		hyperopt \
		--random-state 100 \
		--hyperopt-loss OnlyProfitHyperOptLoss \
		--strategy $(STRATEGY) \
		--strategy-path /freqtrade/user_data/strategies \
		--timeframe $(TIMEFRAME) \
		-c /freqtrade/user_data/config.json \
		--space buy sell roi trailing \
		--timerange $(HYPEROPT_START)-$(HYPEROPT_END) \
		-e $(EPOCHS) \
		-j $(JOBS) || true

hyperopt-buy-docker:
	@echo "$(YELLOW)Hyperopt BUY...$(NC)"
	@docker rm -f $(DOCKER_CONTAINER) 2>/dev/null || true
	@docker run --rm -it \
		--name $(DOCKER_CONTAINER) \
		-v $(PWD)/user_data:/freqtrade/user_data \
		--user $(DOCKER_USER) \
		$(EFFECTIVE_IMAGE) \
		hyperopt \
		--random-state 100 \
		--hyperopt-loss OnlyProfitHyperOptLoss \
		--strategy $(STRATEGY) \
		--strategy-path /freqtrade/user_data/strategies \
		--timeframe $(TIMEFRAME) \
		-c /freqtrade/user_data/config.json \
		--space buy \
		--timerange $(HYPEROPT_START)-$(HYPEROPT_END) \
		-e $(EPOCHS) \
		-j $(JOBS) || true

hyperopt-sell-docker:
	@echo "$(YELLOW)Hyperopt SELL...$(NC)"
	@docker rm -f $(DOCKER_CONTAINER) 2>/dev/null || true
	@docker run --rm -it \
		--name $(DOCKER_CONTAINER) \
		-v $(PWD)/user_data:/freqtrade/user_data \
		--user $(DOCKER_USER) \
		$(EFFECTIVE_IMAGE) \
		hyperopt \
		--random-state 100 \
		--hyperopt-loss OnlyProfitHyperOptLoss \
		--strategy $(STRATEGY) \
		--strategy-path /freqtrade/user_data/strategies \
		--timeframe $(TIMEFRAME) \
		-c /freqtrade/user_data/config.json \
		--space sell \
		--timerange $(HYPEROPT_START)-$(HYPEROPT_END) \
		-e $(EPOCHS) \
		-j $(JOBS) || true

hyperopt-trailing-docker:
	@echo "$(YELLOW)Hyperopt TRAILING...$(NC)"
	@docker rm -f $(DOCKER_CONTAINER) 2>/dev/null || true
	@docker run --rm -it \
		--name $(DOCKER_CONTAINER) \
		-v $(PWD)/user_data:/freqtrade/user_data \
		--user $(DOCKER_USER) \
		$(EFFECTIVE_IMAGE) \
		hyperopt \
		--random-state 100 \
		--hyperopt-loss OnlyProfitHyperOptLoss \
		--strategy $(STRATEGY) \
		--strategy-path /freqtrade/user_data/strategies \
		--timeframe $(TIMEFRAME) \
		-c /freqtrade/user_data/config.json \
		--space trailing \
		--timerange $(HYPEROPT_START)-$(HYPEROPT_END) \
		-e $(EPOCHS) \
		-j $(JOBS) || true

hyperopt-roi-docker:
	@echo "$(YELLOW)Hyperopt ROI...$(NC)"
	@docker rm -f $(DOCKER_CONTAINER) 2>/dev/null || true
	@docker run --rm -it \
		--name $(DOCKER_CONTAINER) \
		-v $(PWD)/user_data:/freqtrade/user_data \
		--user $(DOCKER_USER) \
		$(EFFECTIVE_IMAGE) \
		hyperopt \
		--random-state 100 \
		--hyperopt-loss OnlyProfitHyperOptLoss \
		--strategy $(STRATEGY) \
		--strategy-path /freqtrade/user_data/strategies \
		--timeframe $(TIMEFRAME) \
		-c /freqtrade/user_data/config.json \
		--space roi \
		--timerange $(HYPEROPT_START)-$(HYPEROPT_END) \
		-e $(EPOCHS) \
		-j $(JOBS) || true

hyperopt-quick-docker:
	@echo "$(YELLOW)Quick hyperopt (50 epochs, buy space)...$(NC)"
	@docker rm -f $(DOCKER_CONTAINER) 2>/dev/null || true
	@docker run --rm -it \
		--name $(DOCKER_CONTAINER) \
		-v $(PWD)/user_data:/freqtrade/user_data \
		--user $(DOCKER_USER) \
		$(EFFECTIVE_IMAGE) \
		hyperopt \
		--random-state 100 \
		--hyperopt-loss OnlyProfitHyperOptLoss \
		--strategy $(STRATEGY) \
		--strategy-path /freqtrade/user_data/strategies \
		--timeframe $(TIMEFRAME) \
		-c /freqtrade/user_data/config.json \
		--space buy \
		--timerange $(HYPEROPT_START)-$(HYPEROPT_END) \
		-e 50 \
		-j $(JOBS) || true

# ============================================================================
# HYPEROPT VÝSLEDKY
# ============================================================================

.PHONY: hyperopt-list-docker hyperopt-show-docker

hyperopt-list-docker:
	@echo "$(YELLOW)Seznam hyperopt výsledků...$(NC)"
	@docker run --rm \
		-v $(PWD)/user_data:/freqtrade/user_data \
		--user $(DOCKER_USER) \
		$(EFFECTIVE_IMAGE) \
		hyperopt-list --config /freqtrade/user_data/config.json --profitable

hyperopt-show-docker:
	@echo "$(YELLOW)Zobrazení epochy $(EPOCH)...$(NC)"
	@docker run --rm \
		-v $(PWD)/user_data:/freqtrade/user_data \
		--user $(DOCKER_USER) \
		$(EFFECTIVE_IMAGE) \
		hyperopt-show --config /freqtrade/user_data/config.json -n $(EPOCH)

# ============================================================================
# BACKTESTING
# ============================================================================

.PHONY: backtest-docker quick-backtest-docker backtest-full-year-docker

backtest-docker:
	@echo "$(YELLOW)Backtest (Strategie: $(STRATEGY))...$(NC)"
	@docker run --rm \
		-v $(PWD)/user_data:/freqtrade/user_data \
		$(EFFECTIVE_IMAGE) \
		backtesting \
		--strategy $(STRATEGY) \
		--strategy-path /freqtrade/user_data/strategies \
		--timeframe $(TIMEFRAME) \
		--pairs $(PAIRS) \
		--timerange $(BACKTEST_START)-$(BACKTEST_END) \
		--cache none

backtest-full-year-docker:
	@echo "$(YELLOW)Backtest FULL YEAR (hyperopt range)...$(NC)"
	@docker run --rm \
		-v $(PWD)/user_data:/freqtrade/user_data \
		$(EFFECTIVE_IMAGE) \
		backtesting \
		--strategy $(STRATEGY) \
		--strategy-path /freqtrade/user_data/strategies \
		--timeframe $(TIMEFRAME) \
		--pairs $(PAIRS) \
		--timerange $(HYPEROPT_START)-$(HYPEROPT_END) \
		--cache none

quick-backtest-docker:
	@echo "$(YELLOW)Rychlý backtest (1 týden)...$(NC)"
	@docker run --rm \
		-v $(PWD)/user_data:/freqtrade/user_data \
		$(EFFECTIVE_IMAGE) \
		backtesting \
		--strategy $(STRATEGY) \
		--strategy-path /freqtrade/user_data/strategies \
		--timeframe $(TIMEFRAME) \
		--pairs $(PAIRS) \
		--timerange 20260101-20260108 \
		--cache none

# ============================================================================
# KUBERNETES OPERACE
# ============================================================================

.PHONY: deploy stop status logs logs-follow shell restart

_check_pod:
	@if [ -z "$(POD_NAME)" ]; then \
		echo "$(RED)Pod nenalezen pro deployment $(DEPLOYMENT)$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Pod: $(POD_NAME)$(NC)"

deploy:
	@echo "$(YELLOW)Generování a nasazení WolfStrategyV1 botů...$(NC)"
	@./autogen_wolf_v1.sh

stop:
	@echo "$(YELLOW)Zastavování Wolf botů...$(NC)"
	@./stop_bots_wolf.sh

status:
	@echo "$(YELLOW)Status Kubernetes...$(NC)"
	@kubectl get pods -l app.kubernetes.io/name=wolf
	@kubectl get svc -l app.kubernetes.io/name=wolf

logs:
	@echo "$(YELLOW)Logy...$(NC)"
	@if [ -z "$(POD_NAME)" ]; then \
		kubectl get pods -l app.kubernetes.io/name=wolf; \
	else \
		kubectl logs -n $(NAMESPACE) $(POD_NAME) --tail=50; \
	fi

logs-follow:
	@echo "$(YELLOW)Sledování logů (Ctrl+C pro ukončení)...$(NC)"
	@if [ -z "$(POD_NAME)" ]; then \
		echo "$(RED)Pod nenalezen$(NC)"; \
	else \
		kubectl logs -n $(NAMESPACE) -f $(POD_NAME); \
	fi

shell:
	@echo "$(YELLOW)Připojování k shellu...$(NC)"
	@if [ -z "$(POD_NAME)" ]; then \
		echo "$(RED)Pod nenalezen$(NC)"; \
	else \
		kubectl exec -n $(NAMESPACE) -it $(POD_NAME) -- /bin/bash; \
	fi

restart:
	@echo "$(YELLOW)Restartování podu...$(NC)"
	@if [ -z "$(POD_NAME)" ]; then \
		echo "$(RED)Pod nenalezen$(NC)"; \
	else \
		kubectl delete pod -n $(NAMESPACE) $(POD_NAME); \
		echo "$(GREEN)Pod restartuje automaticky...$(NC)"; \
	fi

# ============================================================================
# FILE MANAGEMENT
# ============================================================================

.PHONY: copy-results copy-data

copy-results:
	@echo "$(YELLOW)Kopírování hyperopt výsledků...$(NC)"
	@mkdir -p ./hyperopt_results
	@kubectl cp -n $(NAMESPACE) $(POD_NAME):/freqtrade/user_data/hyperopt_results ./hyperopt_results 2>/dev/null || echo "Výsledky nenalezeny"
	@echo "$(GREEN)Výsledky v ./hyperopt_results$(NC)"

copy-data:
	@echo "$(YELLOW)Kopírování dat z podu...$(NC)"
	@mkdir -p ./pod_data
	@kubectl cp -n $(NAMESPACE) $(POD_NAME):/freqtrade/user_data/data ./pod_data 2>/dev/null || echo "Data nenalezena"
	@echo "$(GREEN)Data v ./pod_data$(NC)"

# ============================================================================
# KONFIGURACE
# ============================================================================

.PHONY: config-show secrets-list

config-show:
	@echo "$(YELLOW)Konfigurace...$(NC)"
	@kubectl exec -n $(NAMESPACE) $(POD_NAME) -- cat /etc/freqtrade/config.json | head -80

secrets-list:
	@echo "$(YELLOW)Secrets...$(NC)"
	@kubectl get secrets -n $(NAMESPACE) | grep wolf

# ============================================================================
# HYPEROPT BATCH - Sequential optimization pipeline
# ============================================================================
#
# Optimalni poradi pro maximalizaci profitu:
#
#   1. BUY (vstupni podminky) - nejvetsi dopad, urcuje kvalitu signalu
#      donchian_period, rsi_oversold, rsi_period, ema_fast, ema_slow
#      dca_max_count, dca_base_drop, dca_multiplier, dca_cooling_candles
#      -> 10 params, 8 optimize=True, potrebuje nejvic epoch
#
#   2. ROI (minimal_roi tabulka) - kdyz mame dobre vstupy, ladime exity
#      -> freqtrade generuje ROI tabulku, male search space
#
#   3. SELL (exit parametry) - trailing, partial TP, short TP
#      short_take_profit, trailing_atr_mult, breakeven_trigger, partial_profit_pct
#      -> 4 params, stredni search space
#
#   Trailing space preskocen - pouzivame custom_stoploss (ATR-based),
#   nativni trailing_stop je disabled.
#
#   Kazdy krok pouziva vysledky predchoziho (FreqTrade --no-color
#   automaticky nacte posledni best z hyperopt_results).
#
# Pouziti:
#   make hyperopt-batch                          # default 1000/500/500 epoch
#   make hyperopt-batch BUY_EPOCHS=2000          # vic epoch pro buy
#   make hyperopt-batch LOSS_FN=SharpeHyperOptLossDaily  # jina loss funkce
#
# ============================================================================

# Epoch counts per space (buy needs most - largest search space)
BUY_EPOCHS?=1000
ROI_EPOCHS?=500
SELL_EPOCHS?=500

# Loss function - can be overridden per run
# Options: OnlyProfitHyperOptLoss, SharpeHyperOptLossDaily,
#          SortinoHyperOptLossDaily, CalmarHyperOptLoss,
#          MaxDrawDownHyperOptLoss, ProfitDrawDownHyperOptLoss
LOSS_FN?=SharpeHyperOptLossDaily

# Min trades filter - skip results with too few trades
MIN_TRADES?=10

# Docker run template for hyperopt
define HYPEROPT_CMD
docker rm -f $(DOCKER_CONTAINER) 2>/dev/null || true; \
docker run --rm -it \
	--name $(DOCKER_CONTAINER) \
	-v $(PWD)/user_data:/freqtrade/user_data \
	--user $(DOCKER_USER) \
	$(EFFECTIVE_IMAGE) \
	hyperopt \
	--random-state 42 \
	--hyperopt-loss $(LOSS_FN) \
	--strategy $(STRATEGY) \
	--strategy-path /freqtrade/user_data/strategies \
	--timeframe $(TIMEFRAME) \
	-c /freqtrade/user_data/config.json \
	--timerange $(HYPEROPT_START)-$(HYPEROPT_END) \
	--min-trades $(MIN_TRADES) \
	-j $(JOBS)
endef

.PHONY: hyperopt-batch hyperopt-batch-buy hyperopt-batch-roi \
	hyperopt-batch-sell hyperopt-batch-validate

hyperopt-batch: hyperopt-batch-buy hyperopt-batch-roi hyperopt-batch-sell hyperopt-batch-validate
	@echo ""
	@echo "$(GREEN)======================================================$(NC)"
	@echo "$(GREEN)  HYPEROPT BATCH KOMPLETNI$(NC)"
	@echo "$(GREEN)======================================================$(NC)"
	@echo "$(CYAN)  1. BUY   $(BUY_EPOCHS) epoch  - vstupni podminky + DCA$(NC)"
	@echo "$(CYAN)  2. ROI   $(ROI_EPOCHS) epoch  - minimal_roi tabulka$(NC)"
	@echo "$(CYAN)  3. SELL  $(SELL_EPOCHS) epoch  - trailing + TP parametry$(NC)"
	@echo "$(CYAN)  Loss fn: $(LOSS_FN)$(NC)"
	@echo "$(GREEN)======================================================$(NC)"
	@echo ""
	@echo "$(YELLOW)Dalsi kroky:$(NC)"
	@echo "  make hyperopt-show-docker EPOCH=-1   # Nejlepsi vysledek"
	@echo "  make backtest-docker                  # Validacni backtest"
	@echo ""

hyperopt-batch-buy:
	@echo ""
	@echo "$(CYAN)======================================================$(NC)"
	@echo "$(CYAN)  FAZE 1/3: BUY SPACE (vstupni podminky + DCA)$(NC)"
	@echo "$(CYAN)  Epochs: $(BUY_EPOCHS) | Loss: $(LOSS_FN)$(NC)"
	@echo "$(CYAN)  Params: donchian_period, rsi_oversold, rsi_period,$(NC)"
	@echo "$(CYAN)          ema_fast, ema_slow, dca_max_count,$(NC)"
	@echo "$(CYAN)          dca_base_drop, dca_multiplier, dca_cooling$(NC)"
	@echo "$(CYAN)======================================================$(NC)"
	@echo ""
	@$(HYPEROPT_CMD) \
		--space buy \
		-e $(BUY_EPOCHS) || true
	@echo ""
	@echo "$(GREEN)  BUY SPACE hotov. Spoustim validacni backtest...$(NC)"
	@echo ""
	@docker run --rm \
		-v $(PWD)/user_data:/freqtrade/user_data \
		$(EFFECTIVE_IMAGE) \
		backtesting \
		--strategy $(STRATEGY) \
		--strategy-path /freqtrade/user_data/strategies \
		--timeframe $(TIMEFRAME) \
		--pairs $(PAIRS) \
		--timerange $(HYPEROPT_START)-$(HYPEROPT_END) \
		--cache none || true
	@echo ""
	@echo "$(GREEN)  FAZE 1/3 KOMPLETNI$(NC)"
	@echo ""

hyperopt-batch-roi:
	@echo ""
	@echo "$(CYAN)======================================================$(NC)"
	@echo "$(CYAN)  FAZE 2/3: ROI SPACE (minimal_roi tabulka)$(NC)"
	@echo "$(CYAN)  Epochs: $(ROI_EPOCHS) | Loss: $(LOSS_FN)$(NC)"
	@echo "$(CYAN)  Optimalizuje casove ROI tabulku pro exit$(NC)"
	@echo "$(CYAN)======================================================$(NC)"
	@echo ""
	@$(HYPEROPT_CMD) \
		--space roi \
		-e $(ROI_EPOCHS) || true
	@echo ""
	@echo "$(GREEN)  ROI SPACE hotov.$(NC)"
	@echo ""

hyperopt-batch-sell:
	@echo ""
	@echo "$(CYAN)======================================================$(NC)"
	@echo "$(CYAN)  FAZE 3/3: SELL SPACE (exit parametry)$(NC)"
	@echo "$(CYAN)  Epochs: $(SELL_EPOCHS) | Loss: $(LOSS_FN)$(NC)"
	@echo "$(CYAN)  Params: short_take_profit, trailing_atr_mult,$(NC)"
	@echo "$(CYAN)          breakeven_trigger, partial_profit_pct$(NC)"
	@echo "$(CYAN)======================================================$(NC)"
	@echo ""
	@$(HYPEROPT_CMD) \
		--space sell \
		-e $(SELL_EPOCHS) || true
	@echo ""
	@echo "$(GREEN)  SELL SPACE hotov.$(NC)"
	@echo ""

hyperopt-batch-validate:
	@echo ""
	@echo "$(CYAN)======================================================$(NC)"
	@echo "$(CYAN)  VALIDACE: Finalní backtest s optimalizovanými params$(NC)"
	@echo "$(CYAN)  Timerange: $(BACKTEST_START)-$(BACKTEST_END)$(NC)"
	@echo "$(CYAN)  (Out-of-sample data - jiny obdobi nez hyperopt)$(NC)"
	@echo "$(CYAN)======================================================$(NC)"
	@echo ""
	@docker run --rm \
		-v $(PWD)/user_data:/freqtrade/user_data \
		$(EFFECTIVE_IMAGE) \
		backtesting \
		--strategy $(STRATEGY) \
		--strategy-path /freqtrade/user_data/strategies \
		--timeframe $(TIMEFRAME) \
		--pairs $(PAIRS) \
		--timerange $(BACKTEST_START)-$(BACKTEST_END) \
		--cache none || true
	@echo ""
	@echo "$(GREEN)  VALIDACE KOMPLETNI$(NC)"
	@echo ""

# ============================================================================
# WORKFLOWS
# ============================================================================

.PHONY: full-optimization quick-test

full-optimization: hyperopt-batch
	@echo "$(GREEN)Full optimization pipeline dokoncen.$(NC)"

quick-test: backtest-docker
	@echo "$(GREEN)Backtest dokončen$(NC)"

# ============================================================================
# CLEANUP
# ============================================================================

.PHONY: clean-hyperopt clean-data clean-all

clean-hyperopt:
	@echo "$(YELLOW)Mazání hyperopt výsledků...$(NC)"
	@rm -rf user_data/hyperopt_results
	@rm -f user_data/*.log
	@echo "$(GREEN)Hyperopt vyčištěn$(NC)"

clean-data:
	@echo "$(YELLOW)Mazání dat...$(NC)"
	@rm -rf user_data/data
	@echo "$(GREEN)Data vyčištěna$(NC)"

clean-all: clean-hyperopt clean-data
	@echo "$(YELLOW)Čištění kompletní...$(NC)"
	@echo "$(GREEN)Vše vyčištěno$(NC)"

# ============================================================================
# DEFAULT TARGET
# ============================================================================

all: help

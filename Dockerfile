FROM freqtradeorg/freqtrade:develop

LABEL maintainer="wolf-strategy"
LABEL description="WolfStrategyV1 - Long -> Short Profit Flip Trading Bot"

ENV TZ=Europe/Prague
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY WolfStrategyV1.py /freqtrade/user_data/strategies/
COPY generate_hyperopt_config.py /freqtrade/

ENV WOLF_STRATEGY_LOG_LEVEL=INFO
ENV WOLF_SHORT_LEVERAGE=100
ENV WOLF_SHORT_STOP_LOSS=0.008
ENV WOLF_SHORT_TAKE_PROFIT=0.03
ENV WOLF_DCA_MAX_COUNT=5
ENV WOLF_DCA_INCREMENT=1.5

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8081/api/v1/ping || exit 1

CMD ["freqtrade", "trade", "--config", "/etc/freqtrade/bot.yaml"]

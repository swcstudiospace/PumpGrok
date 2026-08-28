# Образ намеренно без ключей: секреты приходят переменными окружения
# (GROKBOT_*), конфиг монтируется томом. Собранный образ можно хранить
# где угодно — в нём нет ничего, чем можно торговать.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    GROKBOT_LOG_PATH=/app/logs/trades.jsonl \
    GROKBOT_STATE_PATH=/app/state/pipeline.json

WORKDIR /app

RUN useradd --system --create-home --home-dir /home/grokbot grokbot

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts
COPY config.example.yaml pyproject.toml README.md ./

# Логи и состояние — тома: они должны переживать пересборку образа.
RUN mkdir -p /app/logs /app/state /app/config && chown -R grokbot:grokbot /app
VOLUME ["/app/logs", "/app/state"]

USER grokbot

# Живость берём из самого пайплайна. Если health выключен (порт 0),
# проверка всегда успешна: тогда за процессом следит только рестарт-политика.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,sys,urllib.request; \
port=os.environ.get('GROKBOT_HEALTH_PORT','0'); \
sys.exit(0) if port in ('','0') else None; \
sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz',timeout=3).status==200 else 1)"

# SIGTERM пайплайн обрабатывает сам: доделывает начатое и сохраняет состояние.
STOPSIGNAL SIGTERM

ENTRYPOINT ["python", "-m", "src.pipeline"]
CMD ["--config", "/app/config/config.yaml"]

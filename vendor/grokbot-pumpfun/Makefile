.PHONY: help install dev test cov lint fmt types check run check-config dashboard replay tune docker clean

PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
CONFIG ?= config.yaml
LOG ?= logs/trades.jsonl

help:            ## показать цели
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | column -t -s "$$(printf '\t')"

install:         ## venv и зависимости для запуска
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -r requirements.txt

dev: install     ## то же плюс линтер, типы, тесты
	$(BIN)/pip install -r requirements-dev.txt

test:            ## прогнать тесты
	$(BIN)/python -m pytest

cov:             ## тесты с покрытием
	$(BIN)/python -m pytest --cov=src --cov-report=term-missing

lint:            ## ruff
	$(BIN)/ruff check .

fmt:             ## ruff с автоисправлением
	$(BIN)/ruff check . --fix

types:           ## mypy
	$(BIN)/mypy src

check: lint types test  ## всё, что гоняет CI

check-config:    ## проверить конфиг, ничего не запуская
	$(BIN)/python -m src.pipeline --config $(CONFIG) --check

run:             ## запустить пайплайн (режим берётся из конфига)
	$(BIN)/python -m src.pipeline --config $(CONFIG)

dashboard:       ## живой дашборд по логу
	$(BIN)/python scripts/dashboard.py $(LOG) --watch 5

replay:          ## сводка по логу
	$(BIN)/python scripts/replay.py $(LOG) --rotated

tune:            ## подобрать веса и порог по логу
	$(BIN)/python scripts/tune.py $(LOG) --rotated

docker:          ## собрать образ
	docker build -t grokbot-pumpfun:latest .

clean:           ## убрать мусор сборки и кэши
	rm -rf .pytest_cache .mypy_cache .ruff_cache **/__pycache__ .coverage

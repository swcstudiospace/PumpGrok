.PHONY: help sync lint fmt typecheck test test-soak test-all cov audit run-paper gateway replay report gates prompts check doctor clean

UV ?= uv
BOT ?= bot-00-chief
TASK ?= $(error TASK=<task-id> is required for gates)
REPLAY ?= tests/fixtures/replay/smoke

# services/desk-signer joins lint, typecheck and audit when its src tree lands; until then those
# service steps are no-ops. services/desk-gateway stays out of the typecheck gate: mypy --strict
# reports one finding in services/desk-gateway/src/desk_gateway/server.py at this base.
SERVICE_SRC := $(wildcard services/desk-signer/src)

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | column -t -s "$$(printf '\t')"

sync:            ## install locked deps incl. dev group
	$(UV) sync --frozen --group dev

lint: sync       ## ruff lint + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(if $(SERVICE_SRC),$(UV) run ruff check $(SERVICE_SRC),echo "services: services/desk-signer/src absent; service lint skipped")

fmt: sync        ## ruff format (writes files; never run by a hook)
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck: sync  ## mypy --strict on src/
	$(UV) run mypy src/
	$(if $(SERVICE_SRC),$(UV) run mypy $(SERVICE_SRC),echo "services: services/desk-signer/src absent; service typecheck skipped")

test: sync       ## fast suite with branch coverage; the floor is pyproject fail_under (soak excluded)
	$(UV) run pytest -q -m 'not slow' --cov=pumpgrok

test-soak: sync  ## slow multi-day soak replay only (-m slow)
	$(UV) run pytest -q -m slow

test-all: sync   ## every test, soak included
	$(UV) run pytest -q -m 'slow or not slow'

cov: sync        ## fast suite with branch coverage; writes coverage.xml; floor in pyproject
	$(UV) run pytest -q -m 'not slow' --cov=pumpgrok --cov-report=term-missing --cov-report=xml:coverage.xml

audit: sync      ## pip-audit against the lockfile
	$(UV) export --frozen --no-dev --no-emit-project --format requirements-txt --no-hashes -o /tmp/pumpgrok-req.txt
	$(UV) run pip-audit -r /tmp/pumpgrok-req.txt --strict
	$(if $(SERVICE_SRC),$(UV) export --frozen --project services/desk-signer --no-dev --no-emit-project --no-emit-package pumpgrok --format requirements-txt --no-hashes -o /tmp/pumpgrok-service-req.txt && $(UV) run pip-audit -r /tmp/pumpgrok-service-req.txt --strict,echo "services: services/desk-signer/src absent; service audit skipped")

run-paper: sync  ## start the paper desk (foreground)
	$(UV) run pumpgrok run --mode paper

gateway:         ## serve the desk gateway over HTTP (foreground, paper only; repo root var/)
	$(UV) run --project services/desk-gateway python -m desk_gateway

replay: sync     ## one cycle against a recorded dataset
	$(UV) run pumpgrok run --mode paper --once --replay $(REPLAY)

report: sync     ## daily report from the ledger
	$(UV) run pumpgrok report --daily

doctor: sync     ## effective config, data sources, ledger, killswitch
	$(UV) run pumpgrok doctor

gates:           ## G-1..G-7 for BOT/TASK (stdlib + pyyaml only, like CI)
	python3 -P ci/gates/run_all.py --bot $(BOT) --base origin/main --receipt .receipts/$(BOT)/$(TASK).json

prompts:         ## assemble prompts and regenerate agent templates
	ASSEMBLE_UV='$(UV)' bash scripts/assemble-prompts.sh
	$(UV) run python scripts/generate-templates.py

check: lint typecheck test audit  ## everything ci.yml runs
	ASSEMBLE_UV='$(UV)' bash scripts/assemble-prompts.sh --check
	$(UV) run python scripts/generate-templates.py --check
	$(UV) run python scripts/generate-event-schemas.py --check
	./scripts/check.sh

clean:           ## caches only; never var/
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find src tests ci -name __pycache__ -type d -prune -exec rm -rf {} +

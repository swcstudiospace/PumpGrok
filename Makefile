.PHONY: help sync lint fmt typecheck test audit run-paper gateway replay report gates prompts check doctor clean

UV ?= uv
BOT ?= bot-00-chief
TASK ?= $(error TASK=<task-id> is required for gates)
REPLAY ?= tests/fixtures/replay/smoke

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | column -t -s "$$(printf '\t')"

sync:            ## install locked deps incl. dev group
	$(UV) sync --frozen --group dev

lint: sync       ## ruff lint + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt: sync        ## ruff format (writes files; never run by a hook)
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck: sync  ## mypy --strict on src/
	$(UV) run mypy src/

test: sync       ## pytest (product + gate self-tests)
	$(UV) run pytest -q

audit: sync      ## pip-audit against the lockfile
	$(UV) export --frozen --no-dev --no-emit-project --format requirements-txt --no-hashes -o /tmp/pumpgrok-req.txt
	$(UV) run pip-audit -r /tmp/pumpgrok-req.txt --strict

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

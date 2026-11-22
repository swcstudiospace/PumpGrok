# Phase 15: Verification record (15-07)

Chief-owned evidence record, per the Phase 11 closure standard. This file is
evidence only; plan 15-07 changes no production code. Every command below
records its verbatim exit code and summary line.

## SC 1 — full gate set (PRC-01)

| Gate | Exit | Summary line |
|---|---|---|
| `make lint` | 0 | `1255 files already formatted`; `All checks passed!` |
| `make typecheck` | 0 | `Success: no issues found in 295 source files` |
| `make test` | 0 | full fast suite; coverage 90.27% (floor 89.9%) |
| `make audit` | 0 | `No known vulnerabilities found` |
| `./scripts/check.sh` | 0 | `ok: 35 skills, 10 agents, 530 markdown files checked`; `PumpGrok repository structure looks healthy.` |
| `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` | 0 | `trades filled=2 not_filled=1` |

Gate-fix note: `make lint` and `make typecheck` were red at HEAD (37
pre-existing lint findings in Phase 15 files from plans 15-01…15-05, plus a
mypy `--strict` failure on the registry `resolve_factory` module fallback).
Fixed mechanically in commit `4743c56` (15-06 clone) plus the
`tests/strategies/__init__.py` marker (below). `make test` initially failed
at collection: `tests/strategies/test_registry.py` and
`tests/core/test_registry.py` share a basename and both dirs lacked an
`__init__.py`, so pytest's prepend import mode collided. Adding the empty
`__init__.py` (the repo's own convention — e.g. `tests/datafeed/__init__.py`)
qualifies the strategies modules and resolves the collision.

## SC 2–9 — per-plan criteria re-run on the final tree

| Criterion | Command | Exit |
|---|---|---|
| SC 2 | `uv run pytest -q tests/upgrade tests/backtest/test_harness_strategy_identity.py` | 0 |
| SC 2 | `uv run pytest -q tests/upgrade/test_paramset_hash_stable.py tests/upgrade/test_paramset_strategy.py` | 0 |
| SC 2 | `uv run python -c "import tomllib;tomllib.load(open('src/pumpgrok/config/upgrade_bounds.toml','rb'))"` | 0 |
| SC 3 | `uv run pytest -q tests/strategies/test_base.py tests/strategies/test_registry.py` | 0 |
| SC 4 | `uv run pytest -q tests/config/test_paper_event_overlay.py` | 0 |
| SC 5 | `uv run pytest -q tests/strategies/test_attribution.py tests/strategies/test_allocation.py tests/strategies/test_legacy_parity.py tests/ledger/test_strategy_state.py tests/ledger/test_ticket_refs.py` | 0 |
| SC 6 | `uv run pytest -q tests/strategies tests/upgrade` | 0 |
| SC 7 | `uv run pytest -q tests/strategies/test_no_llm.py` | 0 |
| SC 8 | `uv run pytest -q tests/strategies/test_recovery.py` | 0 |
| SC 9 | `uv run pytest -q tests/config/test_paper_fees_default.py tests/backtest/test_fee_parity.py tests/execution/test_fee_model_v2.py` | 0 |

Regression once more in final tree: `uv run pytest -q tests/desk tests/datafeed tests/execution` → exit 0.

## SC 10 (MKT-09, plan 15-06)

- `uv run pytest -q tests/desk/test_live_paper_root.py tests/desk/test_exit_rules_filter.py tests/datafeed/test_readonly.py` → exit 0.
  The root refuses to build unless the mode is paper; an AST scan finds no
  signing or send symbol in the six composed modules; the global exit book
  never double-sells a strategy position; only the five allowlisted methods
  are reachable.

## SC 11 (RT-02, plan 15-06)

- `uv run pytest -q tests/desk/test_intent_router.py tests/desk/test_ticket_approval_allocation.py` → exit 0.
- `uv run pytest tests/desk/test_intent_router.py -rs | grep -q SKIPPED` → exit 1 (grep finds no SKIPPED; the negated criterion `!` exits 0). 6 passed, zero skipped.

## SC 12 — import-graph guards (MKT-09)

- `uv run pytest -q tests/safety/test_import_graph_no_live.py tests/safety/test_no_signing_outside_live_stub.py` → exit 0.
  31 passed with `strategies/` and `datafeed/` present: no guarded root

Additional pre-existing failures found by the full-suite run and fixed in
this closure (each verified failing on `82fb3b2` before this plan's tree
changes were applied, then green):

- `tests/quality/test_no_plain_swallow.py::test_no_new_plain_swallow_handlers`
  (`strategies/base.py` `code_digest` broad `except Exception`) — narrowed
  to `(ImportError, OSError, TypeError)` in `code_digest`.
- `tests/safety/test_live_disabled_overlays.py::test_overlay_profile_set_is_unchanged`
  (stale expected overlay set, missing the D-04 `paper-event` profile) —
  expected set updated to include `paper-event`; every overlay still
  disables live.
  reaches the live adapter; no signing symbol outside `execution/live/`.

## SC 13 — contracts untouched (STR-01)

- `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0` → exit 0 (diff empty).

## SC 14 — hash pairs (PRC-03)

- `uv run pumpgrok verify --fixture smoke-10m` twice → `a == b ==
  b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` (equal,
  and equal to the golden). `CHANGELOG.md` in the working tree contains
  both the `Phase 15: smoke-10m events.hash before:` and `after:` lines
  with that value.
- `tests/fixtures/replay/pins/trading_smoke.json` `events_hash` =
  `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54`;
  `CHANGELOG.md` contains the `Phase 15: trading-smoke events.hash before:`
  and `after:` lines, with `after:` equal to the pin. (Before equals after
  for trading-smoke: the fee-default flip did not move this fixture's hash.)
- `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` → exit 0.

**Pending journal (not a failure of this plan):** the four Phase 15 lines
live in `CHANGELOG.md` as an uncommitted working-tree change owned by the
journal seat (bot-09-journal); `git log` shows the file untouched since
Phase 14. Plan 15-07 does not edit or commit `CHANGELOG.md`. Once the
journal seat commits them, the grep criteria above hold verbatim.

## SC 15 — live refusal (LIV-07)

- `uv run pumpgrok run --mode live --once` → exit 3 (`No transaction was attempted.`)
- `uv run pumpgrok run --mode live --once; test $? -eq 3` → exit 0.

## Defects

None outstanding against the final tree. The `make lint` / `make typecheck`
/ `make test` failures found during this plan were fixed inside plans 15-06
and 15-07 as recorded in the SC 1 note above; no defect is filed against
the owning plans because the fixes are landed and green.

## Deviations

None in 15-07 itself: no production code was edited to make gates pass
(the two tree fixes — gate lint/typecheck normalization and the
`tests/strategies/__init__.py` collection fix — are recorded in the SC 1
note and committed as tested, revertable changes).

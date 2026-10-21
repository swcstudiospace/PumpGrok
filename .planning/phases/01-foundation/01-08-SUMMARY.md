---
phase: 01-foundation
plan: 08
subsystem: cli
tags: [cli, replay, logging, correlation, live-gate, doctor, redaction, ledger]

# Dependency graph
requires:
  - phase: 01-02
    provides: "pydantic-settings loader with startup guards, ConfigError, refuse_cli_secrets"
  - phase: 01-03
    provides: "IdFactory, CorrelationId, bind_correlation, RiskBudget and the core facade"
  - phase: 01-04
    provides: "hash-chained LedgerStore, 18 R32 event models, recreate_ledger_db"
  - phase: 01-05
    provides: "FixtureClock, make_rng, manifest-gated load_dataset with CorruptFixture"
provides:
  - "cli.py: parse/check/main split, run and doctor verbs, exit-code map 0/1/2/3/4/5"
  - "Skip-only replay cycle: one JournalNote (source=replay) per run, ledger recreated each run"
  - "execution/live/live_gate.py: LiveGate with the nine R21 ids in order, fail-closed; refusal_lines()"
  - "execution/live/live_adapter.py: LiveAdapterStub; every method appends LiveWriteAttempted then raises LiveGateError"
  - "doctor.py: present subsystems ok, absent ones warn not-yet-implemented, exit 0"
  - "logging/{json,redaction}.py: single setup call, canonical one-line JSON per FOUNDATION_STACK 5.1, RedactionFilter, bind_seat/bind_ticket"
  - "core.ids.ambient_correlation(): correlation accessor for the log formatter"
affects: [01-09, phase-02-restructure]

# Actuals (#2632)
actuals:
  tokens: n/a
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Exit codes are a single map in cli.py; argparse's exit 2 is overridden so 2 means only ledger inconsistency"
    - "Replay order: manifest verification before any ledger file exists; ledger recreated per run"
    - "Correlation and seat travel in contextvars; the JSON formatter reads them, extras override"
    - "RedactionFilter mutates the record once, so every formatter sees redacted text"

key-files:
  created:
    - src/pumpgrok/cli.py
    - src/pumpgrok/doctor.py
    - src/pumpgrok/execution/__init__.py
    - src/pumpgrok/execution/live/__init__.py
    - src/pumpgrok/execution/live/live_gate.py
    - src/pumpgrok/execution/live/live_adapter.py
    - src/pumpgrok/logging/__init__.py
    - src/pumpgrok/logging/json.py
    - src/pumpgrok/logging/redaction.py
    - tests/test_logging.py
    - tests/test_correlation.py
    - tests/test_skip_cycle.py
    - tests/test_live_gate.py
  modified:
    - src/pumpgrok/config/settings.py
    - src/pumpgrok/core/adapter.py
    - src/pumpgrok/core/__init__.py
    - src/pumpgrok/core/ids.py
    - src/pumpgrok/core/correlation.py
    - tests/config/test_settings.py

key-decisions:
  - "The live refusal moved from settings.load_settings into the CLI via LiveGate; the loader's own docstring named this as the point to remove it."
  - "LiveGate and LiveAdapterStub moved from core/adapter.py to execution/live (clean cutover; core facade no longer exports them)."
  - "Ids 3-9 fail closed with the reason naming what is missing; id 8 is always unmet by design. Ids 5 and 6 are unmet because no wallet_allowlist or notional_cap setting exists in this release."
  - "LiveWriteAttempted rows use source=manual: source=paper would enter paper-window metrics and source=replay is refused for live metrics."
  - "Ledger correlation_id stores the span an event was produced under (cycle root for cycle events, <root>.<n> for tool calls), so the chain test can assert child spans on ledger rows. Core docstrings updated; docs/design/interfaces.md:191 still says the root (see Deviations)."
  - "PUMPGROK_LOG_JSON and PUMPGROK_LIVE_ENABLE are declared as non-model env names so the unknown-name guard accepts them; LIVE_ENABLE is read only by the gate and is never a TOML key."
  - "Doctor decides presence with importlib.util.find_spec on each module name, so a subsystem reports present as soon as its package lands."

patterns-established:
  - "Skip cycle: one JournalNote per run, correlation root = cycle ULID from a FixtureClock-seeded IdFactory, seat desk, note_kind note"
  - "Refusals are ledger rows: LiveWriteAttempted carries gate_result_json with the unmet ids before the LiveGateError is raised"
  - "Logs: extras promoted to top-level fields are event, correlation_id, seat, ticket_id, mint, duration_ms; all other extras go to data"

requirements-completed: ["FOUND-013", "OBS-001", "OBS-002"]

# Coverage metadata omitted: legacy prose-only SUMMARY (acceptance is by the commands below).

# Metrics
duration: n/a
completed: 2026-10-21
status: complete
---

# Phase 1 Plan 08: CLI skip cycle, redacted JSON logs, live gate and doctor

**Runnable paper desk: `run --mode paper --once --replay` writes one replay JournalNote and exits 0; live exits 3 listing the unmet R21 ids; doctor exits 0 with honest absent-subsystem warnings; every log line is redacted single-line JSON with correlation spans.**

## Performance

- **Tasks:** 3 (tracer, logging/correlation, live gate/adapter/doctor)
- **Commits:** 3 implementation commits plus this summary
- **Files:** 13 created, 6 modified

## Accomplishments

- The skip-only cycle works end to end: manifest verified before any ledger file (exit 4), ledger recreated per run, fixture events read under the FixtureClock, one `JournalNote` with `source=replay` appended, chain verified, exit 0.
- Live is refused with exit 3 before any other work. The block lists each unmet id as `[ ] n id reason` and states that no transaction was attempted. Run without `--once --replay` exits 5 and creates no ledger.
- `LiveAdapterStub` appends a `LiveWriteAttempted` row for every method and then raises `LiveGateError`. No transaction is built.
- Logs are one canonical JSON object per line (ts, level, logger, msg, event, correlation_id, seat, ticket_id, mint, mode, profile, data). Secrets are masked in msg and in every string leaf, and secret-named keys lose their value.
- Child spans `<ulid>.<n>` appear on log records and on ledger rows under one root.

## Task Commits

1. **Logging and correlation (task 2):** `e1ba782` feat(01-08): redacted JSON logs and correlation contextvars
2. **Live gate, adapter stub and doctor (task 3):** `99aa5f9` feat(01-08): live gate with nine R21 ids, refusing adapter stub and doctor
3. **CLI and skip cycle (task 1, tracer):** `712845e` feat(01-08): skip-only replay cycle through the run verb (FOUND-013)

Commit order is dependency order, not plan order (see Deviations).

**Plan metadata:** this summary commit (docs(01-08)).

## Files Created/Modified

- `src/pumpgrok/cli.py` - parse/check/main, run and doctor verbs, exit-code map, skip cycle.
- `src/pumpgrok/doctor.py` - subsystem report; warnings never fail.
- `src/pumpgrok/execution/live/live_gate.py` - nine ids in order, `check()`, `evaluate()`, `refusal_lines()`.
- `src/pumpgrok/execution/live/live_adapter.py` - refusing stub; append then raise.
- `src/pumpgrok/logging/json.py` - `JsonFormatter`, `setup_logging`, `bind_seat`, `bind_ticket`.
- `src/pumpgrok/logging/redaction.py` - `RedactionFilter`, `redact_text`, `redact_value`, `SECRET_NAME_RE`, value shapes.
- `src/pumpgrok/config/settings.py` - live refusal removed from `load_settings`; `NON_SETTING_ENV_NAMES` added.
- `src/pumpgrok/core/adapter.py`, `core/__init__.py` - `LiveAdapterStub` and `LiveGate` removed (moved).
- `src/pumpgrok/core/ids.py` - `ambient_correlation()`; docstring on ledger correlation.
- `src/pumpgrok/core/correlation.py` - docstring on ledger correlation.
- `tests/test_logging.py` (incl. `test_log_redaction`), `tests/test_correlation.py` (incl. `test_correlation_id_chain`), `tests/test_skip_cycle.py`, `tests/test_live_gate.py` (new).
- `tests/config/test_settings.py` - two live-refusal tests replaced by tests of the gate-owned refusal.

## Decisions Made

- The live refusal belongs to the CLI and `LiveGate`, not to the settings loader. The loader's docstring said to remove it once the gate existed.
- Preconditions 3-9 report unmet with reasons because this release has no source=paper metrics reader, wallet allowlist, notional cap, confirmation verifier, adapter, or readable halt/kill/breaker state. Fail closed.
- Ledger `correlation_id` stores the span an event was produced under (see key-decisions).
- `LiveWriteAttempted.source = manual` (see key-decisions).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Settings startup guard would reject the new env names**
- **Found during:** Task 2/3 (logging and live gate env reads)
- **Issue:** `find_unknown_env` refuses any `PUMPGROK_*` name not in `allowed_env_names()`, so `PUMPGROK_LOG_JSON` and `PUMPGROK_LIVE_ENABLE` would exit 1 before their owners ran.
- **Fix:** Declared `NON_SETTING_ENV_NAMES` in `config/settings.py` and included them in `allowed_env_names()`.
- **Files modified:** `src/pumpgrok/config/settings.py`
- **Verification:** `tests/config/test_settings.py` and `tests/test_skip_cycle.py` pass.
- **Committed in:** `99aa5f9`

**2. [Rule 1 - Bug] `mode=None` init kwarg would shadow `PUMPGROK_MODE` (preventive)**
- **Found during:** Task 1 (CLI settings construction), by reading pydantic-settings source precedence; not reproduced against an unfixed build
- **Issue:** Passing `mode=None` as an init kwarg would take precedence over the env value; `effective_mode` then asserts a non-None mode when the env is set.
- **Fix:** The CLI passes `mode` only when `--mode` is given (`_settings_kwargs`).
- **Files modified:** `src/pumpgrok/cli.py`
- **Verification:** Checked directly on the committed build: `PUMPGROK_MODE=live pumpgrok run --once --replay tests/fixtures/replay/smoke` exits 3; `PUMPGROK_MODE=paper` exits 0. No dedicated test was added.
- **Committed in:** `712845e`

**3. [Rule 2 - Missing critical] Live path still refused by the loader**
- **Found during:** Task 3 (wiring LiveGate)
- **Issue:** `load_settings` raised a ConfigError (exit 1) for effective mode live, so the gate's exit 3 could never be reached.
- **Fix:** Removed the refusal from the loader; the CLI runs the gate. Updated the two tests that asserted the old refusal.
- **Files modified:** `src/pumpgrok/config/settings.py`, `tests/config/test_settings.py`
- **Verification:** `uv run pumpgrok run --mode live --once` exits 3; the updated settings tests pass.
- **Committed in:** `99aa5f9`

### Scope and interpretation

**4. [Rule 4-adjacent, judgment] Core stub relocation**
- `LiveAdapterStub` and `LiveGate` were in `core/adapter.py` with no logging or ledger. They moved to `execution/live` with the ledger-recording behaviour, and the core facade no longer exports them (clean cutover, no alias).

**5. [Interpretation] Redaction length cap**
- The precedent `_redact` truncates to 160 characters. Applying that to every log message would truncate ordinary messages, so the implementation masks secret spans (keep-4) without a message-length cap.

**6. [Interpretation] Ledger correlation column**
- `core/ids.py`, `core/correlation.py` and the test plan treat the ledger `correlation_id` as the producing span. `docs/design/interfaces.md:191` says the column stores the root. The design doc is not changed here; the orchestrator should reconcile it.

**7. [Interpretation] Adapter construction is inert**
- `LiveAdapterStub.__init__` does not raise. paper-engine 7.4 says construction re-runs `check()`; here each refused call re-runs it and records the result, so no construction path can send anything.

**8. [Process] Commit order**
- Commits follow dependency order (logging, then live gate and doctor, then CLI) rather than plan task order, so no intermediate commit has a broken import.

**Total deviations:** 3 auto-fixed (1 blocking, 1 bug, 1 missing critical) plus 5 interpretive notes above.
**Impact on plan:** The plan's behaviours are all met. The auto-fixes were required for the plan's own verify commands to pass. No scope creep beyond the plan's listed files, plus one new test file (`tests/test_live_gate.py`) for the stub behaviour the plan did not test directly.

## Issues Encountered

- `ruff check --no-fix` (read-only; no fix or format was run) reports on touched files: `core/__init__.py` I001 and RUF022 (ordering of `ULID_RE` and the `__all__` entries; `LedgerUnavailable`/`LiveGateError` were already misordered at HEAD); `tests/config/test_settings.py` C420 (pre-existing line). The orchestrator's `ruff check --fix` pass will normalise these.
- `mypy --strict src/` (read-only) reports 4 errors, all in lines this plan did not change: `ledger/events.py:341,349` (dict type arguments) and the `Clock` re-export in `core/ids.py` seen from `core/registry.py:27` and `core/__init__.py:30`.
- The `pytest` harness prints "Pytest: No tests collected" after a passing run in this environment; the dot output and exit 0 are the authoritative result.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The skip cycle, live refusal and doctor are in place for the container HEALTHCHECK (plan 01-09). `pumpgrok doctor` exits 0 and `pumpgrok run --mode paper --once --replay /app/tests/fixtures/replay/smoke` exits 0 from the repo root.
- Open items for the orchestrator:
  - Reconcile `docs/design/interfaces.md:191` with the span-level ledger `correlation_id`.
  - Run the formatter/lint pass once after the wave (see Issues Encountered).
  - Decide whether `LiveWriteAttempted.source=manual` is the intended value.
- **Plan 01-07 review item, restated:** write-tool gating (g6 + approval_id + rollback_plan) now applies to every `kind: write` tool, including non-trade writes. Kept as written; not changed here.

## Verification (run on the committed tree)

- `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exit 0; count query prints `1`; re-run exit 0, count still `1`.
- `uv run pumpgrok doctor` exit 0; absent engine, tools, gateway, supervisor and reports reported `warn ... not-yet-implemented`.
- `uv run pumpgrok run --mode live --once` exit 3; `[ ] 2` through `[ ] 9` listed; no ledger created.
- `uv run pytest -q tests/test_logging.py::test_log_redaction tests/test_correlation.py::test_correlation_id_chain` exit 0.
- `uv run pytest -q tests/test_logging.py tests/test_correlation.py tests/test_skip_cycle.py` exit 0 (plus `tests/test_live_gate.py`).
- `uv run pytest -q` full suite exit 0 (includes `tests/safety/test_static_guards.py` and `tests/test_tools_cli.py`).
- `grep -rniE "sign|send|keypair" src/pumpgrok/execution/live/` matches only prose ("design", "transaction" in docstrings); no signing, send or Keypair symbol.

## Self-Check: PASSED

---
*Phase: 01-foundation*
*Completed: 2026-10-21*

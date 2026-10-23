# Phase 5: Hardening - Pattern Map

**Mapped:** 2026-10-22
**Inputs:** `05-CONTEXT.md` (Locked, Claude's Discretion, Source conflicts, Recorded decisions D1-D11, dependency gate) and `05-RESEARCH.md`.
**Method:** every analog below was read this session with `read`/`grep`; every analog path cited was checked with `git ls-files` and is tracked; the only exception is `vendor/` (retired in `ea06b2b`, see section 0.1), which is cited as history only. No tests, lint, builds or network calls were run.
**Line references** are to the current working tree.

---

## 0. Corrections to the inputs (read first)

These override statements in `05-CONTEXT.md` or `05-RESEARCH.md` where they conflict with the tree.

1. **`vendor/` is gone.** Commit `ea06b2b` (STRUCT-006, Phase 4) retired `vendor/grokbot-pumpfun`. `vendor/grokbot-pumpfun/src/ops.py:298-357` (cited by CONTEXT and RESEARCH) does not exist in the tree, and `git ls-files vendor` is empty. The in-repo analog is `src/pumpgrok/supervisor/health.py` (`HealthServer`). Historical source, if ever needed: `git show ea06b2b^:vendor/grokbot-pumpfun/src/ops.py`.
2. **RESEARCH Pitfall 22 is partly wrong.** `src/pumpgrok/risk/limits.py` exists and is tracked (it defines `EngineLimits`, line 15). `RiskBudget` is defined in `src/pumpgrok/core/risk_budget.py:15`, not in `risk/limits.py`. The RISK fix is therefore: `docs/RISK_POLICY.md:7` and `:39` should point to `src/pumpgrok/core/risk_budget.py`.
3. **AGENTS.md insertion point.** CONTEXT says "after its last GSD block (AGENTS.md:298)". Line 298 is inside the `GSD:stack-start` block (lines 99-361). The last GSD marker is `<!-- GSD:profile-end -->` at **line 405**, which is also EOF. `## Rules index` goes after line 405.
4. **Live overlays already satisfy the static criterion.** `[live] enabled = false` is present in `dev.toml:23-24`, `paper.toml:22-23` and `live.toml:25-26`. No overlay edit is needed. The gate still does not read `enabled` (`live_gate.py:67-85` reads only mode and env).
5. **`run` refuses everything except `--once --replay`.** `cli.py:534-539` prints "not implemented" for any other form. A long-running path does not exist (see D1).
6. **Directories that do not exist yet:** `tests/docs/`, `tests/degradation/`, `tests/soak/`, `tests/fixtures/secrets/`, `tests/fixtures/llm/`, `tests/fixtures/http/adversarial/`, `tests/fixtures/replay/soak-3d/`, `src/pumpgrok/supervisor/metrics.py`, `src/pumpgrok/logging/spans.py`, `scripts/build_soak_fixture.py`. `tests/config/` and `tests/supervisor/` exist.
7. **INV-R-20 owning test is "new".** `tests/ledger/test_ledger_unwritable.py` does not exist (`tests/ledger/` holds only `test_events.py`, `test_fold_full_window.py`, `test_store.py`, `test_store_batch.py`). Nothing is "moved". The closest existing test is `tests/supervisor/test_degraded.py:86`.
8. **`FixtureClock.jump` does not exist.** `src/pumpgrok/replay/clock.py` `FixtureClock` (line 79) has `now` (92), `advance_to` (101), `sleep` and `timeout` (142). INV-R-22 `test_clock_skew.py` must use `advance_to` to an earlier stamp, or add a test-only method. Decide before writing.
9. **Census is non-empty.** Root `tools/` cannot be deleted yet. See section 2.14 for the full file list.
10. **`requests` has no importers** (`rg` over `src tests ci scripts` returns nothing), so the dev dependency `pyproject.toml:36` can go with the `tools/` deletion. **`prometheus` appears nowhere** in `src tests ci pyproject.toml uv.lock`.
11. **`.python-version` is tracked and not in `.dockerignore`**, so `COPY .python-version` is safe (RESEARCH Pitfall 3 confirmed).

---

## 1. File Classification

Key: **E** exact (same role and flow, same conventions); **R** role-match (same role, different content); **N** no analog. "(mod)" = existing file to change, "(new)" = file to create.

### 1a. Source (`src/pumpgrok/`, `scripts/`)

| # | File | Role | Data flow | Closest tracked analog | M |
|---|------|------|-----------|------------------------|---|
| S1 | `logging/spans.py` (new) | context-manager utility | timing, event-driven | `core/ids.py:115` `bind_correlation`; `logging/json.py:36` `bind_seat` | R |
| S2 | `supervisor/metrics.py` (new) | metrics holder, scrape-time snapshot | pull | `supervisor/health.py:34` `build_status` (snapshot dict); `supervisor/health.py:90` `HealthServer` (callable injection) | R |
| S3 | `supervisor/health.py` (mod) | HTTP route, add `/metrics` | request-response | itself, `health.py:120` `_handle`, `:147` `_respond` | E |
| S4 | `supervisor/seat_task.py` (mod) | seat wrapper: cycle histogram, crash counter | event-driven | itself, `seat_task.py:310` `run_guarded`; `:362` `_append_exit_halt` | E |
| S5 | `supervisor/scheduler.py` (mod) | orchestrator: serve loop, health_status, rollover, read-only assert | event loop | itself, `scheduler.py:298-397`, `:497` `run_once_replay` | E |
| S6 | `core/registry.py` (mod) | tool-call wrapper: span per call | request-response | itself, `registry.py:231` `_wrap`, `:243-270` `_Guarded` | E |
| S7 | `cli.py` (mod) | CLI dispatch: `run --serve`, runbook verbs | request-response | itself, `cli.py:367` `_add_run`, `:525` `_run`, `:1235` `_dispatch` | E |
| S8 | `config/settings.py` (mod) | settings model: health port | config | `settings.py:240` `ReplaySettings`, `:164` `OpsSettings` | E |
| S9 | `execution/live/live_gate.py` (mod) | gate evaluator: precondition 1 reads `[live] enabled` (D4 ids) | request-response | itself, `:32` `PRECONDITION_IDS`, `:67-85` rows | E |
| S10 | `doctor.py` (mod) | diagnostics: probe `/healthz` and `/metrics` | request-response | itself, `:16` `SUBSYSTEMS`, `:43` `subsystem_statuses` | R |
| S11 | `logging/__init__.py` (mod) | exports (add `span`) | - | itself, `__all__` block | E |
| S12 | `supervisor/__init__.py` (mod) | exports (add metrics) | - | itself, `:16-36` re-exports | E |
| S13 | DailyRollover emitter (in `scheduler.py` or `seat_task.py`) | ledger writer, day-keyed idempotent | batch, event-driven | `risk/engine.py:175` `halt_key`; `supervisor/seat_task.py:80` `append_escalation`; schema `ledger/events.py:248` `DailyRollover` | R |
| S14 | Census docstring edits: `ledger/desk_bus.py`, `ledger/export.py`, `tools/onchain/authorities.py`, `tools/onchain/holders.py`, `tools/onchain/priority_fee.py` | docstrings | - | themselves | E |
| S15 | `scripts/build_soak_fixture.py` (new) | generator script | transform, file-I/O | `tests/fixtures/replay/smoke-10m/generator.py` (`main`, `_lines`, manifest write) | E |

### 1b. Tests and fixtures

| # | File | Role | Data flow | Closest tracked analog | M |
|---|------|------|-----------|------------------------|---|
| T1 | `tests/degradation/test_llm_failure.py` (new) | fault test | fault-injected | `tests/supervisor/test_degraded.py:47` `test_llm_down_falls_back...`; `:59` replay missing record | R |
| T2 | `tests/degradation/test_rpc_failure.py` (new) | fault test | fault-injected | `tests/supervisor/test_degraded.py:65` `test_rpc_failover_then_blind...` | R |
| T3 | `tests/degradation/test_data_source_outage.py` (new) | fault test (WS and REST) | fault-injected | `tests/supervisor/test_degraded.py:76` `test_ws_silence_trips_data_stale...` | R |
| T4 | `tests/degradation/test_ledger_unwritable.py` (new) | fault test | fault-injected | `tests/supervisor/test_degraded.py:86` `test_unwritable_ledger_buffers_1000...` | E |
| T5 | `tests/degradation/test_clock_skew.py` (new) | fault test | fault-injected | `tests/supervisor/test_degraded.py:117` `test_clock_skew_refuses_appends...` | E |
| T6 | `tests/degradation/test_partial_restart.py` (new) | fault test | fault-injected | `tests/supervisor/test_restarts.py:124` `test_heartbeat_stale...`; `_store`/`_ctx` helpers | R |
| T7 | `tests/soak/test_soak_multiday_replay.py` (new) | soak test (marker `slow`) | batch replay | `tests/replay/test_runner_determinism.py:38`; `tests/supervisor/test_degraded.py:152` ten-seat cycle | R |
| T8 | `tests/supervisor/test_metrics.py` (new) | unit (exposition, nine names) | pull | `tests/supervisor/test_degraded.py` (fixtures, `_store`) | R |
| T9 | `tests/supervisor/test_spans.py` or extension of `tests/test_logging.py` (new/mod) | unit (span event shape, redaction) | event | `tests/test_logging.py` (`root_handlers` fixture, `_lines`) | E |
| T10 | `tests/config/test_health_port_defaults.py` (new, INV-C-11) | config unit | config | `tests/config/test_settings.py` | R |
| T11 | `tests/docs/test_runbook_commands.py` (new) | static doc test | static text | `ci/tests/test_security_workflows.py` (`REPO_ROOT`, `_load_yaml`, `_run_blocks`) | R |
| T12 | `tests/docs/test_changelog_phases.py` (new) | static doc test | static text | `ci/tests/test_security_workflows.py` pattern | R |
| T13 | `ci/tests/test_gates.py::test_invariant_matrix_tests_exist` (mod) | meta-test (parses SAFETY_INVARIANTS section 6, runs `pytest --co`) | static + collect | `ci/tests/test_gates.py:41` `_load`; `:967` AST import check | E |
| T14 | `tests/execution/test_live_gate_fails_fast.py` (mod) | gate test, parametrise nine preconditions | request-response | itself, `:54` `test_live_run_exits_3_with_nine_ordered_lines` | E |
| T15 | `tests/safety/test_no_manipulation_tools.py` (mod) | RISK-007 scan | static AST | itself, `:26` `SOCIAL`, `:30` `_SC4`, `:33` `_STEMS` | E |
| T16 | `tests/safety/test_static_guards.py` (mod) | AST guard (prometheus only in supervisor; span clock) | static AST | itself, `:18` `SRC`, `:21` `CLOCK_ALLOWLIST`, `:25` `_CLOCK_PRIMITIVES`, `:78` `_scan_file` | E |
| T17 | `tests/test_tools_cli.py` (mod) | remove root-oracle classes | CLI | itself (`:35` `TOOLS`, `:38` `load_tool`); replacement pattern `tests/tools/test_verb_coverage.py` | E |
| T18 | `tests/characterization/test_{authority_check,holder_check,jupiter_quote,priority_fee,vendor_log}.py` (mod) | docstrings name root `tools/` | - | themselves | E |
| T19 | `tests/harness/faults.py` (mod) | fault injector (add LLM, RPC, data source, price source, ledger store fakes) | injection | itself, `:42` `FaultInjector`, `:70` `apply`, `:91` `open_sink` | R |
| T20 | `tests/harness/__init__.py` (mod) | harness exports | - | itself (exports `NetworkBlocked`) | E |
| T21 | `tests/fixtures/replay/soak-3d/{events.jsonl,llm.jsonl,manifest.json}` (new) | replay fixture | - | `tests/fixtures/replay/smoke-10m/` | E |
| T22 | `tests/fixtures/llm/*.json`, `tests/fixtures/http/adversarial/*.json` (new) | fixtures | - | `tests/fixtures/http/xai_chat.json`, `holders.json` | E |
| T23 | `tests/fixtures/secrets/*.txt` (new) | planted secrets | - | `tests/test_logging.py` (`PLANTED_*` with `pragma: allowlist secret`) | R |

### 1c. Docs, runbooks, policy

| # | File | Role | Data flow | Closest tracked analog | M |
|---|------|------|-----------|------------------------|---|
| D1 | `docs/runbooks/setup.md` (rewrite) | runbook | - | itself (sections: Quick start, What setup creates, Rules, References) | E |
| D2 | `docs/runbooks/{engine,start_stop,kill_switch,breaker_reset,outage,rollback,reading_reports,go_live}.md` (8 new) | runbook | - | `docs/runbooks/setup.md` | E |
| D3 | `docs/SAFETY_INVARIANTS.md` (mod) | invariant matrix | - | itself, rows INV-C-11 (`:65`), INV-R-20 (`:105`, `:292`), INV-R-22 (`:107`) | E |
| D4 | `docs/design/paper-engine.md` (mod: R21, INV-C-11 amendments) | design | - | itself (not opened for this map) | R |
| D5 | `docs/RISK_POLICY.md` (mod) | policy | - | itself, section 4 (`:144`, `:146`, `:162`, `:170`) | E |
| D6 | `docs/upgrade-plan-desk-v2.md` (mod: 6.6 report) | plan | - | itself (not opened for this map) | R |
| D7 | `CHANGELOG.md` (mod) | changelog | - | itself, heading `:5`, sections `:7`, `:33`, `:41` | E |
| D8 | `AGENTS.md` (mod: `## Rules index` after line 405) | agent index | - | itself, hand-written sections `:7`, `:23`, `:38`, `:47`, `:53`, `:58` | R |
| D9 | `SECURITY.md` (mod: exceptions table) | security policy | - | itself (sections Posture, Key custody, Secrets handling, Container, Untrusted content); no table exists | N (table) |
| D10 | `.receipts/bot-00-chief/complete-phase-5.json` (new receipt) | receipt | - | `.receipts/bot-00-chief/.gitkeep`; `.gitignore` receipt rule | R |

### 1d. Infrastructure and CI

| # | File | Role | Data flow | Closest tracked analog | M |
|---|------|------|-----------|------------------------|---|
| I1 | `Dockerfile` (mod) | container build | build | itself, `:4-5`, `:11-12`, `:15-21`, `:28-29` (HEALTHCHECK), `:34` (CMD) | E |
| I2 | `docker-compose.yml` (mod) | compose service | - | itself (header comment forbids restart policy) | E |
| I3 | `.dockerignore` (verify only) | build context | - | itself | E |
| I4 | `.gitignore` (mod: receipt exception) | ignore rules | - | itself, `.receipts/**/*.json` and `!.receipts/**/.gitkeep` | E |
| I5 | `pyproject.toml` (mod) | deps, markers | - | itself, `:35-36` (`requests`), `:90-93` (addopts, markers) | E |
| I6 | `uv.lock` (regenerate under uv 0.13.4) | lockfile | - | itself | E |
| I7 | `Makefile` (verify; probably no change) | task runner | - | itself, `:25` `test`, `:28` `audit`, `:51` `check` | E |
| I8 | `.github/workflows/security-pr.yml` (mod) | CI, scanners | event | `.github/workflows/gates.yml` `on:` block (pull_request + push to main); itself `:16-18` | E |
| I9 | `.github/workflows/ci.yml` (mod: nightly `schedule:`) | CI | event | itself `:8-13` triggers, `:35` `make lint typecheck test audit` | E |
| I10 | `ci/tests/test_security_workflows.py` (mod) | workflow guard | static YAML | itself, `:27` `WORKFLOW_FILES`, `:31` `BYPASS_SNIPPETS`, `TestGatesWorkflow` | E |
| I11 | `ci/security/gitleaks.toml` (mod if fixtures need path allowlist) | scanner config | - | itself, `[allowlist]` block | E |
| I12 | `ci/gates/check_secrets.py` (no edit; behaviour constraint) | G-3 gate | static | itself, `:25` `ALLOWLIST_MARKER`, `:97` `SKIP_DIRS` | E |
| I13 | `ownership.yaml` (no edit expected) | owner manifest | - | itself | E |

### 1e. Census-driven edits (root `tools/` deletion)

| # | File | Owner (ownership.yaml) | Reference to change |
|---|------|------------------------|---------------------|
| X1 | `tools/` (8 `.py` modules, `README.md`, `__pycache__/`) | bot-02-risk (`:330`) | delete |
| X2 | `skills/{desk-strategy-lab,desk-trade-lifecycle,discovery-tools,grokbot-pipeline,hermes-cron-desk,holder-and-flow-analysis,risk-audit}/SKILL.md`, `skills/README.md` | bot-02-risk (`:208`) | `tools/*.py` paths in text |
| X3 | `rules/pumpgrok-team.mdc:42` | bot-02-risk (`:196`) | `tools/pipeline_evidence.py` |
| X4 | `prompts/bot-01-scout.xml` (source) then regenerate `prompts-assembled/SCOUT.xml` and `agents/scout.md` | prompts bot-02-risk; agents bot-00-chief | `tools/pipeline_evidence.py` |
| X5 | `agents/README.md` | bot-00-chief (`:194`) | text |
| X6 | `hermes/README.md` (`:19-20`, `:93`, `:104`, `:144`) | bot-00-chief (`:204`) | text |
| X7 | `scripts/hermes-verify-isolation.sh` (`:34`, `:41`, `:107`) | bot-00-chief (`scripts/**`, `:200-201`) | `tools/desk_state.py` checks |
| X8 | `scripts/hermes-bootstrap.sh:232` | bot-00-chief (`scripts/**`, `:200-201`) | `${ROOT}/tools/desk_state.py` |
| X9 | `SETUP.md` (`:131-132`, `:152`) | bot-00-chief (`:88`) | `tools/*.py` commands |
| X10 | `README.md`, `ARCHITECTURE.md` | bot-00-chief (`:78`), bot-02-risk (`:82`) | text |
| X11 | `tests/test_tools_cli.py`, `tests/characterization/*` (see T17, T18) | bot-02-risk (`tests/**`, `:336`) | oracle use |
| X12 | `src/pumpgrok/ledger/desk_bus.py`, `ledger/export.py`, `tools/onchain/{authorities,holders,priority_fee}.py` (see S14) | bot-02-risk | docstrings |
| X13 | `AGENTS.md` lines 286 and 359 (inside GSD stack block 99-361) | bot-02-risk | **do not hand-edit** (CONTEXT: GSD markers); D3(b) in RESEARCH needs user sign-off |
| X14 | `.planning/**` historical hits | - | excluded by D3(a) |

---

## 2. Pattern Assignments

Excerpts are copied from the tree. Paths are relative to the repo root.

### 2.1 S1 `logging/spans.py` (new): `span(name, **fields)`

**Analogs:** `src/pumpgrok/core/ids.py:96-150` (contextvar-bound context managers) and `src/pumpgrok/logging/json.py:26-42` (seat binding).

```python
# src/pumpgrok/logging/json.py:26-42 (verbatim, abridged)
SEAT: ContextVar[str | None] = ContextVar("pumpgrok_seat", default=None)
TICKET: ContextVar[str | None] = ContextVar("pumpgrok_ticket", default=None)
PROMOTED_FIELDS = frozenset({"event", "correlation_id", "seat", "ticket_id", "mint", "duration_ms"})


@contextmanager
def bind_seat(seat: str) -> Iterator[None]:
    token = SEAT.set(seat)
    try:
        yield
    finally:
        SEAT.reset(token)
```

- Use the same `ContextVar` + token/reset pattern for the parent span and counter. Parent and counter are contextvars, per CONTEXT.
- Emit with the existing `extra` mechanism. `JsonFormatter.format` (`json.py:73-115`) promotes `event` and `duration_ms` (`PROMOTED_FIELDS`, line 30) and adds `duration_ms` when `hasattr(record, "duration_ms")`. Shape: `log.info("span", extra={"event": "span", "duration_ms": ms, "span": name, ...})`. The `replay/runner.py` `log.info("replay engine cycle complete", extra={"event": "cycle_end", ...})` is the in-repo precedent.
- Redaction is handled by the handler (`json.py` `setup_logging` adds `RedactionFilter`, class at `logging/redaction.py:83`). Span fields must not bypass it.
- **Clock gap (design, must decide):** `span(name, **fields)` takes no clock, and duration must come from the injected `Clock.now()` (INV-S-13). `ToolRegistry` already holds `self._clock` (`registry.py:88-101`). Options: (a) a contextvar bound by the registry or supervisor, mirroring `bind_correlation`; (b) an explicit keyword-only `clock=` that the registry passes. Option (b) breaks the locked signature, so (a) is the lower-risk reading. Record the choice in the plan.
- `time.*` and `asyncio.sleep` are banned in `src/pumpgrok` outside `replay/clock.py` (`tests/safety/test_static_guards.py:21`, `:25`). Do not use `time.perf_counter` for spans.
- Export via `logging/__init__.py` `__all__` (S11).

### 2.2 S6 `core/registry.py`: span every tool call

```python
# src/pumpgrok/core/registry.py:243-270 (verbatim, abridged)
class _Guarded:
    def __init__(self) -> None:
        self.spec = spec

    async def __call__(self, payload: ToolInput, /) -> ToolOutput:
        cid = next_span(current_correlation())
        with bind_correlation(cid), bind_calling_seat(bot.id):
            if spec.requires_approval:
                ...
            async with clock.timeout(spec.timeout_s):
                if policy.attempts <= 1:
                    await limiter.acquire()
                    return await t(payload)
                ...
```

- Insert the span around the `with bind_correlation(cid), bind_calling_seat(bot.id):` block (or as a third item in that `with`), so the span carries `cid` and `bot.id`. The span should cover the `clock.timeout` and any tenacity retry, so the duration includes retries.
- `_wrap` closes over `clock = self._clock` (`registry.py:231-241`). Use that local. Do not add a new clock source.
- `ToolRegistry` has no metrics dependency. Keep it that way (only the supervisor writes metrics).

### 2.3 S2 `supervisor/metrics.py` (new) and S3 `/metrics` route

**Analogs:** `supervisor/health.py:34-73` (`build_status`, the snapshot dict) and `supervisor/health.py:90-101` (`HealthServer` injects `get_status` and `is_ready` callables).

```python
# src/pumpgrok/supervisor/health.py:90-101 (verbatim)
class HealthServer:
    """Minimal asyncio HTTP server for /healthz and /readyz."""

    def __init__(
        self,
        clock: Clock,
        get_status: Callable[[], Mapping[str, Any]],
        is_ready: Callable[[], bool],
    ) -> None:
        self._clock = clock
        self._get_status = get_status
        self._is_ready = is_ready
        self._server: asyncio.AbstractServer | None = None
```

**Design to copy:** `build_registry()` (fresh `CollectorRegistry`, no global default) plus a snapshot callable passed in by the supervisor, exactly as `HealthServer` receives `get_status`. Gauges that are state snapshots are computed at scrape time by calling that callable. `core/` and `risk/` never import `prometheus_client` (enforce with T16).

**Route change (S3)** in `health.py:120-145` `_handle`: add `if path == "/metrics":` before the default branch. `_path_of` (`:138`) already parses the request line.

```python
# src/pumpgrok/supervisor/health.py:147-155 (verbatim, abridged)
@staticmethod
def _respond(writer: asyncio.StreamWriter, code: int, body: Mapping[str, Any]) -> None:
    payload = json.dumps(dict(body)).encode("utf-8")
    head = (
        f"HTTP/1.1 {code} {_reason(code)}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("latin-1")
    writer.write(head + payload)
```

- `_respond` is JSON-only and takes a `Mapping`. `/metrics` needs a bytes body with a text exposition content type. Add a sibling `_respond_bytes(writer, code, payload: bytes, content_type: str)` or give `_respond` a `content_type` parameter. Do not `json.dumps` the exposition.
- Content type: `prometheus_client` exposes `CONTENT_TYPE_LATEST` [ASSUMED name; verify after the `uv add` checkpoint].
- Port and bind: `start(host="127.0.0.1", port=0)` (`health.py:104`). `PUMPGROK_HEALTH_PORT` is not in `settings.py` (no health field anywhere). Add it through a settings model (S8).
- Deadlines: `clock.timeout` only (`HealthServer` already takes `clock`).

**Source of each of the nine families (verified attribute names):**

| Family | Source at scrape or event time | Notes |
|--------|-------------------------------|-------|
| `pumpgrok_cycle_seconds{seat}` (histogram) | observe `SeatTask.last_duration_s` in `seat_task.py:310-340` `run_guarded` after `finished - started` (virtual) | observe in the same place `cycles += 1` happens |
| `pumpgrok_bot_crashes_total{seat}` | `SeatTask.crashes` (incremented in `run_guarded` on `outcome == "crash"`) | counter; supervisor must track its own last-seen value or count at the event |
| `pumpgrok_orders_total{side,outcome}` | **no emitter located** | candidates: ledger events via `LedgerStore.read` (`ledger/store.py:352`), or the paper adapter (`execution/paper_adapter.py`, not opened). [INFERENCE] needs a decision |
| `pumpgrok_equity_sol` | `equity_lamports / 1e9` at scrape (R28) | `Supervisor.health_status()` currently passes **no** equity (see 5.1) |
| `pumpgrok_drawdown_pct` | `drawdown_pct` in `build_status` | currently defaulted to 0.0 by `health_status()` (see 5.1) |
| `pumpgrok_data_age_seconds{source}` | `data_age_s` in `build_status` is one scalar; `DegradedState.ws_last_frame_at` (`scheduler.py:104`, `:152`) gives the WS age | per-source label needs a REST source too; not tracked today |
| `pumpgrok_breaker_state{breaker}` | `Breaker.state` returns `"open"` / `"half-open"` / `"closed"` (`risk/breakers.py:119-123`); map to 2 / 1 / 0 | `BreakerSet` at `breakers.py:323` |
| `pumpgrok_kill_switch` | `KillSwitch.poll()` returns `KillState` (`risk/killswitch.py:142`, class `:78`) | `health_status()` hard-codes `kill_switch=False` (see 5.1) |
| `pumpgrok_ledger_seq` | `LedgerStore.count()` (`ledger/store.py:347`) or the latest `seq` via `read` | `build_status` already takes `ledger_seq` |

### 2.4 S4 `supervisor/seat_task.py`: cycle histogram and crash counter

```python
# src/pumpgrok/supervisor/seat_task.py:310-340 (verbatim, abridged)
async def run_guarded(self, ctx: SeatContext) -> str:
    started = self._clock.now()
    self.last_started_at = started
    outcome = "ok"
    try:
        async with self._clock.timeout(self.timeout_s):
            await self._cycle(ctx)
    except TimeoutError:
        outcome = "crash"
        log.warning("seat %s cycle timed out after %.0fs", self.seat_id, self.timeout_s)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        outcome = "crash"
        log.warning("seat %s cycle crashed: %s", self.seat_id, exc)
    finished = self._clock.now()
    self.last_finished_at = finished
    self.last_duration_s = max(0.0, finished - started)
    self.last_ok = outcome == "ok"
    self.cycles += 1
    if outcome == "ok":
        self._stale_raised = False
    else:
        self.crashes += 1
        await self._on_crash(ctx)
    return outcome
```

- `last_duration_s` is already the virtual cycle duration the histogram needs (CONTEXT: "virtual seconds, from `seat_task.py`"). Record there, after `self.last_duration_s = ...`.
- `SeatTask` has no metrics dependency today; pass an optional observer callable through the constructor (`SeatTask.__init__` at `:255`) so `seat_task.py` does not import `prometheus_client`. This matches "only the supervisor writes metrics".
- The span for each seat cycle (if wanted) wraps `run_guarded`. Span uses the seat `ctx.seat_id`.

### 2.5 S13 DailyRollover emitter (D6: one per UTC day, including the first)

**Schema:** `ledger/events.py:248-254`

```python
class DailyRollover(_ClosedModel):
    """UTC day boundary totals (RiskEngine)."""

    source: EventSource
    day_utc: str
    day_start_equity_lamports: MoneyInt
    prior_day_json: str = ""
    open_positions: list[str] = []
```

**Reducer:** `ledger/reducer.py:349-360` `_on_rollover` resets `counters` and sets `day_utc`. Registered at `:391`.

**Idempotency pattern to copy:** `risk/engine.py:175-177`

```python
def halt_key(reason: str, day_utc: str) -> str:
    """Idempotency per (reason, utc_day): one ``HaltSet`` per reason per day."""
    return hashlib.sha256(f"HaltSet|{reason}|{day_utc}".encode()).hexdigest()
```

A `rollover_key(day_utc)` with the same shape gives one row per day. `utc_day(now_s)` (`risk/engine.py:180`) gives the day.

**Append pattern to copy:** `supervisor/seat_task.py:362-383` `_append_exit_halt` (`ts_utc = format_ts_utc(self._clock.now())`, `self._store.append(ts_utc=..., source=..., correlation_id=..., idempotency_key=..., type="HaltSet", payload={...})`, wrapped in try/except with `log.warning`). Copy the shape for `type="DailyRollover"`.

**Where to emit:** `scheduler.py:328` `_end_of_tick` runs every tick and already gates the health write on a virtual interval (`:339-346`). Emit from there when `utc_day(now)` changes, plus once for the first day seen. Alternative: the soak driver emits explicitly. Decide in the plan.

**Constraint:** `run_once_replay` (`scheduler.py:497`) asserts seat cycles are read-only (`if after != before: raise RuntimeError(...)`). A DailyRollover emitted inside a seat cycle or `_end_of_tick` breaks that assertion. See 5.5.

### 2.6 S5 `supervisor/scheduler.py` and D1 serve mode

**Loop pattern:**

```python
# src/pumpgrok/supervisor/scheduler.py:298-312, 391-397 (verbatim, abridged)
async def tick_once(self) -> dict[str, str]:
    """Start every due seat in roster order; returns seat -> outcome."""
    outcomes: dict[str, str] = {}
    for seat in ROSTER:
        task = self.tasks[seat]
        if not task.is_due(self._clock.now()):
            continue
        child = asyncio.ensure_future(task.run_guarded(self._seat_context(seat)))
        ...


async def serve_forever(self) -> int:
    """Tick until stop; shutdown owns snapshot/export/health instead."""
    while not self._stop.is_set():
        await self.tick_once()
        await self._clock.sleep(TICK_S)
    return 0
```

- `serve_forever` already exists (`:391`) and is not wired to the CLI. `lifecycle.install_signal_handlers` (`lifecycle.py:40`) and `shutdown` (`lifecycle.py:99`, grace `SHUTDOWN_GRACE_S = 30.0` at `:37`) exist and are unused by the CLI.
- `HealthServer(clock, get_status, is_ready)` (`health.py:90`) is ready to be passed `supervisor.health_status` and `supervisor.ready`.
- `Supervisor.ready()` (`:383`) is the `/readyz` contract.
- D1 wants a long-running `run --mode paper --serve` that replays a recorded dataset in a loop. `run_replay` recreates the ledger on every call (`recreate_ledger_db`, `replay/runner.py` inside `run_replay`), so a loop must either (a) reuse one ledger and skip recreation, or (b) reset per iteration and accept that the ledger restarts. Decide before writing; (b) is simpler and matches "replays a recorded dataset in a loop".

### 2.7 S7 `cli.py`: `run --serve`

```python
# src/pumpgrok/cli.py:367-377 (verbatim)
def _add_run(verbs: _VerbsAction, mode_option: _Parser) -> None:
    run = verbs.add_parser("run", parents=[mode_option], help="run the desk")
    run.add_argument("--once", action="store_true", help="run a single cycle and exit")
    run.add_argument("--replay", metavar="DIR", default=None, help="recorded fixture directory")
    run.add_argument(
        "--record", metavar="DATASET", default=None, help="record a dataset (not yet implemented)"
    )
    run.add_argument(
        "--duration", metavar="SECONDS", default=None, type=int, help="record duration (R40)"
    )
```

```python
# src/pumpgrok/cli.py:525-540 (verbatim)
def _run(args: argparse.Namespace, settings: Settings) -> int:
    gate = LiveGate(mode=settings.effective_mode, environ=os.environ, root=Path.cwd())
    if settings.effective_mode == "live":
        preconditions = gate.evaluate()
        if any(not item.met for item in preconditions):
            _say(sys.stderr, *refusal_lines(preconditions))
            return EXIT_LIVE
    if args.record is not None or args.duration is not None:
        return _not_implemented("run --record")
    if not (args.once and args.replay):
        _say(
            sys.stderr,
            "not implemented: this release runs only `run --mode paper --once --replay <dir>`",
        )
        return EXIT_NOT_IMPLEMENTED
    return _skip_cycle(Path(args.replay), settings)
```

- Add `--serve` (store_true) in `_add_run` and a branch in `_run` after the live-gate block. Keep the live-gate block first (live mode must still exit 3, `test_live_run_exits_3_with_nine_ordered_lines`).
- Restart policy `unless-stopped` only with `--serve` (D9). Compose does not change `--once` behaviour.
- Killswitch verbs for runbooks: `killswitch set --reason` and `killswitch flatten --reason` (`cli.py:456-463`, per RESEARCH). There is no `--flatten` flag (D5).
- Doctor: `_doctor_verb` at `cli.py:1017`; `doctor.py:16-29` `SUBSYSTEMS` (module-presence only). Discretion says `pumpgrok doctor` probes `/healthz` and `/metrics`. Add a probe in `doctor.py` next to `subsystem_statuses` (`:43`), using stdlib `urllib.request` (no `curl` in slim images, per RESEARCH Pitfall 4).

### 2.8 S8 `config/settings.py`: health port and `live.enabled`

```python
# src/pumpgrok/config/settings.py:240-248 (verbatim)
class ReplaySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int = 20260101


class LiveSettings(BaseModel):
    """Marker only: enabling live requires the live gate (separate module)."""
```

- Add `HealthSettings` with `model_config = ConfigDict(frozen=True, extra="forbid")` and `port: int = 0` (container sets 8080 via env, per INV-C-11 and D1). The `OpsSettings` class (`:164`) is the other precedent for a small section.
- `PUMPGROK_*` env names are whitelisted by the startup guards (`collect_startup_problems`, `:441`). A new field needs its env name accepted. Check `allowed_env_names()` (called at `:454`) before adding `PUMPGROK_HEALTH_PORT`.
- `LiveSettings` gains `enabled: bool = False`, with `extra="forbid"` so an unknown key fails. The overlays already set it (section 0.4).

### 2.9 S9 `execution/live/live_gate.py`: precondition 1 reads `[live] enabled` (D4)

```python
# src/pumpgrok/execution/live/live_gate.py:32-41 (verbatim)
PRECONDITION_IDS: tuple[str, ...] = (
    "mode_live",
    "live_enable_env",
    "min_paper_days",
    "performance_thresholds",
    "wallet_allowlist",
    "notional_cap",
    "confirmation_record",
    "adapter_registered",
    "no_active_stop",
)
```

```python
# src/pumpgrok/execution/live/live_gate.py:67-85 (verbatim, abridged)
rows: tuple[tuple[bool, str], ...] = (
    (mode_live, mode_reason),
    (env_enabled, "PUMPGROK_LIVE_ENABLE=1" if env_enabled else "PUMPGROK_LIVE_ENABLE is not 1"),
    (days_met, days_reason),
    (perf_met, perf_reason),
    (False, "live.wallet_allowlist is not a setting in this release"),
    (False, "live.notional_cap_sol is not a setting in this release"),
    (False, "var/live_confirmation.json missing" if not confirmation.exists() else "..."),
    (False, "no live adapter implementation ships in this release"),
    (False, "halt, kill switch and breaker state are not readable in this release"),
)
```

- Rows 5-9 are hard-coded `False`. No input can make them true, so an input-driven test cannot show "fails only on that line". Use the approach in RESEARCH Pitfall 14: monkeypatch `LiveGate.evaluate` to return all rows met except the target, then assert exit 3 and exactly that id as `[ ]`.
- Precondition 1 (`mode_live`) should require effective mode live AND `[live] enabled = true` (D4, R21 amendment). Keep the id as in code.
- The matrix INV-C-02 (`docs/SAFETY_INVARIANTS.md`) uses different ids. Update the matrix to the code ids (D4).

### 2.10 T14 `tests/execution/test_live_gate_fails_fast.py`: nine preconditions

```python
# tests/execution/test_live_gate_fails_fast.py:54-60 (verbatim, abridged)
def test_live_run_exits_3_with_nine_ordered_lines(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PUMPGROK_LIVE_ENABLE", raising=False)
    code = main(["run", "--mode", "live", "--once"])
    assert code == 3
    err = capsys.readouterr().err
    assert err.startswith("LIVE GATE: refusing to start in mode=live. 8 of 9")
```

- Add `@pytest.mark.parametrize("target", PRECONDITION_IDS)` (import at the top of the file from `pumpgrok.execution.live`). Keep the aggregate header assertion.
- Existing `test_live_mode_with_paper_overlay_still_runs_gate` (`:70`) and `test_paper_mode_never_evaluates_gate` (`:79`) are the patterns for mode-specific cases.

### 2.11 Degradation suite (T1-T6, T19)

**Harness:** `tests/harness/faults.py`

```python
# tests/harness/faults.py:42-50, 70-74, 90-96 (verbatim, abridged)
class FaultInjector:
    """Apply one fault at `at_index` of an event stream, or to a write sink.
    ...
    """

    def __init__(
        self,
        mode: FaultMode,
        *,
        at_index: int = 0,
        stale_by_s: float = 3600.0,
        retry_after_s: float = 1.0,
    ) -> None: ...

    def apply(self, events: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for index, event in enumerate(events):
            if index != self._at:
                yield event
                continue
            ...

    @contextmanager
    def open_sink(self, path: Path) -> Iterator[IO[str]]:
        if self._mode is FaultMode.UNWRITABLE:
            raise PermissionError(errno.EACCES, "injected: sink is unwritable", str(path))
```

- Today `FaultInjector` only faults event streams and file sinks. It cannot fault an LLM client, RPC client, data source, price source, execution adapter or ledger store (RESEARCH Pattern 5). T19 adds fakes in the same style: a fault mode enum, an `InjectedFault` subclass, and a fault that fires at a call index. Keep `InjectedFault` as the marker class so product errors are never mistaken for injected ones (module docstring, `:1-6`).
- `TIMEOUT` raises builtin `TimeoutError`, the type product code must already handle (`faults.py` module docstring). Copy that rule.
- Test import pattern: `from harness.faults import FaultInjector, FaultMode, InjectedFault, InjectedRateLimit` (`tests/test_network_block.py:14`). `tests/harness/__init__.py` exports `NetworkBlocked`.

**Scenario analogs (`tests/supervisor/test_degraded.py`):**

```python
# tests/supervisor/test_degraded.py:38-44 (verbatim, abridged)
SMOKE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke"


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))
```

- `test_unwritable_ledger_buffers_1000_then_refuses_and_drains` (`:86`) is the INV-R-20 analog (`DegradedState(ledger_writable=False)`, `LEDGER_BUFFER_CAP = 1000`).
- `test_clock_skew_refuses_appends_with_escalation` (`:117`) is the INV-R-22 analog. It uses `FixtureClock(start=0.0)`; the backwards move needs `advance_to` or a new method (section 0.8).
- `test_rpc_failover_then_blind_with_recovery` (`:65`) and `test_ws_silence_trips_data_stale_and_frame_recovers` (`:76`) use `DegradedState` directly. The degradation suite must go through `FaultInjector`-style injection on the real code path (AUTO-008 wording), not only on `DegradedState`.
- INV-R-35 partial restart: `tests/supervisor/test_restarts.py` uses `_store(tmp_path)` and `_ctx(store, clock, seat)` (`:32` and `:38`; `_ctx` builds a `SeatContext` with `make_rng(11)`) and `SeatTask(...)` with `FixtureClock(start=...)`. `test_heartbeat_stale_emits_once_and_resume_clears_latch` (`:124`) is the closest multi-seat pattern.

**Clock and RNG helpers:** `FixtureClock(start=...)` (`replay/clock.py:79`), `make_rng(seed)` (`replay/rng.py`), `IdFactory(clock, make_rng())` (`core/ids.py:34`). Use them; never `time.*`.

### 2.12 T7 soak and D6 rollover (`tests/soak/test_soak_multiday_replay.py`)

**Analogs:**

```python
# tests/replay/test_runner_determinism.py:20, 38-42 (verbatim)
SMOKE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke"


def test_two_seeded_runs_produce_identical_hashes(tmp_path: Path) -> None:
    first = run_replay(SMOKE, FilterSettings(), ledger_path=tmp_path / "a.sqlite")
    ...
```

- `run_replay(dataset_dir, filter_cfg, *, seed, ledger_path)` (`replay/runner.py:95`) returns `ReplayResult` (`:53`) with `events_hash`. `ledger_events_hash` (`:82`) gives the determinism check.
- `run_once_replay` (`scheduler.py:497`) is the ten-seat variant. Its read-only assert conflicts with rollovers (5.5).
- `tests/supervisor/test_degraded.py:152` `test_ten_seat_smoke_cycle_writes_ledger_and_exits_0` is the ten-seat analog for the soak loop.
- `FixtureManifest` (`replay/fixtures.py:39-48`) and `verify_manifest` (`:123`) verify `sha256` digests before any line is trusted (INV-R-30). The soak fixture must pass through the same loader.
- Memory: `tracemalloc` (RESEARCH "Don't hand-roll": `tracemalloc` for growth, `getrusage` only reports peak). No in-repo precedent.
- Exception capture: `sys.excepthook` and the loop exception handler (CONTEXT). No in-repo test precedent. `lifecycle.install_signal_handlers` (`lifecycle.py:40`) is the only signal-handler precedent.
- Markers: register `slow` in `pyproject.toml` `[tool.pytest.ini_options] markers` (`:91-93`). `addopts` contains `--strict-markers` (`:90`), so an unregistered `slow` marker is a collection error.

**Fixture build (S15, `scripts/build_soak_fixture.py`):** analog `tests/fixtures/replay/smoke-10m/generator.py`:

```python
# tests/fixtures/replay/smoke-10m/generator.py (constants and writer, abridged)
DATASET = "smoke-10m"
BASE_EPOCH = 1767225600.0  # 2026-01-01T00:00:00Z
STEP_S = 15.0
COUNT = 41


def _lines(records: list[dict[str, Any]]) -> bytes:
    return ("".join(json.dumps(record) + "\n" for record in records)).encode("utf-8")


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    ...
    (out_dir / "manifest.json").write_bytes(manifest_bytes)
```

- Copy: deterministic labels (sha256 of a domain-separated label, `_derive_mint`), `_lines` JSONL writer, digest-carrying manifest with the same keys as `smoke-10m/manifest.json` (`dataset`, `recorded_from_utc`, `recorded_to_utc`, `seed_hint`, `sources`, `sha256`, `notes`).
- Seed 20260101 (CONTEXT Claude's Discretion). Three UTC days, two rollovers, one graduation, one creator with two launches.
- Budget: committed only if under 5 MB (CONTEXT).

### 2.13 T11, T12 static doc tests and D1-D3 runbooks

**Analog loader pattern:** `ci/tests/test_security_workflows.py`

```python
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WORKFLOW_FILES = ["gates.yml", "security-pr.yml", "ci.yml"]
BYPASS_SNIPPETS = ["|| true", "|| exit 0", "2>/dev/null", "--exit-zero", "--dry-run"]


def _load_yaml(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())
```

For `tests/docs/`, use `REPO_ROOT = Path(__file__).resolve().parents[2]` and read `docs/runbooks/*.md`. Parse only fenced ` ```bash ` blocks; ignore prose (RESEARCH Pitfall 19). Allowed first tokens: `pumpgrok`, `docker` (with `compose` subcommand), `uv` only if the runbook is about the dev loop, and the FOUNDATION 6 canonical commands. The test must reject `curl`, `cp`, and `sed` in fenced blocks. If a runbook needs `cp .env.example .env`, put it in prose or allowlist it with a reason (RESEARCH Pitfall 19). Do not weaken silently.

**Runbook structure (D1):**

```markdown
# Setup runbook

First-run setup for the PumpGrok desk. ...

## Quick start

```bash
uv sync
cp .env.example .env
uv run pumpgrok doctor
uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
./scripts/check.sh
```

## What setup creates
...
## Rules that apply during setup
...
## References
```

- `docs/runbooks/setup.md` (existing) is the only analog. It is stale in three ways that the rewrite must fix: it cites `/workspace/trading-desk/` working directories, it says root `tools/*.py` "stay byte-identical as oracles" (in "Rules that apply during setup"), and its quick-start `cp` is not a canonical command.
- `./scripts/check.sh` in OBS-004 is a success criterion, so keep it in the runbook (it exists: `scripts/check.sh`).
- `breaker_reset.md`: record that no manual reset verb exists (R40). Do not invent one.
- `kill_switch.md`: `pumpgrok killswitch set --reason <text>` and `pumpgrok killswitch flatten --reason <text>` (D5). Do not write `killswitch set --flatten`.
- `start_stop.md`: document the host UID requirement for the `./var` bind mount (RESEARCH Pitfall 5), not a silent `user:` mapping.
- `go_live.md`: list the nine R21 preconditions in the code ids (`live_gate.py:32-41`) and `pumpgrok live confirm` (exit 5 in this release; the human-only verb).
- `reading_reports.md`: `pumpgrok report --daily` / `--weekly` (`cli.py` report verb; `reporting/render.py:170` `render_daily`).

**CHANGELOG check (T12):** existing heading `## [Unreleased] - Phase 1: Foundation (2026-10-21)` (`CHANGELOG.md:5`) contains `Phase 1`. The validation grep is `grep -q "Phase $p" CHANGELOG.md`, so headings of the form `## Phase N: ...` or `## [Unreleased] - Phase N: ...` both pass. Keep the existing "Keep a Changelog" intro (`CHANGELOG.md:3`) and the `### Added / Changed / Removed` subsections (`:7`, `:33`, `:41`).

### 2.14 Census: root `tools/` removal

**Analogs for replacement tests:**

- `tests/tools/test_verb_coverage.py` (`:76` `ScriptedCurves`, `:183` `TestExecBackendCoverage`, `:334` `TestServedVerbCoverage`) runs served CLI verbs through `main` with `monkeypatch`. Use it as the template for CLI-level replacements of `tests/test_tools_cli.py` cases.
- `tests/characterization/test_holder_check.py` already imports the ported module directly (`pumpgrok.tools.onchain.holders`), with a docstring that names the old oracle (lines 1-15). Only the docstring needs to change. Its `@pytest.mark.characterization` pattern stays.

**`tests/test_tools_cli.py` root-oracle use (remove or port):**

- `:35` `TOOLS = ROOT / "tools"`; `:38` `load_tool(name)` loads `TOOLS/<name>.py` by file path.
- `:48` `JupiterQuoteContract`, `:105` `FailClosedExitCodes` (runs `tools/pipeline_evidence.py` in a subprocess), `:194` `HermesScriptsExecutable`, `:206` `TicketHelperDocs` (`:213` reads `tools/README.md`).
- The other classes in the file (for example `TestPaperRegistryPath` at `:266`, `TestOperatorVerbs`, `TestCliRegressionSweep`) use `pumpgrok.cli` and are not oracle tests. Keep them.

**Census command (D3):** `rg -n --hidden -P '(?<![\w/])tools/(README|authority_check|desk_state|holder_check|jupiter_quote|paper_sim|pipeline_evidence|priority_fee|ticket_helper)' --glob '!docs/**' --glob '!vendor/**' --glob '!.git/**' --glob '!.planning/**'`. CONTEXT's literal command is `rg -n -P ...` without `--hidden`, which misses `.github/` and `.receipts/` (RESEARCH D3). The lookbehind `(?<![\w/])` excludes `src/pumpgrok/tools/`.

**Current census (tracked files that match, excluding `docs/`, `vendor/`, `.git/`, `.planning/`):** `AGENTS.md` (GSD block; do not hand-edit), `ARCHITECTURE.md`, `README.md`, `SETUP.md`, `agents/README.md`, `agents/scout.md` (generated), `hermes/README.md`, `prompts-assembled/SCOUT.xml` (generated), `prompts/bot-01-scout.xml`, `rules/pumpgrok-team.mdc`, `scripts/hermes-verify-isolation.sh`, `scripts/hermes-bootstrap.sh`, `skills/README.md`, `skills/desk-strategy-lab/SKILL.md`, `skills/desk-trade-lifecycle/SKILL.md`, `skills/discovery-tools/SKILL.md`, `skills/grokbot-pipeline/SKILL.md`, `skills/hermes-cron-desk/SKILL.md`, `skills/holder-and-flow-analysis/SKILL.md`, `skills/risk-audit/SKILL.md`, `src/pumpgrok/ledger/desk_bus.py`, `src/pumpgrok/ledger/export.py`, `src/pumpgrok/tools/onchain/{authorities,holders,priority_fee}.py`, `tests/characterization/{test_authority_check,test_holder_check,test_jupiter_quote,test_priority_fee,test_vendor_log}.py`, `tests/test_tools_cli.py`, and `tools/*` itself.

**Generated files:** after editing `prompts/bot-01-scout.xml`, run `bash scripts/assemble-prompts.sh` and `python3 scripts/generate-templates.py` (RESEARCH Pitfall 21). Do not edit `prompts-assembled/SCOUT.xml` or `agents/scout.md` directly. `make check` runs both with `--check`.

**Deletion:** `pyproject.toml:35-36` comment and dependency `requests` go in the same change (no importers, section 0.10). `.dockerignore` already excludes `tools`. Re-lock with uv 0.13.4 (section 6).

### 2.15 RISK-007 and `docs/RISK_POLICY.md`

**Test analog:** `tests/safety/test_no_manipulation_tools.py`

```python
# tests/safety/test_no_manipulation_tools.py:26, :30, :33 (verbatim)
SOCIAL = Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "tools" / "social"

# SC4 literal, verbatim: bare write verbs or a write-verb method argument.
_SC4 = re.compile(r"\b(post|put|patch|delete)\b|method=['\"](POST|PUT|PATCH|DELETE)")

# RISK-007 manipulation stems (substring match inside social/ only).
_STEMS = ("post", "reply", "like", "follow", "dm", "broadcast", "wash", "volume")
```

Its docstring says "completed by RISK-007 in Phase 5". RISK-007 (REQUIREMENTS.md:76) also needs: `notify.*` allowlist-only sends, the `browser-ops` forbidden-actions scope, and "no registered tool name matches `post|reply|like|follow|dm|broadcast|wash|volume`". The registry-name check already exists in `tests/safety/test_no_manipulation_tools.py` (imports `build_registry`, `register_read_tools`, `SideEffect`). Extend it; do not create a second file.

**Policy doc:** `docs/RISK_POLICY.md` section 4 "Manipulation boundary (D7)" at `:144`: `4.1 Prohibited` (`:146`), `4.2 Allowed` (`:162`), `4.3` (`:166`), `4.4 Absence checks that prove the boundary` (`:170`). Fix the `risk/limits.py` citations at `:7` and `:39` (section 0.2). Line `:244` table row 10 also names `risk/limits.py` for the `[risk.engine]` constants; check it when editing.

### 2.16 T16 static guards

```python
# tests/safety/test_static_guards.py:18-25 (verbatim, abridged)
SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"

# The only module allowed to read wall time or sleep on a real loop (paper-engine 4.1).
CLOCK_ALLOWLIST = frozenset({"replay/clock.py"})
...
_CLOCK_PRIMITIVES = frozenset(
    {
        "asyncio.sleep",
        "asyncio.timeout",
        "asyncio.wait_for",
        "time.time",
        "time.monotonic",
        "datetime.now",
        ...,
    }
)
```

- Add a test in the same file: no module under `src/pumpgrok/core/` or `src/pumpgrok/risk/` imports `prometheus_client` (AST `Import`/`ImportFrom`, using `_scan_file` at `:78` as the template).
- Add a test that `src/pumpgrok/logging/spans.py` contains no `_CLOCK_PRIMITIVES` (already covered by `test_src_pumpgrok_has_no_forbidden_primitives` at `:138`, so no new test needed; confirm after writing).

### 2.17 Security CI (SEC-005)

**Trigger analog** (`.github/workflows/gates.yml`):

```yaml
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
```

```yaml
# .github/workflows/security-pr.yml:16-18 (current, verbatim)
on:
  pull_request:
    branches: [main]
```

Add `push: branches: [main]` under `on:`. The guard `TestGatesWorkflow.test_triggers_on_pull_request_and_push_to_main` (`ci/tests/test_security_workflows.py`) is the pattern for a matching assertion on `security-pr.yml`. `_trigger(doc)` (`:47`) handles YAML 1.1 reading `on` as `True`.

**Nightly analog** (`.github/workflows/ci.yml`): triggers `:8-13` (`push` and `pull_request` on `main`), `concurrency` block, one job `check` that runs `make lint typecheck test audit` (`:35`). Add `schedule: - cron: "..."` and a nightly job step `uv run pytest -q -m slow tests/soak` with `PUMPGROK_REQUIRE_SOAK=1`. `TestCiWorkflow` (`ci/tests/test_security_workflows.py`) asserts `trigger["pull_request"]["branches"] == ["main"]`; keep that. `make test` runs `pytest -q` (Makefile `:25-26`), so slow tests run on every PR unless deselected. CONTEXT says "Slow tests are not deselected by default", so the PR time cost must be measured (RESEARCH Pitfall 9).

**Pip-audit analog:** `Makefile:28-30` `audit` target is the R2 bridge, verbatim:

```make
audit: sync      ## pip-audit against the lockfile
	$(UV) export --frozen --no-dev --no-emit-project --format requirements-txt --no-hashes -o /tmp/pumpgrok-req.txt
	$(UV) run pip-audit -r /tmp/pumpgrok-req.txt --strict
```

`security-pr.yml` (dependencies job, around `:222-228`) runs `pip install "uv==0.13.4" pip-audit` and then bare `pip-audit -r req.txt --strict`. Change it to `uv run pip-audit -r req.txt --strict` after `uv sync --frozen --group dev` (RESEARCH Pitfall 7). The guard substring `pip-audit -r req.txt --strict` still matches.

**Scanner pinning (observed):** `actions/checkout@v4`, `actions/setup-python@v5`, `actions/upload-artifact@v4` are tag-pinned. `github/codeql-action/upload-sarif@1190a975...` and `aquasecurity/trivy-action@ed142fd0...` are SHA-pinned. `pip install semgrep` (`:93`) and `pip install bandit` (`:145`) are unpinned. FOUNDATION U-4 says actions are pinned by SHA (RESEARCH). Decide whether to pin all `uses:` lines or document the exception in `SECURITY.md`.

**Gitleaks:** `ci/security/gitleaks.toml` has `useDefault = true`, six trading rules, and an `[allowlist]` with only `regexes` (for `${VAR}`). Planted secret fixtures (T23) must carry `# pragma: allowlist secret` per line (`ci/gates/check_secrets.py:25` `ALLOWLIST_MARKER`), or the allowlist needs a `paths` entry. `SKIP_DIRS` (`check_secrets.py:97`) does not skip `tests/fixtures`.

**Exceptions table (SECURITY.md, D9):** no analog exists. Required columns from CONTEXT: check, fingerprint, reason, owner, ISO expiry. "An expired row fails the workflow" needs a new check. No in-repo table to copy.

### 2.18 Container (I1, I2)

**Dockerfile (current, verbatim where it matters):**

```dockerfile
# Dockerfile:4-5
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /uvx /bin/

# Dockerfile:11-12
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Dockerfile:20-21
RUN useradd --system --create-home --home-dir /home/pumpgrok pumpgrok \
 && mkdir -p /app/var \

# Dockerfile:28-29
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["pumpgrok", "doctor"]

# Dockerfile:34
CMD ["run", "--mode", "paper", "--once", "--replay", "tests/fixtures/replay/smoke"]
```

- Non-root `pumpgrok` user (`:20`) and `/app/var` ownership already exist. Keep.
- `COPY .python-version pyproject.toml uv.lock README.md ./` before `uv sync --frozen --no-dev --no-editable` (R49 V-3; RESEARCH Pitfall 3).
- HEALTHCHECK: replace `pumpgrok doctor` (module presence only, `doctor.py:16-29`) with a stdlib probe of `http://127.0.0.1:${PUMPGROK_HEALTH_PORT}/healthz`. The FOUNDATION 3.3 pattern is in `docs/FOUNDATION_STACK.md` (tracked; `:290-355` per RESEARCH; not re-opened for this map).
- CMD (D1): `["run", "--mode", "paper", "--serve"]`, with the replay dataset given explicitly. The one-shot form stays available for Phase 1 criterion 4 (`docker compose run --rm pumpgrok run --mode paper --once --replay ...`, D1).
- `uv` pin: `ghcr.io/astral-sh/uv:0.13.4` (tag, not digest). Verify the digest per R49 V-2 if a digest pin is adopted.

**docker-compose.yml (current):** header comment (lines 1-11) explicitly says "It deliberately has NO restart policy ... Do not add a restart policy here." D1/D9 supersede this only for `--serve`. Update the header, not just the keys. Current keys: `build: .`, `image: pumpgrok:local`, `container_name: pumpgrok`, `env_file` (optional `.env`), `environment: PUMPGROK_PROFILE`, `ports: "127.0.0.1:8080:8080"`, `logging` json-file 20m/5, `deploy.resources.limits.memory: 512M`. Add: `PUMPGROK_HEALTH_PORT: "8080"`, `volumes: ./var:/app/var`, `stop_grace_period: 45s`, `healthcheck`, `restart: unless-stopped` (serve only). Ownership of bind mount: RESEARCH Pitfall 5.

### 2.19 I8, I9 workflows and gitignore

- `.gitignore` receipts: `.receipts/**/*.json` is ignored except `!.receipts/**/.gitkeep`. Add `!.receipts/bot-00-chief/complete-phase-5.json` (RESEARCH Pitfall 18, D3). `.receipts/bot-00-chief/.gitkeep` is tracked (the analog).
- Per-owner receipts: `ownership.yaml` gives `docs/runbooks/**`, `src/pumpgrok/supervisor/**`, `src/pumpgrok/cli.py` to bot-00-chief; `.github/workflows/**`, `SECURITY.md`, `ci/**`, `Dockerfile`, `pyproject.toml`, `Makefile`, `src/pumpgrok/core/**`, `src/pumpgrok/logging/**`, `tests/**`, `docs/RISK_POLICY.md` to bot-02-risk (`ownership.yaml:137-143`, `:266-292`, `:336`); `CHANGELOG.md` to bot-09-journal (`:86-87`). Phase 5 spans three seats; RESEARCH Pitfall 20 says split into per-owner branches, each with its receipt.

### 2.20 D7 CHANGELOG and D8 AGENTS

- `CHANGELOG.md` heading style to copy: `## [Unreleased] - Phase 1: Foundation (2026-10-21)` (`:5`), then `### Added`, `### Changed`, `### Removed` (`:7`, `:33`, `:41`). One block per phase, Phase 1 through Phase 5.
- `AGENTS.md`: hand-written sections are `## Where the rules live` (`:7`), `## The ten seats` (`:23`), `## Before the first edit` (`:38`), `## Receipts` (`:47`), `## Secrets` (`:53`), `## Run the checks` (`:58`), then `:71` "Generated and maintained sections follow." The rules index is a list of rule files to read first; model it on `## Where the rules live`. Insert after line 405 (section 0.3).

---

## 3. Shared Patterns

| Concern | Source (copy from) | Apply to |
|---------|-------------------|----------|
| Virtual time only | `replay/clock.py:22` `Clock` protocol; `tests/safety/test_static_guards.py:21-37` | `spans.py`, `metrics.py`, `seat_task.py`, `health.py`, `scheduler.py` |
| Context-bound state | `core/ids.py:96-150` (`bind_correlation`), `logging/json.py:26-42` (`bind_seat`) | `spans.py`, registry span wrap |
| Redacted handler | `logging/json.py` `setup_logging` + `logging/redaction.py:83` `RedactionFilter` | any new log emission (span, rollover, serve) |
| Ledger idempotency keys | `risk/engine.py:175-177` (`halt_key`), `supervisor/seat_task.py:80-131` (`escalation|{kind}|{seat}|{ts}`), `replay/runner.py` `derive_idempotency_key` | `DailyRollover` emitter |
| Health JSON route | `supervisor/health.py:120-155` | `/metrics` route (bytes, not JSON) |
| Fresh registries and fixtures | `tests/supervisor/test_restarts.py:27-43` (`_store`, `_ctx`) | all new supervisor and degradation tests |
| Fault injection | `tests/harness/faults.py:19-96`, marker class `InjectedFault` | `tests/degradation/*` |
| Static text and AST guards | `tests/safety/test_static_guards.py`, `tests/safety/test_no_manipulation_tools.py`, `ci/tests/test_security_workflows.py` | T11, T13, T15, T16, I10 |
| CLI tests | `tests/tools/test_verb_coverage.py` (`_run`, `monkeypatch.chdir`), `tests/execution/test_live_gate_fails_fast.py:54` | T14, CLI `--serve` tests, T17 |
| Fixture manifests and digests | `replay/fixtures.py:39-48` (`FixtureManifest`), `tests/fixtures/replay/smoke-10m/manifest.json` | T21, S15 |
| Workflow triggers | `.github/workflows/gates.yml` `on:` (pull_request + push to main) | I8 |
| Config sections | `config/settings.py:240-243` (`ReplaySettings`), `:164` (`OpsSettings`) | S8 |
| Network block | `tests/conftest.py` (autouse, offline by default) | every new test; no live calls in fixtures |

---

## 4. No Analog Found

| File or capability | Why none | Planner should use |
|--------------------|----------|--------------------|
| `prometheus_client` usage (`CollectorRegistry`, `Counter`, `Histogram`, `generate_latest`) | no tracked code imports it; vendor hand-rolled exposition was retired | RESEARCH Pattern 1 (ASSUMED API); verify after the checkpoint |
| Multi-day replay driver | `run_once_replay` runs one dataset once; no day loop exists | build in `tests/soak/` with `run_once_replay`-style setup |
| Nightly `schedule:` trigger | no workflow has one | RESEARCH D11 shape |
| SECURITY.md exception table and expiry check | no table exists | CONTEXT columns; a stdlib check modelled on `ci/gates/check_*.py` |
| Runbook command validator | no tracked doc test | parse fenced `bash` only (section 2.13) |
| Fault fakes for LLM, RPC, data source, price source, execution adapter, ledger store | `FaultInjector` covers events and sinks only | extend `tests/harness/faults.py` (T19) |
| Container HEALTHCHECK probe (stdlib HTTP) | no in-repo probe; `pumpgrok doctor` only | FOUNDATION 3.3 (`docs/FOUNDATION_STACK.md`) |
| Changelog-per-phase test | none | T12 |
| `sys.excepthook` / loop exception handler test | none | `asyncio` loop exception handler in soak test |
| Orders-total emitter | not located | section 2.3 table; decide the source |

---

## 5. Pitfalls and Gaps Found in the Tree

These are specific to the current code. Each one changes a plan step.

1. **`Supervisor.health_status()` hard-codes state.** `scheduler.py:371-381` passes `ledger_status="CONSISTENT"`, `kill_switch=False`, and no `equity_lamports`, `drawdown_pct`, `data_age_s`, `ledger_seq`, `breakers`, `breaker`. Gauges built from it would be 0 or wrong. Feed real values, or make the metrics snapshot a separate callable.
2. **`run_once_replay` asserts read-only seat cycles.** `scheduler.py:497-` raises if `store.count()` changes. DailyRollover rows and any `Escalation` written during a soak break the assertion. Either emit rollovers outside the assertion window, or change the assertion to allow the rollover key only (and say so in the test).
3. **`HealthServer._respond` is JSON-only** (`health.py:147-155`). `/metrics` cannot reuse it unchanged.
4. **`health.py` docstring says "No metrics endpoint here (Phase 5)"** (module docstring, lines 1-12). Update it in the same change.
5. **INV-C-11 vs D1.** `--once` and `--replay` must bind port 0 (INV-C-11, `SAFETY_INVARIANTS.md:65`). `--serve` binds `PUMPGROK_HEALTH_PORT`. Amend INV-C-11 in the matrix and `docs/design/paper-engine.md` as D1 states.
6. **Compose `run` and `up` share one command** (RESEARCH Pitfall 2). Phase 1 criterion 4 uses `docker compose run --rm pumpgrok` and needs explicit one-shot args (D1 amendment).
7. **`killswitch set --flatten` does not exist** (`cli.py:456-463`). Runbooks use `killswitch flatten --reason`.
8. **`live.enabled` is never read** (`live_gate.py:67-85`). Precondition 1 must read it after the R21 amendment (D4).
9. **`FixtureClock.jump` does not exist** (`replay/clock.py:79-150`).
10. **Gate ids differ** between `PRECONDITION_IDS` (`live_gate.py:32-41`) and INV-C-02 in `SAFETY_INVARIANTS.md`. Adopt the code ids (D4).
11. **Matrix cells contain `|` inside backticks**, e.g. INV-R-01 `[env_at_start|file|alert]` (RESEARCH Pitfall 17). The meta-test (T13) parser must handle pipes inside code spans, or the doc escapes `\|`.
12. **`security-pr.yml` has no `push:` trigger** (`:16-18`). SEC-005 needs one (D7).
13. **`security-pr.yml` pip-audit is bare** (`pip install ... pip-audit` then `pip-audit`). Use `uv run` (section 2.17).
14. **`slow` marker unregistered** (`pyproject.toml:91-93`, `--strict-markers` at `:90`). Register before any `@pytest.mark.slow`.
15. **`pyproject.toml:35` comment** says the root `tools/` oracle is kept until Phase 5 for `tests/test_tools_cli.py`. Remove both when the oracle is gone.
16. **Dockerfile COPY misses `.python-version`** (`:11`).
17. **`ci.yml` has no `schedule:`** (`:8-13`).
18. **`.receipts/**/*.json` is gitignored** (`.gitignore`). Add the exception (section 2.19).
19. **`setup.md` quick start uses `cp .env.example .env`** (`docs/runbooks/setup.md`, Quick start block). Not a canonical command; RESEARCH Pitfall 19.
20. **Prompt and agent files are generated** (`prompts-assembled/SCOUT.xml`, `agents/scout.md`). Edit sources and regenerate (section 2.14).
21. **`uv` on the host is 0.11.26**; the pin is 0.13.4 (RESEARCH env table). Install 0.13.4 before `uv lock` or `uv add`.
22. **`SECURITY.md` has no exceptions table** (D9 needs to create it).
23. **Secrets gate scans tests.** Planted fixtures trip G-3 unless each line carries `pragma: allowlist secret` (section 2.17).
24. **Actions pinning is mixed** (section 2.17).
25. **RISK_POLICY cites `risk/limits.py` for `RiskBudget`** (section 0.2).
26. **Vendor path citations are dead** (section 0.1). Any plan step that cites `vendor/grokbot-pumpfun/...` will fail.

---

## 5a. Phase 5 success criteria to analog map

| Criterion (ROADMAP Phase 5) | Test or check | Closest analog |
|------------------------------|---------------|----------------|
| SC1: `pytest -q tests/soak/test_soak_multiday_replay.py tests/degradation/` | T1-T7 | `tests/supervisor/test_degraded.py`, `tests/supervisor/test_restarts.py`, `tests/replay/test_runner_determinism.py` |
| SC2: nine metric names in `src/pumpgrok` (grep count = 9), metrics tests under `uv run pytest -q` | S2, T8 | `tests/supervisor/test_degraded.py` (fixtures) |
| SC3: nine runbooks, `./scripts/check.sh`, CHANGELOG phases, compose healthy | D1-D2, T11, T12, I1, I2 | `docs/runbooks/setup.md`, `CHANGELOG.md`, `scripts/check.sh` |
| SC4: `tests/safety/test_no_manipulation_tools.py tests/execution/test_live_gate_fails_fast.py`; overlays `enabled = false` | T14, T15, S9 | `tests/execution/test_live_gate_fails_fast.py`, `tests/safety/test_no_manipulation_tools.py` |
| SC5: `security-pr.yml` green on main or SECURITY.md exceptions | I8, I10, D9 | `.github/workflows/gates.yml`, `ci/tests/test_security_workflows.py` |
| Checkpoint: `run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 | existing | `tests/supervisor/test_degraded.py:170` (`test_smoke_cycle_cli_exits_0_with_no_network`) |
| Census empty and `test ! -d tools` | X1-X14 | section 2.14 |
| Matrix meta-test `ci/tests/test_gates.py::test_invariant_matrix_tests_exist` | T13 | `ci/tests/test_gates.py:41` `_load` |

---

## 6. Locked decisions the planner must respect (from CONTEXT "Recorded decisions")

- D1: `docker compose up -d pumpgrok` serves `pumpgrok run --mode paper --serve`, replaying a recorded dataset in a loop; health body labelled `ledger_source=replay`; INV-C-11 amended.
- D2: all matrix owning tests implemented; the meta-test is not narrowed (56 missing; the research count is 56 of 66 path references).
- D3: census keeps the literal command, adds `--hidden`, excludes `.planning/**`; `tests/test_tools_cli.py` migrated; AGENTS GSD block not hand-edited.
- D4: adopt code precondition ids; R21 amended so precondition 1 reads `[live] enabled`.
- D5: runbooks use `killswitch flatten --reason`.
- D6: one DailyRollover per UTC day including the first (three in soak-3d).
- D7: add `push` trigger to `security-pr.yml`; list no check pre-emptively; if `gh` cannot authenticate, report SEC-005 as blocked.
- D8: keep fail-closed curve layout; record REVIEW; no live RPC probe.
- D9: see D1.
- D10: keep `ubuntu-latest`; guard test stays.
- D11: nightly `schedule:` on `ci.yml` for `pytest -q -m slow tests/soak` with `PUMPGROK_REQUIRE_SOAK=1`.
- Dependency gate: `prometheus-client` is SUS in the legitimacy audit. `checkpoint:human-verify` before `uv add`. Not approved by the orchestrator.
- Tooling: uv 0.13.4 before locking.

---

## 7. Metadata

**Analog search scope:** `src/pumpgrok/{supervisor,logging,core,risk,replay,ledger,config,execution,reporting,tools}/`, `tests/{supervisor,replay,execution,safety,tools,harness,characterization,config,fixtures}/`, `ci/{gates,security,tests}/`, `.github/workflows/`, root infra files, `docs/runbooks/`, `docs/SAFETY_INVARIANTS.md`, `docs/RISK_POLICY.md`, `ownership.yaml`.
**Files opened:** about 45 (read and grep). Not opened: `docs/design/paper-engine.md`, `docs/FOUNDATION_STACK.md`, `docs/upgrade-plan-desk-v2.md`, `src/pumpgrok/execution/paper_adapter.py`, `skills/*` bodies beyond grep hits. Items that depend on them are marked.
**Tracked check:** every analog path cited above was checked with `git ls-files` (this session); `tests/safety/test_network_block.py` does not exist (the file is `tests/test_network_block.py`).
**Not executed:** pytest, ruff, mypy, make, docker, uv, gh, and the census `rg` run only as a read-only grep.
**Pattern extraction date:** 2026-10-22

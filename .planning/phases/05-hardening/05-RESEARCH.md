# Phase 5: Hardening - Research

**Researched:** 2026-10-22
**Domain:** Python 3.12 paper-trading desk hardening: metrics, health serving, multi-day replay soak, fault injection, runbooks, security CI, container health, go-live proof, root `tools/` deletion
**Confidence:** HIGH for in-repo gaps (read directly this session); MEDIUM for library APIs (training knowledge, flagged); LOW for CI and container runtime outcomes (not executed; no tests, lint or builds were run, per assignment)

<user_constraints>
## User Constraints (from CONTEXT.md)

Source: `.planning/phases/05-hardening/05-CONTEXT.md` (status "Ready for planning", mode "Seeded from design docs"). Copied verbatim.

### Locked Decisions
- Logging (Phase 1, consumed): JSON line per record, FOUNDATION 5.1 fields, RedactionFilter on every handler (OBS-001). Correlation id is a bare ULID (`core/ids.py`); children `<ulid>.<n>` (R29, OBS-002). FOUNDATION `cid_` prefix superseded.
- `logging/spans.py` (bot-02-risk): `span(name, **fields)` for `with` and `async with`; parent and counter in contextvars; duration from injected `Clock.now()` (INV-S-13); emits `event="span"`. `core/registry.py` wraps every tool call (OBS-003).
- `supervisor/metrics.py` (bot-00-chief): `build_registry()` returns a fresh `CollectorRegistry`. Exactly nine families, names verbatim: `pumpgrok_cycle_seconds{seat}` histogram (virtual seconds, from `seat_task.py`); `pumpgrok_bot_crashes_total{seat}`; `pumpgrok_orders_total{side,outcome}` (filled|rejected|unknown_result); `pumpgrok_equity_sol` (lamports/1e9 at scrape only, R28); `pumpgrok_drawdown_pct`; `pumpgrok_data_age_seconds{source}`; `pumpgrok_breaker_state{breaker}` (0 closed, 1 half-open, 2 open; paper-engine 6.6); `pumpgrok_kill_switch` (0/1); `pumpgrok_ledger_seq`. Counters passed with `_total`. Only the supervisor writes metrics; `core/` and `risk/` never import prometheus_client.
- `supervisor/health.py` (Phase 4 owns `/healthz`, `/readyz`): add `GET /metrics` (`generate_latest`). Stdlib asyncio server in the pattern of vendor `ops.py:298-357`; binds 127.0.0.1; port `PUMPGROK_HEALTH_PORT` (8080 container, 0 under `--once`/`--replay`, INV-C-11); deadlines via `clock.timeout`.
- Runbooks (OBS-004; bot-00-chief): exactly `docs/runbooks/{setup,engine,start_stop,kill_switch,breaker_reset,outage,rollback,reading_reports,go_live}.md`. Commands limited to FOUNDATION 6 canonical commands, `pumpgrok` verbs and `docker compose` lifecycle verbs; `tests/docs/test_runbook_commands.py` (new) enforces it. `breaker_reset.md` records that no manual reset verb exists (R40).
- Degradation `tests/degradation/` (AUTO-008): one file per AUTO-005 row: `test_llm_failure.py` (INV-R-34), `test_rpc_failure.py` (INV-R-33), `test_data_source_outage.py` (WS and REST, INV-R-32), `test_ledger_unwritable.py` (INV-R-20), `test_clock_skew.py` (INV-R-22); plus `test_partial_restart.py` (INV-R-35). Inject via `tests/harness/faults.py` FaultInjector on FixtureClock.
- Soak (AUTO-007): `tests/soak/test_soak_multiday_replay.py`: `test_soak_replay_bounded_memory` (marker `slow`, soak-3d) and `test_soak_short_pr` (smoke-10m). Growth after first virtual hour < 20 MB (REVIEW); `sys.excepthook` and loop exception handler fail the test; one DailyRollover per day; ledger verifies; report per day.
- Security (SEC-005): `.github/workflows/security-pr.yml` (FOUND-010 creates; finalised here): gitleaks (`ci/security/gitleaks.toml`, G-3 rules), bandit, semgrep, pip-audit, trivy (HIGH,CRITICAL, exit-code 1). Triggers: pull_request and push to main. pip-audit: `uv export --frozen --no-dev --no-emit-project --format requirements-txt --no-hashes -o req.txt`, then `uv run pip-audit -r req.txt --strict` (R2, R49 V-4). Actions pinned by SHA (FOUNDATION U-4); uv 0.13.4 (R49 V-2).
- `SECURITY.md` exceptions: check, fingerprint, reason, owner, ISO expiry; an expired row fails the workflow.
- Container (FOUNDATION 3.3-3.4, amended): multi-stage python:3.12-slim; uv 0.13.4; copy `.python-version` before `uv sync --frozen --no-dev --no-editable` (R49 V-3); non-root `pumpgrok` user; compose service `pumpgrok`, `./var:/app/var` bind, `127.0.0.1:8080:8080`, healthcheck `/healthz`, `stop_grace_period: 45s`.
- Go-live (GOLIVE-003): `docs/runbooks/go_live.md` lists the nine R21 preconditions and `pumpgrok live confirm`. `tests/execution/test_live_gate_fails_fast.py` (Phase 4 file) parametrises all nine. Each overlay `src/pumpgrok/config/overlays/{dev,paper,live}.toml` has `[live] enabled = false` (flag: paper-engine 7.1 lacks `enabled`; gate reads it inside precondition (1); R21 amendment needed).
- RISK-007: `docs/RISK_POLICY.md` section 4 (D7, line 144) and 4.4 (line 170) state the boundary; `tests/safety/test_no_manipulation_tools.py` enforces it (R39).
- Deletion: root `tools/` (eight `.py` modules, README.md, `__pycache__/`) removed only when the census below is empty. No shim (MIGRATION_MAP rows 63-78).
- Milestone: `CHANGELOG.md` with `## Phase 1` through `## Phase 5`; `AGENTS.md` gains `## Rules index` after its last GSD block (AGENTS.md:298); upgrade plan 6.6 report; `.receipts/bot-00-chief/complete-phase-5.json`; `ci/tests/test_gates.py::test_invariant_matrix_tests_exist`.

### Claude's Discretion
- soak-3d synthesised from smoke-10m by `scripts/build_soak_fixture.py` (seed 20260101; three UTC days, two rollovers, one graduation, one creator with two launches), digests in manifest, committed if under 5 MB. Nightly sets `PUMPGROK_REQUIRE_SOAK=1` (absence fails); locally absence skips.
- Slow tests are not deselected by default. Kill flatten: `pumpgrok killswitch set --flatten`. `pumpgrok doctor` probes `/healthz` and `/metrics`; runbooks use it, not curl.
- Runner `[self-hosted, Linux, X64]` (FOUNDATION U-3); bandit and semgrep rules in `ci/security/`. CHANGELOG.md owner bot-09-journal (ROSTER).

### Source conflicts decided here
- Brief paths `tests/safety/test_fault_injection.py` and `tests/safety/test_soak.py` are NOT used: AUTO-007, AUTO-008 and ROADMAP criterion 1 name `tests/soak/` and `tests/degradation/`.
- Nine runbooks (OBS-004), not seven. Harness is `tests/harness/faults.py` (FOUND-012), not `tests/fault_injection.py`.
- SAFETY INV-R-20 test moves `tests/ledger/` to `tests/degradation/`; its section 6 row is updated.
- Upgrade plan 9.2 deletes `tools/README.md` in batch 2.3; Phase 5 deletes what remains.

### Deferred Ideas (OUT OF SCOPE)
- FOUNDATION 5.5 extra metric families, `pumpgrok_ws_duplicates_total`, OpenTelemetry, dashboards: v1.x.
- Manual breaker-reset verb (user decision); operator-recorded soak-3d: v1.x.
- Phase 4 owns GOLIVE-001/002, SEC-004, `/readyz`, STRUCT-006. No live adapter ships.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description (REQUIREMENTS.md) | Research Support (state of the tree today) |
|----|-------------------------------|--------------------------------------------|
| RISK-007 | Compliance boundary stated in RISK_POLICY; manipulation-tool test passes over social, notify and browser-ops | `docs/RISK_POLICY.md` exists (sec 4 at line 144, 4.4 at line 170). Section 4.4 cites a test name `test_no_posting_or_volume_tools` that does not exist. `tests/safety/test_no_manipulation_tools.py` covers only `tools/social` text and only read-tool names; no notify allowlist or browser-ops scan. [VERIFIED: docs/RISK_POLICY.md:170-177; tests/safety/test_no_manipulation_tools.py:35-82] |
| AUTO-007 | `tests/soak/test_soak_multiday_replay.py` replays soak-3d: memory growth bound, no unhandled exception, one DailyRollover per day, ledger verifies, report per day | No `tests/soak/`, no `soak-3d` fixture, no `scripts/build_soak_fixture.py`. No code emits `DailyRollover` (type and reducer handler exist only). [VERIFIED: src/pumpgrok/ledger/events.py:67,248; src/pumpgrok/ledger/reducer.py:349,391; grep over src/pumpgrok finds no emitter] |
| AUTO-008 | Fault-injection suite under `tests/degradation/` drives each AUTO-005 row through FaultInjector | No `tests/degradation/`. `tests/harness/faults.py` has modes `stale, timeout, rate_limit, raise, unwritable` and only event-stream and sink injection; the matrix needs `unknown` and `malformed` modes and service fakes that do not exist. [VERIFIED: tests/harness/faults.py:20-25,42,70,91] |
| OBS-003 | `GET /metrics` exposes the nine families and span timings for every tool call | No metrics module, no prometheus dependency, no `/metrics` route, no span module. `HealthServer._handle` routes every non-`/readyz` path to the health JSON. [VERIFIED: src/pumpgrok/supervisor/health.py:120-135; pyproject.toml dependencies list; uv.lock has no prometheus entry] |
| OBS-004 | Nine runbooks exist, commands canonical or `pumpgrok` verbs, pass `./scripts/check.sh` | Only `docs/runbooks/setup.md` exists, and it is stale (`/workspace/trading-desk/`, root `tools/` described as oracles). No command test. [VERIFIED: docs/runbooks/setup.md:19,28] |
| OBS-005 | CHANGELOG records every phase; AGENTS indexes rules; milestone report lists final results | CHANGELOG has only one phase heading. AGENTS has no `Rules index`. No milestone report and no `complete-phase-5.json` receipt. [VERIFIED: CHANGELOG.md:5] |
| SEC-005 | `security-pr.yml` green on main, or every non-green check listed in SECURITY.md with ISO expiry | Workflow exists with all five scanners but triggers on `pull_request` only. SECURITY.md has no exception table. `gh` is installed but not authenticated, so the main-branch run status cannot be read here. [VERIFIED: .github/workflows/security-pr.yml:16-18; SECURITY.md:1-55; `gh auth status` output] |
| GOLIVE-003 | `docs/runbooks/go_live.md` documents the procedure; `tests/execution/test_live_gate_fails_fast.py` proves each of the nine preconditions; `live.enabled = false` in every overlay | Overlays already set `[live] enabled = false` (dev, paper, live). `go_live.md` missing. Test file exists but asserts only the aggregate header and has no per-precondition parametrisation. Gate reads `enabled` nowhere; preconditions 5-9 are hard-coded `False`. [VERIFIED: src/pumpgrok/config/overlays/{dev,paper,live}.toml `[live]` blocks; src/pumpgrok/execution/live/live_gate.py:63-89] |
</phase_requirements>

## Summary

Phases 1-4 delivered the library layer (settings, ledger, replay, risk engine, paper adapter, supervisor class, health JSON builder, live gate stub, reports) and the static gates. Phase 5 is mostly *wiring, evidence and missing test files*, and the research found that several ROADMAP success criteria cannot be satisfied by the current code without a decision.

The most consequential gaps, in priority order:

1. **Nothing serves health or runs a long-lived desk.** `HealthServer` exists but no process starts it. `supervisor/scheduler.py` has `Supervisor.serve_forever()`, but the CLI `run` verb only accepts `--once --replay <dir>` and otherwise returns exit 5 (`EXIT_NOT_IMPLEMENTED`). Criterion 3 requires `docker compose ps pumpgrok` to report `healthy` via `/healthz`, which needs a long-running entrypoint. That conflicts with the Phase 1 one-shot container design (R50, criterion 4 of Phase 1), with INV-C-11 (health port 0 under `--replay`), and with the absence of any live data feed. This is decision D1.
2. **The invariant matrix meta-test is far larger than the Phase 5 IDs suggest.** `docs/SAFETY_INVARIANTS.md` section 6 lists 66 owning-test references; 56 point to files that do not exist (path-level check). Rows labelled Phase 1 through Phase 4 are missing too. The milestone deliverable `ci/tests/test_gates.py::test_invariant_matrix_tests_exist` requires every row to be collected. This is decision D2, and reducing it needs explicit user approval.
3. **Metrics are entirely absent**: no prometheus dependency, no `supervisor/metrics.py`, no span module, no `/metrics`, and `pumpgrok doctor` does not probe any endpoint.
4. **DailyRollover is never emitted.** AUTO-007 cannot pass until the supervisor emits it.
5. **Degradation fakes and the soak fixture do not exist.** `FaultInjector` covers event streams and sinks only. The matrix assumes `FixtureClock.jump`, which is not defined in `replay/clock.py`.
6. **Security CI is not on main.** `security-pr.yml` does not run on pushes to main, so `gh run list --branch main` can return nothing; SECURITY.md has no exception table; and `gh` cannot authenticate in this environment.
7. **Deletion is blocked by a census gap.** The literal census misses hidden directories and misses `tests/test_tools_cli.py`, which loads six root modules through a constructed path.

Primary recommendation: resolve decisions D1, D2, D3 and D7 with the user before planning Wave 3 (container, go-live proof and SEC-005). Everything else (metrics, spans, DailyRollover emitter, degradation suite, soak fixture, runbooks, CHANGELOG, AGENTS index, deletion migration) can be planned now.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Prometheus registry and nine families | Supervisor (process) | Ledger/reducer (state source) | Only the supervisor writes metrics (CONTEXT lock); gauges read state at scrape time |
| `/metrics` and `/healthz` serving | Supervisor (asyncio HTTP server) | Container HEALTHCHECK and compose healthcheck (consumers) | `HealthServer` already lives in `supervisor/health.py`; bind 127.0.0.1 |
| Span timing and JSON span events | Logging (cross-cutting) | Core registry wrap (`core/registry.py:231`) | Spans must not import prometheus; they emit log events only |
| DailyRollover emission | Supervisor end-of-tick | Ledger (single writer, `BEGIN IMMEDIATE`) | Reducer already folds the event; only the scheduler knows the UTC day boundary |
| Multi-day soak | Test harness on FixtureClock | Replay fixtures (manifest digests) | Virtual time only (INV-S-13); no wall-clock sleeps |
| Degradation faults | Test harness (`tests/harness/faults.py`) | Service fakes in tests | Faults are injected through protocol boundaries, never in product code |
| Live gate proof | Execution (live package) | CLI (`run --mode live`, exit 3) | Fail-fast is a startup contract; test per precondition |
| Container health | Image (Dockerfile HEALTHCHECK) | Compose service healthcheck | Single health definition preferred (see Pitfalls) |
| Security scanning | CI (GitHub Actions) | Repo scanner configs under `ci/security/` | Runs on pull_request and push to main |
| Runbooks and command contract | Documentation (bot-00-chief) | Doc test `tests/docs/test_runbook_commands.py` | Commands are checked, not trusted |
| Root `tools/` deletion | Repository (all tiers) | Characterization tests and skills text | Must migrate or remove every oracle consumer first |

## Standard Stack

### Core (already present)
| Library | Version (pinned) | Purpose | Status |
|---------|------------------|---------|--------|
| pydantic / pydantic-settings | `>=2.14.1,<3` / `>=2.16.1,<3` | Settings and models | [VERIFIED: pyproject.toml dependencies] |
| httpx | `>=0.28.1,<0.29` | RPC and HTTP tests via `httpx.MockTransport` (no respx) | [VERIFIED: pyproject.toml; tests/tools/onchain/test_rpc.py:3 says "B13: no respx"] |
| websockets | `>=17.3,<18` | Vendor-port monitor only (`engine/monitor.py`), not wired to any runtime | [VERIFIED: pyproject.toml; src/pumpgrok/engine/monitor.py:35] |
| tenacity | `>=9.2.1,<10` | RPC retries with `sleep=clock.sleep` | [VERIFIED: pyproject.toml] |
| pytest / pytest-asyncio | `>=9.1.1,<10` / `>=1.4.0,<2` | Test runner; `asyncio_mode = "auto"` | [VERIFIED: pyproject.toml [tool.pytest.ini_options]] |
| pip-audit | `>=2.10.1,<3` (dev) | Dependency audit | [VERIFIED: pyproject.toml dev group] |

### New for Phase 5
| Library | Version | Purpose | Why | Status |
|---------|---------|---------|-----|--------|
| prometheus-client | latest on PyPI is 0.26.0 (published 2026-07-24; `requires_python >=3.9`); pin with `>=0.26,<0.27` after confirming | `CollectorRegistry`, `generate_latest`, counters, gauges, histogram for `/metrics` | FOUNDATION 5.5 and the CONTEXT lock name it; vendor hand-rolls text exposition (`vendor/grokbot-pumpfun/src/ops.py:41-67`, cited in FOUNDATION_STACK.md) | [VERIFIED: pypi.org/pypi/prometheus-client/json; legitimacy seam verdict below] |
| uv | 0.13.4 (must be installed for locking) | Lockfile and export that match R49 V-2 | Host has uv 0.11.26; a lock written by 0.11.26 may differ from the 0.13.4 CI contract | [VERIFIED: `uv --version` on host = 0.11.26; uv 0.13.4 exists on PyPI] |
| pytest marker `slow` | n/a | Tag soak tests | `pyproject.toml` sets `addopts = "-q --strict-markers"` and registers only `replay` and `characterization`, so an unregistered `slow` marker is a collection error | [VERIFIED: pyproject.toml:90-93] |

Removal candidate: the dev dependency `requests>=2.32,<3` exists only for root `tools/`. No `import requests` or `from requests` exists under `src`, `tests`, `ci` or `scripts`. Remove it in the same change that deletes `tools/`, then re-lock. [VERIFIED: pyproject.toml:35-36 comment and dependency; rg over src/tests/ci/scripts found no requests imports]

**Installation (after approval, via the checkpoint in the legitimacy audit):**
```bash
uv add "prometheus-client>=0.26,<0.27"   # run under uv 0.13.4 only
```

### Alternatives considered
| Instead of | Could use | Tradeoff |
|------------|-----------|----------|
| prometheus-client | Hand-rolled text exposition (vendor precedent) | Rejected: FOUNDATION 5.5 and the CONTEXT lock require the reference client; less code to audit at the cost of one dependency |
| stdlib asyncio HTTP server | aiohttp / FastAPI | Rejected: FOUNDATION keeps the no-framework HTTP server; no web framework enters the trust base |
| tracemalloc for soak memory | RSS via `resource.getrusage` | `getrusage` reports peak RSS, not growth after a point in time; tracemalloc gives traced current bytes, at a speed cost |

## Package Legitimacy Audit

Seam command run this session: `node /root/.agents/gsd-core/bin/gsd-tools.cjs query package-legitimacy check --ecosystem pypi prometheus-client`.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| prometheus-client | PyPI | published 2026-07-24 (latest 0.26.0) | unknown (null in seam) | https://github.com/prometheus/client_python | SUS (reason: `unknown-downloads`) | Flagged, not removed. Planner MUST add a `checkpoint:human-verify` task before `uv add`, confirming the repository URL and the release |
| uv 0.13.4 | PyPI (installer, not a runtime dependency) | released before 2026-10-22 | n/a | https://github.com/astral-sh/uv | Not checked by seam (tooling pin from R49 V-2) | Approved as pinned tooling; verify SHA of the installer image in Dockerfile |

[WARNING: flagged as suspicious - verify before using.] prometheus-client: the seam returned SUS only for missing download counts; the repository URL is the official Prometheus client. The planner must still add the human-verify checkpoint per protocol.

**Packages removed due to SLOP verdict:** none.
**Packages flagged as suspicious [SUS]:** prometheus-client (checkpoint required).

## Architecture Patterns

### Pattern 1: Metrics registry built fresh, written only by the supervisor
**What:** `supervisor/metrics.py` exposes `build_registry() -> CollectorRegistry` and a small `Metrics` holder with the nine families. Gauges that are state snapshots (equity, drawdown, kill switch, ledger seq, breaker state, data age) are computed at scrape time from a snapshot callable, so `core/` and `risk/` never import prometheus.
**When to use:** always for this phase; `build_registry()` must be fresh per call so tests do not collide on the global default registry.
**Example:**
```python
# Source: prometheus_client public API (training knowledge, not verified in this session) [ASSUMED]
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

def build_registry() -> CollectorRegistry:
    registry = CollectorRegistry(auto_describe=True)
    Counter("pumpgrok_bot_crashes", "Seat crashes", ["seat"], registry=registry)  # exposed as ..._total
    # ... remaining families
    return registry
```
Note: the exposed name of a Counter declared without `_total` gets `_total` appended, while a name already ending in `_total` is accepted. The CONTEXT says "Counters passed with `_total`." The planner must add a test that greps the exposition for the exact nine names, because the grep in ROADMAP criterion 2 checks source text, not exposition.

### Pattern 2: Route `/metrics` before the health fallthrough
**What:** `HealthServer._handle` currently sends every path except `/readyz` to the status JSON (`supervisor/health.py:124-130`). Add an explicit `/metrics` branch that returns `generate_latest(registry)` with `text/plain` content type. `_respond` is JSON-only today, so it needs a content-type parameter.
**Gotcha:** `_path_of` defaults to `/healthz` on parse failure; keep that, but `/metrics` must not fall through to health status JSON.

### Pattern 3: DailyRollover from the supervisor end-of-tick
**What:** In `Supervisor._end_of_tick` (`scheduler.py`, method at line ~328), compare the UTC day of `clock.now()` with the last emitted day, and append `DailyRollover` once per new day through the ledger store. Use an idempotency key derived from the day (e.g. `DailyRollover|<utc_day>`), matching the `HaltSet` key pattern in SAFETY_INVARIANTS.md (INV-R-04).
**Gotcha:** the reducer's `_on_rollover` (`ledger/reducer.py:349`) already exists; check what it resets before emitting, since emitting changes the folded state and every replay digest.

### Pattern 4: Span as a dual sync/async context manager with contextvars
**What:** `logging/spans.py` provides `span(name, **fields)` as a class with `__enter__/__exit__` and `__aenter__/__aexit__`. Parent id and child counter live in a ContextVar. `core/correlation.py` already provides `child_span(root, n)` producing `<ulid>.<n>`; reuse it, do not re-implement.
**Gotcha:** the CONTEXT signature `span(name, **fields)` does not carry a clock, yet duration must come from `Clock.now()`. Decide how the clock is bound (for example a ContextVar set at cycle start by `seat_task.py`). This is an unstated design gap.

### Pattern 5: Degradation tests drive product code through protocol fakes
**What:** each AUTO-005 row gets one test file. Faults are injected at protocol boundaries (LLM client, RPC endpoints, data source, price source, execution adapter, ledger store) through small fake classes, plus `FaultInjector` for event streams and sinks. Extend `FaultMode` with `malformed` and `unknown` modes (required by the matrix for INV-R-34 and INV-R-12).
**Existing protocol seams:** `core/adapter.py:146` (`ExecutionAdapter`), `core/datasource.py:43` (`DataSource`), `execution/paper_adapter.py:76` (`PriceSource`), `ledger/store.py` (`LedgerStore`), `tools/onchain/rpc.py` (`RpcClient`, tested with `httpx.MockTransport`), `core/llm.py` (`GrokOps`).

### Pattern 6: Long-running entrypoint (only after decision D1)
**What:** a non-replay `run` path would construct `Supervisor(...)`, start `HealthServer` on `PUMPGROK_HEALTH_PORT`, install signal handlers (`supervisor/lifecycle.py:40`), run `serve_forever()`, and call `shutdown()`. None of this is wired today. The data plane for seat cycles does not exist outside replay (`_replay_cycles` in `scheduler.py` builds cycles from a dataset only).

### Anti-Patterns to Avoid
- **Putting `prometheus_client` imports in `core/` or `risk/`:** breaks the CONTEXT lock and an AST test should enforce it.
- **Using the default global prometheus REGISTRY:** causes duplicate-registration errors across tests; always use `build_registry()`.
- **Wall-clock timing in spans or metrics:** `time.time`, `time.monotonic` and `asyncio.sleep` are banned in `src/pumpgrok` (INV-S-13).
- **Hand-editing inside GSD markers in AGENTS.md:** the CONTEXT forbids it; see decision D3.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Metrics text exposition | Custom formatter (vendor `ops.py:41-67`) | `prometheus_client.generate_latest` | Escaping and TYPE/HELP lines are easy to get subtly wrong |
| Correlation span ids | New id scheme | `core/correlation.py` `child_span`, `root_of`, `is_child_span` | Already tested by Phase 1 |
| Secret scanning | Custom regexes alone | gitleaks (`ci/security/gitleaks.toml`) plus G-3 gate | Redundant scanners are the point of SEC-005 |
| Static AST safety checks | Grep-only checks | `ast` walkers as in `tests/safety/test_no_signing_outside_live_stub.py` | Grep misses aliasing; the repo already uses AST |
| Fixture integrity | Ad-hoc hashing | Existing manifest digest loader in `replay/fixtures.py` (refuses corrupt fixtures) | INV-R-30 already specifies it |
| Health HTTP server | New web framework | Existing stdlib `HealthServer` | Keeps the trust base small (FOUNDATION) |
| Markdown command validation | Free-text review | `tests/docs/test_runbook_commands.py` parsing fenced `bash` blocks | The CONTEXT requires an automated test |

## Runtime State Inventory

Phase 5 removes root `tools/` and renames nothing stored at runtime. Answers to each category:

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None. `var/` (gitignored) holds replay ledgers under `var/replay/<dataset>/`; the deletion does not touch them. [VERIFIED: .gitignore `var/` rule] | None |
| Live service config | None outside git. No n8n-style external workflow references the root `tools/` paths. [INFERENCE: no external config is in the repo; not verifiable from here] | Confirm with operator before deletion |
| OS-registered state | None. No systemd, launchd or cron entries are in the repo that call `tools/` paths. [VERIFIED: no such files in repo listing] | None |
| Secrets and env vars | None reference tool paths. [VERIFIED: `.env.example` placeholders only, per INV-S-06 expectations] | None |
| Build artifacts | The root tools directory `__pycache__/`, and generated prompt and template files (`prompts-assembled/SCOUT.xml`, `agents/scout.md`) that quote the pipeline-evidence bridge path. Regenerate after source edits. | Delete `__pycache__`; regenerate prompts and templates from edited sources |

**Canonical question:** after every repository file is updated, what still refers to the old tool paths? Answer: the Docker image excludes `tools` (`.dockerignore` lists it); the census below is the only in-repo consumer list, plus `tests/test_tools_cli.py` and the census gaps listed under decision D3.

## Common Pitfalls

### Pitfall 1: Compose `healthy` is not reachable with the current design
**What goes wrong:** `docker compose up -d --build pumpgrok` runs the one-shot replay CMD (`Dockerfile:34`), exits 0, and the container is not healthy. Even with a long-running command, `/healthz` returns 503 when any seat is stale or a breaker is open (`supervisor/health.py:54`: `degraded = ledger_status != "CONSISTENT" or stale or halted or kill_switch or breaker == "open"`), and no live data feed is wired.
**Why it happens:** R50 chose a one-shot service; no long-running CLI path exists; health semantics assume live data.
**How to avoid:** resolve decision D1 first.
**Warning signs:** `docker compose ps` shows `(health: starting)` for the first 30 s (healthcheck `start-period=30s`), then `unhealthy`.

### Pitfall 2: Compose `run` and `up` share one `command`
**What goes wrong:** `docker compose run --rm pumpgrok` (Phase 1 criterion 4) uses the same service command as `up`. Making the service long-running makes Phase 1's criterion never finish.
**How to avoid:** either amend the Phase 1 literal to pass explicit one-shot arguments, or use a second service. The ROADMAP names `pumpgrok` for both; this needs user approval (D1).

### Pitfall 3: Dockerfile omits `.python-version` (R49 V-3)
**What goes wrong:** `COPY pyproject.toml uv.lock README.md ./` (`Dockerfile:11`) does not copy `.python-version`, so `uv sync --frozen` may not select the pinned Python 3.12. `.dockerignore` does not exclude `.python-version`, so adding it is safe.
**Fix:** `COPY .python-version pyproject.toml uv.lock README.md ./` before the sync.

### Pitfall 4: HEALTHCHECK calls `pumpgrok doctor`, not `/healthz`
**What goes wrong:** `Dockerfile:28-29` runs `pumpgrok doctor`, which only checks module presence (`doctor.py` `SUBSYSTEMS`). The CONTEXT requires `/healthz`.
**Fix:** use the FOUNDATION 3.3 pattern: a stdlib `urllib.request` probe of `http://127.0.0.1:${PUMPGROK_HEALTH_PORT}/healthz` (no curl in slim images). `PUMPGROK_HEALTH_PORT` is not a settings field today (no `health` match in `config/settings.py`), so add it with a default of 8080 for the container and 0 under `--once`/`--replay`.
**Warning:** the probe must run only when the server is serving; under the one-shot CMD the port is 0 and the probe would fail (harmless for `run`, but noisy in logs).

### Pitfall 5: Bind-mounting `./var` and file ownership
**What goes wrong:** the image creates `/app/var` owned by the `pumpgrok` system user (`Dockerfile:20-22`). A host bind mount replaces it with the host directory, owned by the host user. Writes by the container user then fail on Linux hosts.
**Fix:** document the host UID requirement in `docs/runbooks/start_stop.md`, or use a named volume. Do not add `user:` mapping silently; it changes the security posture.

### Pitfall 6: `security-pr.yml` never runs on main
**What goes wrong:** the `on:` block lists only `pull_request` (`security-pr.yml:16-18`). `gh run list --workflow security-pr.yml --branch main` returns nothing until a push trigger on `main` exists and a run completes after merge.
**Fix:** add `push: branches: [main]` (CONTEXT lock). The guard test `ci/tests/test_security_workflows.py` pins `runs-on: ubuntu-latest` (lines 83-85) and asserts the pip-audit substring `pip-audit -r req.txt --strict` (lines 173-176). Both remain satisfiable.

### Pitfall 7: pip-audit runs from a global pip install, not `uv run`
**What goes wrong:** `security-pr.yml:229` installs `pip-audit` with `pip install "uv==0.13.4" pip-audit` and then calls bare `pip-audit`. CONTEXT (R49 V-4) requires `uv run pip-audit -r req.txt --strict`.
**Fix:** change to `uv run pip-audit -r req.txt --strict` after a `uv sync --frozen --group dev` (or rely on the dev group), so the scanned tool is the locked one. The guard substring still matches.

### Pitfall 8: `slow` marker is not registered
**What goes wrong:** `addopts` includes `--strict-markers` (`pyproject.toml:90`), and `markers` registers only `replay` and `characterization` (`pyproject.toml:91-93`). Any `@pytest.mark.slow` causes a collection error for the whole `pytest -q` run.
**Fix:** add `"slow: multi-day soak replay (nightly; PUMPGROK_REQUIRE_SOAK=1 makes absence fail)"` to markers.

### Pitfall 9: Soak will also run on every PR
**What goes wrong:** CONTEXT says slow tests are not deselected by default. A committed soak-3d fixture (under 5 MB) makes `make test` (which runs `pytest -q`) execute the three-day soak on every PR. The upgrade plan (open item 4) budgets under 30 minutes.
**Fix:** measure once the soak exists; if PR wall time is unacceptable, this contradicts a CONTEXT discretion item and needs user approval. Also: `ci.yml` has no `schedule:` trigger; the nightly soak job needs one.

### Pitfall 10: DailyRollover semantics vs "two rollovers"
**What goes wrong:** CONTEXT says soak-3d has "three UTC days, two rollovers," while AUTO-007 says "at least one DailyRollover per day." Three days contain two midnight boundaries. If the emitter fires only on boundaries, day 1 has none and AUTO-007 fails on day 1.
**Fix:** decision D6 (recommended: emit one per UTC day including the first, so three per soak-3d, and treat "two rollovers" as the boundary count).

### Pitfall 11: Changing the ledger changes replay digests
**What goes wrong:** adding DailyRollover, span events or metric side effects changes the ledger hash chain and any golden digests. `tests/replay/test_runner_determinism.py` and `verify --fixture smoke-10m` determinism (PAPER-004) must still produce identical hashes across two runs. Two runs stay identical; but any pinned digest in tests will break.
**Fix:** grep tests for pinned digests before changing the emitter; update in the same commit.

### Pitfall 12: The `FixtureClock.jump` method the matrix assumes does not exist
**What goes wrong:** SAFETY_INVARIANTS.md INV-R-22 uses `FixtureClock.jump(-30)`. `src/pumpgrok/replay/clock.py` defines `now`, `sleep`, `timeout` (plus `advance_to` per its docstring) and no `jump`.
**Fix:** add `jump` under test-only control, or drive the skew through `advance_to` with an earlier timestamp (the ledger's skew check compares against `last_event_ts`).

### Pitfall 13: Live gate ids in code do not match the matrix
**What goes wrong:** `PRECONDITION_IDS` in code is `mode_live, live_enable_env, min_paper_days, performance_thresholds, wallet_allowlist, notional_cap, confirmation_record, adapter_registered, no_active_stop` (`live_gate.py:32-41`). The matrix INV-C-02 uses `effective_mode_live, env_live_enable, paper_window_14d, thresholds, wallet_allowlist, notional_cap, confirmation_record, adapter_registered, no_active_safety_state`.
**Fix:** decision D4. Pick one set and update the other document.

### Pitfall 14: "Each precondition independently" cannot be shown by changing inputs alone
**What goes wrong:** preconditions 5-9 are hard-coded `False` (`live_gate.py:80-86`; the ninth row at line 84 reads "halt, kill switch and breaker state are not readable in this release"). No environment can make them true, so an input-driven test cannot show the gate fails only on that one line.
**Fix:** the parametrised test should replace one row's evaluator (monkeypatch `LiveGate.evaluate` to return all rows met except the target) and assert exit 3 with exactly that id as `[ ]` on stderr. Also assert the existing aggregate header `LIVE GATE: refusing to start in mode=live.` (asserted at `test_live_gate_fails_fast.py:60`).

### Pitfall 15: `live.enabled` is not read
**What goes wrong:** precondition 1 is `mode_live = self._mode == "live"` (`live_gate.py:63`); `[live] enabled` is never consulted. CONTEXT requires the gate to read it inside precondition (1), which needs an R21 amendment.
**Fix:** after amendment, precondition 1 requires effective mode live AND `[live] enabled = true`; overlays keep `enabled = false`, so the gate stays closed.

### Pitfall 16: `killswitch set --flatten` does not exist
**What goes wrong:** CONTEXT says kill flatten is `pumpgrok killswitch set --flatten`. The CLI has `killswitch set --reason` (`cli.py:458-459`) and a separate `killswitch flatten --reason` (`cli.py:460-463`).
**Fix:** runbooks document `pumpgrok killswitch flatten --reason <text>`; decision D5 records the drift.

### Pitfall 17: Matrix table cells contain `|` inside backticks
**What goes wrong:** INV-R-01's test cell contains `[env_at_start|file|alert]` (section 6 row). Naive `|` splitting breaks the parser. Matrix cells also use placeholders such as `[*]` and `[<variant>]`.
**Fix:** the meta-test parser must handle pipes inside code spans, and map `[*]` and `[<variant>]` to collected node-id prefixes, or the doc should escape pipes as `\|`.

### Pitfall 18: `.receipts/**/*.json` is gitignored
**What goes wrong:** `.gitignore` ignores `.receipts/**/*.json` except `.gitkeep`. `.receipts/bot-00-chief/complete-phase-5.json` will not be committed unless force-added or the ignore rule gets an exception.
**Fix:** add `!.receipts/bot-00-chief/complete-phase-5.json` (or the specific receipt pattern) in the same change. Recorded in D3.

### Pitfall 19: Runbook command test must ignore prose and check code fences only
**What goes wrong:** `setup.md` uses `cp .env.example .env` inside a bash block (`docs/runbooks/setup.md`, Quick start). That is not canonical, `pumpgrok` or `docker compose`.
**Fix:** either describe the copy in prose, or add an explicit allowlist entry in the test with a reason. Do not weaken the test silently.

### Pitfall 20: Ownership and receipts are per seat
**What goes wrong:** `gates.yml` derives the acting bot from the branch prefix and checks a receipt under `.receipts/$BOT/`. Phase 5 touches paths owned by several seats: `docs/runbooks/**` and `src/pumpgrok/supervisor/**` (bot-00-chief); `.github/workflows/**`, `SECURITY.md`, `rules/**`, `scripts/check.sh`, `ci/security/**`, `docs/RISK_POLICY.md` and `src/pumpgrok/core/**` (bot-02-risk); `CHANGELOG.md` (bot-09-journal per CONTEXT).
**Fix:** split the work into per-owner branches, each with its own receipt. Verify the owners in `ownership.yaml` with `python3 ci/gates/check_ownership.py --validate-manifest` before planning.

### Pitfall 21: Generated files
**What goes wrong:** `prompts-assembled/SCOUT.xml` and `agents/scout.md` are generated from `prompts/bot-01-scout.xml` and the templates. Editing generated files directly fails `scripts/assemble-prompts.sh --check` and `generate-templates.py --check` (both in `make check`).
**Fix:** edit the sources and rerun `bash scripts/assemble-prompts.sh` and `python3 scripts/generate-templates.py`.

### Pitfall 22: `docs/RISK_POLICY.md` cites a file that does not exist
**What goes wrong:** the policy names `src/pumpgrok/risk/limits.py` as the home of the budget (lines 7 and 39). The risk package has `engine.py`, `killswitch.py`, `breakers.py`, `sizing.py` and `__init__.py` only.
**Fix:** RISK-owned doc fix in the RISK-007 change (point to the real module that holds `RiskBudget`).

### Pitfall 23: Phase 4 verification is not evidence for Phase 5 items
**What goes wrong:** `04-VERIFICATION.md` reports "No gaps" for Phase 4 criteria. It did not check the health server is served, the invariant matrix, metrics or DailyRollover emission.
**Fix:** treat Phase 5 gap claims in this document as the authoritative inventory.

## Code Examples

Only patterns grounded in repo code are given. External API shapes are marked `[ASSUMED]`.

### Existing health route (the insertion point for `/metrics`)
```python
# Source: src/pumpgrok/supervisor/health.py:120-130 (verified this session)
async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        request = await reader.read(65536)
        path = self._path_of(request)
        if path == "/readyz":
            code = 200 if self._is_ready() else 503
            self._respond(writer, code, {"ready": self._is_ready()})
        else:
            status = dict(self._get_status())
            code = 200 if is_ok(status) else 503
            self._respond(writer, code, status)
```

### Fault injection today (what FaultInjector can and cannot do)
```python
# Source: tests/harness/faults.py:70-88 (verified this session)
# FaultInjector.apply(events) yields the stream with one index faulted:
#   STALE rewinds ts_utc; TIMEOUT / RATE_LIMIT / RAISE raise; UNWRITABLE affects open_sink only.
# It cannot fault an LLM client, an RPC endpoint, a data source, a price source,
# an execution adapter or a ledger store. Those need fakes (see Architecture Pattern 5).
```

### Compose service the criterion needs (target shape; values from CONTEXT lock)
```yaml
# Source: CONTEXT lock + FOUNDATION_STACK.md 3.4 [CITED: docs/FOUNDATION_STACK.md:327-355]
services:
  pumpgrok:
    build: .
    image: pumpgrok:local
    container_name: pumpgrok
    env_file:
      - path: .env
        required: false
    environment:
      PUMPGROK_PROFILE: "${PUMPGROK_PROFILE:-paper}"
      PUMPGROK_HEALTH_PORT: "8080"
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./var:/app/var
    stop_grace_period: 45s
    # command, restart and healthcheck depend on decisions D1 and D9
```
The current file (`docker-compose.yml`) has no `volumes`, `stop_grace_period` or `healthcheck`, and its header comment explicitly forbids a restart policy under the one-shot design.

## Decisions Required (escalate to user before planning the affected items)

| ID | Question | Conflict | Options | Recommendation |
|----|----------|----------|---------|----------------|
| D1 | How does `docker compose up -d pumpgrok` reach `healthy` via `/healthz` with no live data? | ROADMAP criterion 3 vs Phase 1 criterion 4 (one-shot `docker compose run --rm pumpgrok`); INV-C-11 (port 0 under `--replay`); no live DataSource wired; R47 (pump.fun REST returns HTTP 530) | (a) Amend Phase 1 criterion 4 to pass explicit one-shot args; make the service default a long-running `run --mode paper --serve` that replays a recorded dataset in a loop and serves health; amend INV-C-11 so `--serve` enables the port. (b) Keep the one-shot design and change criterion 3 to a probe-based check. (c) Build live feed plumbing (out of scope; not feasible with R47) | (a), with the health body labelled `ledger_source=replay` so it is never mistaken for live data. Requires explicit approval of two ROADMAP/INV amendments |
| D2 | Must all 56 missing invariant-matrix owning tests exist for `test_invariant_matrix_tests_exist`? | CONTEXT lists the meta-test as a deliverable that parses every row; 56 of 66 path references are missing, including Phase 1-4 rows | (a) Implement all 56 (large; many are small AST or unit tests). (b) Narrow the meta-test to Phase 5 rows and record the rest as REVIEW debt | (a). Reducing scope requires explicit user approval (completeness rule) |
| D3 | How is the census made honest? | The literal `rg` command omits hidden directories (`.planning/`, `.github/`, `.receipts/`). Two AGENTS.md hits (lines 286 and 359) sit inside the GSD stack block (`AGENTS.md:99-361`), which CONTEXT forbids editing; that block is generated from `.planning/research/STACK.md` | (a) Keep the literal command; add `--hidden` and exclude `.planning/**` as historical records (amends CONTEXT's command). (b) Edit `.planning/research/STACK.md` and regenerate the GSD block. Also add the receipt ignore exception (Pitfall 18) | (a) for `.planning/**`; (b) for the two AGENTS hits. Both need user sign-off because the census command is locked |
| D4 | Which precondition ids and what does precondition 1 read? | Code ids (`live_gate.py:32-41`) differ from matrix ids (INV-C-02); code does not read `[live] enabled` | Adopt code ids and update the matrix, or the reverse. Amend R21 so precondition 1 includes `enabled` | Adopt code ids; amend R21 as CONTEXT states |
| D5 | Kill flatten command | CONTEXT says `killswitch set --flatten`; CLI has `killswitch flatten --reason` | Document the existing verb, or add a `--flatten` flag to `set` | Document the existing `flatten` verb; no new flag |
| D6 | DailyRollover per day | "two rollovers" for three days vs "at least one per day" | Emit one per UTC day including day 1 (three total) vs boundaries only | Emit per UTC day including day 1; AUTO-007 is the stricter reading |
| D7 | SEC-005 evidence | `gh` cannot authenticate here; a main-branch run only exists after merge; SECURITY.md has no table | Wait for a real green main run after the push trigger lands, or list genuinely failing checks with fingerprint, reason, owner and ISO expiry | Add the push trigger, then rely on the first main run; list only checks that actually fail. Do not pre-list anything |
| D8 | R65 live curve-layout probe | Probe attempted and failed (`tests/fixtures/rpc/bonding_curve/layout.json` records `getProgramAccounts` timeouts); layout is ASSUMED | Run the live probe (network, needs approval) or record as REVIEW | Keep fail-closed behaviour (already implemented: `curve_layout.py:30-35`); record REVIEW in the milestone report; do not run a live probe without approval |
| D9 | Restart policy | FOUNDATION 3.4 has `restart: unless-stopped`; R50 forbids any restart policy for the one-shot design | Add only with a long-running command (D1) | Add only after D1 is approved |
| D10 | Runner label | CONTEXT discretion says `[self-hosted, Linux, X64]`; `ci/tests/test_security_workflows.py:83-85` asserts `ubuntu-latest` for every job | Keep hosted runners and keep the guard, or change the guard | Keep `ubuntu-latest`; the guard is RISK-owned and FOUNDATION U-3 is unresolved |
| D11 | Nightly soak schedule | `ci.yml` has no `schedule:` trigger; CONTEXT wants nightly `pytest -q -m slow tests/soak` with `PUMPGROK_REQUIRE_SOAK=1` | Add schedule to `ci.yml` (RISK-owned) | Add it; it is a required milestone item |

## Phase 4 Carry-Overs (R62, R64, R65): status

| Item | Requirement | Evidence found this session | Status |
|------|-------------|------------------------------|--------|
| R62 degraded reputation book | Refuse buys, exits still run, `reputation_degraded` breaker-scope reason, Escalation; tests in `tests/safety/` | `risk/engine.py:10,138,689` describe and implement `reputation_degraded`; `tests/safety/test_reputation_degraded.py` exists (8.7 KB) | Implemented in code; the test has not been executed here |
| R64 atomic consume-and-order, verb coverage | Approval consumption in the same ledger transaction; a repeated decision returns the first fill; a by-key read path; TOOL-011 full verb coverage and removal of exit 5 for served verbs | `ledger/store.py:415` `by_key`; `tests/tools/test_verb_coverage.py` exists; `cli.py:86` still defines `EXIT_NOT_IMPLEMENTED = 5`, used by `run --record` (`cli.py:537`) and by absent-subsystem envelopes (`cli.py:168`) | Partially evidenced; needs a verb-by-verb check against `test_verb_coverage.py` before the milestone report |
| R65 bonding-curve layout | ASSUMED until a live probe; no paper entry may consume an RPC-derived price while ASSUMED | `tools/onchain/curve_layout.py:30-35`: `LAYOUT_STATUS: Final[str] = "ASSUMED"` and "the PaperAdapter refuses with data_unavailable (fail closed)"; `tests/fixtures/rpc/bonding_curve/layout.json` records a failed probe | Fail-closed in code; probe not verified (decision D8) |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker daemon | Container build, compose healthy check | Yes (server running) | Docker 29.6.2 (server 29.6.2, overlayfs, cgroup v2) | None needed |
| Docker Compose | `docker compose` criteria | Yes | v5.3.1 | None needed |
| Base image `python:3.12-slim` | Dockerfile builder/runtime | Not cached locally; `registry-1.docker.io/v2/` answers HTTP 401 (reachable, auth needed for pull) | n/a | Pull at build time [ASSUMED: anonymous pull succeeds] |
| `ghcr.io/astral-sh/uv:0.13.4` | Dockerfile builder | Reachable (`ghcr.io/v2/` HTTP 401); not cached | 0.13.4 | Pull at build time [ASSUMED] |
| uv | Locking, `uv run` | Yes, wrong version | 0.11.26 on host; 0.13.4 required | Install 0.13.4 before `uv lock` / `uv add` |
| Python | Runtime | `/usr/bin/python3` present; version not recorded | unknown; project pins 3.12 | Use `uv` managed Python per `.python-version` |
| `gh` CLI | SEC-005 criterion | Installed but not authenticated: token in GH_TOKEN is invalid | 2.45.0 | None here; SEC-005 evidence must come from a working environment (D7) |
| gitleaks, bandit, semgrep, pip-audit, trivy on host | Local security scans | Not on PATH | n/a | CI installs them; do not run locally unless approved |
| Network (pypi.org, github.com) | Dependency add, legitimacy checks | Yes (HTTP 200) | n/a | n/a |

**Missing dependencies with no fallback:** a working `gh` login (needed to read the main-branch security run for SEC-005; D7).
**Missing dependencies with fallback:** uv 0.13.4 (install first); scanners (CI only).

## Validation Architecture

Literal commands are copied from ROADMAP Phase 5 success criteria (`.planning/ROADMAP.md`, Phase 5 block), CONTEXT checkpoint (specifics b), and the census. "EXISTS" or "MISSING" is the file state read this session. No test was executed.

### ROADMAP Phase 5 success criteria

| # | Literal command (verbatim) | Depends on (file: state) |
|---|----------------------------|--------------------------|
| SC1 | `uv run pytest -q tests/soak/test_soak_multiday_replay.py tests/degradation/` | `tests/soak/test_soak_multiday_replay.py`: MISSING. `tests/degradation/` directory: MISSING, must contain `test_llm_failure.py`, `test_rpc_failure.py`, `test_data_source_outage.py`, `test_ledger_unwritable.py`, `test_clock_skew.py`, `test_partial_restart.py`: all MISSING. `tests/harness/faults.py`: EXISTS (modes lack `unknown`, `malformed`). `tests/fixtures/replay/smoke-10m/`: EXISTS. `tests/fixtures/replay/soak-3d/`: MISSING. `scripts/build_soak_fixture.py`: MISSING. `pyproject.toml` `slow` marker: MISSING (Pitfall 8). DailyRollover emitter: MISSING (Pattern 3). |
| SC2 | `grep -rhoE "pumpgrok_(cycle_seconds\|bot_crashes_total\|orders_total\|equity_sol\|drawdown_pct\|data_age_seconds\|breaker_state\|kill_switch\|ledger_seq)" src/pumpgrok \| sort -u \| wc -l` prints `9`, and the metrics tests pass under `uv run pytest -q` | `src/pumpgrok/supervisor/metrics.py`: MISSING. Metrics tests (proposed `tests/supervisor/test_metrics.py`): MISSING. `src/pumpgrok/supervisor/health.py`: EXISTS (no `/metrics` branch). `prometheus-client` in `pyproject.toml` and `uv.lock`: MISSING. Current grep count: 0. |
| SC3a | `for f in setup engine start_stop kill_switch breaker_reset outage rollback reading_reports go_live; do test -f docs/runbooks/$f.md \|\| exit 1; done && ./scripts/check.sh` | `docs/runbooks/setup.md`: EXISTS (stale). Eight others: MISSING. `scripts/check.sh`: EXISTS (does not check runbooks; ASCII and emoji sweep applies). `tests/docs/test_runbook_commands.py`: MISSING. |
| SC3b | `for p in 1 2 3 4 5; do grep -q "Phase $p" CHANGELOG.md \|\| exit 1; done` | `CHANGELOG.md`: EXISTS; contains "Phase 1" only (line 5). Phases 2-5: MISSING. |
| SC3c | `docker compose up -d --build pumpgrok && docker compose ps pumpgrok` reports the service `healthy` via the supervisor `/healthz` probe | `Dockerfile`: EXISTS (COPY lacks `.python-version`; HEALTHCHECK uses `pumpgrok doctor`). `docker-compose.yml`: EXISTS (no healthcheck, no `./var` bind, no `stop_grace_period`). `supervisor/health.py`: EXISTS but not served by any process. CLI long-running `run` path: MISSING. `PUMPGROK_HEALTH_PORT` setting: MISSING. Literal `docker compose ps` immediately after `up -d` reports `starting` for up to 30 s (`start-period=30s`), so the criterion needs a bounded wait loop in the runbook (decision D1). |
| SC4a | `uv run pytest -q tests/safety/test_no_manipulation_tools.py tests/execution/test_live_gate_fails_fast.py` | `tests/safety/test_no_manipulation_tools.py`: EXISTS (four tests; no notify allowlist, browser-ops or named `test_no_posting_or_volume_tools`). `tests/execution/test_live_gate_fails_fast.py`: EXISTS (aggregate header test; no nine-way parametrisation). `docs/RISK_POLICY.md` section 4.4: EXISTS (cites the missing test name). |
| SC4b | `for f in src/pumpgrok/config/overlays/*.toml; do uv run python -c "import tomllib,sys; d=tomllib.load(open('$f','rb')); assert d.get('live',{}).get('enabled') is False, '$f'" \|\| exit 1; done` | `src/pumpgrok/config/overlays/dev.toml`, `paper.toml`, `live.toml`: EXIST; each has `[live]` with `enabled = false` (verified by reading). Expected to pass; not executed. |
| SC5 | `gh run list --workflow security-pr.yml --branch main --limit 1 --json conclusion -q '.[0].conclusion'` prints `success`, or every non-green check is listed in `SECURITY.md` with an expiry date | `.github/workflows/security-pr.yml`: EXISTS (no push trigger; `pip-audit` not via `uv run`). `SECURITY.md`: EXISTS (no exception table). `ci/security/gitleaks.toml`, `semgrep.yml`, `bandit.ini`, `bandit_json_to_sarif.py`: EXIST. `ci/tests/test_security_workflows.py`: EXISTS (guards; runs without network). `gh` authentication: BROKEN here (D7). |

### CONTEXT checkpoint and milestone commands (not ROADMAP criteria; required by CONTEXT)

| Command | Depends on (file: state) |
|---------|--------------------------|
| `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` | `src/pumpgrok/cli.py` `_run` (`cli.py:525`) and `run_once_replay` in `supervisor/scheduler.py`: EXIST. Fixture `tests/fixtures/replay/smoke/`: EXISTS. |
| `uv run pytest -q -m slow tests/soak` (nightly) | `tests/soak/`: MISSING. `slow` marker: MISSING. `ci.yml` `schedule:`: MISSING (D11). |
| `rg -n -P '(?<![\w/])tools/(README\|authority_check\|desk_state\|holder_check\|jupiter_quote\|paper_sim\|pipeline_evidence\|priority_fee\|ticket_helper)' --glob '!docs/**' --glob '!vendor/**' --glob '!.git/**'` must print nothing | Literal census prints about 86 lines across about 40 files (skills, README, SETUP, ARCHITECTURE, AGENTS, agents, prompts, rules, hermes, scripts, `src/pumpgrok/ledger/desk_bus.py`, `src/pumpgrok/ledger/export.py`, three `src/pumpgrok/tools/onchain/*` modules, five characterization tests, and the root `tools/` modules). The hidden-directory variant adds historical `.planning/**` hits (D3). |
| Second census (proposed, missing from CONTEXT): `rg -n 'ROOT / "tools"\|TOOLS =\|spec_from_file_location' tests` | `tests/test_tools_cli.py:35` (`TOOLS = ROOT / "tools"`) and `:40` (`spec_from_file_location`) load six root modules and README. The literal census cannot see them. |
| `test ! -d tools` | Root `tools/` directory: EXISTS today. |
| `ci/tests/test_gates.py::test_invariant_matrix_tests_exist` | `ci/tests/test_gates.py`: EXISTS; the named test: MISSING. Parses `docs/SAFETY_INVARIANTS.md` section 6 (lines 240-309). 56 of 66 referenced files are MISSING. |
| `.receipts/bot-00-chief/complete-phase-5.json` | MISSING; gitignored by `.receipts/**/*.json` (Pitfall 18). |

### Requirement-level test files (proposed; none exist yet)
| Requirement | Test file(s) to create or extend | State |
|-------------|----------------------------------|-------|
| AUTO-007 | `tests/soak/test_soak_multiday_replay.py` (`test_soak_replay_bounded_memory`, `test_soak_short_pr`) | MISSING |
| AUTO-008 | `tests/degradation/*.py` (seven files) | MISSING |
| OBS-003 | `tests/supervisor/test_metrics.py`; `tests/logging/test_spans.py`; `tests/test_doctor_probes.py` | MISSING (note `tests/logging/` directory does not exist; the matrix path `tests/logging/test_redaction.py` is also missing) |
| OBS-004 | `tests/docs/test_runbook_commands.py` | MISSING |
| OBS-005 | `ci/tests/test_gates.py::test_invariant_matrix_tests_exist`; a CHANGELOG/AGENTS check (proposed `tests/docs/test_changelog_phases.py`) | MISSING |
| RISK-007 | extend `tests/safety/test_no_manipulation_tools.py` (notify allowlist, browser-ops text scan, full registry names) | PARTIAL |
| GOLIVE-003 | extend `tests/execution/test_live_gate_fails_fast.py` (nine-way parametrisation) | PARTIAL |
| SEC-005 | extend `ci/tests/test_security_workflows.py` (push trigger on security-pr; `uv run pip-audit`) | PARTIAL |

## Security Domain

Required: `security_enforcement` is not disabled in config. Applies to this phase: logging and metrics exposure, health endpoint exposure, container surface, CI scanners, secrets in runbooks and fixtures.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no operator login in scope) | n/a; `live confirm` HMAC is Phase 4 |
| V3 Session Management | no | n/a |
| V4 Access Control | yes (who can read `/metrics` and `/healthz`) | Bind 127.0.0.1 only; compose `127.0.0.1:8080:8080`; no unauthenticated write routes |
| V5 Input Validation | yes (HTTP request line parsing) | Current `_path_of` tolerant parser; `/metrics` accepts only GET; reject other methods |
| V6 Cryptography | no new crypto | n/a |
| V7 Error handling and logging | yes | Metrics and spans must not leak secrets; RedactionFilter on every handler (OBS-001) |
| V14 Configuration | yes | Container non-root; no secrets baked in; `live.enabled = false` (SC4b) |

### Known Threat Patterns for this phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Metrics or health exposing secret-shaped values | Information disclosure | Metrics carry only numbers and labels from a fixed set; health body built from `build_status` only (no settings dump); add a test scanning `/metrics` and `/healthz` bodies against G-3 shapes |
| Health or metrics port reachable from LAN | Information disclosure, tampering via API | Bind 127.0.0.1; compose publishes `127.0.0.1:8080` only |
| Scanner bypass via `|| true` or `--exit-zero` | Tampering | Guard test already forbids these snippets (`ci/tests/test_security_workflows.py:BYPASS_SNIPPETS`) |
| Unpinned third-party actions and downloads | Tampering (supply chain) | Pin actions by SHA (FOUNDATION U-4). `security-pr.yml` uses tag pins for `actions/checkout@v4`, `actions/setup-python@v5`, `actions/upload-artifact@v4` and an unverified gitleaks tarball download (`security-pr.yml:51-53`). Recommended hardening within SEC-005; verify checksums |
| Unpinned Python tooling in CI | Tampering | `pip install semgrep` and `pip install bandit` are unpinned (`security-pr.yml:93,145`); pin versions |
| Runbook command injection by copy-paste | Tampering | Command test (OBS-004) plus no `curl` in runbooks |
| Replayed fixtures reaching live gate | Spoofing of paper window | LiveGate refuses ledgers containing `source=replay` (existing, INV-C-09) |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | prometheus-client Counter names: declaring `..._total` yields exposition `..._total` (and un-suffixed names get `_total` appended) | Pattern 1 | Wrong metric names in `/metrics`; the grep in SC2 would still pass but scrapes would not match dashboards. Mitigate with an exposition test |
| A2 | `CollectorRegistry(auto_describe=True)`, `generate_latest`, `CONTENT_TYPE_LATEST` names and signatures | Code Examples | Compile error in planning; verify against installed package |
| A3 | Anonymous pull of `python:3.12-slim` and `ghcr.io/astral-sh/uv:0.13.4` succeeds from this host | Environment Availability | Image build blocked; needs registry login |
| A4 | Compose `healthy` status appears after one successful healthcheck within `start-period` plus `interval` (30 s + 30 s) | Pitfall 1 | Criterion timing differs; planner must add a bounded wait |
| A5 | Root `tools/` is not referenced by any external operator config | Runtime State Inventory | Operator-side breakage after deletion; confirm with user |
| A6 | Soak-3d replay finishes under 30 minutes on the runner | Pitfall 9 | Nightly job timeout; measure |
| A7 | `ci.yml` nightly schedule can run on `ubuntu-latest` within minutes | D11 | Quota or cost; decision D10 |
| A8 | No test in `tests/` pins a ledger digest that a new DailyRollover would change | Pitfall 11 | Failing determinism tests; grep before emitter change |

## Open Questions

1. **Long-running entrypoint and data plane (D1).**
   - What we know: `Supervisor.serve_forever` and `HealthServer` exist; no CLI path wires them; no live DataSource is wired; R47 documents pump.fun REST HTTP 530.
   - What's unclear: which recorded or live data the serving loop uses.
   - Recommendation: approve option (a) in D1 with the health body labelled `ledger_source=replay`.
2. **Matrix scope (D2).** Whether the 56 missing owning tests are in scope for Phase 5.
3. **Census policy (D3).** Whether `.planning/**` is excluded and whether a GSD-block edit is allowed.
4. **Live precondition ids and rule 1 (D4).**
5. **DailyRollover count (D6).**
6. **SEC-005 evidence (D7).** Who runs the first main-branch security run, and where its result is recorded.
7. **R65 probe (D8).** Whether a live probe is approved.
8. **Restart policy (D9)** and **nightly schedule (D11)**.
9. **Soak in default PR runs (Pitfall 9).** Whether the three-day soak may run on every PR, given CONTEXT's "not deselected by default".

## Sources

### Primary (HIGH confidence, read in this session)
- `.planning/phases/05-hardening/05-CONTEXT.md` (all sections)
- `.planning/ROADMAP.md` Phase 5 block (lines ~155-179)
- `.planning/REQUIREMENTS.md` (RISK-007, AUTO-007, AUTO-008, OBS-003..005, SEC-005, GOLIVE-003)
- `.planning/STATE.md`, `.planning/phases/04-paper-trading-and-autonomy/04-CONTEXT.md` (binding resolutions R62, R64, R65)
- `docs/SAFETY_INVARIANTS.md` sections 1-3 and 6 (rows 244-309, counts at line 311)
- `docs/RISK_POLICY.md` sections 2.2, 3.3, 4.1-4.4
- `docs/FOUNDATION_STACK.md` sections 3.3-3.4 (lines 290-355), section 6 canonical commands (line 708+)
- `docs/upgrade-plan-desk-v2.md` (R44-R49 rows; deliverables 5D, 5E; open items 4, 7)
- `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.gitignore`, `Makefile`, `pyproject.toml`, `ownership.yaml` (ownership rules around lines 137-160), `SECURITY.md`, `CHANGELOG.md`, `AGENTS.md` (GSD markers at lines 99, 361, 405)
- `.github/workflows/{ci,gates,security-pr}.yml`; `ci/tests/test_security_workflows.py`
- `src/pumpgrok/cli.py` (lines 86, 368-485, 525-545, 1063), `src/pumpgrok/supervisor/{health,scheduler,seat_task,lifecycle}.py`, `src/pumpgrok/ledger/{events,reducer,store}.py`, `src/pumpgrok/core/{registry,tool,correlation,llm}.py`, `src/pumpgrok/replay/clock.py`, `src/pumpgrok/execution/live/live_gate.py`, `src/pumpgrok/config/overlays/*.toml`, `src/pumpgrok/doctor.py`, `src/pumpgrok/tools/onchain/curve_layout.py`
- `tests/harness/faults.py`, `tests/safety/test_no_manipulation_tools.py`, `tests/execution/test_live_gate_fails_fast.py`, `tests/test_tools_cli.py`, `tests/fixtures/replay/smoke-10m/generator.py`, `tests/fixtures/rpc/bonding_curve/layout.json`
- Host probes: `docker info`, `docker compose version`, `gh auth status`, `uv --version`, `which` for toolchain, `docker images`, registry HTTP probes, PyPI JSON for `prometheus-client` and `uv==0.13.4`

### Secondary (MEDIUM)
- Package legitimacy seam output (`gsd-tools.cjs query package-legitimacy check`) for prometheus-client: SUS, `unknown-downloads`

### Tertiary (LOW, training knowledge; flagged)
- prometheus_client API details (Assumptions A1, A2)

## Metadata

**Confidence breakdown:**
- Current-state gaps: HIGH (direct reads and literal greps this session)
- Standard stack: HIGH for versions from PyPI JSON; MEDIUM for API shapes (A2)
- Architecture: MEDIUM (design choices flagged in Open Questions)
- Pitfalls: HIGH for cited lines; MEDIUM for behaviour not executed
- Runtime outcomes (compose healthy, soak timing, scanner results, `gh` run status): LOW (not executed; intentionally not run per assignment)

**Research date:** 2026-10-22
**Valid until:** 2026-11-21 for in-repo facts (re-verify if any Phase 5 file changes); 7 days for PyPI versions and registry reachability (fast-moving)

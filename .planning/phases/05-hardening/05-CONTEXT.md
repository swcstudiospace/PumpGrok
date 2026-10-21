# Phase 5: Hardening - Context

**Gathered:** 2026-10-21
**Status:** Ready for planning
**Mode:** Seeded from design docs (discuss replaced; decisions locked by R16-R49)

<domain>
## Phase Boundary

Metrics and spans, `/metrics`, nine runbooks, CHANGELOG and AGENTS index, degradation and soak suites, security CI, go-live proof with live disabled, deletion of root `tools/` at zero census.

Requirement ids (8, ROADMAP): RISK-007, AUTO-007, AUTO-008, OBS-003, OBS-004, OBS-005, SEC-005, GOLIVE-003.
OBS: OBS-003, OBS-004, OBS-005. SEC: SEC-005. GOLIVE: GOLIVE-003.
OBS-001/002 and SEC-001/002 are Phase 1; consumed here, not rebuilt.
</domain>

<decisions>
## Implementation Decisions

### Locked
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
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `vendor/grokbot-pumpfun/src/ops.py:298-357`: HealthServer `/healthz` and `/metrics` routing (pattern only).
- `docs/FOUNDATION_STACK.md:290-355` (Dockerfile, compose), `:502-559` (CI drafts).

### Established Patterns
- HEAD `1f7cb6e` has no `src/`, `ci/`, `.github/`, runbooks, CHANGELOG, SECURITY.md, Dockerfile or compose (`ls`); Phases 1-4 create them.
- `AGENTS.md:295-298` is GSD-managed; never edit inside GSD markers.

### Integration Points
- `supervisor/health.py`, `supervisor/seat_task.py`, `core/registry.py`, `config/overlays/*.toml`.
</code_context>

<specifics>
## Specific Ideas

(a) Verification must be automated: every success criterion is a command; no human_verification items; no live network in tests; recorded or synthetic fixtures only.

(b) Checkpoint: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0; then ROADMAP Phase 5 criteria 1-5; `uv run pytest -q -m slow tests/soak` in nightly CI. Census must print nothing, then `test ! -d tools`: `rg -n -P '(?<![\w/])tools/(README|authority_check|desk_state|holder_check|jupiter_quote|paper_sim|pipeline_evidence|priority_fee|ticket_helper)' --glob '!docs/**' --glob '!vendor/**' --glob '!.git/**'` (lookbehind excludes `src/pumpgrok/tools/`).

(c) Fixtures: `tests/fixtures/replay/smoke` (checkpoint), `smoke-10m` (AUTO-006, PR soak), `soak-3d` (nightly), `tests/fixtures/{http/adversarial,llm}/*.json`, `tests/fixtures/secrets/*.txt`.
</specifics>

<deferred>
## Deferred Ideas

- FOUNDATION 5.5 extra metric families, `pumpgrok_ws_duplicates_total`, OpenTelemetry, dashboards: v1.x.
- Manual breaker-reset verb (user decision); operator-recorded soak-3d: v1.x.
- Phase 4 owns GOLIVE-001/002, SEC-004, `/readyz`, STRUCT-006. No live adapter ships.
</deferred>

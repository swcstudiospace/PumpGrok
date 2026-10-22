---
phase: "5"
slug: "hardening"
# status lifecycle: draft (seeded by plan-phase) -> validated (set by validate-phase sec 6)
# audit-milestone sec 5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-22"
---

# Phase 5 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (`>=9.1.1,<10`) with pytest-asyncio (`>=1.4.0,<2`, `asyncio_mode = "auto"`) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` (addopts `-q --strict-markers`; `slow` marker MISSING, Wave 0) |
| **Quick run command** | `uv run pytest -q tests/safety/test_no_manipulation_tools.py tests/execution/test_live_gate_fails_fast.py` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | not measured; provisional ~1800 seconds including soak-3d (A6) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q tests/safety/test_no_manipulation_tools.py tests/execution/test_live_gate_fails_fast.py` plus the task's own command in the map below
- **After every plan wave:** Run `uv run pytest -q` and the ROADMAP criterion commands mapped to that wave
- **Before `/gsd:verify-work`:** Full suite must be green; every ROADMAP Phase 5 criterion command (SC1-SC5) must exit 0 or print its expected value
- **Max feedback latency:** 1800 seconds (provisional, not measured; soak-3d budget per A6)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 5-SC1 | TBD | TBD | AUTO-007, AUTO-008 | - | Soak memory growth bounded; unhandled exceptions fail the test; one DailyRollover per UTC day; ledger verifies; each AUTO-005 fault row degrades without unhandled failure | integration (FixtureClock) | `uv run pytest -q tests/soak/test_soak_multiday_replay.py tests/degradation/` | MISSING W0: tests/soak/test_soak_multiday_replay.py; tests/degradation/ (test_llm_failure.py, test_rpc_failure.py, test_data_source_outage.py, test_ledger_unwritable.py, test_clock_skew.py, test_partial_restart.py); tests/fixtures/replay/soak-3d/; scripts/build_soak_fixture.py. EXISTS: tests/harness/faults.py (no unknown/malformed modes); tests/fixtures/replay/smoke-10m/ | pending |
| 5-SC2 | TBD | TBD | OBS-003 | Information disclosure: metrics carry numbers and labels only | `/metrics` exposes exactly the nine families verbatim; equity computed at scrape time only | unit + static grep | `grep -rhoE "pumpgrok_(cycle_seconds\|bot_crashes_total\|orders_total\|equity_sol\|drawdown_pct\|data_age_seconds\|breaker_state\|kill_switch\|ledger_seq)" src/pumpgrok \| sort -u \| wc -l` (expect 9), then `uv run pytest -q` | MISSING W0: src/pumpgrok/supervisor/metrics.py; tests/supervisor/test_metrics.py; prometheus-client absent from pyproject.toml and uv.lock. EXISTS: src/pumpgrok/supervisor/health.py (no /metrics branch) | pending |
| 5-SC3a | TBD | TBD | OBS-004, OBS-005 | - | Nine runbooks exist; commands limited to canonical, `pumpgrok` and `docker compose` verbs; no curl in runbooks | doc / static | `for f in setup engine start_stop kill_switch breaker_reset outage rollback reading_reports go_live; do test -f docs/runbooks/$f.md \|\| exit 1; done && ./scripts/check.sh` | MISSING W0: docs/runbooks/{engine,start_stop,kill_switch,breaker_reset,outage,rollback,reading_reports,go_live}.md; tests/docs/test_runbook_commands.py. EXISTS: docs/runbooks/setup.md (stale, Pitfall 19); scripts/check.sh | pending |
| 5-SC3b | TBD | TBD | OBS-005 | - | CHANGELOG carries a heading for each of Phases 1-5 | doc / static | `for p in 1 2 3 4 5; do grep -q "Phase $p" CHANGELOG.md \|\| exit 1; done` | EXISTS: CHANGELOG.md (Phase 1 only, line 5). MISSING W0: tests/docs/test_changelog_phases.py (proposed) | pending |
| 5-SC3c | TBD | TBD | FOUND-003, OBS-004 | - | Container runs non-root; health served on 127.0.0.1:8080 only; healthcheck probes /healthz | container / integration | `docker compose up -d --build pumpgrok && docker compose ps pumpgrok` (service reports healthy; bounded wait loop needed, start-period 30 s) | EXISTS: Dockerfile (no .python-version COPY; HEALTHCHECK runs pumpgrok doctor); docker-compose.yml (no healthcheck, no ./var bind). MISSING: long-running run path (decision D1); PUMPGROK_HEALTH_PORT setting | pending |
| 5-SC4a | TBD | TBD | RISK-007, GOLIVE-003 | - | Manipulation-tool scan covers social, notify and browser-ops; each of the nine live preconditions fails fast with exit 3 and its own id | unit (AST / text scan) | `uv run pytest -q tests/safety/test_no_manipulation_tools.py tests/execution/test_live_gate_fails_fast.py` | EXISTS (PARTIAL): both files. MISSING extension: notify allowlist, browser-ops scan, nine-way parametrisation. docs/RISK_POLICY.md sec 4.4 cites missing test name test_no_posting_or_volume_tools | pending |
| 5-SC4b | TBD | TBD | GOLIVE-003 | - | `live.enabled = false` in dev, paper and live overlays | static config | `for f in src/pumpgrok/config/overlays/*.toml; do uv run python -c "import tomllib,sys; d=tomllib.load(open('$f','rb')); assert d.get('live',{}).get('enabled') is False, '$f'" \|\| exit 1; done` | EXISTS: src/pumpgrok/config/overlays/dev.toml, paper.toml, live.toml | pending |
| 5-SC5 | TBD | TBD | SEC-005 | Tampering: unpinned actions and tooling in security-pr.yml; scanner bypass via `\|\| true` or `--exit-zero` | CI evidence | `gh run list --workflow security-pr.yml --branch main --limit 1 --json conclusion -q '.[0].conclusion'` (expect success), OR every non-green check listed in SECURITY.md with ISO expiry | EXISTS: .github/workflows/security-pr.yml (pull_request trigger only); SECURITY.md (no exception table); ci/tests/test_security_workflows.py (PARTIAL). gh NOT AUTHENTICATED in this environment (D7) | pending |
| 5-CP | TBD | TBD | Phase checkpoint | - | Smoke replay completes one skip-only cycle with no network access | smoke | `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` | EXISTS: src/pumpgrok/cli.py (_run); supervisor/scheduler.py (run_once_replay); tests/fixtures/replay/smoke/ | pending |
| 5-MS | TBD | TBD | OBS-005 | - | Invariant matrix owning tests exist for every row of docs/SAFETY_INVARIANTS.md section 6 | meta-test | `uv run pytest -q ci/tests/test_gates.py::test_invariant_matrix_tests_exist` | MISSING W0: named test; 56 of 66 referenced files MISSING (decision D2 scope) | pending |

*Status: pending / green / red / flaky*

*Task IDs 5-SCn, 5-CP and 5-MS are provisional (Plans TBD); plan-phase replaces them with {N}-{plan}-{task} IDs.*

---

## Wave 0 Requirements

- [ ] `tests/soak/test_soak_multiday_replay.py` - stubs for AUTO-007 (`test_soak_replay_bounded_memory`, `test_soak_short_pr`)
- [ ] `tests/degradation/test_llm_failure.py`, `test_rpc_failure.py`, `test_data_source_outage.py`, `test_ledger_unwritable.py`, `test_clock_skew.py`, `test_partial_restart.py` - stubs for AUTO-008 (research also cites seven files in one table; the six named files are listed here)
- [ ] `tests/harness/faults.py` - add `unknown` and `malformed` FaultMode values; service fakes for LLM client, RPC endpoint, data source, price source and ledger store
- [ ] `tests/fixtures/replay/soak-3d/` and `scripts/build_soak_fixture.py` - synthesised from smoke-10m (seed 20260101; three UTC days)
- [ ] `pyproject.toml` - register `slow` marker (Pitfall 8)
- [ ] `src/pumpgrok/supervisor/metrics.py` and `tests/supervisor/test_metrics.py` - stubs for OBS-003 (nine families)
- [ ] `tests/logging/test_spans.py` (directory `tests/logging/` does not exist) - stubs for OBS-003 span timings
- [ ] `tests/test_doctor_probes.py` - stubs for `pumpgrok doctor` probes of /healthz and /metrics
- [ ] `tests/docs/test_runbook_commands.py` - OBS-004 command contract
- [ ] `tests/docs/test_changelog_phases.py` - OBS-005 CHANGELOG check
- [ ] `prometheus-client` (`>=0.26,<0.27`, under uv 0.13.4) - add only after a `checkpoint:human-verify` task (SUS legitimacy verdict)
- [ ] Framework: pytest and pytest-asyncio already present; no framework install needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Compose service reaches healthy via supervisor /healthz | FOUND-003, OBS-004 (SC3c) | Needs a running Docker daemon and image pulls (python:3.12-slim, ghcr.io/astral-sh/uv:0.13.4; anonymous pull ASSUMED); not executed during research | Run `docker compose up -d --build pumpgrok`, then poll `docker compose ps pumpgrok` until `healthy`, allowing for start-period 30 s plus interval |
| Security workflow green on main | SEC-005 (SC5) | Needs an authenticated `gh` (GH_TOKEN currently invalid) and a push to main that triggers the new workflow; cannot exist before merge | After merge, run the SC5 `gh run list` command; otherwise list each failing check in SECURITY.md with fingerprint, reason, owner and ISO expiry |
| Scope decisions D1, D2, D3, D7 | OBS-004, OBS-005, SEC-005, GOLIVE-003 | User approval required before planning (completeness rule); not an automated test | Record the user decision in 05-CONTEXT.md, then re-run plan-phase |
| Soak-3d runtime on PR runs | AUTO-007 | Whether the soak runs on every PR (Pitfall 9, A6) needs measurement on the runner | Measure after the soak exists; escalate if PR wall time is unacceptable |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 1800s (provisional)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

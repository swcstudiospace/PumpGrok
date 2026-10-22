---
phase: 05-hardening
verified: 2026-10-22T13:10:00Z
status: gaps_found
score: 4/5 success criteria verified
gaps:
  - truth: "SC5: security-pr.yml green on main, or every non-green check listed in SECURITY.md with an expiry date (SEC-005)"
    status: failed
    reason: "gh run list --workflow security-pr.yml --branch main returns HTTP 404 (no workflow run exists on main), exit 1; SECURITY.md exceptions table has a header row and zero exception rows, so the alternative compliance path is also unmet."
    artifacts:
      - path: "SECURITY.md"
        issue: "Exceptions table (line 63-64) contains only the header; zero rows."
    missing:
      - "A green security-pr.yml run on main, or exception rows with expiry dates in SECURITY.md"
---

# Phase 5: Hardening Verification Report

**Phase Goal:** The desk survives multi-day replay, injected faults and restarts;
exposes metrics and health; ships runbooks and proven go-live gates with live
disabled; and carries security and changelog evidence.
**Verified:** 2026-10-22T13:10:00Z
**Status:** gaps_found
**Re-verification:** No - initial verification (no prior VERIFICATION.md existed).

Method: goal-backward. Each of the 5 ROADMAP success criteria was executed
literally; exit codes and key output recorded below. SUMMARY.md claims were not
trusted: WR-01..WR-09 fix claims from 05-REVIEW.md (iteration 2) were
spot-checked against the source at HEAD c363bf6.

Environment note (pre-existing, corroborated by 01/02/04 SUMMARYs): piping
`uv run pytest` output through `tail` prints a bogus "Pytest: No tests
collected" line. File-redirected runs and `.venv/bin/python -m pytest` runs are
authoritative. All test evidence below comes from file-redirected logs
(/tmp/sc1.log, /tmp/sc1b.log, /tmp/sc4.log, /tmp/metrics.log, /tmp/docs.log)
plus `--collect-only` counts. Concurrent pytest runs were avoided (a sibling
run breaks collection in this environment); everything ran sequentially.

## Goal Achievement

### Observable Truths (success criteria)

| # | Truth (SC) | Status | Evidence |
|---|------------|--------|----------|
| 1 | Soak + degradation suite exits 0 (AUTO-007, AUTO-008) | VERIFIED | `.venv/bin/python -m pytest -q tests/soak/test_soak_multiday_replay.py tests/degradation/`: EXIT 0, 34 dots, no failures. `--collect-only`: 34 (clock_skew 2, data_outage 8, ledger_unwritable 3, llm_failure 11, partial_restart 3, rpc_failure 4, soak 3). Logs /tmp/sc1.log, /tmp/sc1b.log, /tmp/collect1.log. |
| 2 | Metric-name grep prints 9; metrics tests pass (OBS-003) | VERIFIED | `grep -rhoE "pumpgrok_(...)" src/pumpgrok \| sort -u \| wc -l` prints 9; all nine names present (bot_crashes_total, breaker_state, cycle_seconds, data_age_seconds, drawdown_pct, equity_sol, kill_switch, ledger_seq, orders_total). Metrics tests `tests/supervisor/test_metrics.py` (12) + `tests/supervisor/test_serve_mode.py` (9): EXIT 0, 21 dots. Log /tmp/metrics.log. |
| 3 | Runbooks + check.sh + CHANGELOG + healthy compose service (OBS-004, OBS-005, FOUND-003) | VERIFIED | Runbook presence loop: all 9 `docs/runbooks/*.md` present, no MISSING. `./scripts/check.sh`: EXIT 0 ("35 skills, 10 agents, 218 markdown files checked"). CHANGELOG loop `Phase 1..5`: no MISSING. `docker compose ps pumpgrok`: `Up 3 hours (healthy)`, EXIT 0. No rebuild needed (already running healthy). |
| 4 | Safety + live-gate tests exit 0; every overlay has live.enabled false (RISK-007, GOLIVE-003) | VERIFIED | `.venv/bin/python -m pytest -q tests/safety/test_no_manipulation_tools.py tests/execution/test_live_gate_fails_fast.py`: EXIT 0, 30 dots (collected 7+23=30). Overlay loop over `src/pumpgrok/config/overlays/{dev,live,paper}.toml`: all assert `live.enabled is False`, loop EXIT 0. Log /tmp/sc4.log. |
| 5 | security-pr.yml green on main, or exceptions in SECURITY.md with expiry (SEC-005) | FAILED | `gh run list --workflow security-pr.yml --branch main --limit 1 --json conclusion -q '.[0].conclusion'`: HTTP 404 "Not Found", EXIT 1. `SECURITY.md` Exceptions section (lines 56-64): table header only, zero exception rows. Neither compliance path is met. |

**Score:** 4/5 criteria verified.

### Checkpoint

| Command | Result | Status |
|---------|--------|--------|
| `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` | EXIT 0; `cycle_end` event, `engine_decision=skip reason=data_unavailable`, `ledger_seq=1` | PASS |

`git status --porcelain` after the checkpoint shows only the two pre-existing
untracked files (`.planning/phases/01-foundation/01-REVIEW.iter2.md`,
`.planning/state.json`); the replay wrote nothing tracked.

### Required Artifacts (spot-verified in source, not just present)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pumpgrok/supervisor/metrics.py` | 9 metric names + exposition | VERIFIED | Constants CYCLE_SECONDS..LEDGER_SEQ (lines 54-62); `Metrics.exposition`; wired as `get_metrics=metrics.exposition` in serve path (`scheduler.py:802`); snapshot at `scheduler.py:741-747`. |
| `src/pumpgrok/supervisor/health.py` | /healthz + /metrics, 503 on snapshot failure | VERIFIED | `_handle` try/except returns explicit 503 `{"metrics": False, "error": ...}` (lines 143-146). WR-05 claim holds. |
| `src/pumpgrok/supervisor/scheduler.py` | host threading, rollover latch, shared kill-switch latch | VERIFIED | `serve_replay(host="127.0.0.1")` (:778), `server.start(host, port)` (:804); `_emit_rollover` catches `IntegrityError` + latches day (:417-421); shared `kill_switch_engaged(store)` (:106-121) used by both health body (:470) and snapshot (:747). WR-02/03/04 hold. |
| `src/pumpgrok/config/settings.py` | bounded port, validated host | VERIFIED | `port: Field(default=0, ge=0, le=65535)`; `_validate_host` accepts IP literal or RFC 1123 hostname, raises ValueError otherwise (lines 278-299, `import ipaddress` line 26). WR-06 and WR-09 hold; commit 3a115f8 confirmed in tree. |
| `src/pumpgrok/replay/runner.py` | failed verify removes created ledger | VERIFIED | `except` calls delete-only `recreate_ledger_db(target)` then re-raises; `finally: store.close()` (lines 180-189). WR-07 holds. |
| `Dockerfile` | no image HEALTHCHECK (WR-08) | VERIFIED | No `^HEALTHCHECK` instruction; comment block (line 28) records the decision. Compose carries the `/healthz` probe (container-loopback, host-loopback-only publish). |
| `src/pumpgrok/cli.py` | ClearRefused imported (WR-01-adjacent lint fix) | VERIFIED | Line 78 imports `ClearRefused`; line 843 handles it. Genuine latent NameError fix, present. |
| `src/pumpgrok/doctor.py` | single SUBSYSTEMS (WR-01) | VERIFIED | One definition (line 19) + one use (line 87). |
| `docs/runbooks/*.md` (9) | setup, engine, start_stop, kill_switch, breaker_reset, outage, rollback, reading_reports, go_live | VERIFIED | All 9 files present; `tests/docs/test_runbook_commands.py` passes (in docs run, 20 dots EXIT 0). |
| `docs/RISK_POLICY.md`, `docs/runbooks/go_live.md` | compliance boundary, go-live procedure | VERIFIED | Both files exist (35.5K and 2.5K). |
| `CHANGELOG.md` | Phase 1..5 entries | VERIFIED | Loop finds all five; `tests/docs/test_changelog_phases.py` passes. |
| Pinning tests for WR fixes | 5 named tests exist | VERIFIED | `test_serve_host_env_override`, `test_serve_replay_binds_loopback_by_default`, `test_health_port_rejects_out_of_range_values` in `tests/config/test_health_port_defaults.py`; `test_metrics_route_snapshot_failure_is_503_with_body` in `tests/supervisor/test_metrics.py`; `test_verify_failure_removes_the_created_ledger` in `tests/replay/test_runner_determinism.py`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| serve path | HealthServer | `get_metrics=metrics.exposition` (`scheduler.py:802`) | WIRED | /metrics serves live snapshot; 503 path pinned by test. |
| CLI | scheduler serve | `settings.health.host` threaded through (`cli.py:571-574`) | WIRED | Compose sets 0.0.0.0; default loopback. |
| health body /metrics gauge | ledger store | shared `kill_switch_engaged(store)` over same store object | WIRED | Body and gauge cannot disagree (WR-04). |
| replay runner | ledger file | `recreate_ledger_db` + `LedgerStore(target)` at run time | WIRED | Ledger created lazily per run (known deviation, intended). |
| notifier | sinks | `redact_text`/`redact_value` at fan-out (`notifier.py:120-123`) | WIRED | Redaction at fan-out edge (known deviation, intended). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| serve _snapshot | ledger_seq, kill_switch | live `LedgerStore.read` scan + shared latch | Yes (compose /healthz healthy; checkpoint ledger_seq=1) | FLOWING |
| Metrics exposition | 9 gauges/counters | observer + snapshot closure | Yes (serve-mode tests assert rendered values) | FLOWING |
| replay ledger | events_hash, ledger_seq | fixture events via `append_batch` + verify | Yes (checkpoint cycle_end) | FLOWING |

### Behavioral Spot-Checks

Covered by the suites above (all suites execute behavior, not just presence):
SC1 exercises memory bound, rollover, and all six fault rows; SC4 executes the
live gate (exit 3, nine ordered lines per the test names) and the manipulation
boundary scan over real `tools/social/` content; the checkpoint executes one
real paper replay cycle. No separate ad-hoc probes were needed.

### Probe Execution

No phase-declared `probe-*.sh` scripts exist for phase 5; criterion commands
themselves are the probes and were all executed in this report. No
MISSING_PROBE.

### Requirements Coverage

| Requirement | Source | Description | Status | Evidence |
|-------------|--------|-------------|--------|----------|
| RISK-007 | SC4 | Manipulation boundary + test | SATISFIED | 7/7 manipulation tests pass; overlays live.enabled false. |
| AUTO-007 | SC1 | soak-3d multiday replay | SATISFIED | 3 soak tests pass (part of 34). |
| AUTO-008 | SC1 | fault-injection suite | SATISFIED | 31 degradation tests pass (part of 34). |
| OBS-003 | SC2 | /metrics + span timings | SATISFIED | 9 names; 21 metrics/serve tests pass. |
| OBS-004 | SC3 | 9 runbooks + check.sh | SATISFIED | All present; check.sh EXIT 0; runbook-commands test passes. |
| OBS-005 | SC3 | CHANGELOG all phases | SATISFIED | Phases 1-5 present; changelog test passes. |
| SEC-005 | SC5 | security workflow green or exceptions | BLOCKED | gh 404; zero exception rows. THE gap. |
| GOLIVE-003 | SC4 | go-live gate proof, live disabled | SATISFIED | 23 live-gate tests pass; all overlays false; go_live.md present. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| .planning/phases/05-hardening/05-REVIEW.md | 187 | `ruff format --check .` wants a blank line in a python fence (doc commit c363bf6) | Info | None on behavior; canonical `ruff format --check .` exits 1 on this doc file only. All 155 src files formatted; `ruff check .` exits 0; `mypy src/` exits 0 (155 files). Not an SC; recorded for the orchestrator, not fixed (verify-only run). |

No TBD/FIXME/XXX markers introduced by this phase were found in the
criterion paths; no stub patterns (empty handlers, static returns) in the
verified artifacts. (Note: a bare-`ruff` binary outside `uv run` reports an
S310 in `doctor.py:58`; the canonical `uv run ruff check .` passes - version
artifact, disregarded.)

### Human Verification Required

None. All automatable checks ran with real exit codes. The container health is
machine-verified (`Up 3 hours (healthy)` via the `/healthz` probe); no visual,
UX, or external-service behavior is asserted by the phase goal beyond what the
suites execute.

### Gaps Summary

One gap blocks the phase: **SC5 / SEC-005**. `security-pr.yml` has no run on
`main` (GitHub API returns HTTP 404 for the workflow on the main branch, and
this run is forbidden from pushing or merging, so no run can be produced here),
and `SECURITY.md` lists zero exceptions with expiry dates, so the alternative
compliance path is also unmet. This is the expected outcome per the assignment
brief. All other criteria (SC1-SC4), the checkpoint, all eight requirement IDs
except SEC-005, and every code-review fix claim (WR-01..WR-09) verify against
the actual source at HEAD c363bf6.

### Known Deviations Recorded (verified in source, non-blocking)

1. Env knobs are `PUMPGROK_HEALTH__PORT` / `PUMPGROK_HEALTH__HOST` (double
   underscore, pydantic-settings nesting) though the plan wrote single
   underscore. Consistent across compose, settings, and tests.
2. Image HEALTHCHECK removed by WR-08; `docs/FOUNDATION_STACK.md` (~line 316)
   still documents a HEALTHCHECK with the single-underscore var. Docs drift;
   liveness is covered by the compose `/healthz` probe (container healthy).
3. `ci/tests/test_security_workflows.py` receipt test (commit 5e58da2) asserts
   tracked `.receipts/*.json` is a subset of the `.gitignore`-allowlisted set,
   not absolute zero. Correct subset check, verified in diff.
4. Replay-runner ledger is created lazily at run time (`recreate_ledger_db` +
   `LedgerStore(target)` in `runner.py:145-146`), not at import.
5. Notifier redacts at fan-out (`notifier.py:120-123`), as designed.
6. Gates note: `uv run ruff check .` EXIT 0, `uv run mypy src/` EXIT 0
   (155 files), full criterion suites EXIT 0 - all on current HEAD c363bf6
   (i.e. including WR-09 commit 3a115f8). Only `ruff format --check .` flags
   the 05-REVIEW.md fence (info above). The orchestrator's planned full-suite
   re-run after 3a115f8 remains its call.

---
_Verified: 2026-10-22T13:10:00Z_
_Verifier: Claude (gsd-verifier)_

---
phase: 05-hardening
plan: 01
subsystem: observability
tags: [metrics, spans, prometheus, health, pytest-markers]
status: complete
commits:
  - 43a8f45
  - 09d4bd8
  - 652f9dc
plan_head_before: 6995084
dependency_graph:
  requires: []
  provides: [slow-marker, span-timing, metrics-registry, metrics-route, health-port]
  affects: [05-02, 05-03, soak, degradation]
tech_stack:
  added: ["prometheus-client>=0.26,<0.27"]
  patterns: [contextvar-clock-binding, callable-injection, fresh-registry-per-test]
key_files:
  created:
    - src/pumpgrok/logging/spans.py
    - src/pumpgrok/supervisor/metrics.py
    - tests/logging/test_spans.py
    - tests/supervisor/test_metrics.py
    - tests/config/test_health_port_defaults.py
  modified:
    - src/pumpgrok/logging/__init__.py
    - src/pumpgrok/core/registry.py
    - src/pumpgrok/supervisor/__init__.py
    - src/pumpgrok/supervisor/seat_task.py
    - src/pumpgrok/supervisor/health.py
    - src/pumpgrok/config/settings.py
    - tests/safety/test_static_guards.py
    - pyproject.toml
    - uv.lock
decisions:
  - "Clock binding for span(): contextvar bound by the registry (bind_clock), mirroring bind_correlation (PATTERNS 2.1 lower-risk reading); recorded in spans.py module docstring."
  - "orders_total source: ledger reads at scrape time via sync_orders delta tracking, not adapter counters (avoids double-counting retries); recorded in metrics.py module docstring."
  - "Unknown breaker state maps to 2 (open): fail-closed."
  - "Health port env spelling is PUMPGROK_HEALTH__PORT (repo nested-delimiter convention); plan text wrote PUMPGROK_HEALTH_PORT loosely. Default 0; compose sets 8080 in plan 07; health_port() forces 0 under --once/--replay."
metrics:
  duration: "1 session"
  tasks: 3
  commits_actual: 3
---

# Phase 5 Plan 01: Observability Core Summary

One-liner: Virtual-clock span timing for every tool call plus a supervisor-owned
Prometheus registry serving GET /metrics with exactly the nine locked families,
with the slow marker registered and prometheus-client pinned under uv 0.13.4.

## Tasks Completed

### Task 1: Approve prometheus-client legitimacy and install uv 0.13.4 (checkpoint, approved)

Pre-approved by the user (05-01-CHECKPOINT.md, "Approve both"). Host uv was
already 0.13.4 and `uv add "prometheus-client>=0.26,<0.27"` had already resolved
0.26.0 into pyproject.toml and uv.lock, so the remaining work was registering
the slow marker:

- `pyproject.toml`: added `slow: multi-day soak replay (nightly;
  PUMPGROK_REQUIRE_SOAK=1 makes absence fail)` to `[tool.pytest.ini_options] markers`.
- Committed with the checkpoint record and the dependency changes.

Verify: `uv --version | grep -q 0.13.4 && grep -q prometheus-client pyproject.toml
&& grep -q '"slow:' pyproject.toml` exit 0. `uv run pytest -q --collect-only`
exit 0. Commit: 43a8f45.

### Task 2: Span timing for every tool call (auto)

- `src/pumpgrok/logging/spans.py` (new): `span(name, **fields)` dual sync/async
  context manager; parent name and depth in contextvars; duration from the
  injected Clock only (entering without a bound clock raises); emits
  `event="span"` with `duration_ms` through the regular extra mechanism so
  RedactionFilter still applies.
- `src/pumpgrok/logging/__init__.py`: export `span`, `bind_clock`.
- `src/pumpgrok/core/registry.py`: `_Guarded.__call__` now enters
  `bind_correlation`, `bind_calling_seat`, `bind_clock(clock)`, `span(spec.name)`,
  so every tool call emits one redacted span covering retries with the cid.
- `tests/logging/test_spans.py` (new): Clock-delta duration, async support,
  nesting order, unbound-clock error, secret key redaction, one span per
  registry call with virtual duration.
- `tests/safety/test_static_guards.py`: new
  `test_no_prometheus_client_outside_supervisor` (AST scan; all of src except
  `supervisor/`).

Verify: `uv run pytest -q tests/logging/test_spans.py
tests/safety/test_static_guards.py` exit 0. Commit: 09d4bd8.

### Task 3: Metrics registry, seat hooks, /metrics route and health-port setting (auto)

- `src/pumpgrok/supervisor/metrics.py` (new): `build_registry()` returns a fresh
  `CollectorRegistry`; `Metrics` holder with the nine verbatim families
  (counters declared with `_total`); gauges refreshed at scrape time from an
  injected snapshot callable; `observe(seat, duration_s, outcome)` matches the
  SeatTask observer shape; `sync_orders` reconciles cumulative ledger reads
  with delta tracking so scrapes never double-count.
- `src/pumpgrok/supervisor/seat_task.py`: optional `cycle_observer` called at
  the site that sets `last_duration_s` (best-effort, guarded); no
  prometheus_client import.
- `src/pumpgrok/supervisor/health.py`: `HealthServer` takes optional
  `get_metrics`; `GET /metrics` returns exposition bytes with the exposition
  content type via `_respond_bytes` (never json.dumps); non-GET is 405;
  `/healthz` and `/readyz` unchanged; docstring updated.
- `src/pumpgrok/supervisor/__init__.py`: export `Metrics`, `NINE_FAMILIES`,
  `build_registry`.
- `src/pumpgrok/config/settings.py`: `HealthSettings` (frozen, extra forbid,
  port default 0) wired as `health`; `health_port()` forces 0 under
  `--once`/`--replay` (INV-C-11).
- `tests/supervisor/test_metrics.py` (new): exposition carries exactly the nine
  names (guards Counter `_total` suffix behaviour), virtual-second histogram,
  crash counting, scrape-time gauges, ledger reconciliation, unknown breaker,
  seat hook end-to-end, /metrics route (content type, 405, provider-absent 503).
- `tests/config/test_health_port_defaults.py` (new): default 0, env override,
  `test_once_and_replay_disable_health_port`, frozen model.

Verify: SC2 grep prints 9; `uv run pytest -q
tests/supervisor/test_metrics.py tests/config/test_health_port_defaults.py`
exit 0. Commit: 652f9dc.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FixtureClock.sleep deadlocks tests with no advancer.**
Found during: Task 2 verify (pytest hung until timeout).
Issue: `FixtureClock.sleep` only fires when virtual time advances via
`advance_to`; awaiting it in a tool/cycle under test with nothing advancing
time hangs forever.
Fix: advance virtual time synchronously (`clock.advance_to(clock.now() + d)`)
inside test doubles instead of awaiting sleep.
Files: tests/logging/test_spans.py, tests/supervisor/test_metrics.py.

**2. [Rule 1 - Bug] Span records suppressed by logger level.**
Found during: Task 2 verify (0 records captured).
Issue: `log.info` on `pumpgrok.spans` is suppressed when the root logger sits
at WARNING; capture handlers alone do not enable INFO.
Fix: `_captured` test helper sets the spans logger to INFO and restores it.
Files: tests/logging/test_spans.py.

**3. [Rule 1 - Bug] Blocking urlopen on the event-loop thread deadlocks the route test.**
Found during: Task 3 verify (hung on the last test).
Issue: `urllib.request.urlopen` called directly in an async test blocks the
loop thread, so the `HealthServer` task never processes the connection.
Fix: run the fetch in `asyncio.to_thread`, matching the existing lifecycle test.
Files: tests/supervisor/test_metrics.py.

**4. [Rule 2 - Correctness] Health port env spelling.**
Found during: Task 3 implementation.
Issue: the plan wrote `PUMPGROK_HEALTH_PORT`, but the repo convention for
nested models is the double-underscore delimiter (`PUMPGROK_HEALTH__PORT`,
as in `PUMPGROK_RISK__MAX_TRADE_FRACTION`); the single-underscore name would
trip the unknown-setting startup guard.
Fix: nested `health.port` (double underscore, auto-covered by
`allowed_env_names`); documented in settings docstring and here. The plan-07
compose change should use the double-underscore spelling.

No stubs, no skipped tests, no unrun verifies. Threat model T-05-01 holds:
gauges carry numbers and fixed labels only, equity computed at scrape time,
no settings dump in health or metrics bodies.

## Self-Check

- src/pumpgrok/logging/spans.py: FOUND
- src/pumpgrok/supervisor/metrics.py: FOUND
- tests/logging/test_spans.py: FOUND
- tests/supervisor/test_metrics.py: FOUND
- tests/config/test_health_port_defaults.py: FOUND
- 43a8f45: FOUND
- 09d4bd8: FOUND
- 652f9dc: FOUND

## Self-Check: PASSED

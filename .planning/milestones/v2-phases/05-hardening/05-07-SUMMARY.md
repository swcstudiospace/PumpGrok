---
phase: 05-hardening
plan: 07
subsystem: deployability
tags: [serve-mode, healthz, metrics, container, security-ci, soak, sec-005]
status: complete
commits:
  - c15596c
  - 08b568f
plan_head_before: 9ce2695
dependency_graph:
  requires: [05-01, 05-03]
  provides: [serve-path, container-health, security-push-trigger, nightly-soak, exceptions-gate]
  affects: [05-08]
tech_stack:
  added: []
  patterns: [wall-clock-serve-loop, stdlib-urllib-probes, uv-run-scanner, expiry-gate-script]
key_files:
  created:
    - tests/supervisor/test_serve_mode.py
    - tests/test_doctor_probes.py
    - ci/security/check_exceptions.py
  modified:
    - src/pumpgrok/cli.py
    - src/pumpgrok/supervisor/scheduler.py
    - src/pumpgrok/supervisor/health.py
    - src/pumpgrok/supervisor/__init__.py
    - src/pumpgrok/doctor.py
    - Dockerfile
    - docker-compose.yml
    - .github/workflows/security-pr.yml
    - .github/workflows/ci.yml
    - ci/tests/test_security_workflows.py
    - SECURITY.md
decisions:
  - "Serve binds 0.0.0.0 in-container; LAN safety from the 127.0.0.1 compose publish (T-05-17, Rule 1)."
  - "Pinning branch for scanner tooling: semgrep==1.182.1, bandit==1.9.4 (PyPI-verified); zero SECURITY.md exception rows."
  - "SC5 BLOCKED: remote has no security-pr.yml workflow and zero main-branch runs; nothing merged/pushed per hard constraint."
metrics:
  duration: "1 session"
  tasks: 3
  commits_actual: 2
actuals:
  tokens: 10600
  tasks: 3
  commits: 2
---

# Phase 5 Plan 07: Serve, Scan and Soak Summary

One-liner: Long-running `run --mode paper --serve` replay loop serving
`/healthz` and `/metrics` with a healthy compose service, a push-triggered
security gate with pinned scanners and uv-run pip-audit, a nightly required
soak job, and an exceptions table with an expiry gate; SEC-005 blocked with
real evidence.

## Tasks Completed

### Task 1: Serve mode, doctor probes and container health (c15596c)

- `src/pumpgrok/cli.py`: `--serve` flag in `_add_run`; `_run` branch after the
  live-gate block (live still exits 3 first). `--serve` without `--replay`, or
  with `--once`, exits 5. `_serve_replay_loop` validates the dataset name,
  resolves the port via `health_port()` (0 under `--once`/`--replay` per
  amended INV-C-11, nonzero required here: refusal names
  `PUMPGROK_HEALTH__PORT`, never its value), and runs `serve_replay`.
  One-shot path byte-identical.
- `src/pumpgrok/supervisor/scheduler.py`: `Supervisor` takes an optional
  `cycle_observer` passed to every `SeatTask` (backward compatible).
  `build_serve_replay` runs `run_replay` once, wires the ten offline replay
  cycles with `source="replay"` (health body `ledger_source=replay`), a
  `Metrics` snapshot (`ledger_seq` real, `kill_switch` matching the health
  body), and the observer. `serve_replay` starts `HealthServer` with
  `metrics.exposition`, installs lifecycle signal handlers, and loops
  `serve_forever` until SIGINT/SIGTERM, then closes server and store.
  Listens on all container interfaces: Docker forwards published ports to the
  container IP, never its loopback (Rule 1 fix, see Deviations).
- `src/pumpgrok/doctor.py`: `probe_served_endpoints` (stdlib urllib, 2 s
  timeout, `ok` only on HTTP 200) plus `SERVED_ENDPOINTS`; `doctor_report`
  appends both probe lines (warn when `health.port=0`, no network attempted),
  summary line stays last so `tools/desk/doctor.py` is unaffected.
- `src/pumpgrok/supervisor/health.py`: docstring records the serve binding
  and the doctor probes. `Dockerfile`: `.python-version` copied before sync;
  HEALTHCHECK is the stdlib `/healthz` probe on `PUMPGROK_HEALTH__PORT`.
- `docker-compose.yml`: serve command, `PUMPGROK_HEALTH__PORT=8080`,
  `./var:/app/var` bind, 45 s grace, `/healthz` healthcheck,
  `restart: unless-stopped` (serve path only), header rewritten (D1/D9,
  bind-mount ownership pointing at `docs/runbooks/start_stop.md`, port split).
- Tests: `test_serve_mode.py` (8 tests: replay label, ten-seat tick, stop,
  both endpoints with all nine families, CLI rejections, one-shot exit 0);
  `test_doctor_probes.py` (3 tests: unreachable warn, served ok with
  `ledger_source=replay`, report lines when unbound).

Verify: `docker compose up -d --build pumpgrok && docker compose ps pumpgrok`
exit 0, `healthy`; host probes `/healthz` ok/replay/paper and `/metrics` 200
with `pumpgrok_cycle_seconds`; in-container `pumpgrok doctor` shows both
endpoints ok; `docker compose run --rm ... --once --replay ...` exit 0;
`uv run pytest -q tests/supervisor/test_serve_mode.py
tests/test_doctor_probes.py` exit 0 (11 passed).

### Task 2: Security workflow hardening and nightly soak schedule (08b568f)

- `.github/workflows/security-pr.yml`: `push: branches: [main]` added under
  `on` (header comment updated). Dependencies job runs
  `uv sync --frozen` then `uv run pip-audit -r req.txt --strict`
  (guard substring kept verbatim). `semgrep==1.182.1` and `bandit==1.9.4`
  pinned (PyPI-verified 2026-10-22). Pinning branch taken: no exception rows.
- `.github/workflows/ci.yml`: `schedule: [cron: "17 3 * * *"]` plus a `soak`
  job (`if: schedule`, ubuntu-latest) running
  `uv run pytest -q -m slow tests/soak` under `PUMPGROK_REQUIRE_SOAK=1`.
- `ci/tests/test_security_workflows.py`: `TestSecurityPrPushTrigger`
  (PR+push trigger, uv-run pip-audit, pinned installs),
  `TestCiWorkflow.test_nightly_soak_schedule_requires_soak`,
  `TestSecurityExceptions` (columns plus zero rows, expired and malformed
  rows reported).
- `SECURITY.md`: Exceptions table schema with zero rows; expiry enforced by
  new `ci/security/check_exceptions.py` (stdlib, exit 1 on expired/malformed),
  wired through the guard suite (runs in the gates check).

Verify: `uv run pytest -q ci/tests/test_security_workflows.py` exit 0
(50 passed); `python3 ci/security/check_exceptions.py` exit 0
("no expired rows").

### Task 3: SEC-005 evidence (no commit, no files changed)

SC5 literal run for real in an authenticated environment:

- `gh run list --workflow security-pr.yml --branch main --limit 1 --json conclusion -q '.[0].conclusion'`
  exit 1, output:
  `HTTP 404: Not Found (https://api.github.com/repos/swcstudiospace/PumpGrok/actions/workflows/security-pr.yml)`
- `gh workflow list` prints nothing; `gh run list --branch main --limit 3`
  prints `[]` (zero runs on main).
- `gh auth status`: logged in as SomeRandmGuyy (GH_TOKEN), active account,
  token present (value redacted here).

SC5 is BLOCKED: the first main-branch run does not exist because the push
trigger only lands on main after merge, and nothing is merged or pushed in
this run (hard constraint). `SECURITY.md` left with zero invented rows, per
the blocked-state path.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Serve bound 127.0.0.1 is unreachable through a published port.**
Found during: Task 1 docker verify (host probes RST, 0 bytes; in-container 200).
Fix: `serve_replay` listens on all container interfaces; LAN safety rests on
the compose `127.0.0.1:8080` publish prefix. Compose header and scheduler
docstring record the split (T-05-17 mitigation now reads: host publish is the
loopback boundary; no unauthenticated write routes).
Files: `src/pumpgrok/supervisor/scheduler.py`, `docker-compose.yml`.

**2. [Rule 1 - Bug] `check_exceptions.py` resolved the repo root one level short.**
Found during: Task 2 verify (`cannot read .../ci/SECURITY.md`).
Fix: `parents[2]`, restored the dropped stdlib imports from the same edit.
Files: `ci/security/check_exceptions.py`.

**3. [Rule 1 - Bug] Blocking urlopen on the event-loop thread deadlocks the probe test.**
Found during: Task 1 verify (TimeoutError, same shape as 05-01 deviation 3).
Fix: fetch runs in `asyncio.to_thread`.
Files: `tests/test_doctor_probes.py`.

**4. [Rule 3 - Blocking] Host `./var` bind mount not writable by container user.**
Found during: Task 1 docker verify (PermissionError on
`var/replay/smoke/ledger.sqlite`).
Fix: applied the documented `docs/runbooks/start_stop.md` step
(`chown -R 999:999 var`, container uid from `id pumpgrok`); no repo change.
Files: none.

Pre-existing failures (out of scope, not caused here, identical on clean
tree `9ce2695`): `test_killswitch_env_passes_settings_validation`,
`test_second_run_recreates_the_replay_ledger`,
`test_live_is_refused_with_exit_3_before_other_work`. Left for 05-08
end-to-end re-verification.

Environment note: bare `uv run pytest` intermittently reported
"No tests collected" (exit 0) in this sandbox; `uv run --no-sync pytest`
against the already-synced venv ran the identical bits and is quoted in the
verifies above.

## Known Stubs

None. Stub scan over all created/modified source and test files found no
TODO/FIXME/placeholder markers (excluding the intentional
`not-yet-implemented` doctor vocabulary).

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: T-05-17 bind split | src/pumpgrok/supervisor/scheduler.py, docker-compose.yml | Serve listens on all container interfaces; loopback boundary moved to the compose `127.0.0.1:8080` publish. Other services on the same compose network could reach :8080 (read-only GET routes). |

T-05-18 holds (actions SHA-pinned as before; semgrep/bandit now ==-pinned;
uv 0.13.4). T-05-19 holds (no bypass snippets; expiry rows fail the gate).
No new network endpoints beyond the planned read-only pair.

## Self-Check

- tests/supervisor/test_serve_mode.py: FOUND
- tests/test_doctor_probes.py: FOUND
- ci/security/check_exceptions.py: FOUND
- c15596c: FOUND in `git log`
- 08b568f: FOUND in `git log`
- docker compose ps pumpgrok: healthy (verified this session)
- gh SC5 literal output captured verbatim above

## Self-Check: PASSED

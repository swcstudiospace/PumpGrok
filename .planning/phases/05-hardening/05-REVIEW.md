---
phase: 05-hardening
reviewed: 2026-10-22T00:00:00Z
depth: deep
files_reviewed: 106
files_reviewed_list:
  - .github/workflows/ci.yml
  - .github/workflows/security-pr.yml
  - Dockerfile
  - ci/security/check_exceptions.py
  - ci/tests/test_gates.py
  - ci/tests/test_security_workflows.py
  - docker-compose.yml
  - pyproject.toml
  - scripts/README.md
  - scripts/build_soak_fixture.py
  - scripts/hermes-bootstrap.sh
  - scripts/hermes-verify-isolation.sh
  - src/pumpgrok/cli.py
  - src/pumpgrok/config/settings.py
  - src/pumpgrok/core/registry.py
  - src/pumpgrok/doctor.py
  - src/pumpgrok/execution/live/live_gate.py
  - src/pumpgrok/ledger/desk_bus.py
  - src/pumpgrok/ledger/export.py
  - src/pumpgrok/logging/__init__.py
  - src/pumpgrok/logging/spans.py
  - src/pumpgrok/replay/clock.py
  - src/pumpgrok/replay/runner.py
  - src/pumpgrok/supervisor/__init__.py
  - src/pumpgrok/supervisor/health.py
  - src/pumpgrok/supervisor/metrics.py
  - src/pumpgrok/supervisor/scheduler.py
  - src/pumpgrok/supervisor/seat_task.py
  - src/pumpgrok/tools/notify/notifier.py
  - src/pumpgrok/tools/onchain/authorities.py
  - src/pumpgrok/tools/onchain/holders.py
  - src/pumpgrok/tools/onchain/priority_fee.py
  - tests/characterization/test_authority_check.py
  - tests/characterization/test_holder_check.py
  - tests/characterization/test_jupiter_quote.py
  - tests/characterization/test_priority_fee.py
  - tests/characterization/test_vendor_log.py
  - tests/characterization/test_vendor_ports.py
  - tests/config/test_forbidden_env_keys_refused.py
  - tests/config/test_health_port_defaults.py
  - tests/config/test_invalid_config_fails_fast.py
  - tests/config/test_mode_defaults_paper.py
  - tests/config/test_overlay_precedence.py
  - tests/config/test_secrets_never_dumped.py
  - tests/degradation/test_clock_skew.py
  - tests/degradation/test_data_source_outage.py
  - tests/degradation/test_ledger_unwritable.py
  - tests/degradation/test_llm_failure.py
  - tests/degradation/test_partial_restart.py
  - tests/degradation/test_rpc_failure.py
  - tests/desk/test_check_sh_passes.py
  - tests/desk/test_doctor_and_once.py
  - tests/desk/test_hermes_cron_contract.py
  - tests/docs/test_changelog_phases.py
  - tests/docs/test_runbook_commands.py
  - tests/execution/test_graduation_force_close.py
  - tests/execution/test_live_gate_fails_fast.py
  - tests/execution/test_paper_fill_model.py
  - tests/execution/test_single_send.py
  - tests/fixtures/http/adversarial/mixed.json
  - tests/fixtures/llm/timeout.json
  - tests/fixtures/replay/soak-3d/events.jsonl
  - tests/fixtures/replay/soak-3d/llm.jsonl
  - tests/fixtures/replay/soak-3d/manifest.json
  - tests/fixtures/secrets/planted.txt
  - tests/harness/__init__.py
  - tests/harness/faults.py
  - tests/harness/test_faults.py
  - tests/ledger/test_desk_bus_mirror.py
  - tests/ledger/test_every_action_journaled.py
  - tests/ledger/test_ledger_restart_reconcile.py
  - tests/logging/test_redaction.py
  - tests/logging/test_spans.py
  - tests/replay/test_fixture_manifest.py
  - tests/replay/test_replay_determinism.py
  - tests/risk/test_approval_phrase.py
  - tests/risk/test_breaker_trip_and_cooldown.py
  - tests/risk/test_check_order_caps.py
  - tests/risk/test_halts.py
  - tests/risk/test_kill_switch_one_cycle.py
  - tests/risk/test_limits_validation.py
  - tests/safety/test_constitution_constants.py
  - tests/safety/test_env_example_placeholders.py
  - tests/safety/test_live_adapter_raises.py
  - tests/safety/test_model_output_validated_before_tool.py
  - tests/safety/test_money_types.py
  - tests/safety/test_no_direct_time.py
  - tests/safety/test_no_eval_or_shell.py
  - tests/safety/test_no_live_write_in_rosters.py
  - tests/safety/test_no_manipulation_tools.py
  - tests/safety/test_no_signing_outside_live_stub.py
  - tests/safety/test_no_uuid_module.py
  - tests/safety/test_no_vendor_imports.py
  - tests/safety/test_static_guards.py
  - tests/soak/test_soak_multiday_replay.py
  - tests/supervisor/test_degraded.py
  - tests/supervisor/test_metrics.py
  - tests/supervisor/test_serve_mode.py
  - tests/supervisor/test_supervisor_bounded_restart.py
  - tests/test_doctor_probes.py
  - tests/test_idempotency.py
  - tests/test_live_gate.py
  - tests/test_skip_cycle.py
  - tests/test_tools_cli.py
  - tests/tools/test_adversarial_metadata.py
  - tests/tools/test_money_registry_tracer.py
findings:
  critical: 0
  warning: 8
  info: 4
  total: 12
status: issues_found
---

# Phase 05: Code Review Report

**Reviewed:** 2026-10-22
**Depth:** deep
**Files Reviewed:** 106
**Status:** issues_found

## Summary

Reviewed the full phase 5 diff (b558790..HEAD): 20 source files plus tests, CI,
scripts, Dockerfile, compose, and pyproject. Cross-checked the new serve path
(`cli --serve` -> `build_serve_replay` -> `serve_replay` -> `HealthServer`),
the nine-family Prometheus registry, span timing, the live-gate row-1 amendment,
health-port config, replay-runner DB creation order, rollover emission, and the
deploy/CI surface (Dockerfile, compose, security workflows, hermes scripts).

No live-trading bypass found: the gate amendment is fail-closed
(`live_enabled` defaults False, CLI wires `settings.live.enabled`, row 8 stays
structurally unmet), no secrets or shell injection in the new code, no YAML
workflow injection, scanner pins added. No CRITICAL findings.

Eight warnings remain, all in new phase-5 code: a duplicated module-level block,
an unconditional 0.0.0.0 bind, a duplicate-key retry storm in `_emit_rollover`,
a hardcoded-false kill-switch gauge in serve snapshots, an unguarded metrics
refresh that drops connections, an unbounded health port, a wrong "leaves no
file" comment, and an image HEALTHCHECK that probes a port the default command
never binds. Four info items record deliberate-but-lossy behaviors worth
pinning down later.

## Warnings

### WR-01: Duplicate SUBSYSTEMS block in doctor.py (second shadows first)

**File:** `src/pumpgrok/doctor.py:19-29` and `src/pumpgrok/doctor.py:70-82`
**Issue:** The 11-entry `SUBSYSTEMS` tuple is defined twice, byte-identical.
The second assignment silently shadows the first, so a future edit to the
first block (lines 19-29) would have no effect and no linter or test would
catch the divergence: `subsystem_statuses()` reads the name `SUBSYSTEMS`,
which resolves to the second definition. A duplicated 12-line block that
invites silent divergence is a real maintainability defect, not a nit.
**Fix:**
```python
# Keep exactly one definition (the one at lines 19-29); delete lines 70-82.
```

### WR-02: serve_replay hardcodes bind 0.0.0.0 with no loopback option

**File:** `src/pumpgrok/supervisor/scheduler.py:757` (`bound = await server.start("0.0.0.0", port)`)
**Issue:** The serve path always listens on all container interfaces. LAN
safety rests entirely on `docker-compose.yml` publishing `127.0.0.1:8080`.
An operator running `pumpgrok run --serve` directly on a host (the documented
one-shot form shows host runs are normal) exposes `/healthz` and `/metrics`
to the LAN with no authentication. Read-only endpoints, but equity/drawdown/
ledger-seq internals leak to any adjacent host, and there is no flag to bind
loopback instead.
**Fix:**
```python
# Default to loopback; opt in to 0.0.0.0 only via an explicit flag/env.
bound = await server.start(host, port)  # host="127.0.0.1" unless --serve-public
```

### WR-03: _emit_rollover retries a duplicate key every tick after a same-day restart

**File:** `src/pumpgrok/supervisor/scheduler.py:383-410`
**Issue:** `idempotency_key` is `UNIQUE` (`src/pumpgrok/ledger/store.py:42`),
and `append` raises on duplicates. On a supervisor restart within the same UTC
day, `_last_rollover_day` resets to `None`, the append raises `IntegrityError`,
the handler logs a warning and returns *without* setting `_last_rollover_day`
— so every subsequent tick retries the same doomed insert and logs again.
This is a per-tick write attempt plus log spam for the rest of the day, and it
masks real append failures behind the same warning line.
**Fix:**
```python
except sqlite3.IntegrityError:
    # Same-day restart: the row already exists; latch the day and stay quiet.
    self._last_rollover_day = day
    return
except Exception as exc:
    log.warning("daily rollover append failed: %s", exc)
    return
```

### WR-04: Serve snapshot hardcodes kill_switch False, so the gauge can never trip

**File:** `src/pumpgrok/supervisor/scheduler.py:706-713`
**Issue:** `_snapshot()` returns `{"ledger_seq": seq, "kill_switch": False}`
unconditionally, with the comment "kill switch matches the health body" — but
the health body itself hardcodes `kill_switch=False`
(`scheduler.py:435` in `health_status`). `Metrics.refresh()` fully supports a
True value (`tests/supervisor/test_metrics.py:100-103` pins `1.0`), yet in the
only production wiring the gauge is dead: an engaged kill switch during serve
still scrapes `pumpgrok_kill_switch 0.0`. A safety gauge that cannot fire is
worse than no gauge.
**Fix:**
```python
def _snapshot() -> dict[str, Any]:
    try:
        seq = store.count()
    except Exception:
        seq = 0
    return {"ledger_seq": seq, "kill_switch": supervisor.kill_switch_engaged()}
```
wired to the same latch `health_status` should read (fix both together).

### WR-05: Snapshot exception in /metrics drops the connection with no HTTP response

**File:** `src/pumpgrok/supervisor/metrics.py:170-196` with `src/pumpgrok/supervisor/health.py:137-155`
**Issue:** `Metrics.refresh()` calls `self._snapshot()` and the `float(...)`
conversions with no guard. `HealthServer._handle` invokes `self._get_metrics()`
inside its try block, so any snapshot failure jumps to `except: log.warning`
and closes the writer with zero bytes written. Prometheus records a connection
reset (not a 5xx), and the doctor probe surfaces only an exception type name.
Scrape failures should be explicit 503/500 with a body.
**Fix:**
```python
elif path == "/metrics":
    ...
    else:
        try:
            payload = self._get_metrics()
        except Exception as exc:
            self._respond(writer, 503, {"metrics": False, "error": type(exc).__name__})
        else:
            self._respond_bytes(writer, 200, payload, EXPOSITION_CONTENT_TYPE)
```

### WR-06: HealthSettings.port is an unbounded int; bad ports fail late with a traceback

**File:** `src/pumpgrok/config/settings.py:254-265` (`port: int = 0`)
**Issue:** No `ge`/`le` bound. `PUMPGROK_HEALTH__PORT=99999` passes
`load_settings()` validation, then `serve_replay` -> `asyncio.start_server`
raises `OSError` with an unhandled traceback instead of the project's
fail-fast `ConfigError` + exit code convention. Negative values are caught by
the `port <= 0` check in `_serve_replay_loop` (exit 2), but out-of-range high
ports are not validated anywhere.
**Fix:**
```python
port: int = Field(default=0, ge=0, le=65535)
```

### WR-07: run_replay "leaves no file" comment is false; failed runs leave a ledger file

**File:** `src/pumpgrok/replay/runner.py:126-127` (comment) vs `:143-144` (`recreate_ledger_db(target)`)
**Issue:** The comment claims "a failed run (corrupt fixture, stale gap,
missing LLM record) leaves no file", but `recreate_ledger_db` (unlink + fresh
empty DB) runs *before* `append_batch` and `store.verify()`. An append or
verify failure after that point leaves an empty-but-valid sqlite file at the
target that file-existence checks will mistake for a successful replay output.
Either the comment or the ordering is wrong.
**Fix:** Move `recreate_ledger_db(target)` back above the checks is wrong too
(it would delete on every attempt); instead unlink the target on failure:
```python
try:
    stored = store.append_batch(...)
    if not store.verify():
        raise LedgerInconsistent("replay ledger failed verification")
except Exception:
    store.close()
    with contextlib.suppress(OSError):
        Path(target).unlink()
    raise
```
or correct the comment to state the actual guarantee.

### WR-08: Image HEALTHCHECK probes :8080 but the default image command never binds a port

**File:** `Dockerfile:29-30` vs `Dockerfile:33-36` (ENTRYPOINT/CMD one-shot)
**Issue:** The image-level `HEALTHCHECK` curl-probes port 8080, but the
image's default command is the one-shot skip-only replay cycle, which exits 0
without starting any server (INV-C-11: `--once`/`--replay` force port 0). A
bare `docker run` of the image reports unhealthy during its whole (brief) life;
any orchestration that waits on `healthy` before proceeding hangs until the
container exits. The compose-level healthcheck (correct for serve) already
overrides this, so the image-level one only harms non-compose runs.
**Fix:** Remove the `HEALTHCHECK` from the Dockerfile and keep the probe
solely in `docker-compose.yml` (serve path only), or gate the probe on the
serve command.

## Info

### IN-01: orders_total is always 0 under serve (event wiring absent)

**File:** `src/pumpgrok/supervisor/scheduler.py:706-713`
**Issue:** The module docstring in `metrics.py` documents `note_order` for the
live path and `sync_orders` ledger reconciliation at scrape time, but the serve
`_snapshot` provides neither `"orders"` nor calls either method, so
`pumpgrok_orders_total` scrapes `0` forever in the only production wiring.
Deliberate for replay (no orders exist), but the gap between the documented
design and the wired behavior should be pinned by a test asserting the serve
snapshot keys.
**Fix:** Add a test asserting the serve snapshot emits exactly
`{"ledger_seq", "kill_switch"}` and documents why orders/breakers/equity are
absent in replay mode.

### IN-02: Unknown paths and query strings fall through to the full status body

**File:** `src/pumpgrok/supervisor/health.py:147-155`
**Issue:** `_path_of` returns the raw path including any query string, so
`/metrics?x=1` misses the metrics branch and returns JSON status, and
`/nope` returns the full health body (200/503) instead of 404. No write route
exists, so this is fingerprinting noise at most, but a Prometheus scrape with
params would silently get JSON instead of exposition format.
**Fix:** Strip query strings (`path.split("?", 1)[0]`) and return 404 for
unknown paths.

### IN-03: hermes-verify-isolation.sh iterates env names via unquoted command substitution

**File:** `scripts/hermes-verify-isolation.sh:107-115`
**Issue:** `for name in $(env | cut -d= -f1 | grep '^PUMPGROK_' || true)` relies
on word splitting; correct today (env names cannot contain whitespace) but
fragile under `set -u` + shellcheck (SC2046/SC2086 class). Also unsets run in
a subshell, which is correct but subtle.
**Fix:**
```bash
while IFS= read -r name; do unset "$name"; done < <(env | cut -d= -f1 | grep '^PUMPGROK_' || true)
```

### IN-04: FixtureClock.jump allows _now below zero with no validation

**File:** `src/pumpgrok/replay/clock.py:114-128`
**Issue:** A large negative `delta_s` drives `_now` negative (or before fixture
start) with no guard; `advance_to`'s backwards check is bypassed by design for
skew tests. Downstream is safe today (`seat_task.py:334` clamps durations with
`max(0.0, ...)`), but a negative virtual clock is a footgun for future
consumers of `now()` (ordering, idempotency scopes, rollover days).
**Fix:** Clamp at zero or record the jump in a diagnostic counter:
```python
self._now = max(0.0, self._now + delta_s)
```

---

_Checked against: `docs/SAFETY_INVARIANTS.md` invariant matrix (INV-C, INV-R,
INV-S rows), the live gate (`live_gate.py`), and the serve/metrics/health call
chain end to end. Test-only and fixture files were skimmed for contract drift;
no findings there. `tests/fixtures/secrets/planted.txt` is an intentional
scanner-canary fixture, not a leaked secret._

_Reviewed: 2026-10-22_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_

---
phase: 05-hardening
reviewed: 2026-10-22T12:30:00Z
depth: deep
files_reviewed: 108
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
  - tests/replay/test_runner_determinism.py
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
  - tests/supervisor/test_scheduler.py
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
  warning: 1
  info: 4
  total: 5
status: issues_found
---

# Phase 05: Code Review Report (iteration 2, post-fix re-review)

**Reviewed:** 2026-10-22T12:30:00Z
**Depth:** deep
**Files Reviewed:** 108
**Status:** issues_found

## Summary

Re-reviewed the full phase 5 diff (b558790..HEAD) against the post-fix tree,
with focus on (a) verifying each iteration-1 warning WR-01..WR-08 is actually
fixed in the current source, and (b) hunting regressions introduced by the fix
commits f529c0a..5e58da2 (including the lint autofix chain 0b6fef2..ac486f0).

All eight prior warnings verify as FIXED, each with a pinning test. No
regressions found in the fix or lint commits: the import hoists (525dabc) are
test-only reorderings with no src-side cycle risk (src never imports tests);
the SIM102 collapses (056495c) are semantics-identical boolean merges in
test scanners; the re-export drop (397a3d7) is safe (no importer of
`build_status` from the `pumpgrok.supervisor` package exists); the
`ClearRefused` import (8e9487c) fixes a genuine latent NameError in the
killswitch-clear error path in cli.py:843 and is pinned by a new test; the
receipt-test rework (5e58da2) is a correct subset check
(`tracked_json <= allowed`).

One new low-severity warning (WR-09): the `PUMPGROK_HEALTH__HOST` knob added by
the WR-02 fix has no value validation, so a typo escapes the fail-fast
ConfigError convention as an unhandled socket traceback. The four iteration-1
info items were re-verified as still present and unchanged (deliberate
behaviors, carried over). No CRITICAL findings: no live-trading bypass, no
secrets, no injection in the new or fixed code.

## Prior Findings Verification (iteration 1: WR-01..WR-08)

| ID | Status | Evidence in current tree |
|----|--------|--------------------------|
| WR-01 | fixed | `src/pumpgrok/doctor.py` has exactly one `SUBSYSTEMS` definition (line 19); the duplicate block is deleted (commit f529c0a, 15 deletions). |
| WR-02 | fixed | `serve_replay` takes `host: str = "127.0.0.1"` (`scheduler.py:778`), binds via `server.start(host, port)` (`:804`); CLI threads `settings.health.host` through (`cli.py:571-574`); compose opts the container into `0.0.0.0` while publishing host-loopback only. Pinned by `test_serve_host_env_override` and `test_serve_replay_binds_loopback_by_default`. |
| WR-03 | fixed | `_emit_rollover` catches `sqlite3.IntegrityError` before generic `Exception`, latches `_last_rollover_day`, and returns quietly (`scheduler.py:417-421`). Precise: the insert uses the day-keyed `rollover_key(day)` as `idempotency_key`, and `store.append` re-raises sqlite errors unwrapped (`store.py:214-217`), so the handler can only fire when the row already exists. |
| WR-04 | fixed | Shared `kill_switch_engaged(store)` latch (`scheduler.py:106-121`) mirrors the `KillSwitch.poll` fold (same `read(limit=None)` scan as `killswitch.py:281`); both `health_status` (`:470`) and the serve `_snapshot` (`:747`) read it over the same store object built in `build_serve_replay`, so body and gauge cannot disagree. Pinned by new serve-mode tests. |
| WR-05 | fixed | `HealthServer._handle` wraps `self._get_metrics()` in try/except and responds explicit `503 {"metrics": False, "error": <type>}` (`health.py:143-146`) instead of dropping the connection. Pinned by `test_metrics_route_snapshot_failure_is_503_with_body` (asserts 503 + JSON content type + exact payload). |
| WR-06 | fixed | `HealthSettings.port` is now `Field(default=0, ge=0, le=65535)` (`settings.py:268`); out-of-range values fail fast as `ConfigError`. Pinned by `test_health_port_rejects_out_of_range_values` (99999/65536/-1 rejected, 65535 accepted). |
| WR-07 | fixed | The `except` path calls `recreate_ledger_db(target)` (`runner.py:185`), which despite its name is delete-only (unlinks sqlite plus -wal/-shm, `store.py:71-76`; it creates nothing). The `finally: store.close()` after the unlink closes a WAL fd against a deleted inode without recreating the file. Pinned by `test_verify_failure_removes_the_created_ledger`. |
| WR-08 | fixed | No `HEALTHCHECK` in Dockerfile (commit 2b8ca3b); the comment block records that liveness for the serve path lives in `docker-compose.yml`, whose probe targets container-loopback `/healthz` (reachable since the container binds `0.0.0.0`) and whose publish is host-loopback-only. |

## Warnings

### WR-09: New `PUMPGROK_HEALTH__HOST` knob has no value validation; typos escape fail-fast

**File:** `src/pumpgrok/config/settings.py:267`
**Issue:** The WR-02 fix added `host: str = Field(default="127.0.0.1", min_length=1)`
alongside the now-bounded port (`ge=0, le=65535`). Any nonempty string passes
validation, so a typo such as `PUMPGROK_HEALTH__HOST="256.300.1.1"` (or a blank
`" "`) survives `load_settings()` and only fails later inside
`asyncio.start_server(host, port)` (`scheduler.py:804`) with an unhandled
`socket.gaierror` traceback. The project's convention (and the WR-06 fix) is
that bad serve config fails fast as `ConfigError` (exit 2); `_serve_replay_loop`
(`cli.py:568-574`) guards only `port <= 0`, so the host path is inconsistent
with the port path it was added beside. Fails loudly, operator-error only,
hence Warning rather than Blocker; the existing test
(`test_serve_host_env_override`) pins the happy path only.
**Fix:** Validate at load time and raise `ConfigError` on failure, e.g.
```python
import ipaddress

try:
    ipaddress.ip_address(v)  # or accept a hostname regex for names
except ValueError:
    raise ConfigError(f"invalid health host: {v!r}")
```
or resolve-and-convert in `health_port()` / `_serve_replay_loop` so a bad host
exits 2 with a message instead of a traceback.

## Info

### IN-01: orders_total is always 0 under serve (carried over, unchanged)

**File:** `src/pumpgrok/supervisor/scheduler.py:741-747`
**Issue:** The serve `_snapshot` still returns only `{"ledger_seq", "kill_switch"}`;
no `"orders"` key, so `pumpgrok_orders_total` scrapes `0` in the only production
wiring despite `note_order`/`sync_orders` support in `Metrics`. Deliberate for
replay (no orders exist); noted for a future test pinning the serve snapshot keys.

### IN-02: Query strings miss the /metrics branch; unknown paths return the health body (carried over, unchanged)

**File:** `src/pumpgrok/supervisor/health.py:136-137`, `:163-170`
**Issue:** `_path_of` returns the raw request target, so `/metrics?x=1` falls
through to the JSON status branch and `/nope` returns the health body (200/503)
instead of 404. No write route exists; fingerprinting noise at most.

### IN-03: hermes-verify-isolation.sh iterates env names via unquoted command substitution (carried over, unchanged)

**File:** `scripts/hermes-verify-isolation.sh:112`
**Issue:** `for name in $(env | cut -d= -f1 | grep '^PUMPGROK_' || true)` relies on
word splitting (SC2046/SC2086 class). Correct today (env names cannot contain
whitespace); fragile under `set -u` + shellcheck.

### IN-04: FixtureClock.jump allows _now below zero (carried over, unchanged)

**File:** `src/pumpgrok/replay/clock.py:114-128`
**Issue:** A large negative `delta_s` drives `_now` negative with no guard.
Downstream is safe today (`seat_task.py` clamps durations); a negative virtual
clock is a footgun for future consumers of `now()`.

---

*Reviewed: 2026-10-22T12:30:00Z*
*Reviewer: Claude (gsd-code-reviewer)*
*Depth: deep*

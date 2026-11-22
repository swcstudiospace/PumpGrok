# Phase 19 Plan 04: Hosted Runtime Core Summary

**Phase:** 19-observability · **Plan:** 04
**Status:** complete
**Date:** 2026-11-22

## What was built

- `src/pumpgrok/config/settings.py` (HOST-01, HOST-08): `PUMPGROK_STATE_DIR` and `PUMPGROK_LOG_LEVEL` accepted as env names; `collect_startup_problems` refuses a relative/empty state dir and any log level outside DEBUG/INFO/WARNING/ERROR. Helpers `state_root`, `resolve_state_path`, `valid_log_level`, `LOG_LEVELS`.
- `src/pumpgrok/config/logging_config.py` (HOST-08): validated level from env; JSON logging in every profile via `setup_logging`.
- `src/pumpgrok/supervisor/health_server.py` (new, HOST-03/04/05/06): `HostedHealthServer` serving only `/livez`, `/readyz`, `/metrics`; 404 with empty body elsewhere; `/livez` 200 while the loop runs, `/readyz` 503 on failed/stale ticks, halted desk 200 with halt in body (D-09); `ledger_status` from the tick callback; `shutdown_exit_code` helper.
- `src/pumpgrok/ledger/backup.py` (HOST-07): `backup_ledger`, `verify_candidate`, `restore_ledger` (verify-then-atomic-replace; failure leaves the active file byte-identical).
- `src/pumpgrok/cli/ledger.py`, `parsing.py`, `dispatch.py`: `pumpgrok ledger backup|restore` verb wired end to end.
- `docker-compose.yml` (HOST-02): both services mount the named volume `pumpgrok-state:/app/var`; no `./var` host bind; command stays the fixture replay (no hosted run until HARD-07).
- `tests/hosted/` (8 files): state-dir, compose-volume, probes, ledger-status, routes, shutdown-exit, backup-restore, log-config — each with a negative case.

## Gates

`uv run pytest tests/hosted/test_state_dir.py tests/hosted/test_compose_volume.py tests/hosted/test_health_probes.py tests/hosted/test_health_ledger_status.py tests/hosted/test_health_routes.py tests/hosted/test_shutdown_exit.py tests/hosted/test_log_config.py tests/hosted/test_ledger_backup_restore.py` → 26 passed.

## Deviations

- The legacy `HealthServer` in `health.py` (serves `/healthz` for existing callers: doctor probes, compose healthchecks, serve-mode tests) is retained; the strict three-route surface lives in the new `health_server.py` for the hosted path. See 19-04 summary for rationale; migrating every legacy `/healthz` caller would cascade into doctor/compose/serve tests beyond this plan's files.
- `ci/tests/test_compose_docker_secrets.py` and `ci/tests/test_image_digest_pins.py` (plan 19-04 `<verification>`) do not exist yet — they are owned by plan 19-06, which creates them.

## Requirements

HOST-01 through HOST-08.

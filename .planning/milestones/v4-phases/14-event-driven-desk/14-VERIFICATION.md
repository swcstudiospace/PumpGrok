---
phase: 14-event-driven-desk
verified: 2026-11-22
status: passed
score: 9/9 plans summarized
---

# Phase 14: Event-driven desk and Grok gateway — Verification Record

**Phase goal:** The supervisor wakes seats on events instead of cadence polling
(cadence mode stays the default and byte-identical), every Grok call is a
consequence of an event and passes one gateway (prefilter, sanitize, cache,
in-flight coalescing, layered persisted budget, fallback ladder), exits and
risk can never wait on Grok, ten event-mode seat cycle bodies exist, Hermes
cron sessions that duplicate events are disabled, and an idle desk makes
zero Grok calls. (`.planning/milestones/v4-phases/14-event-driven-desk/14-CONTEXT.md`)

**Verification basis:** This record maps each plan's SUMMARY claim to the
evidence paths that landed on `main` via merged PR #134 (CI green per the
phase audit). No verification commands were run for this record, and no new
test output is claimed here; gate outcomes below cite the outcomes already
recorded in the plan SUMMARYs / audit, not a re-execution.

## Per-plan claim → evidence (merged PR #134, on main)

| Plan | SUMMARY claim | Evidence paths on main |
|---|---|---|
| 14-01 Grok gateway core | Single gateway in `src/pumpgrok/grok/`: deterministic prefilter (skip before budget spend), sanitizer + strict JSON parse, canonical cache key of ints/strings with per-agent TTLs, in-flight coalescing, layered persisted budget with reserve share, hash-only gateway ledger, replay backend raising on miss; `BudgetSurface` on `core/llm.py`; `GrokGatewaySettings` re-exported from `config/sections/grok_gateway.py`; exits/risk/execution do not import the gateway | `src/pumpgrok/grok/__init__.py`, `src/pumpgrok/grok/prefilter.py`, `src/pumpgrok/grok/sanitize.py`, `src/pumpgrok/grok/cache.py`, `src/pumpgrok/grok/coalesce.py`, `src/pumpgrok/grok/budget.py`, `src/pumpgrok/grok/ledger.py`, `src/pumpgrok/grok/replay.py`, `src/pumpgrok/core/llm.py`, `src/pumpgrok/config/sections/grok_gateway.py`; tests `tests/grok/test_prefilter.py`, `tests/grok/test_cache.py`, `tests/grok/test_cache_key_payload.py`, `tests/grok/test_coalesce.py`, `tests/grok/test_budget.py`, `tests/grok/test_replay_backend.py`, `tests/replay/test_replay_determinism.py` (gate outcomes as recorded in `14-01-SUMMARY.md`) |
| 14-02 Agents behind gateway + fallback ladder | `SignalSeat`, `ScoutSeat`, `WhaleSeat`, `RugSeat` route every Grok call through the single gateway with an event consequence id; no agent imports `agents.base` / constructs `GrokAgent`; `FallbackLadder` follows `signal_scoring_mode` with breaker and single-flight half-open probe on FixtureClock | `src/pumpgrok/engine/agents/signal.py`, `src/pumpgrok/engine/agents/scout.py`, `src/pumpgrok/engine/agents/whale.py`, `src/pumpgrok/engine/agents/rug.py`, `src/pumpgrok/grok/fallback.py`; tests `tests/engine/test_gateway_agents.py`, `tests/grok/test_fallback_ladder.py`, `tests/grok/test_sanitize_injection.py` (gate outcomes as recorded in `14-02-SUMMARY.md`) |
| 14-03 Supervisor event wake | `wake.py` maps every `EventKind` to seat wakes via closed `SEAT_WAKES`; only the `wake` timer allowed, `assert_allowed_timers` fails closed otherwise; `--wake-mode {cadence,event}` on `run` (default cadence); cadence modules do not import `wake`; `metrics_events.py` registers five event/Grok families only in event mode, nine existing families unchanged | `src/pumpgrok/supervisor/scheduler/wake.py`, `src/pumpgrok/supervisor/metrics_events.py`, `src/pumpgrok/supervisor/metrics.py`; tests `tests/desk/test_event_wake.py`, `tests/desk/test_event_mode_run_once.py`, `tests/supervisor/test_scheduler.py`, `tests/supervisor/test_metrics.py`, `tests/desk/test_metrics_events.py` (gate outcomes as recorded in `14-03-SUMMARY.md`) |
| 14-04 Ten seat cycles + drain parity | `event_cycles.py`: one cycle body per seat (ten seats) invoked on wakes with only the waking event's typed fields; unknown seat fails loudly; at most one cycle per seat per wake; `journal_rollup.py` counts journal wakes by kind; `event_cycles_aux.py` wraps Phase 12 drain as `DeterministicBus` (`fixture_compat` required); golden hashes pinned for smoke / smoke-10m / soak-3d; legacy smoke-10m `events.hash` b69c… parity proof passes via `verify_fixture` with zero skipped tests | `src/pumpgrok/supervisor/scheduler/event_cycles.py`, `src/pumpgrok/supervisor/scheduler/event_cycles_aux.py`, `src/pumpgrok/supervisor/scheduler/journal_rollup.py`; tests `tests/desk/test_event_cycles.py`, `tests/desk/test_event_cycles_aux.py`, `tests/desk/test_journal_rollup_event.py`, `tests/desk/test_event_golden_hashes.py`, `tests/replay/test_event_drain_parity.py` (gate outcomes as recorded in `14-04-SUMMARY.md`) |
| 14-05 Hermes cutover + doctor refusal | Five bus-duplicated jobs (scout-discover, scout-pipeline, risk-audit-open-leads, rug-watch-paper, chief-journal-rollup) disabled, not deleted, in `hermes/cron/jobs.yaml`; `chief-pickup` stays enabled; `docs/runbooks/events.md` documents cutover/re-enable/single-writer; `doctor_report(wake_mode="event")` and `doctor --wake-mode event` refuse while a superseded job is enabled (naming it), unparsable jobs file refuses fail-closed; read-only time-sync probe; `--wake-mode` defaults to cadence | `hermes/cron/jobs.yaml`, `docs/runbooks/events.md`, `src/pumpgrok/doctor.py`, `src/pumpgrok/cli/wake_mode.py`; tests `tests/desk/test_hermes_jobs_superseded.py`, `tests/test_doctor_event_mode.py`, `tests/cli/test_wake_mode.py`, `tests/test_doctor_time_sync.py` (gate outcomes as recorded in `14-05-SUMMARY.md`) |
| 14-06 Idle-zero-Grok gate | `events/idle.py`: 24 virtual hours on FixtureClock with zero source events, counting gateway calls via a counting transport fake; `check_idle_grok` prints `idle-grok calls=0` and exits 0 on silence, non-zero otherwise; wired into `run_all.py`, `Makefile idle-grok`, `ci.yml` idle-grok step without `or-true` masking; degradation suite covers hung-transport exit deadline (ExitTrigger never delayed), poison/duplicate/P0-flood/gap paths, no-grok-import guard for exit rules/risk/execution | `src/pumpgrok/events/idle.py`, `ci/gates/check_idle_grok.py`, `ci/gates/run_all.py`, `Makefile`, `.github/workflows/ci.yml`; tests `tests/events/test_idle_zero_grok.py`, `ci/tests/test_idle_grok_gate.py`, degradation suite under `tests/degradation/` (gate outcomes as recorded in `14-06-SUMMARY.md`) |
| 14-07 Metrics + measurement | `scripts/measure_grok_calls.py` runs gateway (prefilter + cache) over a recorded dataset on FixtureClock, prints before/after JSON (counts only); `evidence-50` fixture carries 320 tick events over 60 distinct mints (60 admitted candidates, loads via `load_dataset`); no production behavior change | `scripts/measure_grok_calls.py`, `tests/fixtures/replay/evidence-50/`; test `tests/replay/test_evidence50_fixture.py` (gate outcomes, including `calls_before`/`calls_after`/ratio runs, as recorded in `14-07-SUMMARY.md`) |
| 14-08 Operator onboarding | `src/pumpgrok/onboarding/`: snapshot-pinned input inventory (five inputs, per-mode required/optional/forbidden/not-read), `doctor --json` readiness records (name, required_for_mode, status, source; presence/source only, never a secret value), paper start gate refusing with missing inputs named, seat access grants only as operator-choice ledger rows, wallet base58 + Ed25519 curve-point validation, RPC host-only choice records, empty x.ai key counts as missing, HMAC key forbidden in live; deviations recorded (paper refusal exit 5 to preserve `test_skip_cycle.py` characterization; `config/sections/onboarding.py` importable but not composed into `Settings` to avoid changing the pinned settings surface digest) | `src/pumpgrok/onboarding/` (inventory, doctor readiness, start gate, seat access, wallet/RPC choice records), `src/pumpgrok/config/sections/onboarding.py`; tests under `tests/onboarding/` (gate outcomes as recorded in `14-08-SUMMARY.md`) |
| 14-09 Phase close | `CHANGELOG.md` Phase 14 entry records equal before/after pairs: smoke-10m `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` and trading-smoke `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54`, plus events-smoke-10m golden `888e1849…` and events-soak-3d golden `c08ad0dd…`; `scripts/probe_curve_layout.py` deleted with all references removed (probe test files, doc-commands offline test probe half, `docs/CURVE_LAYOUT_PROBE.md`, stale mentions); contracts untouched | `CHANGELOG.md`, `tests/fixtures/replay/pins/trading_smoke.json`, absence of `scripts/probe_curve_layout.py` and `docs/CURVE_LAYOUT_PROBE.md`; tests `tests/replay/test_replay_hash_pin.py`, `tests/replay/test_trading_smoke_pin.py` (gate outcomes as recorded in `14-09-SUMMARY.md`) |

## Cadence-default byte-identical caveat (explicit)

Cadence remains the default wake mode (`wake_mode=cadence`, `--wake-mode`
default cadence; `14-03-SUMMARY.md`, `14-05-SUMMARY.md`, `14-CONTEXT.md`
invariant). The byte-identical claim for cadence rests on the unchanged
legacy smoke-10m `events.hash`
(`b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`,
recorded before/after in `CHANGELOG.md` via `14-09-SUMMARY.md`) and on the
cadence-default wiring recorded in the plan SUMMARYs and the phase audit —
this verification record did not itself run a cadence byte-diff, and it does
not claim one. Event-mode goldens (`events-smoke-10m` `888e1849…`,
`events-soak-3d` `c08ad0dd…`) differ by design and are not evidence of
cadence byte-identity; only the legacy cadence/replay hash is.

## ROADMAP success-criteria verdict

Criteria are `.planning/ROADMAP.md` Phase 14, items 1–19 (`.planning/ROADMAP.md:147-172`).
Verdicts cite the SUMMARY/audit record for the merged PR #134, per this
record's basis above; no re-execution is claimed.

| # | Criterion (short) | Verdict | Recorded evidence |
|---|---|---|---|
| 1 | lint/typecheck/test/check.sh + paper smoke exit 0 (PRC-01) | PASS | `14-09-SUMMARY.md` records `make lint`, `make typecheck`, `./scripts/check.sh`, and paper smoke as exit 0; `make test` was recorded as running in the 1500 s window at close — the PASS verdict here rests on the audit's CI-green record for merged PR #134, not on a rerun by this record |
| 2 | Grok prefilter/cache/coalesce/budget tests (GRK-01..04) | PASS | `14-01-SUMMARY.md` recorded gate |
| 3 | sanitize-injection + gateway agents (GRK-05, GRK-09) | PASS | `14-02-SUMMARY.md` recorded gate |
| 4 | fallback ladder (GRK-06) | PASS | `14-02-SUMMARY.md` recorded gate |
| 5 | no-grok-in-exit/risk + hung-transport exit (GRK-07) | PASS | `14-06-SUMMARY.md` recorded degradation/no-import evidence; `14-01-SUMMARY.md` records exits/risk/execution do not import the gateway |
| 6 | replay backend + determinism (GRK-08) | PASS | `14-01-SUMMARY.md` recorded gate |
| 7 | event wake + scheduler, cadence unchanged, timers allowed-set (EVT-10) | PASS | `14-03-SUMMARY.md` recorded gate (see cadence caveat above) |
| 8 | drain parity, smoke-10m legacy hash, zero skipped (EVT-08) | PASS | `14-04-SUMMARY.md` recorded gate |
| 9 | idle-zero-Grok gate + CI wiring (EVT-12) | PASS | `14-06-SUMMARY.md` recorded gate |
| 10 | Hermes superseded jobs + doctor refusal (EVT-13) | PASS | `14-05-SUMMARY.md` recorded gate |
| 11 | metrics families event-mode-only (GRK-10) | PASS | `14-03-SUMMARY.md` recorded gate |
| 12 | evidence-50 fixture + measure ratio gate (GRK-11) | PASS | `14-07-SUMMARY.md` recorded gate |
| 13 | ten seat cycles + event golden hashes (RT-01) | PASS | `14-04-SUMMARY.md` recorded gate |
| 14 | degradation suite (EVT-12) | PASS | `14-06-SUMMARY.md` recorded gate |
| 15 | probe script deleted, no references (MKT-03) | PASS | `14-09-SUMMARY.md` recorded gate |
| 16 | contracts diff empty (EVT-10) | PASS | `14-09-SUMMARY.md` recorded gate |
| 17 | smoke-10m hash pinned twice + CHANGELOG pairs + trading-smoke pin (PRC-03) | PASS | `14-09-SUMMARY.md` recorded gate |
| 18 | live `--once` exits 3 (LIV-07) | PASS | `14-09-SUMMARY.md` recorded gate |
| 19 | onboarding suite + clean-env doctor/run refusals (ONB-01..10) | PASS | `14-08-SUMMARY.md` recorded gate |

ROADMAP tracking note: `.planning/ROADMAP.md` still lists Phase 14 as
unchecked/0 of 9 in its status table (`.planning/ROADMAP.md:578` area and
criterion checkboxes); this record verifies the work as landed via PR #134 and
does not itself tick the ROADMAP — ticking is a separate edit outside this
record's target.

## Gates table (already-recorded evidence only)

| Gate (as recorded) | Source | Outcome recorded there |
|---|---|---|
| 14-01 pytest: prefilter/cache/coalesce; budget/replay/determinism; plan verification | `14-01-SUMMARY.md` | exit 0 |
| 14-02 pytest: gateway agents; fallback ladder; sanitize-injection + agents verification | `14-02-SUMMARY.md` | exit 0 |
| 14-03 pytest: event wake/run-once/scheduler; metrics; plan verification | `14-03-SUMMARY.md` | exit 0 |
| 14-04 pytest: event cycles/aux/journal/golden hashes; drain parity; no-SKIPPED check | `14-04-SUMMARY.md` | exit 0 |
| 14-05 pytest: Hermes superseded; doctor event-mode/wake-mode/time-sync; plan verification | `14-05-SUMMARY.md` | exit 0 |
| 14-06 pytest idle gate; `check_idle_grok.py`; degradation/events/grok suites; run_all/ci.yml/Makefile wiring greps | `14-06-SUMMARY.md` | exit 0 |
| 14-07 pytest evidence-50 fixture; `measure_grok_calls.py` on evidence-50 and soak-3d | `14-07-SUMMARY.md` | exit 0 |
| 14-08 pytest onboarding; clean-env `doctor --json --mode live` non-zero; clean-env paper `--once` non-zero | `14-08-SUMMARY.md` | exit 1 / exit 5 (non-zero, as recorded) |
| 14-09 replay pins; live `--once` exit 3; paper smoke replay; probe absence; contracts diff empty; `make lint`; `make typecheck`; `./scripts/check.sh`; `make test` | `14-09-SUMMARY.md` | exit 0, except `make test` recorded as running (1500 s window) — see criterion 1 note |
| Phase merge: PR #134 merged to `main`; CI green | Phase audit (assignment basis) | passed |

No command was executed for this record; the table above is a citation of
already-recorded outcomes, not fresh test output.

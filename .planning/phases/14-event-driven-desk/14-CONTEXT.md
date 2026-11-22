# Phase 14 Context: Event-driven desk and Grok gateway

## Goal

The supervisor wakes seats on events instead of cadence polling (cadence mode stays the default and byte-identical), every Grok call is a consequence of an event and passes one gateway (prefilter, sanitize, cache, in-flight coalescing, layered persisted budget, fallback ladder), exits and risk can never wait on Grok, ten event-mode seat cycle bodies exist, Hermes cron sessions that duplicate events are disabled, and an idle desk makes zero Grok calls.

## Depends on

- Phase 12 (12-02, 12-03: bus, sources, drain) — typed catalog, EventBus lanes, SourceSupervisor, deterministic drain.
- Phase 13 (13-02: live price source and marks) — fail-closed LivePriceSource, held-mint marks.
- Phase 11 plans 11-01, 11-03, 11-04, 11-05, 11-09 (pins, CI, splits, seat_task) — pinned replay hashes, waiver removal, hotspot splits.

## Invariants (non-negotiable)

- Paper-only: `run --mode live --once` exits 3 (LIV-07). No live adapter, no keys, no signing symbols in `src/pumpgrok/` (paper harness in `src/pumpgrok/harness/` may hold a test-only signer stub, never imported by production code).
- smoke-10m events.hash stays `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` at phase close (PRC-03). Trading-smoke hash pinned in `tests/fixtures/replay/pins/trading_smoke.json`; records equal before/after pairs in CHANGELOG.md (trading-smoke pair moves once, in Phase 15).
- Cadence is the default `wake_mode`; event mode is opt-in via `--wake-mode event` / `wake_mode=event`. Cadence output is byte-identical to pre-Phase-14.
- No contract surface changes: `git diff --name-only v4-base -- contracts` is empty (EVT-10).
- Money is integer lamports/base units; time comes only from the injected `Clock`; no `datetime.now|time.sleep` under `src/pumpgrok/events` or `src/pumpgrok/grok`.
- Receipts approved by `human:SomeRandmGuyy` at the ship checkpoint after Phase 14 (no self-approval); journal CHANGELOG PR + chief `.planning` close per PRC-06.
- Do NOT delete `scripts/probe_curve_layout.py` here: it is removed in Phase 14 per criterion 15 (`test ! -e scripts/probe_curve_layout.py`) only after the criterion's preconditions hold; if the file is absent already, the criterion passes trivially. The superseded-probe deletion is planned in 14-09.

## Locked decisions for this phase

- One Grok gateway in `src/pumpgrok/grok/` (prefilter, sanitize, cache, budget, ledger, replay backend) plus `core/llm.py` budget surface. Four agents run behind it; the signal seat never calls `GrokAgent.run` directly.
- Wake in `supervisor/scheduler/wake.py` with `SEAT_WAKES`; remaining timers are exactly the allowed set.
- Hermes cron cutover in `hermes/cron/jobs.yaml` with `docs/runbooks/events.md`, doctor refusal, time-sync probe, `--wake-mode` flag.
- `scripts/measure_grok_calls.py` + `evidence-50` fixture + `ci/gates/check_idle_grok.py` wired into `run_all.py`, Makefile, `ci.yml`.
- Onboarding family ONB-01..ONB-10: input inventory, `doctor --json` missing-input report, paper start gate, seat access approval, wallet/RPC choice record. No secret value is echoed, stored, logged, or written to the ledger.

## Requirement coverage map (26 requirements)

| Area | Requirements | Plans |
|---|---|---|
| Gateway core | GRK-01, GRK-02, GRK-03, GRK-04, GRK-07, GRK-08 | 14-01 |
| Agents + fallback | GRK-05, GRK-09, GRK-06 | 14-02 |
| Wake + scheduler | EVT-10 | 14-03 |
| Seat cycles + drain parity | RT-01, EVT-08 | 14-04 |
| Hermes cutover | EVT-13 | 14-05 |
| Idle-zero-Grok gate | EVT-12 | 14-06 |
| Metrics + measurement | GRK-10, GRK-11 | 14-07 |
| Onboarding | ONB-01..ONB-10 | 14-08 |
| Close | PRC-01, PRC-03 (hashes + CHANGELOG), MKT-03 (probe-script deletion) | 14-09 |

## Plan list

- 14-01 Grok gateway core (Wave 1)
- 14-02 Agents behind gateway + fallback ladder (Wave 2, depends on 14-01)
- 14-03 Supervisor event wake (Wave 2, depends on 14-01; file-disjoint with 14-02)
- 14-04 Ten seat cycles + drain parity (Wave 3, depends on 14-03)
- 14-05 Hermes cutover + doctor refusal (Wave 3, depends on 14-03)
- 14-06 Idle-zero-Grok gate (Wave 4, depends on 14-01)
- 14-07 Metrics + measurement (Wave 4, depends on 14-01)
- 14-08 Operator onboarding (Wave 2, depends on 14-01 config surface; file-disjoint)
- 14-09 Phase close (Wave 5, depends on 14-04..14-08)

## Discuss summary (operator intent capture)

Narrative: with `wake_mode=event`, the recorded smoke dataset runs through the bus to the same hash, an idle desk is silent (zero Grok calls over 24 virtual hours), a hung Grok cannot delay an exit sell, and cadence mode is unchanged. Out of scope: flipping the default `wake_mode` to event (OD-20, next milestone), strategies (Phase 15), promotion (Phase 17), live path (Phase 18), doctor v4 full sections (Phase 19 — only the event-mode refusal + time-sync probe here).

Decisions: prefilter skips before any budget spend; cache key is an explicit payload of ints/strings with per-agent TTLs, fallbacks never cached; layered budget is atomic and restart-safe; exits/risk never import the gateway (static-guard enforced); replay backend raises on miss, never reaches the network.

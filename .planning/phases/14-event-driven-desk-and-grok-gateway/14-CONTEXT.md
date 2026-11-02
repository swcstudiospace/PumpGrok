# Phase 14 CONTEXT: Event-driven desk and Grok gateway

Milestone v4, Phase 14. Goal per ROADMAP: the supervisor wakes seats on events instead of cadence polling (cadence mode stays the DEFAULT and unchanged), every Grok call is a consequence of an event and passes ONE gateway (prefilter, sanitize, cache, in-flight coalescing, layered persisted budget, fallback ladder), exits and risk can never wait on Grok, Hermes cron sessions that duplicate events are disabled in event mode, event-mode seat cycle bodies exist for all ten seats, and an idle desk makes zero Grok calls.

Depends on: Phase 12 (bus, SourceSupervisor, drain), Phase 13 (14-04 reads 13-02), Phase 11 (seat_task split 11-09, pins 11-01). Reuses without re-implementing: core/llm.py GrokOps, core/budget.py CallBudget, engine/agents/base.py GrokAgent._call, replay ReplayLlm and llm_request_for, canonical_request_hash, supervisor/scheduler/{supervisor,seat_task,degraded,serve}.py, metrics.py.

## Locked decisions (NON-NEGOTIABLE)

- D-01: Money integer lamports; Decimal only for ratios.
- D-02: Clock-only time.
- D-03: Live stays refused (exit 3).
- D-04: hashes are identity only; a cache key or request hash is an identity, never a score.
- D-05: mypy --strict, ruff, no dead code, no swallowed errors, no placeholders, ASCII-only docs.
- D-06: Gateway pipeline order: deterministic prefilter (skip before any spend), sanitize, cache, in-flight coalescing, layered persisted budget, execute through the existing GrokAgent._call, strict parse. Fallback ladder follows DegradedState.signal_scoring_mode, whose real values are llm, rule_fallback, observe_only_buys, replay (degraded.py:89-97); the gateway never reads a bus_backlog flag (none exists).
- D-07: Cache key is an explicit payload of ints and strings {kind, agent, model, prompt_sha, schema, sanitizer, input} with every Decimal rendered by str(); `canonical_request_hash` is NOT fed raw requests (its volatile-key regex drops keys containing _at, seed, span and _freeze raises TypeError on Decimal). Tests: Decimal-bearing request gives a stable key; renamed age-like fields do not vanish. TTLs: narrative 24 h, auditor 300 s, timing 900 s, checker 60 s; pessimistic fallbacks never cached; transport errors negative-cached 30 s; LRU 5000.
- D-08: LayeredBudget minute/hour/day windows (defaults 6/60/400) with atomic all-or-nothing try_spend, persisted, windows from clock.now(), fail closed if unreadable; `reserve` priority (the checker) may use the top 20 percent. GrokOps.precheck reports budget.denial_reason() (LayeredBudget has no max_per_day). Fallback is proven with REAL budget exhaustion, not a mocked limiter.
- D-09: Strict parse: the whole reply must be one JSON object (no first-balanced-object scavenging); result models extra=forbid; flags match ^[a-z_]{1,32}$ max 8; reasoning max 400 chars and never fed into a later prompt; a flagged-injection token sends NO untrusted text. Sanitizer: NFKC, strip control/zero-width/bidi, truncate (name 32, symbol 12, description 280, URLs host only).
- D-10: exit_rules, risk, execution and engine/watcher never import pumpgrok.grok (static import-graph test); the gateway runs only in P1 handlers with a 20 s call deadline on clock.timeout; a hung transport cannot delay an ExitTrigger sell. The signal seat calls the gateway, never GrokAgent.run.
- D-11: Supervisor(wake_mode="cadence"|"event"), default cadence. run_once_replay, tick_once and FIXTURE_SEAT_CADENCES behave unchanged "by test" (A4 DOES edit scheduler/serve.py, which hosts run_once_replay): TSMOKE pin and smoke-10m stay green and the A2 parity runs on `smoke`. Event mode: is_due is pending wakes or heartbeat due; wakes per SEAT_WAKES.
- D-12: Allowed timers in event mode are exactly: Heartbeat per seat every 30 s (stale after 3 missed), health.json every 10 s, Timer(daily_rollover) (rollover_key idempotent), reconcile every 300 s and once at start, kill-source poll 2 s, relay tail 2 s, per-position ExitDeadline at open, position watchdog only while positions are open (max_silence_s 30 then a curve read), MTM refresh every 45 s only while positions are open. An idle desk has none beyond heartbeat and health.
- D-13: Hermes (OD-13): in event mode disable scout-discover, scout-pipeline, risk-audit-open-leads, chief-pickup, rug-watch-paper AND chief-journal-rollup (field `superseded_by: events`); the event-triggered journal cycle performs the rollup on Timer(daily_rollover); `require_activity` is dropped because [SILENT] is printed inside an already running session. Doctor refuses event mode while a superseded job is enabled. Cadence mode is unchanged.
- D-14: Seat cycle bodies exist only as _replay_* today (supervisor/scheduler/replay_cycles.py:27-136). 14-05 (RT1a: scout, signal, risk, sniper, exit) and 14-06 (RT1b: whale, rug, shill, journal rollup, chief, heartbeat) add event-mode bodies only; cadence and replay code is not edited. They produce the golden hashes `events-smoke-10m` and `events-soak-3d`.
- D-15: GRKFX evidence-50 fixture is hand-authored (coverage=fixture, never promotion evidence) with unique_buyers, name, symbol, creator so passes_filter admits at least 50 candidates, asserted with the production filter. The ratio gate (scripts/measure_grok_calls.py --max-ratio 0.2) runs on evidence-50 AND soak-3d (soak-3d has 2 mints and no evidence fields, so it alone is vacuous).
- D-16: Chief tests live under tests/desk (wake, metrics, Hermes); T4 and importorskip are deleted; risk-owned idle and hang tests land in 14-07 after the code exists; `! uv run pytest FILE -rs | grep -q SKIPPED` proves no skips.
- D-17: The idle-Grok gate is wired three ways at once because ci/gates/ is overlaid from the base ref (a new gate script is inert in its own PR): run_all.py entry, pytest wrapper ci/tests/test_idle_grok_gate.py, ci.yml step plus Makefile target. Doctor adds a read-only clock-skew probe; event mode and live refuse to start on failure (assert_no_skew at degraded.py:52).
- D-18: The nine metric families (NINE_FAMILIES) stay unchanged; event, Grok, per-strategy P and live-path L families register only in event mode in supervisor/metrics_events.py.

## Grey-area defaults

- G-01: Sidecar tables grok_cache, grok_budget, grok_calls in var/events/events.sqlite. Reason: same non-ledger rule as Phase 12.
- G-02: Replay backend: ReplayBackend wraps ReplayLlm via canonical_request_hash; a miss raises ReplayMissingRecord, never the network; legacy llm.jsonl hashes still resolve. Reason: smoke fixtures keep working.
- G-03: Breaker: 3 consecutive failures sets llm_available false, 60 s Clock cooldown, one half-open probe.

## Phase boundary

In scope: src/pumpgrok/grok/, core/llm.py and budget surface, engine/agents gateway adapters (signal seat), supervisor wake/WakeRouter/DegradedBridge/metrics_events/seat cycles, hermes/cron jobs.yaml and prompts, scripts/measure_grok_calls.py, deletion of scripts/probe_curve_layout.py, doctor event-mode checks, wake-mode CLI flag, idle gate. Out of scope: strategy runtime, promotion, live path, default flip of wake_mode (OD-20).

## Canonical references

src/pumpgrok/supervisor/{seat_task,metrics,lifecycle}.py and scheduler/*, src/pumpgrok/core/{llm,budget}.py, src/pumpgrok/engine/agents/*, hermes/cron/jobs.yaml, hermes/cron/prompts/chief-journal.md, skills/hermes-cron-desk/SKILL.md, docs/runbooks/events.md, ci/gates/run_all.py, research/A-events-grok.md sections 4 to 8.

## Existing code insights

- No non-replay composition root instantiates GrokAgent or GrokOps today (only tests); the gateway owns that wiring.
- Baseline measured about 12 Hermes sessions per hour, 10 of them idle; seat_task._ESCALATION_SEVERITY gains the new Escalation kinds.
- `verify` calls run_once_replay (cli/verbs_ops.py:190); GrokOps.precheck currently reads budget.max_per_day.

## Specifics

- `GrokGateway.call(GrokRequest) -> GrokOutcome`; GrokRequest(agent, schema, tier, prompt_sha, payload, entity, cause_event_id, priority=normal|reserve, ttl_s); AgentPort protocol (name, prompt_sha, build_request, run_network, parse, fallback); outcome carries fallback_level (fresh, cache_hit, coalesced, prefilter_skip, rule_fallback, observe_only_buys, pessimistic).
- SEAT_WAKES (event mode): chief on RiskEdge, SourceStatus change, escalation relay, Heartbeat; scout on TokenLaunched, Migration; risk on CandidateReady, PositionTick (1/s coalesced), OrderOutcome, RiskEdge; exit on PositionTick, ExitDeadline, OrderOutcome(sell), RiskEdge(halt); journal on OrderOutcome, PositionChange(closed), Timer(daily_rollover) with a flush only when dirty.
- Hash rule this phase: smoke-10m and trading-smoke pairs EQUAL; 14-08 additionally records the `events-smoke-10m events.hash` and `events-soak-3d events.hash` golden lines.

## Deferred ideas

Event mode as default; removing stop_loss_poll_seconds from bounds; live per-call cost reconciliation against provider billing; shill seat event source.

## Ownership, receipt and hash rules (every plan of this phase)

- Branch `bot-0N-seat/v4-pPHASE-slug`, one PR per (phase, seat) (PR table below). Receipt `.receipts/bot-0N-seat/v4-pPHASE-slug.json` (task_id = slug, branch = the branch), tracked through the glob `!.receipts/bot-0*/v4-p*.json` from plan 11-01; no other seat edits .gitignore.
- `approved_by` is NEVER self-written and a seat never approves its own work. An agent reviewer (chief for risk-authored work, risk for other seats) reads the diff; human-gated receipts are committed WITHOUT approved_by and the owner adds `human:SomeRandmGuyy` in a batch at the ship checkpoint (after phases 12, 14, 17, 19).
- Seat purity: every path resolves to the plan seat via `resolve_owner(path, load_manifest(DEFAULT_MANIFEST))`; tests/** is risk except tests/desk/** (chief) and tests/engine/** (signal); execution/** sniper; cli/** risk; supervisor/** chief. A foreign-test failure gets a one-file companion plan by the owning seat, merged first.
- Replay hashes: smoke-10m `events.hash` is `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` (seq=2 events=41, verdict and rollover rows only). Trading `smoke` (5 events, seq 11) gave `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54` at HEAD 641927c; plan 11-01 pins it at v4-base; it moves only in plan 15-01. Run receipts in a fresh worktree without var/ledger.sqlite.
- Live stays refused: `uv run pumpgrok run --mode live --once; test $? -eq 3`; nothing arms it.
- Acceptance lines are real commands; exit 0 means success. The G-2 bypass family (collect-only, `--co`, `|| true`, stderr to /dev/null, `--force`, `--dry-run`, inline PUMPGROK_LIVE_ENABLE) never appears; `! cmd -rs | grep -q SKIPPED` proves no skips. Plans touching src also run make lint and make typecheck.


## Plans (9 planned; research/plans.json is the source)

Pull requests in merge order (numbers from research/pr-plan.md):

| PR | Branch | Plans | Approver | Checkpoint |
|----|--------|-------|----------|------------|
| PR-17 | `bot-02-risk/v4-p14-grok-gateway` | 14-01 | bot-00-chief (agent) | CP14 |
| PR-18 | `bot-08-signal/v4-p14-gateway-agents` | 14-02 | bot-02-risk (agent) | CP14 |
| PR-19 | `bot-00-chief/v4-p14-event-wake-cycles` | 14-03, 14-04, 14-05, 14-06 | bot-02-risk (agent) | CP14 |
| PR-20 | `bot-02-risk/v4-p14-doctor-failure-suite-idle-gate` | 14-07 | human:SomeRandmGuyy (batch); agent review first | CP14 |
| PR-21 | `bot-09-journal/v4-p14-changelog` | 14-08 | bot-02-risk (agent) | CP14 |
| PR-22 | `bot-00-chief/v4-p14-close` | 14-09 | bot-02-risk (agent) | CP14 |

### 14-01: Grok gateway core with the explicit cache key payload, and the non-vacuous evidence fixture

- seat bot-02-risk; wave 1; PR-17; depends_on: 12-02; requirements: GRK-01, GRK-02, GRK-03, GRK-04, GRK-05, GRK-06, GRK-07, GRK-08, GRK-11.
- files: src/pumpgrok/grok/__init__.py, src/pumpgrok/grok/gateway.py, src/pumpgrok/grok/prefilter.py, src/pumpgrok/grok/cache.py, src/pumpgrok/grok/budget.py, src/pumpgrok/grok/sanitize.py, src/pumpgrok/grok/ledger.py, src/pumpgrok/grok/replay_backend.py, src/pumpgrok/core/llm.py, tests/grok/test_prefilter.py, tests/grok/test_cache.py, tests/grok/test_coalesce.py, tests/grok/test_budget.py, tests/grok/test_sanitize_injection.py, tests/grok/test_fallback_ladder.py, tests/grok/test_replay_backend.py, tests/safety/test_no_grok_in_exit_risk.py, tests/grok/test_cache_key_payload.py, tests/fixtures/replay/evidence-50/events.jsonl, tests/fixtures/replay/evidence-50/manifest.json, tests/fixtures/replay/evidence-50/llm.jsonl, tests/replay/test_evidence50_fixture.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/grok tests/safety/test_no_grok_in_exit_risk.py tests/replay/test_replay_determinism.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/replay/test_evidence50_fixture.py
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 14-02: Agents behind the gateway (AgentPort adapters, strict parse)

- seat bot-08-signal; wave 2; PR-18; depends_on: 11-01, 14-01; requirements: GRK-05, GRK-09.
- files: src/pumpgrok/engine/agents/base.py, src/pumpgrok/engine/agents/narrative.py, src/pumpgrok/engine/agents/auditor.py, src/pumpgrok/engine/agents/timing.py, src/pumpgrok/engine/agents/checker.py, src/pumpgrok/engine/agents/gateway_agents.py, tests/engine/test_gateway_agents.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/engine/test_gateway_agents.py tests/characterization/test_agents.py
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 14-03: Supervisor event wake: WakeRouter, heartbeat and allowed timers, DegradedBridge, shutdown hook

- seat bot-00-chief; wave 1; PR-19; depends_on: 11-01, 11-09, 12-02, 12-03; requirements: EVT-08, EVT-10, EVT-12.
- files: src/pumpgrok/supervisor/scheduler/wake.py, src/pumpgrok/supervisor/scheduler/supervisor.py, src/pumpgrok/supervisor/scheduler/degraded.py, src/pumpgrok/supervisor/scheduler/serve.py, src/pumpgrok/supervisor/seat_task.py, src/pumpgrok/supervisor/lifecycle.py, tests/desk/test_event_wake.py, tests/desk/test_event_mode_run_once.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/desk/test_event_wake.py tests/desk/test_event_mode_run_once.py
! uv run pytest tests/desk/test_event_wake.py -rs | grep -q SKIPPED
uv run pytest -q tests/replay/test_event_drain_parity.py
uv run pytest -q tests/replay/test_trading_smoke_pin.py
make lint
make typecheck
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 14-04: Event and Grok metrics, call measurement script, Hermes cron cutover, delete the superseded probe script

- seat bot-00-chief; wave 3; PR-19; depends_on: 11-01, 12-02, 13-02, 14-01, 14-02, 14-03; requirements: GRK-10, GRK-11, EVT-13, MKT-03; owner decisions: OD-13.
- files: src/pumpgrok/supervisor/metrics_events.py, src/pumpgrok/supervisor/metrics.py, tests/desk/test_metrics_events.py, scripts/measure_grok_calls.py, hermes/cron/jobs.yaml, hermes/cron/prompts/chief-journal.md, hermes/README.md, skills/hermes-cron-desk/SKILL.md, docs/runbooks/events.md, tests/desk/test_hermes_jobs_superseded.py, scripts/probe_curve_layout.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/supervisor/test_metrics.py tests/desk/test_metrics_events.py
! uv run pytest tests/desk/test_metrics_events.py -rs | grep -q SKIPPED
uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/evidence-50 --min-candidates 50 --max-ratio 0.2
uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/soak-3d --max-ratio 0.2
uv run pytest -q tests/desk/test_hermes_jobs_superseded.py
! uv run pytest tests/desk/test_hermes_jobs_superseded.py -rs | grep -q SKIPPED
python3 ci/gates/check_ownership.py --validate-manifest
! grep -rn probe_curve_layout src tests docs scripts skills Makefile .github
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
```

### 14-05: Event-mode seat cycle bodies, part 1: scout, signal, risk, sniper, exit

- seat bot-00-chief; wave 3; PR-19; depends_on: 11-01, 14-01, 14-02, 14-03; requirements: RT-01, EVT-10.
- files: src/pumpgrok/supervisor/scheduler/event_cycles.py, tests/desk/test_event_cycles.py, tests/desk/test_event_golden_hashes.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/desk/test_event_cycles.py tests/desk/test_event_golden_hashes.py
! uv run pytest tests/desk/test_event_cycles.py -rs | grep -q SKIPPED
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/replay/test_trading_smoke_pin.py
make lint
make typecheck
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 14-06: Event-mode seat cycle bodies, part 2: whale, rug, shill, journal rollup, chief, heartbeat

- seat bot-00-chief; wave 4; PR-19; depends_on: 14-04, 14-05; requirements: RT-01, EVT-13.
- files: src/pumpgrok/supervisor/scheduler/event_cycles_aux.py, tests/desk/test_event_cycles_aux.py, tests/desk/test_journal_rollup_event.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/desk/test_event_cycles_aux.py tests/desk/test_journal_rollup_event.py
! uv run pytest tests/desk/test_event_cycles_aux.py -rs | grep -q SKIPPED
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 14-07: Event-mode CLI flag, doctor refusal and time-sync probe; cross-cutting failure suite and the idle-Grok gate in CI

- seat bot-02-risk; wave 5; PR-20; depends_on: 11-03, 12-03, 14-02, 14-03, 14-04, 14-06; order_after 11-04, 11-05; requirements: EVT-13, EVT-12, GRK-07.
- files: src/pumpgrok/doctor.py, src/pumpgrok/cli/parsing.py, src/pumpgrok/cli/verbs_state.py, tests/test_doctor_event_mode.py, tests/cli/test_wake_mode.py, tests/test_doctor_time_sync.py, tests/degradation/test_event_bus_faults.py, tests/degradation/test_event_recovery.py, tests/degradation/test_event_grok_faults.py, ci/gates/check_idle_grok.py, Makefile, tests/events/test_idle_zero_grok.py, tests/degradation/test_grok_hang_exit.py, ci/gates/run_all.py, ci/tests/test_idle_grok_gate.py, .github/workflows/ci.yml.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/test_doctor_event_mode.py tests/cli/test_wake_mode.py tests/test_doctor_probes.py
uv run pytest -q tests/test_doctor_time_sync.py
uv run pytest -q tests/degradation
uv run python ci/gates/check_idle_grok.py
uv run pytest -q tests/events/test_idle_zero_grok.py tests/degradation/test_grok_hang_exit.py ci/tests/test_idle_grok_gate.py
grep -q check_idle_grok ci/gates/run_all.py
grep -q idle-grok .github/workflows/ci.yml
grep -q idle-grok Makefile
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 14-08: CHANGELOG: golden hashes events-smoke-10m and events-soak-3d; both legacy hash pairs unchanged

- seat bot-09-journal; wave 6; PR-21; depends_on: 14-01, 14-02, 14-03, 14-04, 14-05, 14-06, 14-07; order_after 13-06; requirements: PRC-03, PRC-06.
- files: CHANGELOG.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -qF 'Phase 14: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
grep -qF 'Phase 14: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 14: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 14: trading-smoke events.hash after: $p" CHANGELOG.md
grep -qF 'events-smoke-10m events.hash' CHANGELOG.md
grep -qF 'events-soak-3d events.hash' CHANGELOG.md
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 14-09: Phase 14 close: STATE, verification record, progress table

- seat bot-00-chief; wave 7; PR-22; depends_on: 14-01, 14-02, 14-03, 14-04, 14-05, 14-06, 14-07, 14-08; order_after 13-07; requirements: PRC-06.
- files: .planning/STATE.md, .planning/ROADMAP.md, .planning/phases/14-event-driven-desk-and-grok-gateway/14-VERIFICATION.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -q 'Phase 14' .planning/STATE.md
./scripts/check.sh
test -f .planning/phases/14-event-driven-desk-and-grok-gateway/14-VERIFICATION.md
python3 ci/gates/check_ownership.py --validate-manifest
```

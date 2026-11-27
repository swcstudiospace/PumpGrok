# Roadmap: PumpGrok Desk v3

## Overview

PumpGrok Desk v3 makes the paper desk autonomous and evaluable, closes the integrity gaps the v2 audits found, and documents the codebase for agents. Live trading stays disabled throughout. Five phases follow the owner's sequence. Phase 6 closes the audited invariant violations and the feature-lineage gaps first, so every later phase builds on integer money and fail-closed state. Phase 7 rewrites the docs against that fixed code. Phase 8 adds the holdout-aware backtest, the shared result schema and the paper divergence check. Phase 9 adds bounded, reversible paper parameter promotion and applies the approved constitution amendment together with the code it describes. Phase 10 records live readiness and keeps live refused.

Coverage: all 34 v3 requirements map to exactly one phase (see Traceability in `.planning/REQUIREMENTS.md`).
# Roadmap: PumpGrok Desk v4

## Overview

PumpGrok Desk v4 makes the paper desk event-driven and multi-strategy, and builds a fully tested but DORMANT live path that only a human can arm. Live trading stays disabled throughout: `run --mode live` exits 3 on every default start, no key or signing code enters the desk package, and the constitution amendment is drafted for the owner and applied only by a human-approved pull request. Nine phases continue the v3 numbering. Phase 11 lays the quality foundation first (pinned replay hashes, no PR-number waivers, a fast test path, coverage and complexity ratchets, the six hotspots split behind characterization tests), so every later phase edits small, pinned code. Phase 12 adds the typed event runtime as a library. Phase 13 corrects the curve layout and adds the read-only live feed and recorder. Phase 14 wakes seats on events and puts every Grok call behind one gateway. Phase 15 adds the strategy framework and four baseline strategies in paper. Phase 16 adds Metrics v2 and autonomous strategy backtests. Phase 17 adds per-strategy risk, the promotion lifecycle and the event desk composition root. Phase 18 builds the dormant live path and the segregated signer. Phase 19 adds observability, documentation, a nightly soak and the milestone audit. Every phase closes with the replay hash pairs recorded in CHANGELOG.md; the smoke-10m hash never moves, and the trading-smoke hash moves exactly once, in Phase 15.

Coverage: all 157 v4 requirements map to exactly one phase (see Traceability in `.planning/REQUIREMENTS.md`).

## Shipped

- [x] **v2: PumpGrok Desk v2** - shipped 2026-10-23, 5 phases, 44 plans. Archived: [roadmap](milestones/v2-ROADMAP.md), [requirements](milestones/v2-REQUIREMENTS.md), [audit](milestones/v2-MILESTONE-AUDIT.md).
- [x] **v3: PumpGrok Desk v3** - closed 2026-11-01 with 7 phases (6-10, 20, 21), tech_debt recorded, 36 plans, 34 requirements. Archived: [roadmap](milestones/v3-ROADMAP.md), [requirements](milestones/v3-REQUIREMENTS.md).

## Phases

- [x] **Phase 11: Engineering foundation and quality** - Pinned replay hashes, waivers removed, soak split, coverage and complexity ratchet, six hotspots split behind characterization tests, v4 planning adopted (35 requirements)
- [x] **Phase 12: Event runtime core** - Settings skeleton, single event catalog, EventBus with P0 lane, DLQ, deterministic drain and SourceSupervisor (10 requirements). Verified 2026-11-08 (12-VERIFICATION.md, status passed, 12/12 must-haves); merged to main via PRs #61 to #63.
- [x] **Phase 13: Curve truth, live market data and recorder** - Token-first curve layout, read-only live feed, fail-closed LivePriceSource, marks, recorder, human-reviewed status flips (11 requirements). Correction 2026-11-15: the phrase "fee model v2 selectable" was wrong; the 13-03 receipt records fee model v2 as untouched, so fee model v2 is built in Phase 15 plan 15-07 (FEE-01).
- [x] **Phase 14: Event-driven desk and Grok gateway** - Event-mode supervisor wake, one Grok gateway, ten seat cycles, Hermes cutover, idle-zero-Grok gate and measurement (26 requirements). Closed 2026-11-14 with criterion 1e (paper smoke checkpoint) DEFERRED TO DEPLOYMENT by owner decision: it needs the operator authorization on the Grok Bot machine, not in this repo. Criteria 1a-1d, 2-16, 18, 19 pass on head 634d87e; criterion 17 uses the owner-amended seeded baseline 1dffa784; criterion 12 uses soak-3d-tokens (216 admitted).
- [x] **Phase 15: Strategy framework and multi-strategy paper** - Strategy protocol and runtime, four baseline strategies, parameter identity, fee model v2 default, live-data paper root and Intent router (8 requirements). Closed 2026-11-15 with criterion 1 (paper smoke checkpoint) DEFERRED TO DEPLOYMENT by owner decision, as Phase 14 was. Every other criterion passes on head f3c8472 per the owner record: full make test exit 0 (coverage 91.86%), lint, typecheck and check.sh exit 0, contract diff 0, live exit 3, trading-smoke pin a4461e80 (approved), smoke-10m 1dffa784 unchanged. Open for owner: criterion 14 still names the b69c29 smoke-10m literal, which the measured 1dffa784 does not match. See `phases/15-strategy-framework-and-multi-strategy-paper/15-08-SUMMARY.md`.
- [x] **Phase 16: Backtest v2 and autonomous evaluation** - Metrics v2, round trips, strategy-aware replay, gap segmentation, evidence grading, autonomous backtest scheduler, record and import verbs (8 requirements). Closed 2026-11-17 with criterion 1 (paper smoke checkpoint) DEFERRED TO DEPLOYMENT by owner decision (16-PLANS-INDEX.md row J). Criteria 2, 8, 10, 11, 12 and 13 verified at f05381d, with 8 and 12 re-run at 3414e1d (no src, tests or contracts change in between). Criteria 3 to 7 and 9: test files present at 3414e1d and inside the full make test run (exit 0) at f05381d. Smoke-10m events.hash 1dffa784 and trading-smoke a4461e80 unchanged from 5fa947b. Receipts: .receipts/bot-02-risk/16-07-gates.json, .receipts/bot-09-journal/16-07-changelog.json, .receipts/bot-00-chief/16-07-close.json.
- [ ] **Phase 17: Risk hardening and promotion lifecycle** - Strategy slices and kills, entry checks, feed health, promotion lifecycle, event desk composition root and restart recovery (14 requirements)
- [ ] **Phase 18: Dormant live path, amendment-gated** - Dormant live path: real gate rows, arm scope, desk-signer service, instruction allowlist, shadow mode, amendment applied by a human-approved PR (21 requirements)
- [ ] **Phase 19: Observability, docs, hardening and milestone audit** - Doctor v4, health and metrics sections, alert rules, v4 docs, nightly event soak, waiver removal and the milestone audit (24 requirements)

## Phase Details

### Phase 11: Engineering foundation and quality

**Goal**: The test and quality scaffolding every later phase leans on exists before any feature lands: the trading `smoke` and smoke-10m hashes are pinned, every PR-number waiver is gone, every seat can track its receipt without touching a foreign path, the soak test is out of the default path, coverage and a complexity ratchet are measured, the six hotspots (paper_adapter sell, batch and confirm, RiskEngine._evaluate, cli/backtest, config/settings.py, supervisor/seat_task.py) are split behind characterization tests with the replay hashes unchanged, property tests, a mutation smoke target, an SBOM step, compose hardening and CI coverage of services/ are in place, and the v4 roadmap and requirements are adopted.
**Depends on**: Nothing in v4. The branches start from main after the owner-approved merge of draft PRs 16 to 20 (order 18, 19, 20, 17 for 17 to 20; tag `v4-base`); plans 11-01, 11-03 and 11-09 carry the external prerequisite EXT:PRS-16-20-MERGED
**Requirements**: QLT-01, QLT-02, QLT-03, QLT-04, QLT-05, QLT-06, QLT-07, QLT-08, QLT-09, QLT-10, PRC-03, PRC-04, PRC-05, PRC-09, PRC-10, HARD-01, HARD-02, HARD-03, HARD-04, HARD-05, HARD-06, HARD-07, HARD-08, HARD-09, HARD-10, HARD-11, HARD-12, HARD-19, HARD-24, HARD-25, HARD-26, HARD-30, HARD-31, HARD-32, HARD-33
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py tests/replay/test_runner_determinism.py` exits 0 and `python3 -c "import json;d=json.load(open('tests/fixtures/replay/pins/trading_smoke.json'));assert d['fixture']=='smoke' and len(d['events_hash'])==64 and d['seq']>1"` exits 0; the trading `smoke` ledger hash and full row dump are pinned in a clean cwd, and the preflight `test -f src/pumpgrok/backtest/equity.py && grep -rq 'def is_writer' src/pumpgrok/ledger && grep -rq 'verify_stored_content' src/pumpgrok` exits 0 (it fails until draft PRs 17 to 20 are merged) (PRC-09)
  3. `! grep -nE 'pull_request\.number' .github/workflows/gates.yml` exits 0, `uv run pytest -q ci/tests/test_no_pr_waivers.py ci/tests/test_security_workflows.py` exits 0 and `grep -qF '!.receipts/bot-0*/v4-p*.json' .gitignore` exits 0; no waiver remains and a non-risk seat can track its receipt (PRC-04, PRC-05)
  4. `uv run pytest -q tests/quality/test_fast_split.py` exits 0, `make -n test | grep -q 'not slow'` exits 0 and `make -n test-soak | grep -q 'm slow'` exits 0; the 49 minute soak test is out of the default path and runs through `make test-soak` and nightly CI (QLT-01)
  5. `make cov` exits 0, `grep -n 'fail_under' pyproject.toml` exits 0 and `test -f coverage.xml` exits 0; branch coverage is measured and the floor equals the measured baseline minus one point (QLT-02)
  6. `uv run ruff check .` exits 0, `uv run python -c "import tomllib;s=tomllib.load(open('pyproject.toml','rb'))['tool']['ruff']['lint']['select'];assert {'C901','PLR0912','PLR0915'}<=set(s)"` exits 0 and `uv run pytest -q ci/tests/test_complexity_ratchet.py` exits 0; the legacy baseline only shrinks and every new package is outside it (QLT-03)
  7. `uv run pytest -q tests/characterization tests/config/test_settings_surface_characterization.py tests/cli/test_backtest_verb_characterization.py tests/supervisor/test_seat_task_characterization.py` exits 0 and `! uv run pytest tests/supervisor/test_seat_task_characterization.py -rs | grep -q SKIPPED` exits 0; each hotspot is pinned by a test that passes on both the old and the split code (QLT-05)
  8. `uv run pytest -q tests/quality/test_function_size.py` exits 0, `uv run mypy src/` exits 0 and `uv run pytest -q tests/characterization tests/risk tests/safety tests/replay tests/cli tests/backtest tests/config tests/supervisor tests/execution` exits 0; no function in the successors of the six hotspots exceeds 60 lines and behavior is unchanged (QLT-04)
  9. `uv run pytest -q tests/quality/test_no_plain_swallow.py tests/core/test_manifests_errors.py tests/test_doctor_errors.py tests/tools/onchain/test_onchain_errors.py tests/tools/market/test_jupiter_errors.py` exits 0; the six plain-swallow excepts are narrowed to typed error tuples and a guard rejects new ones (QLT-06)
  10. `uv run python -c "import hypothesis,mutmut,pytest_cov"` exits 0 and `uv run pytest -q tests/property` exits 0; hypothesis covers integer lamport math, reducer ordering and replay determinism (QLT-07)
  11. `make mutation-smoke` exits 0, `grep -q 'risk' docs/mutation-testing.md` exits 0 and `! make -n check | grep -q mutation` exits 0; the target is scoped to risk and execution and is not part of `make check` (QLT-08)
  12. `uv run pytest -q ci/tests/test_sbom_step.py` exits 0; the CycloneDX SBOM is produced as a CI artifact (QLT-09)
  13. `uv run pytest -q tests/safety/test_compose_hardening.py` exits 0 and `uv run python -c "import yaml;yaml.safe_load(open('docker-compose.yml'))"` exits 0; compose services run read-only with tmpfs, all capabilities dropped and no-new-privileges (QLT-10)
  14. `uv run pytest -q ci/tests/test_ci_covers_services.py` exits 0, `make -n typecheck | grep -q services` exits 0, `make -n lint | grep -q services` exits 0 and `make -n audit | grep -q services` exits 0; CI lint, typecheck and audit cover services/ when present (PRC-10)
  15. `uv run pytest -q tests/tools/onchain/test_pump_events.py` exits 0; the pump event decoder is pulled forward and round-trips all five event types (MKT-02)
  16. `uv run pytest -q tests/desk/test_probe_pump_accounts.py` exits 0 and `! grep -nE 'sendTransaction|send_transaction|requestAirdrop|signTransaction' scripts/probe_pump_accounts.py` exits 0; the read-only probe script is delivered and has no send path (MKT-03)
  17. `test -f .planning/milestones/v3-ROADMAP.md && test -f .planning/milestones/v3-REQUIREMENTS.md && grep -qE 'Phase 11: Engineering foundation' .planning/ROADMAP.md && grep -qE 'Coverage: v4 requirements' .planning/REQUIREMENTS.md` exits 0 and `test -f .planning/phases/11-engineering-foundation-and-quality/11-VERIFICATION.md && grep -q 'Phase 11' .planning/STATE.md` exits 0; v3 is archived, the v4 roadmap and requirements are installed and the phase closes with one chief-owned record (PRC-06)
  18. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" && grep -qF "Phase 11: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md && grep -qF "Phase 11: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0, `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 11: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 11: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0; both pairs are recorded and equal, because this phase does not move either hash (PRC-03)
  19. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live stays refused (LIV-07)
  20. `uv run pytest -q tests/hardening ci/tests/test_check_receipt_bypass.py ci/tests/test_check_receipt_reexec.py ci/tests/test_check_secrets_skips.py ci/tests/test_gates_yml_no_mask.py` exits 0; HARD-01 to HARD-12, HARD-19, HARD-24 to HARD-26 and HARD-30 to HARD-33 hold, and HARD-04 remains pending owner confirmation (HARD-01 to HARD-33)

**Checkpoint**: `make test` is fast, coverage and complexity are measured, both replay hashes are pinned, the hotspots are small and characterized, no PR-number waiver remains, and a non-risk seat can open a clean PR.

**Deliverables**:

- [ ] Receipt allowlist glob `!.receipts/bot-0*/v4-p*.json`, waiver removal and the two hash pins (`tests/replay/test_replay_hash_pin.py`, `tests/replay/test_trading_smoke_pin.py`, `tests/fixtures/replay/pins/trading_smoke*.json`) (PRC-03, PRC-04, PRC-05, PRC-09)
- [ ] `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `security-pr.yml` and `docker-compose.yml`: fast and soak split, coverage floor, complexity ratchet, hypothesis, mutmut, SBOM, compose hardening, services in lint, typecheck and audit (QLT-01 to QLT-03, QLT-07 to QLT-10, PRC-10)
- [ ] Characterization tests and the six hotspot splits in `src/pumpgrok/execution/paper_adapter/`, `risk/engine/`, `cli/backtest*.py`, `config/sections/` and `supervisor/seat_*.py` (QLT-04, QLT-05)
- [ ] Narrowed excepts in `tools/onchain/`, `tools/market/jupiter.py`, `doctor.py` and `core/manifests.py` with `tests/quality/test_no_plain_swallow.py` (QLT-06)
- [ ] `tools/onchain/pump_events.py` decoder and `scripts/probe_pump_accounts.py` read-only probe, pulled forward from the live-data phase (MKT-02, MKT-03)
- [ ] v4 `.planning/` adoption: archived v3 roadmap and requirements, installed v4 ROADMAP, REQUIREMENTS and PROJECT (PRC-06)
- [ ] `CHANGELOG.md` Phase 11 entry with the smoke-10m and trading-smoke before and after pairs (PRC-03)
- [ ] Hardening family: `tests/hardening/` and `ci/tests/` checks and the code fixes they name in `src/pumpgrok/`, `ci/gates/`, `.github/workflows/gates.yml` and `tools/desk/receipt_check.py` (HARD-01 to HARD-12, HARD-19, HARD-24 to HARD-26, HARD-30 to HARD-33)

**Plans**: 11 planned (11-01 to 11-11) in 6 waves. Plan ids: 11-01, 11-02, 11-03, 11-04, 11-05, 11-06, 11-07, 11-08, 11-09, 11-10, 11-11. Source of truth: the v4 plan index, which is not in this repository; the plan ids listed here are the list of record. The per-plan PLAN and SUMMARY files are written under `.planning/phases/11-*/` by the GSD workflow. The plan decomposition for the new HARD requirements is produced by gsd-plan-phase when Phase 11 is planned.

### Phase 12: Event runtime core

**Goal**: A typed, bounded, deterministic event runtime exists as a library: every v4 settings section exists once in a config-gated skeleton, frozen event models with derived ids live in one catalog, an EventBus has per-entity FIFO lanes, a never-dropping P0 lane, dedup, coalescing, seeded retry, a persisted DLQ and graceful shutdown, a deterministic drain serves replay, and a SourceSupervisor owns reconnect backoff, staleness, resync and cursors. Nothing is wired into the supervisor yet and the replay path is untouched.
**Depends on**: Phase 11 plans 11-01 (pins and waivers) and 11-04 (settings split); the rest of Phase 11 may run in parallel
**Requirements**: EVT-01, EVT-02, EVT-03, EVT-04, EVT-05, EVT-06, EVT-07, EVT-09, EVT-14, PRC-11
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/config/test_v4_settings_skeleton.py tests/config/test_events_settings.py tests/config/test_live_settings_caps.py` exits 0, `uv run ruff check src/pumpgrok/config` exits 0 and `uv run mypy src/pumpgrok/config` exits 0; every v4 section exists once, defaults are off, and a notional cap above 1.0 SOL refuses to load (PRC-11)
  3. `uv run pytest -q tests/events/test_models.py tests/events/test_bus_lanes.py tests/events/test_bus_backpressure.py` exits 0; event ids are derived, priority is a function of kind, P0 is never dropped, P1 overflow reaches the DLQ, per-entity order is FIFO (EVT-01, EVT-02, EVT-03)
  4. `uv run pytest -q tests/events/test_bus_dedup_coalesce.py tests/events/test_bus_retry_dlq.py tests/cli/test_events_cli.py` exits 0; dedup TTLs, debounce and latest-wins coalescing run on the injected Clock, retries use seeded jitter, `pumpgrok events dlq replay` republishes (EVT-04, EVT-05)
  5. `uv run pytest -q tests/events/test_handler_idempotency.py tests/events/test_bus_shutdown.py` exits 0; double delivery changes no ledger row and `recover()` processes pending events exactly once (EVT-06, EVT-07)
  6. `uv run pytest -q tests/events/test_sources.py tests/degradation/test_event_source_faults.py` exits 0; backoff resets only after stable_s, a 121 second silence yields SourceStatus stale, resync seeds held mints, a corrupt cursor starts clean (EVT-09)
  7. `uv run pytest -q tests/events/test_models_v4_kinds.py tests/harness tests/config` exits 0 and `test "$(grep -rl 'class EventKind' src/pumpgrok | wc -l)" -eq 1` exits 0; one event catalog and one staleness owner exist (EVT-14)
  8. `uv run pytest -q tests/replay/test_event_drain_parity.py -k determinism` exits 0, `uv run pytest -q tests/replay/test_event_drain_parity.py -k smoke_trading` exits 0 and `! uv run pytest tests/replay/test_event_drain_parity.py -rs | grep -q SKIPPED` exits 0; two drains of the same events and seed are byte-identical and the quiescence loop holds (EVT-08, first half; the fixture_compat parity on smoke-10m is proven in Phase 14)
  9. `! grep -rnE 'datetime\.(now|utcnow)|time\.(time|sleep)\(' src/pumpgrok/events` exits 0 and `uv run pytest -q tests/safety` exits 0 with the new packages present; time comes only from the injected Clock and no signing symbol appeared (EVT-01)
  10. `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0` exits 0; no contract surface changed in this phase (`v4-base` is the tag on the commit where draft PRs 16 to 20 are merged) (EVT-14)
  11. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" && grep -qF "Phase 12: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md && grep -qF "Phase 12: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0, `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 12: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 12: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0; both pairs are recorded and equal, because this phase does not move either hash (PRC-03)
  12. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live stays refused (LIV-07)

**Checkpoint**: The event library passes its suite in isolation, the sidecar sqlite never touches the ledger, every v4 settings section is present and off, and replay output is byte-identical.

**Deliverables**:

- [ ] `src/pumpgrok/config/sections/` skeleton for events, grok_gateway, datafeed, recorder, strategies, backtest_v2, risk_strategy, promotion, live, signer and paper_fees, all gated off (PRC-11)
- [ ] `src/pumpgrok/events/` models (the single catalog), bus, store, dlq, drain and sources (EVT-01 to EVT-09, EVT-14)
- [ ] Typed errors in `core/errors.py` and `FaultyEventSource`, `FaultyGrokTransport` fakes in `tests/harness/faults.py`
- [ ] `pumpgrok events dlq list|replay|purge` verb in `src/pumpgrok/cli/events.py` and `docs/design/events-grok.md` (EVT-05)
- [ ] `CHANGELOG.md` Phase 12 entry with both hash pairs (PRC-03)

**Plans**: 5 planned (12-01 to 12-05) in 5 waves. Plan ids: 12-01, 12-02, 12-03, 12-04, 12-05. Source of truth: the v4 plan index, which is not in this repository; the plan ids listed here are the list of record. The per-plan PLAN and SUMMARY files are written under `.planning/phases/12-*/` by the GSD workflow.

### Phase 13: Curve truth, live market data and recorder

**Goal**: The curve account layout is corrected to the official token-first order and probed read-only against live accounts; the paper fee model v2 is selectable and the paper adapter has a paper factory and an entry-gate hook; a bounded, rate-limited, read-only live feed (PumpPortal create and migration frames plus logsSubscribe trade events) produces integer ticks, a LivePriceSource that fails closed, marks for held mints, and a recorder that seals self-verifying datasets with gaps recorded; the datafeed events are bridged onto the Phase 12 bus. LAYOUT_STATUS and EVENT_DECODE_STATUS become VERIFIED only after a human review.
**Depends on**: Phase 12 (12-01 to 12-03 for settings, bus, sources); Phase 11 plans 11-01, 11-06, 11-07 and 11-09 (pins, paper adapter split, decoder, probe script)
**Requirements**: MKT-01, MKT-02, MKT-03, MKT-04, MKT-05, MKT-06, MKT-07, MKT-08, MKT-10, REC-01, REC-02
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/tools/onchain/test_curve_layout.py tests/tools/onchain/test_pump_events.py tests/tools/onchain/test_price_gate.py` exits 0; 49 and 166 byte accounts decode, a bad discriminator is rejected, all five event types round-trip, unknown and unverified sources are refused (MKT-01, MKT-02, MKT-04)
  3. `uv run pytest -q tests/desk/test_probe_pump_accounts.py tests/tools/onchain/test_probe_record.py tests/docs` exits 0, `grep -q 'decoded_pending_review' docs/CURVE_LAYOUT_PROBE.md || grep -qE 'Status: (ASSUMED|VERIFIED)' docs/CURVE_LAYOUT_PROBE.md` exits 0 and `grep -q 'Status: ASSUMED' docs/CURVE_LAYOUT_PROBE.md || (grep -q 'Status: VERIFIED' docs/CURVE_LAYOUT_PROBE.md && grep -qE 'reviewed_by.*human:' docs/CURVE_LAYOUT_PROBE.md)` exits 0; VERIFIED appears only with a human reviewer, otherwise ASSUMED with the exact probe error (MKT-03)
  4. `uv run pytest -q tests/tools/onchain/test_event_decode_status.py tests/tools/onchain/test_probe_record.py` exits 0 and `grep -rqE 'EVENT_DECODE_STATUS[^=]*=\s*"(ASSUMED|VERIFIED)"' src/pumpgrok` exits 0; the flip to VERIFIED needs a human-set reviewed_by, the default is to leave ASSUMED (MKT-10)
  5. `uv run pytest -q tests/execution tests/cli/test_review_trade_prices.py tests/safety/test_blind_advisory.py` exits 0 under the recorded status; the execution tests are status-agnostic and pass before and after the layout rewrite (MKT-04)
  6. `uv run pytest -q tests/execution/test_fee_model_v2.py tests/execution/test_paper_factory.py tests/execution/test_entry_gate_hook.py tests/safety/test_import_graph_no_live.py tests/characterization/execution` exits 0; fee model v2 is selectable with v1 still the default, the paper factory never imports the live path (FEE-01)
  7. `uv run pytest -q tests/datafeed/test_watchset.py tests/datafeed/test_mintbook.py tests/datafeed/test_bridge.py tests/events/test_models_v4_kinds.py` exits 0; the watch set never exceeds its cap, pins held mints and counts overflow, datafeed events map onto bus kinds (MKT-05)
  8. `uv run pytest -q tests/datafeed/test_feed.py tests/test_network_block.py` exits 0; a TIMEOUT reconnect yields no duplicate signature, emits gap events and honors the 30 per 10 s limiter (MKT-06)
  9. `uv run pytest -q tests/datafeed/test_price_source.py tests/datafeed/test_graduation.py` exits 0; price is None when disconnected, a completed curve refuses entry, a gap holds the position, a timeout marks zero (MKT-07)
  10. `uv run pytest -q tests/datafeed/test_marks.py` exits 0; every held mint is marked within 60 s on a fake Clock and no timer exists while flat (MKT-08)
  11. `uv run pytest -q tests/replay/test_live_recorder.py tests/replay/test_live_recorder_manifest_strings.py` exits 0; a sealed dataset passes load_dataset with ticks only and non-decreasing timestamps (REC-01)
  12. `uv run pytest -q tests/replay/test_live_recorder.py -k 'gap or torn'` exits 0; gaps are written to gaps.jsonl and a torn last line is recovered on startup (REC-02)
  13. `uv run pytest -q tests/datafeed/test_readonly.py` exits 0; only allowlisted RPC and PumpPortal methods are reachable (MKT-09, first half; the composition-root test completes in Phase 15)
  14. `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0` exits 0; no contract surface changed in this phase (`v4-base` is the tag on the commit where draft PRs 16 to 20 are merged) (MKT-05)
  15. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" && grep -qF "Phase 13: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md && grep -qF "Phase 13: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0, `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 13: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 13: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0; both pairs are recorded and equal, because this phase does not move either hash (PRC-03)
  16. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live stays refused (LIV-07)

**Checkpoint**: Datasets can be recorded from the live feed without any code path able to send, the curve layout is either VERIFIED by a human or recorded ASSUMED with the probe error, and the paper desk can price entries only from allowlisted sources.

**Deliverables**:

- [ ] `tools/onchain/curve_layout.py` token-first layout and allowlist price gate; `tools/onchain/pump_events.py` status record `EVENT_DECODE_STATUS` (MKT-01, MKT-02, MKT-04, MKT-10)
- [ ] Probe artifacts and `docs/CURVE_LAYOUT_PROBE.md` with the decoded_pending_review record; human-set review for the two VERIFIED flips (MKT-03, MKT-10)
- [ ] `src/pumpgrok/datafeed/` (events, mintbook, watchset, readonly, bridge, portal, logs, resync, fallback, price, graduation, marks) (MKT-05 to MKT-09)
- [ ] `replay/live_recorder.py`, `import_data.py`, `trim.py` (REC-01, REC-02)
- [ ] `execution/fees.py` fee model v2 (selectable, v1 default), `execution/paper_factory.py` and `execution/entry_hook.py` (FEE-01)
- [x] `CHANGELOG.md` Phase 13 entry with both hash pairs (PRC-03)

**Plans**: 7 planned (13-01 to 13-07) in 6 waves. Plan ids: 13-01, 13-02, 13-03, 13-04, 13-05, 13-06, 13-07. Human-gated: 13-05. Source of truth: the v4 plan index, which is not in this repository; the plan ids listed here are the list of record. The per-plan PLAN and SUMMARY files are written under `.planning/phases/13-*/` by the GSD workflow.

### Phase 14: Event-driven desk and Grok gateway

**Goal**: The supervisor wakes seats on events instead of cadence polling (cadence mode stays the default and byte-identical), every Grok call is a consequence of an event and passes one gateway (prefilter, sanitize, cache, in-flight coalescing, layered persisted budget, fallback ladder), exits and risk can never wait on Grok, ten event-mode seat cycle bodies exist, Hermes cron sessions that duplicate events are disabled, and an idle desk makes zero Grok calls.
**Depends on**: Phase 12 (12-02, 12-03: bus, sources, drain); Phase 13 (13-02: live price source and marks); Phase 11 plans 11-01, 11-03, 11-04, 11-05 and 11-09 (pins, CI, splits, seat_task)
**Requirements**: EVT-08, EVT-10, EVT-12, EVT-13, GRK-01, GRK-02, GRK-03, GRK-04, GRK-05, GRK-06, GRK-07, GRK-08, GRK-09, GRK-10, GRK-11, RT-01, ONB-01, ONB-02, ONB-03, ONB-04, ONB-05, ONB-06, ONB-07, ONB-08, ONB-09, ONB-10
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/grok/test_prefilter.py tests/grok/test_cache.py tests/grok/test_cache_key_payload.py tests/grok/test_coalesce.py tests/grok/test_budget.py` exits 0; the prefilter skips before any spend, the cache key is an explicit payload of ints and strings with the stated TTLs, N identical requests make one call, the layered budget is atomic and restart-safe (GRK-01, GRK-02, GRK-03, GRK-04)
  3. `uv run pytest -q tests/grok/test_sanitize_injection.py tests/engine/test_gateway_agents.py` exits 0; the injection corpus is defeated, the four agents run behind the gateway and the signal seat never calls GrokAgent.run directly (GRK-05, GRK-09)
  4. `uv run pytest -q tests/grok/test_fallback_ladder.py` exits 0; the ladder follows signal_scoring_mode with breaker and half-open probe (GRK-06)
  5. `uv run pytest -q tests/safety/test_no_grok_in_exit_risk.py tests/degradation/test_grok_hang_exit.py` exits 0; exit_rules, risk, execution and the watcher do not import the gateway and a hung transport cannot delay an ExitTrigger sell (GRK-07)
  6. `uv run pytest -q tests/grok/test_replay_backend.py tests/replay/test_replay_determinism.py` exits 0; a replay miss raises and never reaches the network (GRK-08)
  7. `uv run pytest -q tests/desk/test_event_wake.py tests/desk/test_event_mode_run_once.py tests/supervisor/test_scheduler.py` exits 0 and `! uv run pytest tests/desk/test_event_wake.py -rs | grep -q SKIPPED` exits 0; event mode wakes seats per SEAT_WAKES, cadence mode is unchanged, the timers are exactly the allowed set (EVT-10)
  8. `uv run pytest -q tests/replay/test_event_drain_parity.py` exits 0 and `! uv run pytest tests/replay/test_event_drain_parity.py -rs | grep -q SKIPPED` exits 0; the DeterministicBus under fixture_compat reproduces the legacy smoke-10m hash with zero skipped tests (EVT-08)
  9. `uv run pytest -q tests/events/test_idle_zero_grok.py ci/tests/test_idle_grok_gate.py` exits 0, `uv run python ci/gates/check_idle_grok.py` exits 0, `grep -q check_idle_grok ci/gates/run_all.py` exits 0, `grep -q idle-grok .github/workflows/ci.yml` exits 0 and `grep -q idle-grok Makefile` exits 0; 24 virtual hours with no source events make zero Grok calls and the gate runs in CI (EVT-12)
  10. `uv run pytest -q tests/desk/test_hermes_jobs_superseded.py tests/test_doctor_event_mode.py tests/cli/test_wake_mode.py tests/test_doctor_time_sync.py` exits 0 and `! uv run pytest tests/desk/test_hermes_jobs_superseded.py -rs | grep -q SKIPPED` exits 0; superseded cron jobs are disabled and doctor refuses event mode while one is enabled (EVT-13)
  11. `uv run pytest -q tests/supervisor/test_metrics.py tests/desk/test_metrics_events.py` exits 0 and `! uv run pytest tests/desk/test_metrics_events.py -rs | grep -q SKIPPED` exits 0; the nine existing metric families are unchanged and the event and Grok families appear only in event mode (GRK-10)
  12. `uv run pytest -q tests/replay/test_evidence50_fixture.py` exits 0, `uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/evidence-50 --min-candidates 50 --max-ratio 0.2` exits 0 and `uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/soak-3d-tokens --max-ratio 0.2` exits 0; the ratio gate runs on a fixture with at least 50 admitted candidates (GRK-11). Owner amendment 2026-11-13: soak-3d has no token facts and is pinned by the soak tests, so the gate runs on the derived synthetic soak-3d-tokens dataset.
  13. `uv run pytest -q tests/desk/test_event_cycles.py tests/desk/test_event_cycles_aux.py tests/desk/test_journal_rollup_event.py tests/desk/test_event_golden_hashes.py` exits 0 and `! uv run pytest tests/desk/test_event_cycles.py -rs | grep -q SKIPPED` exits 0; all ten seat cycle bodies run on wakes and the event-mode golden hashes hold (RT-01)
  14. `uv run pytest -q tests/degradation tests/events tests/grok` exits 0; the failure-injection scenarios (poison handler, transient retry, exit deadline, P0 flood, P1 overflow, duplicates, crash mid-drain, disconnect storm, silent source, gap, corrupt cursor, Grok breaker, budget windows, injection corpus, hung transport, 100 concurrent requests, replay miss, ledger unwritable) pass (EVT-12)
  15. `test ! -e scripts/probe_curve_layout.py && ! grep -rn probe_curve_layout src tests docs scripts skills Makefile .github` exits 0; the superseded probe script is deleted (MKT-03)
  16. `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0` exits 0; no contract surface changed in this phase (`v4-base` is the tag on the commit where draft PRs 16 to 20 are merged) (EVT-10)
  17. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700" && grep -qF "Phase 14: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md && grep -qF "Phase 14: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0, `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 14: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 14: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0; both pairs are recorded. Owner amendment 2026-11-13: the seeded replay grants (approved) moved smoke-10m to the 1dffa784 baseline recorded as the after value; the verify check now expects that baseline, and the before value stays the recorded pre-seeding pin (PRC-03).
  18. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live stays refused (LIV-07)
  19. `uv run pytest -q tests/onboarding` exits 0, `{ env -i PATH="$PATH" HOME="$HOME" uv run pumpgrok doctor --json --mode live >/dev/null; test $? -ne 0; }` exits 0 and `{ env -i PATH="$PATH" HOME="$HOME" uv run pumpgrok run --mode paper --once >/dev/null 2>&1; test $? -ne 0; }` exits 0; ONB-01 to ONB-10 hold, and the paper start is refused until its required inputs and seat access decisions are recorded (ONB-01 to ONB-10)

**Checkpoint**: With wake_mode=event the desk runs the recorded smoke dataset through the bus to the same hash, an idle desk is silent, a hung Grok cannot delay an exit, and cadence mode is unchanged.

**Deliverables**:

- [ ] `src/pumpgrok/grok/` gateway (prefilter, sanitize, cache, budget, ledger, replay backend) and the `core/llm.py` budget surface (GRK-01 to GRK-08)
- [ ] Agents behind the gateway in `src/pumpgrok/engine/agents/` (GRK-05, GRK-09)
- [ ] `supervisor/scheduler/wake.py`, supervisor event mode, `supervisor/metrics_events.py` and `supervisor/scheduler/event_cycles*.py` (EVT-10, GRK-10, RT-01)
- [ ] Hermes cron cutover in `hermes/cron/jobs.yaml`, `docs/runbooks/events.md`, doctor refusal, time-sync probe and the `--wake-mode` flag (EVT-13)
- [ ] `scripts/measure_grok_calls.py`, the `evidence-50` fixture, `ci/gates/check_idle_grok.py` wired into `run_all.py`, the Makefile and `ci.yml` (EVT-12, GRK-11)
- [ ] `CHANGELOG.md` Phase 14 entry with both hash pairs and the `events-smoke-10m` and `events-soak-3d` golden hashes (PRC-03)
- [ ] Grok operator onboarding family (ONB-01 to ONB-10): `tests/onboarding/` checks, the input inventory, the `doctor --json` missing-input report, the paper start gate, seat access approval, and the wallet and RPC choice record

**Plans**: 9 planned (14-01 to 14-09) in 7 waves. Plan ids: 14-01, 14-02, 14-03, 14-04, 14-05, 14-06, 14-07, 14-08, 14-09. Source of truth: the v4 plan index, which is not in this repository; the plan ids listed here are the list of record. The per-plan PLAN and SUMMARY files are written under `.planning/phases/14-*/` by the GSD workflow. The plan decomposition for the new ONB requirements is produced by gsd-plan-phase when Phase 14 is planned.

### Phase 15: Strategy framework and multi-strategy paper

**Goal**: A frozen Strategy protocol, a static registry, a runtime with read-only contexts and per-strategy capital slices exist; parameter identity covers strategy parameters with legacy hashes unchanged; legacy_screening runs through the runtime with fills identical to run_once_replay; three baseline strategies (momentum_breakout, new_launch_sniper, mean_reversion) have bounded, version-controlled parameters and fixture datasets; paper fee model v2 becomes the default with one recorded trading-smoke re-pin; and a live-data paper composition root and an Intent to exec.place router provably cannot send.
**Depends on**: Phase 13 (13-01 datafeed settings and bridge, 13-02 live price source, 13-03 fee model v2 and entry hook); Phase 14 plan 14-03 (supervisor wake); Phases 11 and 12 (pins, settings, bus)
**Requirements**: MKT-09, STR-01, STR-03, STR-04, STR-05, STR-06, FEE-01, RT-02
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/upgrade tests/backtest/test_harness_strategy_identity.py` exits 0, `uv run pytest -q tests/upgrade/test_paramset_hash_stable.py tests/upgrade/test_paramset_strategy.py` exits 0 and `uv run python -c "import tomllib;tomllib.load(open('src/pumpgrok/config/upgrade_bounds.toml','rb'))"` exits 0; ParamSet, bounds and the harness trial identity cover `[strategy.ID.PARAM]` and legacy content hashes are byte-identical (STR-06)
  3. `uv run pytest -q tests/strategies/test_base.py tests/strategies/test_registry.py` exits 0; the strategy version id changes with code or parameters and the declared BOUNDS equal the `[strategy.ID.PARAM]` sections of upgrade_bounds.toml exactly (STR-01)
  4. `uv run pytest -q tests/config/test_paper_event_overlay.py` exits 0; the paper-event overlay (6 open positions, 40 trades per day) exists as a new overlay and the live overlay is unchanged at 3 and 20 (STR-01)
  5. `uv run pytest -q tests/strategies/test_attribution.py tests/strategies/test_allocation.py tests/strategies/test_legacy_parity.py tests/ledger/test_strategy_state.py tests/ledger/test_ticket_refs.py` exits 0; legacy_screening writes no refs, per-strategy P&L folds to the desk total, legacy through the runtime equals run_once_replay fills and net lamports (STR-03)
  6. `uv run pytest -q tests/strategies tests/upgrade` exits 0; every rule flips exactly at its bound and each fixture dataset (`strat-breakout`, `strat-launch`, `strat-reversion`) produces its asserted fills (STR-04)
  7. `uv run pytest -q tests/strategies/test_no_llm.py` exits 0; no hook can reach an LLM client and an idle runtime makes zero calls (STR-05)
  8. `uv run pytest -q tests/strategies/test_recovery.py` exits 0; strategy restart-recovery state restores tapes, peaks and probation (RT-04, library half; the desk wiring is proven in Phase 17)
  9. `uv run pytest -q tests/config/test_paper_fees_default.py tests/backtest/test_fee_parity.py tests/execution/test_fee_model_v2.py` exits 0; fee model v2 is the paper default and backtest and paper fees agree (FEE-01)
  10. `uv run pytest -q tests/desk/test_live_paper_root.py tests/desk/test_exit_rules_filter.py tests/datafeed/test_readonly.py` exits 0; the root refuses to build unless the mode is paper, an AST scan finds no signing or send symbol outside the allowlist, and the global exit book never double-sells a strategy position (MKT-09)
  11. `uv run pytest -q tests/desk/test_intent_router.py tests/desk/test_ticket_approval_allocation.py` exits 0 and `! uv run pytest tests/desk/test_intent_router.py -rs | grep -q SKIPPED` exits 0; strategy Intents reach exec.place only through the router with ticket and approval allocation, and below the autonomous-paper level the router journals refusals and approves nothing (RT-02)
  12. `uv run pytest -q tests/safety/test_import_graph_no_live.py tests/safety/test_no_signing_outside_live_stub.py` exits 0 with `strategies/` and `datafeed/` present (MKT-09)
  13. `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0` exits 0; no contract surface changed in this phase (`v4-base` is the tag on the commit where draft PRs 16 to 20 are merged) (STR-01)
  14. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" && grep -qF "Phase 15: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md && grep -qF "Phase 15: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0 and `uv run pytest -q tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qE 'Phase 15: trading-smoke events.hash before: [0-9a-f]{64}' CHANGELOG.md && grep -qF "Phase 15: trading-smoke events.hash after: $p" CHANGELOG.md && test "$(grep -oE 'Phase 15: trading-smoke events.hash before: [0-9a-f]{64}' CHANGELOG.md | grep -oE '[0-9a-f]{64}')" != "$p"` exits 0; the smoke-10m pair is equal and the trading-smoke pair moves exactly once, from the old pin to the new pin, because of the fee model v2 default (PRC-03)
  15. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live stays refused (LIV-07)

**Checkpoint**: Four strategies run in paper against a recorded or live-fed source with isolated slices, the one deliberate hash move is recorded, and the runtime is off in every default configuration.

**Deliverables**:

- [ ] `ledger/strategy_state.py`, ticket attribution refs and `strategies/allocation.py` (STR-03)
- [ ] `upgrade/params.py`, `upgrade/bounds.py`, `upgrade/gate.py` and `backtest/candidate.py` generalized to strategy parameters, legacy hashes pinned by a golden test (STR-06)
- [ ] `src/pumpgrok/strategies/` base, registry, runtime, tape, attribution, memefilters, recovery, legacy and the three baseline strategies (STR-01 to STR-05, RT-04)
- [ ] `config/upgrade_bounds.toml` strategy sections, the `paper-event.toml` overlay and three fixture datasets (STR-01, STR-04)
- [ ] `execution/fees.py` default flip and the Phase 15 trading-smoke re-pin in `tests/fixtures/replay/pins/` (FEE-01, PRC-03)
- [ ] `supervisor/live_paper.py`, `supervisor/exit_rules.py` ticket filter and `supervisor/intent_router.py` (MKT-09, RT-02)
- [ ] `CHANGELOG.md` Phase 15 entry: equal smoke-10m pair, moved trading-smoke pair (PRC-03)

**Plans**: 8 planned (15-01 to 15-08) in 7 waves. Plan ids: 15-01, 15-02, 15-03, 15-04, 15-05, 15-06, 15-07, 15-08. Source of truth: the v4 plan index, which is not in this repository; the plan ids listed here are the list of record. The per-plan PLAN and SUMMARY files are written under `.planning/phases/15-*/` by the GSD workflow.

### Phase 16: Backtest v2 and autonomous evaluation

**Goal**: Backtests report the full Metrics v2 set with undefined values as None, group fills into round trips, replay strategies through the same pipeline as live-paper on a FixtureClock, segment gapped datasets, grade evidence so that only recorded, complete, long, gap-light data can count toward promotion, and run autonomously and idempotently on dataset or strategy edges. The CLI gains record, replay and strategy backtest verbs and the reports gain a per-strategy section.
**Depends on**: Phase 15 (strategy core and legacy parity); Phase 14 plan 14-07 (CLI wake-mode lane); Phase 13 plan 13-01 (recorder); Phases 11 and 12
**Requirements**: REC-03, BT-08, BT-09, BT-10, BT-11, BT-12, BT-13, OBS-07
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/backtest/test_metrics_v2.py tests/backtest/test_roundtrip.py tests/backtest/test_metrics.py` exits 0 and `! grep -rniE 'expected (return|profit|pnl)|will earn' src/pumpgrok/backtest src/pumpgrok/reporting --include=*.py` exits 0; the formulas hold, undefined values are None, and annualization under 7 days returns annualization_valid=false (BT-08, BT-09)
  3. `uv run pytest -q tests/backtest/test_lookahead.py tests/backtest/test_grading.py` exits 0; traded_only, fixture and hand-authored data never grade as promotion evidence and extreme data after time T never changes a decision at or before T (BT-10)
  4. `uv run pytest -q tests/backtest/test_gaps.py` exits 0; a position open at a gap is flattened with the 500 bps haircut or excluded and flagged, with no entries during the cooldown (BT-11)
  5. `uv run pytest -q tests/backtest/test_strategy_replay.py tests/backtest/test_dataset_curve_source_perf.py` exits 0; legacy_screening replayed on smoke matches the v1 fills and net lamports and the per-mint bisect index meets its perf-shaped test (BT-12)
  6. `uv run pytest -q tests/backtest/test_scheduler.py tests/backtest/test_evidence_provider.py` exits 0; a repeated edge does no work, a run needs read_autonomy at autonomous-paper, no LLM client is constructible, results persist deterministically and the BacktestEvidenceProvider serves the promotion gate (BT-13)
  7. `uv run pytest -q tests/cli/test_record.py tests/cli/test_strategy_backtest.py` exits 0; `run --record`, `replay trim|rebuild-ticks|import` rerun byte-identically (REC-03)
  8. `uv run pumpgrok backtest --fixture smoke-10m > /tmp/bt-a.md && uv run pumpgrok backtest --fixture smoke-10m > /tmp/bt-b.md && cmp /tmp/bt-a.md /tmp/bt-b.md` exits 0; the v3 verb output is byte-identical across runs (BT-06 from v3, unchanged)
  9. `uv run pytest -q tests/reporting/test_strategy_section.py` exits 0; daily and weekly reports carry a per-strategy section whose parts sum to the desk view (OBS-07)
  10. `! grep -rnE 'grid|itertools\.product' src/pumpgrok/engine src/pumpgrok/backtest --include=*.py` exits 0 and `uv run pytest -q tests/backtest/test_single_search_engine.py` exits 0; no second search engine appears (BT-07 from v3, unchanged)
  11. `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0` exits 0; no contract surface changed in this phase (`v4-base` is the tag on the commit where draft PRs 16 to 20 are merged) (BT-12)
  12. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700" && grep -qF "Phase 16: smoke-10m events.hash before: 1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700" CHANGELOG.md && grep -qF "Phase 16: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0, `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 16: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 16: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0; both pairs are recorded and equal, because this phase does not move either hash (PRC-03). Owner amendment 2026-11-15: the criterion 12 baseline is amended from b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d to 1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700, the smoke-10m hash measured at the Phase 14 and Phase 15 heads.
  13. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live stays refused (LIV-07)

**Checkpoint**: A recorded or imported dataset can be backtested per strategy, graded, and the result is persisted and published to the promotion gate as an event.

**Deliverables**:

- [ ] `backtest/metrics_v2.py`, `roundtrip.py`, `event_source.py`, `strategy_run.py`, `gaps.py`, `grading.py` (BT-08 to BT-12)
- [ ] `backtest/scheduler.py`, `store.py` and `evidence.py` (BacktestEvidenceProvider) (BT-13)
- [ ] CLI verbs `run --record`, `live serve`, `replay trim|rebuild-ticks|import`, `backtest --strategy` in `src/pumpgrok/cli/` (REC-03)
- [ ] `reporting/strategy_section.py` per-strategy report section (OBS-07)
- [ ] `CHANGELOG.md` Phase 16 entry with both hash pairs (PRC-03)

**Plans**: 7 planned (16-01 to 16-07) in 6 waves. Plan ids: 16-01, 16-02, 16-03, 16-04, 16-05, 16-06, 16-07. Source of truth: the v4 plan index, which is not in this repository; the plan ids listed here are the list of record. The per-plan PLAN and SUMMARY files are written under `.planning/phases/16-*/` by the GSD workflow.

### Phase 17: Risk hardening and promotion lifecycle

**Goal**: The risk engine enforces per-strategy slices and strategy kills on existing R34 rows (19 rows and the risk_json shape unchanged), entry checks and feed health fail closed, the loss-velocity breaker state and the halt verdict are corrected (live failure classes and the live-path UNKNOWN halt are Phase 18), strategies move BACKTEST to PAPER to LIVE_ELIGIBLE and back on recorded evidence under version-controlled thresholds with no timers and no Grok, and the event desk composition root wires all of it, recovers from restarts, and refuses to build unless paper.
**Depends on**: Phase 15 (strategy core, allocation, ticket attribution); Phase 16 (backtest evidence and CLI); Phase 14 (wake, gateway, seat cycles); Phase 13 (feed, entry hook); Phases 11 and 12
**Requirements**: RSK-01, RSK-02, RSK-03, RSK-05, RSK-08, PRM-01, PRM-02, PRM-03, PRM-04, PRM-05, PRM-06, RT-03, RT-04
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/risk/test_strategy_slice.py tests/risk/test_strategy_kill.py` exits 0; a buy above the slice is capped or rejected on `max_token_fraction`, a kill row blocks buys but not exits and clears only with a human (RSK-01, RSK-02)
  3. `uv run pytest -q tests/risk/test_feed_health.py tests/risk/test_loss_velocity_reset.py tests/risk/test_evaluate_halts_verdict.py tests/supervisor/test_review_scheduler.py` exits 0; staleness is lazy and idle-quiet, a required feed that never ticked fails closed in live mode, the loss-velocity breaker reports half-open from half_open and persists its BreakerReset, and evaluate_halts raises on a corrupt ledger and returns the already-active verdict (RSK-03; S-B1 and S-B2). The live failure producers and the live-path UNKNOWN halt move to Phase 18 (RSK-04; owner decision 2026-11-18)
  4. `uv run pytest -q tests/risk/test_entry_checks.py tests/execution/test_entry_gate_hook.py` exits 0 and `uv run python -c "import tomllib;tomllib.load(open('src/pumpgrok/config/mint_lists.toml','rb'))"` exits 0; authority, Token-2022 extension, holder concentration, list and BLIND cases are rejected, and the desk passes its entry gate into `build_paper_adapter` (`uv run pytest -q tests/execution/test_paper_factory_entry_gate.py tests/desk/test_event_desk_holder_flag.py` exits 0) (RSK-05)
  5. `uv run pytest -q tests/risk/test_step_rows_stable.py tests/characterization/risk` exits 0; STEP_IDS length is 19 and the risk_json shape is unchanged (RSK-08)
  6. `uv run pytest -q tests/promotion/test_stages.py tests/promotion/test_thresholds.py tests/promotion/test_gate_reuse.py tests/upgrade` exits 0; stages are ledger rows with a decision log, a looser threshold than the LiveGate floors refuses to load, the upgrade gate checks are reused and there is no second search (PRM-01, PRM-02, PRM-03)
  7. `uv run pytest -q tests/promotion/test_demotion.py` exits 0 and `uv run pumpgrok promotion demote --help` exits 0; a hash change resets to BACKTEST, demotion is automatic and one operation rolls a strategy back (PRM-04)
  8. `uv run pytest -q tests/promotion/test_no_timers.py tests/desk/test_live_paper_risk_wiring.py` exits 0 and `! grep -rnE 'clock\.sleep|pumpgrok\.grok' src/pumpgrok/promotion` exits 0; the evaluator is event-triggered and subscribed by the composition root (PRM-05)
  9. `uv run pytest -q tests/promotion/test_writer_discipline.py` exits 0; only is_writer callers write and stored content is verified (PRM-06)
  10. `uv run pytest -q tests/desk/test_event_desk_e2e.py tests/desk/test_event_desk_idle.py` exits 0 and `! uv run pytest tests/desk/test_event_desk_e2e.py -rs | grep -q SKIPPED` exits 0; the event desk wires bus, sources, runtime, gateway, router and promotion edges end to end on recorded data, exhausts a real LayeredBudget in e2e, and an idle desk is silent (RT-03)
  11. `uv run pytest -q tests/desk/test_restart_recovery.py tests/desk/test_restart_exit_deadlines.py` exits 0 and `! uv run pytest tests/desk/test_restart_recovery.py -rs | grep -q SKIPPED` exits 0; restart restores exit deadlines, probation, the desk-wide watch set and exit peaks from the ledger, tapes start empty and the strategies decide nothing until their windows refill (RT-04; tape restore is Phase 18, owner decision 2026-11-18)
  12. `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 6 && git diff --name-only v4-base -- contracts | grep -qx 'contracts/events/strategy_kill_set.schema.json' && git diff --name-only v4-base -- contracts | grep -qx 'contracts/events/strategy_kill_cleared.schema.json' && git diff --name-only v4-base -- contracts | grep -qx 'contracts/events/promotion_stage_set.schema.json' && git diff --name-only v4-base -- contracts | grep -qx 'contracts/changes/phase-17-strategy-kill-events.yaml' && git diff --name-only v4-base -- contracts | grep -qx 'contracts/changes/g7-tool-packs-required.yaml' && git diff --name-only v4-base -- contracts | grep -qx 'contracts/tool-packs/.gitkeep'` exits 0; `git diff --name-only v4-base -- contracts` lists exactly the three event schemas (strategy_kill_set, strategy_kill_cleared, promotion_stage_set), the two change documents under `contracts/changes/` (phase-17-strategy-kill-events.yaml, g7-tool-packs-required.yaml) and `contracts/tool-packs/.gitkeep`, and nothing else (owner amendments 2026-11-18; `v4-base` is the tag on the commit where draft PRs 16 to 20 are merged) (PRM-01)
  13. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700" && grep -qF "Phase 17: smoke-10m events.hash before: 1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700" CHANGELOG.md && grep -qF "Phase 17: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0, `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 17: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 17: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0; both pairs are recorded and equal, because this phase does not move either hash (D17-1 amendment: smoke-10m pin 1dffa78448f720b98a7fbb1c5f9a7c0e1959d7f24061c5e255ad56045ee18700 replaces the stale b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d literal; trading-smoke pin a4461e80f926e46f9d5b85b0305c41fb44c72b63a875369e2b825ea8b7cd9404 is read from the pin file) (PRC-03)
  14. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live stays refused (LIV-07)

**Checkpoint**: With every new behavior config-gated off the replay hashes are unchanged; with it on, slices, kills, staleness, entry checks, promotion and restart recovery work end to end under test, and a paper strategy can reach LIVE_ELIGIBLE on evidence. This is the first point where the whole paper desk runs end to end on recorded data.

**Deliverables**:

- [x] `risk/strategy_slice.py`, `risk/entry_checks.py`, `risk/feed_health.py`, `config/mint_lists.toml`, breaker extensions and the engine reason mapping on existing rows (RSK-01 to RSK-03, RSK-05, RSK-08)
- [x] `src/pumpgrok/promotion/`, `config/promotion_thresholds.toml`, the `upgrade/gate.py` paper parameter and the `promotion demote` verb (PRM-01 to PRM-06)
- [x] `events/event_desk.py` composition root, wake subscriptions and the entry-gate wiring in `supervisor/live_paper.py` (PRM-05, RT-03)
- [x] `supervisor/recovery.py` restart recovery wiring with crash tests; restores probation, the watch set, exit deadlines and exit peaks from the ledger, tapes start empty (RT-04, narrowed 2026-11-18)
- [x] `CHANGELOG.md` Phase 17 entry with both hash pairs (PRC-03)

**Plans**: 7 planned (17-01 to 17-07) in 6 waves. Plan ids: 17-01, 17-02, 17-03, 17-04, 17-05, 17-06, 17-07. Source of truth: the v4 plan index, which is not in this repository; the plan ids listed here are the list of record. The per-plan PLAN and SUMMARY files are written under `.planning/phases/17-*/` by the GSD workflow.

### Phase 18: Dormant live path, amendment-gated

**Goal**: The five hardcoded-unmet live gate rows become real checks, a segregated desk-signer process with single-send persistence, an instruction-level transaction allowlist, chain reconciliation and shadow mode exists, the desk holds no key and no signing symbol, exit sells are never blocked by entry-only gate rows, and the constitution amendment is applied by the owner in one human-approved pull request. Live stays refused: with the overlay disabled, no env flag and no record, `run --mode live` exits 3; arming remains a human-only runbook step.
**Depends on**: Phase 17 (17-02, 17-03, 17-04: feed health, promotion, composition root); Phases 11, 12 and 15; plan 13-03; plans 18-03 to 18-06, 18-08 and 18-09 are amendment_wait and merge only after the owner approves the exact text (OD-01) and plan 18-07 merges
**Requirements**: RSK-04 (live parts: the live failure producers and the live-path UNKNOWN halt, moved from Phase 17 by owner decision 2026-11-18), RSK-06, RSK-09, LIV-03, LIV-04, LIV-05, LIV-06, LIV-07, LIV-08, LIV-09, LIV-10, LIV-11, LIV-12, LIV-13, LIV-14, LIV-15, LIV-16, LIV-17, LIV-18, LIV-19, LIV-20, PRC-07
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/ledger/test_stop_state.py` exits 0; the no_active_stop reader folds halt, kill, breakers and strategy kills read-only and an unreadable ledger is unmet (LIV-05)
  3. `python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/v4-live-source.yaml` exits 0, `python3 scripts/generate-event-schemas.py --check` exits 0 and `uv run pytest -q tests/ledger/test_live_source.py tests/contracts/test_live_source_contract.py` exits 0; the additive live event source passes G-4 as a change document (LIV-14)
  4. `uv run pytest -q tests/ledger/test_event_source_literal_sites.py` exits 0; the nine literal sites of the event source are explicit, three widened and six pinned narrow by an AST test (LIV-20)
  5. `uv run pytest -q tests/live/test_gate_rows56.py tests/live/test_arm_record.py` exits 0; gate rows 5 and 6 are real settings, a notional cap above 1.0 SOL is a ConfigError at load, the arm record is bound to the configuration hash and expiry (LIV-03, LIV-04)
  6. `uv run pytest -q tests/live/test_arm_scope.py tests/live/test_arm_expiry_ceiling.py` exits 0; the arm record binds (strategy id, parameter-set hash) pairs, any hash change needs a new arm and expiry never exceeds the 168 hour ceiling (LIV-17)
  7. `uv run pytest -q tests/live/test_gate_exit_rows.py tests/live/test_exit_sells_autonomous_live.py` exits 0; exit sells pass with a halt set, a kill file present, a breaker open and an arm expired while entries are refused in the same states, and autonomous_live is minted for exit and flatten sells while a live position is open (RSK-09)
  8. `uv run pytest -q tests/live/test_registry.py tests/execution/test_build_adapter_registry.py` exits 0; the registry holds exactly `signer`, the gate reports row 8 only through it and `build_adapter` dispatches to the live factory only when the gate is open (LIV-06)
  9. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0, `uv run pytest -q tests/safety/test_live_refusal_lists_nine.py` exits 0 and `for f in src/pumpgrok/config/overlays/*.toml; do uv run python -c "import tomllib;d=tomllib.load(open('$f','rb'));assert d.get('live',{}).get('enabled') is False,'$f'" || exit 1; done` exits 0; with overlays disabled, no env flag and no record rows 1, 2 and 7 stay unmet and every overlay still ships live disabled (LIV-07)
  10. `cd services/desk-signer && uv run pytest -q` exits 0, `uv run pytest -q tests/safety/test_signer_isolation.py` exits 0, `uv run ruff check services` exits 0, `uv run mypy services/desk-signer/src` exits 0 and `make audit` exits 0; signer policy refusals hold when frames bypass the desk and the signer imports only its allowlisted desk modules (LIV-08)
  11. `cd services/desk-signer && uv run pytest -q tests/test_txpolicy_allowlist.py tests/test_blockhash_signer_owned.py tests/test_final_bytes_verify.py tests/test_alt_refused.py tests/test_token2022_wallet_ata.py tests/test_policy_order.py` exits 0; the instruction-level allowlist, signer-owned blockhash and final-bytes verification hold (LIV-18)
  12. `uv run pytest -q tests/live/test_single_send.py tests/core/test_signer_protocol.py` exits 0; the SIGNED row is fsynced before sendTransaction, maxRetries is 0 and UNKNOWN is never retried (LIV-09)
  13. `uv run pytest -q tests/live/test_reconcile.py tests/desk/test_live_wiring_dormant.py` exits 0; reconcile and restart recovery resolve non-terminal orders from chain with no timers in the desk (LIV-10)
  14. `uv run pytest -q tests/safety/test_no_signing_outside_live_stub.py tests/test_doctor_probes.py` exits 0 and `! grep -rnE '^(from|import) (solders|solana)|sendTransaction|Keypair' src/pumpgrok` exits 0; the desk holds no key or signer import and doctor flags the HMAC key in a desk environment (LIV-11)
  15. `uv run pytest -q tests/live/test_shadow.py` exits 0; shadow-live records zero place frames and the expected-versus-simulated gap (LIV-12)
  16. `uv run pytest -q tests/live/test_stage_mirror.py tests/live/test_tx_failed_onchain_latch.py` exits 0; stage, kill and halt rows are mirrored idempotently into the live ledger and a failed on-chain send latches a human-clear halt (LIV-19)
  17. `uv run pytest -q tests/safety tests/live/test_autonomous_live.py tests/safety/test_risk_choke_point.py tests/safety/test_signer_only_bypass.py` exits 0; guard tests are tightened and green, no order reaches the signer past a failed check, autonomous_live is minted only when armed, verified and the strategy is listed (LIV-13, LIV-15, RSK-06)
  18. `uv run pytest -q tests/safety/test_constitution_amendment_2026_10_28.py tests/safety/test_constitution_amendment.py tests/safety/test_amendment_copies_complete.py` exits 0 and `python3 scripts/generate-templates.py --check` exits 0; the amended text equals the owner-approved draft as corrected by the errata and every quoting copy is updated (LIV-16)
  19. `uv run pytest -q ci/tests/test_no_pr_waivers.py` exits 0 and `make check` exits 0; the amendment lands as one owner-applied pull request with exactly one step-scoped G-1 waiver pinned by test (PRC-07)
  20. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" && grep -qF "Phase 18: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md && grep -qF "Phase 18: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0, `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 18: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 18: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0; both pairs are recorded and equal, because this phase does not move either hash (PRC-03)

**Checkpoint**: A fresh checkout refuses live with exit 3, the amendment text on main equals the approved draft, the signer suite is green, and the runbooks list every human step; nothing is armed.

**Deliverables**:

- [ ] `ledger/stop_state.py`, `core/signer_protocol.py`, the additive live event source in `ledger/events.py`, `contracts/changes/v4-live-source.yaml` and regenerated `contracts/events/*.schema.json` (LIV-05, LIV-14, LIV-20)
- [ ] `execution/live/live_gate.py` (check_entry and check_exit), `arm.py`, `signer_client.py`, `registry.py`, `reconcile.py`, `shadow.py`, `mirror.py` and the `doctor.py` key check (LIV-03, LIV-04, LIV-06, LIV-10, LIV-12, LIV-15, LIV-17, LIV-19, RSK-09)
- [ ] `services/desk-signer/` with its own suite, lock, Dockerfile and compose service: IPC, nonce window, attestation over the socket, single send, reconcile, instruction-level policy (LIV-08, LIV-09, LIV-11, LIV-18)
- [ ] `execution/live_factory.py` and the `build_adapter` dispatch, tightened guard tests and rewritten registry tests (LIV-06, LIV-13)
- [ ] Constitution amendment applied by the owner in one pull request: every copy, the frozen oracle `tests/safety/amendment_2026_10_28_frozen.txt` and one step-scoped waiver (LIV-16, PRC-07)
- [ ] `docs/runbooks/go_live.md`, `signer.md`, `live_rollback.md` and the dormant live wiring in `supervisor/live_paper.py` (LIV-07, LIV-10)
- [ ] `CHANGELOG.md` Phase 18 entry with both hash pairs (PRC-03)

**Plans**: 11 planned (18-01 to 18-11) in 7 waves. Plan ids: 18-01, 18-02, 18-03, 18-04, 18-05, 18-06, 18-07, 18-08, 18-09, 18-10, 18-11. Human-gated: 18-07. Amendment-wait (merge only after the approved amendment lands): 18-03, 18-04, 18-05, 18-06, 18-08, 18-09. Source of truth: the v4 plan index, which is not in this repository; the plan ids listed here are the list of record. The per-plan PLAN and SUMMARY files are written under `.planning/phases/18-*/` by the GSD workflow.

### Phase 19: Observability, docs, hardening and milestone audit

**Goal**: Operators can see the event runtime, sources, Grok budget, strategy stages and kills, and signer attestation in doctor, health.json and metrics; alert rules name only real metrics; the docs, skills and runbooks describe v4 and every documented command runs; a nightly event-mode soak guards the idle-zero-Grok invariant; the amendment waiver is gone; and a milestone audit traces every requirement to evidence and records that live is still refused.
**Depends on**: Phases 17 and 18 (17-02, 17-03, 17-04, 18-02, 18-07, 18-10, 18-11); plans 11-03, 13-02, 14-04, 14-07 and 16-04 for CI, metrics and CLI lanes
**Requirements**: PRC-06, PRC-08, OBS-01, OBS-02, OBS-03, OBS-04, OBS-05, OBS-06, HOST-01, HOST-02, HOST-03, HOST-04, HOST-05, HOST-06, HOST-07, HOST-08, HOST-09, HOST-10, HOST-11, HOST-12, HOST-13, HOST-14, HOST-15, HOST-16
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0, `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0, `make cov` still meets its floor and `make test-all` exits 0 once (PRC-01)
  2. `uv run pytest -q tests/test_doctor_v4.py tests/test_doctor_probes.py tests/test_doctor_event_mode.py` exits 0; doctor reports bus, sources, Grok windows, strategy stages, kills and signer attestation read-only (OBS-01)
  3. `uv run pytest -q tests/supervisor/test_metrics.py tests/desk/test_health_event_sections.py tests/desk/test_metrics_strategy.py` exits 0 and `! uv run pytest tests/desk/test_health_event_sections.py -rs | grep -q SKIPPED` exits 0; health.json and the metric families carry event, strategy, promotion, performance and live sections (OBS-02)
  4. `uv run pytest -q tests/docs/test_alert_rules.py` exits 0; every alert expression names a metric that the registry exposes (OBS-03)
  5. `./scripts/verify_doc_commands.sh` exits 0, `./scripts/check.sh` exits 0, `uv run pytest -q tests/test_skill_manifests.py` exits 0 and `grep -qE 'event mode|wake_mode' README.md SETUP.md CLAUDE.md` exits 0; docs describe v4 and every command in them runs (OBS-04)
  6. `PUMPGROK_REQUIRE_SOAK=1 uv run pytest -q -m slow tests/soak/test_soak_event_mode.py` exits 0 once; the event-mode soak shows zero idle Grok calls and its golden hash (OBS-06)
  7. `! grep -nE 'pull_request\.number' .github/workflows/gates.yml` exits 0 and `uv run pytest -q ci/tests` exits 0; the amendment waiver is removed and the waiver set is empty again (PRC-08)
  8. `test -f .planning/milestones/v4-MILESTONE-AUDIT.md` exits 0 and `for r in $(grep -oE '^- \[.\] [A-Z]+-[0-9]+' .planning/REQUIREMENTS.md | grep -oE '[A-Z]+-[0-9]+'); do grep -q $r .planning/milestones/v4-MILESTONE-AUDIT.md || exit 1; done` exits 0; every requirement id appears in the audit with evidence (OBS-05)
  9. `for p in 11 12 13 14 15 16 17 18 19; do grep -qF "Phase $p: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md || exit 1; grep -qE "Phase $p: trading-smoke events.hash after: [0-9a-f]{64}" CHANGELOG.md || exit 1; done` exits 0; one journal CHANGELOG entry and one chief close record per phase (PRC-06)
  10. `uv run pytest -q tests/safety` exits 0 and `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live is still refused on the final tree (OBS-05)
  11. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" && grep -qF "Phase 19: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md && grep -qF "Phase 19: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0, `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 19: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 19: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0; both pairs are recorded and equal, because this phase does not move either hash (PRC-03)
  12. `uv run pytest -q tests/hosted ci/tests/test_compose_docker_secrets.py ci/tests/test_image_digest_pins.py` exits 0; HOST-01 to HOST-14 hold, and no hosted run starts, with or without the compose named volume (HOST-02), until HARD-07 passes (HOST-01 to HOST-14)
  13. HOST-15: a hosted replay run labels every health body and metric family as a replay demo until live-data paper lands.
  14. HOST-16: the compose desk service runs the live-data paper root and no longer the bundled fixture; gated on Phase 15 and on the OD-04 probe review.

**Checkpoint**: The audit file exists, every requirement is traced, `make check` is green, live is refused, and the human arm procedure is the only remaining step toward live.

**Deliverables**:

- [ ] Doctor v4 report in `src/pumpgrok/doctor.py` (OBS-01)
- [ ] `health.json` event and strategy sections and per-strategy P and live L metric families in `supervisor/health.py` and `supervisor/metrics_events.py` (OBS-02)
- [ ] `docs/observability/alerts.yaml` checked by `tests/docs/test_alert_rules.py` (OBS-03)
- [ ] `ARCHITECTURE.md`, `CLAUDE.md`, `AGENTS.md`, `README.md`, `SETUP.md`, the market-data, replay-and-backtest, doctor and monitoring skills and the datafeed, recorder and promotion runbooks (OBS-04)
- [ ] Nightly event-mode soak in `.github/workflows/ci.yml` and `tests/soak/test_soak_event_mode.py` (OBS-06)
- [ ] Waiver removal in `.github/workflows/gates.yml` (PRC-08)
- [ ] `.planning/milestones/v4-MILESTONE-AUDIT.md`, v4 archive and the final `CHANGELOG.md` closeout (OBS-05, PRC-06)
- [ ] Hosted runtime family (HOST-01 to HOST-16): `tests/hosted/` and `ci/tests/` checks for the state directory, health probes and routes, shutdown exit, ledger backup and restore, log level, gateway bind and tokens, health bind and read timeout, Docker secrets and digest pins, the replay-demo label (HOST-15), and the compose live-data root (HOST-16); no hosted run starts, with or without the named volume (HOST-02), until HARD-07 passes

**Plans**: 9 planned (19-01 to 19-09) in 5 waves. Plan ids: 19-01, 19-02, 19-03, 19-04, 19-05, 19-06, 19-07, 19-08, 19-09. Human-gated: 19-08. Source of truth: the v4 plan index, which is not in this repository; the plan ids listed here are the list of record. The per-plan PLAN and SUMMARY files are written under `.planning/phases/19-*/` by the GSD workflow. The plan decomposition for the new HOST requirements is produced by gsd-plan-phase when Phase 19 is planned.

## Progress

**Execution Order:**
Phases are numbered in dependency order and overlap in time; a plan starts when its dependencies merge (see `.planning/STATE.md`, Dependency levels and scheduling): 11 -> 12 -> 13 -> 14 -> 15 -> 16 -> 17 -> 18 -> 19

Ship checkpoints, where the owner approves receipts in batches as human:SomeRandmGuyy: after Phase 12, after Phase 14, after Phase 17 and after Phase 19. Run every hash command in a fresh git worktree (no `var/ledger.sqlite`), because `verify` reads the active-set record from the working-directory ledger.

## Phases

- [x] **Phase 6: Integrity closure** - Audited invariant violations closed or proven present, feature-lineage fixes re-applied, replay hash before and after recorded (12 requirements)
- [x] **Phase 7: Documentation upgrade** - CLAUDE.md codebase map, trimmed AGENTS.md, contradictions corrected, historical design banners (4 requirements)
- [x] **Phase 8: Backtest and paper evaluation** - Run manifests, holdout and trial accounting, `pumpgrok backtest` verb, shared result schema and divergence check (10 requirements)
- [x] **Phase 9: Bounded paper self-upgrade** - Content-hashed bounded parameter promotion with exact rollback, BLIND advisory rule and the approved constitution amendment (6 requirements)
- [x] **Phase 10: Live readiness, kept disabled** - Live refused with exit 3, no live adapter, import-graph proof and a deferred live-readiness record (2 requirements)
- Archived, left unfinished (q1 default): v2 phase 3 (v2-3) is BLOCKED on a human-supplied account; it stays archived with this note and is not reopened.

## Phase Details

### Phase 6: Integrity closure

**Goal**: Every audited invariant violation on main is closed or proven present, the two feature-lineage fixes are applied with regression tests, and replay output is unchanged or its change is recorded in CHANGELOG.md by before and after hash.
**Depends on**: Nothing (first v3 phase; branch `bot-00-chief/phase-6-integrity` from origin/main f3887bb)
**Requirements**: INT-01, INT-02, INT-03, INT-04, INT-05, INT-06, INT-07, INT-08, INT-09, INT-10, PRC-01, PRC-02
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test` and `./scripts/check.sh` each exit 0 (PRC-01)
  2. `uv run pytest -q tests/integrity/test_money_types.py` exits 0 and `! grep -rnE "\b[a-z_]*(lamport|equity|fee|pnl|cost|price|size|balance)[a-z_]*\s*:\s*float\b" src/pumpgrok --include=*.py` exits 0 (INT-01)
  3. `uv run pytest -q tests/integrity/test_fail_closed_state.py` exits 0; the test corrupts the ledger peak state, the seat initial equity and the genesis equity, and expects a typed error from each (INT-02)
  4. `uv run pytest -q tests/integrity/test_daily_loss_integer.py` exits 0; a non-positive day-start equity fails the check and is never treated as zero loss (INT-03)
  5. `uv run pytest -q tests/integrity/test_single_sol_conversion.py` exits 0 and `! grep -rn "1_000_000_000" src/pumpgrok --include=*.py | grep -v "src/pumpgrok/core/"` exits 0 (INT-04)
  6. `uv run pytest -q tests/integrity/test_rng_roots.py` exits 0, `! grep -rn "os.urandom" src/pumpgrok --include=*.py | grep -v -E "src/pumpgrok/core/(ids|binding_key)\.py"` exits 0, and `! grep -rn "DEFAULT_SEED" src/pumpgrok --include=*.py | grep -v "src/pumpgrok/replay/"` exits 0 (INT-05)
  7. `uv run pytest -q tests/integrity/test_live_gate_clock.py` exits 0 (gate output byte-identical under a fixture clock) and `! grep -nE "time\.time|datetime\.(now|utcnow)" src/pumpgrok/execution/live/live_gate.py` exits 0 (INT-06)
  8. `uv run pytest -q tests/integrity/test_wr07_replay_ledger_removed.py tests/integrity/test_ledger_mark_fee_partial_sell.py` exits 0, and each of the two tests fails on its pre-fix parent: `git worktree add --detach /tmp/int07-pre 4c19fd9^ && cp -r tests/integrity /tmp/int07-pre/tests/ && (cd /tmp/int07-pre && uv run pytest -q tests/integrity/test_wr07_replay_ledger_removed.py)` exits 1, then the same with `76975bb^` and `test_ledger_mark_fee_partial_sell.py` exits 1, then `git worktree remove --force /tmp/int07-pre` exits 0 (INT-07)
  9. `uv run pytest -q tests/integrity/test_function_length.py` exits 0; it asserts that `_place_buy`, `_place_order` and `_replay_cycles` are each at most 60 lines after the stage split (INT-08)
  10. `uv run pytest -q tests/integrity/test_peaks_survive_restart.py` exits 0; trailing-stop peaks are restored from the ledger after a simulated serve restart (INT-09)
  11. `uv run python scripts/probe_curve_layout.py` exits 0 and writes `docs/CURVE_LAYOUT_PROBE.md` with one line `Status: VERIFIED` or `Status: ASSUMED`; when it reads ASSUMED, `grep -E "^Error: .+" docs/CURVE_LAYOUT_PROBE.md` exits 0 and carries the exact probe error, which satisfies INT-10 and is not a blocker; `! grep -nE "sendTransaction|send_transaction|requestAirdrop|signTransaction" scripts/probe_curve_layout.py` exits 0; `grep -rqE 'LAYOUT_STATUS[^=]*=\s*"ASSUMED"' src/pumpgrok` exits 0 or `grep -rqE 'LAYOUT_STATUS[^=]*=\s*"VERIFIED"' src/pumpgrok` exits 0 to match the recorded status (INT-10). The pattern allows the annotated assignment `LAYOUT_STATUS: Final[str] = "ASSUMED"`; the unannotated `\s*=\s*` form cannot match it (corrected 2026-10-25).
  12. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0 (live stays refused)
  13. `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0
  14. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b"` exits 0, and `grep -qE "Phase 6: smoke-10m events.hash before: [0-9a-f]{64}" CHANGELOG.md && grep -qF "Phase 6: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0; the before value is the events.hash printed on the phase branch before its first edit, and the after value is the hash this phase produces (INT-08 and the replay rule)
  15. `grep -qE "5b5d6a1" CHANGELOG.md && grep -qE "9772655" CHANGELOG.md` exits 0 (review of the Omega CI runner migration recorded, the v2 deferred item)
  16. `test "$(git branch --show-current | grep -cE '^bot-0[0-9]-[a-z-]+/phase-6-[a-z-]+$')" -eq 1` exits 0 and `gh pr list --head "$(git branch --show-current)" --json isDraft,mergedAt --jq 'all(.isDraft and .mergedAt == null)'` prints `true` (PRC-02)
  17. `python3 ci/gates/run_all.py --bot bot-00-chief --receipt .receipts/bot-00-chief/phase-6.json` exits 0 for each completion claim in this phase (PRC-01)

**Checkpoint**: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` completes one cycle, `uv run pumpgrok verify --fixture smoke-10m` prints the same events.hash on two runs, live stays refused with exit 3, and the canonical gate set is green.

**Deliverables**:

- [x] `src/pumpgrok/ledger/export.py`, `src/pumpgrok/engine/models.py`, `src/pumpgrok/engine/analyzer.py`, `src/pumpgrok/engine/exits.py`, `src/pumpgrok/engine/reputation.py`, `src/pumpgrok/engine/tune.py`: integer money, Decimal for ratios only, and the static guard `tests/integrity/test_money_types.py` (INT-01)
- [x] `src/pumpgrok/ledger/reducer.py`, `src/pumpgrok/supervisor/seat_task.py`, `src/pumpgrok/supervisor/lifecycle.py`: typed fail-closed errors in place of silent defaults, with regression tests (INT-02)
- [x] Daily-loss halt in `src/pumpgrok/risk/`: integer arithmetic and a failed check for non-positive day-start equity (INT-03)
- [x] One SOL-to-lamports conversion in `src/pumpgrok/core/`, used by `src/pumpgrok/core/risk_budget.py`, the CLI and `src/pumpgrok/core/approvals.py`; the copy in `src/pumpgrok/reporting/render.py` removed (INT-04)
- [x] `src/pumpgrok/core/ids.py` and `src/pumpgrok/core/binding_key.py` as the only `os.urandom` roots; `DEFAULT_SEED` in `src/pumpgrok/replay/rng.py` confined to replay; guard in `tests/integrity/test_rng_roots.py` (INT-05)
- [x] `src/pumpgrok/execution/live/live_gate.py` reads time only through the injected clock (INT-06)
- [x] WR-07 (commit 4c19fd9, replay ledger removed on failed append or verify) and the ledger-mark venue-fee fix (commit 76975bb) re-applied on the phase branch. Neither is an ancestor of origin/main (checked 2026-10-25; both sit on `feat/grokbot-desk-merge`, which stays untouched per V3-3). Regression tests in `tests/integrity/` (INT-07)
- [x] `src/pumpgrok/execution/paper_adapter.py` (`_place_buy`, `_place_order`) and `src/pumpgrok/supervisor/scheduler.py` (`_replay_cycles`) split into stage functions with unchanged behaviour (INT-08)
- [x] Trailing-stop peak persistence and restore in `src/pumpgrok/engine/exits.py` and `src/pumpgrok/risk/engine.py` (INT-09)
- [x] `scripts/probe_curve_layout.py` (read-only) and `docs/CURVE_LAYOUT_PROBE.md`; `LAYOUT_STATUS` in `src/pumpgrok` set to match the probe result; entries fail closed while ASSUMED (INT-10)
- [x] `CHANGELOG.md` entries: the Phase 6 before and after replay hash lines, and the review of Omega CI runner migration commits 5b5d6a1 and 9772655 (PRC-01)
- [x] Phase branch and draft PR per AGENTS.md; no merge to main (PRC-02)

**Plans**: 9 planned (06-01 to 06-09) plus fix-up 06-01b; all have SUMMARY files. Phase closed 2026-10-26 with owner-approved deviations (see .planning/phases/06-integrity-closure/06-VERIFICATION.md, Owner closure).

### Phase 7: Documentation upgrade

**Goal**: CLAUDE.md, AGENTS.md, README, ARCHITECTURE, SETUP, the replay skill, the plugin version statements and the vendor pin describe the code as fixed by Phase 6, and historical design records say so in a banner.
**Depends on**: Phase 6
**Requirements**: DOC-01, DOC-02, DOC-03, DOC-04
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `test "$(grep -cE '^## (Purpose|Stack|Layout|Commands|Architecture|Conventions|GSD artifact|Safety|Known gaps)' CLAUDE.md)" -ge 9` exits 0 (DOC-01)
  3. `! grep -nE '^\s*[-*] ' CLAUDE.md | grep -v '`'` exits 0; every bullet in CLAUDE.md cites a backticked repository path (a grep proxy for "every statement cites a file"; the phase review checks prose statements) (DOC-01)
  4. `test "$(wc -l < AGENTS.md)" -lt "$(git show origin/main:AGENTS.md | wc -l)"` exits 0, `grep -q "CLAUDE.md" AGENTS.md` exits 0, and `! grep -niE "placeholder" AGENTS.md` exits 0 (DOC-02)
  5. `./scripts/verify_doc_commands.sh` exits 0; it runs each command in the Commands sections of AGENTS.md and CLAUDE.md and checks its documented exit code (DOC-02)
  6. `uv run pytest -q tests/docs/` exits 0; it asserts that plugin version statements match `pyproject.toml`, that `docs/VENDOR_PIN.md` matches the vendored snapshot, that every command named in README, ARCHITECTURE, SETUP and `skills/replay-and-backtest/SKILL.md` exists in the CLI help, and that no contradiction from the 2026-10-25 docs audit remains (DOC-03)
  7. `uv run pytest -q tests/docs/test_historical_banners.py` exits 0; every historical design record it lists begins with the banner "Historical design record" (DOC-04)
  8. `test "$(grep -cE 'DOC-0[1-4]' CHANGELOG.md)" -ge 4` exits 0 (DOC-03)
  9. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && grep -qF "Phase 6: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0; the replay output is unchanged by this phase, and CHANGELOG.md records `Phase 7: smoke-10m events.hash after: $a` with the same value

**Checkpoint**: every command, version and path in the docs resolves against the code, `./scripts/verify_doc_commands.sh` is green, and the replay hash is unchanged from Phase 6.

**Deliverables**:

- [x] `CLAUDE.md` at the repository root: purpose, stack, layout, commands, architecture and data flow, conventions, GSD artifact locations, safety rules and known gaps, each bullet citing a file (DOC-01)
- [x] `AGENTS.md` trimmed: stale GSD research dump and placeholder blocks removed, rules index kept, commands verified, links `CLAUDE.md` instead of duplicating it (DOC-02)
- [x] `scripts/verify_doc_commands.sh`: runs the documented commands with their expected exit codes (DOC-02)
- [x] `README.md`, `ARCHITECTURE.md`, `SETUP.md`, `skills/replay-and-backtest/SKILL.md`, plugin version statements and `docs/VENDOR_PIN.md` corrected for every contradiction in the 2026-10-25 docs audit (DOC-03)
- [x] `tests/docs/` consistency tests and `tests/docs/test_historical_banners.py` (DOC-03, DOC-04)
- [x] Banner "Historical design record" on the design records under `docs/` (`docs/design/`, `docs/DISCOVERY.md`, `docs/MIGRATION_MAP.md`, `docs/upgrade-plan-desk-v2.md`); the set is fixed in `tests/docs/test_historical_banners.py` (DOC-04)
- [x] `CHANGELOG.md` entry for each documentation change, tagged with its DOC id, and the Phase 7 replay hash line (DOC-03)

**Plans**: 6 complete (07-01 to 07-06). Verification: `.planning/phases/07-documentation-upgrade/07-VERIFICATION.md` (passed, 9 of 9 criteria). Criterion 6 checks the vendor pin and a retirement statement, not a snapshot (OVERRIDE-D; the snapshot was deleted in Phase 4). Criterion 5 runs the offline subset; make targets, `run --serve` and `check.sh` are name-checked, not executed. Overrides A to D are recorded in the plan SUMMARY files.

### Phase 8: Backtest and paper evaluation

**Goal**: A `pumpgrok backtest` verb runs a parameter set over a recorded dataset with a holdout and trial accounting and writes byte-identical reports; the holdout-aware harness replaces the in-sample grid search; backtest results and paper ledger trades share one schema and a divergence check on the D7 defaults blocks promotion on breach.
**Depends on**: Phase 6 (integer money and the new result schema)
**Requirements**: BT-01, BT-02, BT-03, BT-04, BT-05, BT-06, BT-07, PAP-01, PAP-02, PAP-03
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/backtest/test_run_manifest.py` exits 0; the manifest holds the whole-dataset digest over every file in the dataset directory, the seed, the FilterSettings hash, the parameter-set hash and the code version, and changing one byte of a dataset file changes the run id (BT-01)
  3. `uv run pytest -q tests/backtest/test_replay_result_fields.py` exits 0; each fill carries price, venue fee, network cost, latency, filled fraction and outcome (BT-02)
  4. `uv run pytest -q tests/backtest/test_holdout_split.py` exits 0; the holdout is the final 20 percent of the time window, no tuning step reads it, and the report names the split identifiers (BT-03)
  5. `uv run pytest -q tests/backtest/test_trial_limits.py` exits 0; a search above 20 trials is flagged ineligible for promotion, and a search above 50 trials is rejected with a typed error (BT-04)
  6. `uv run pytest -q tests/backtest/test_metrics.py` exits 0; `grep -rnE "annualiz" src/pumpgrok/backtest --include=*.py` exits 0 with the annualization stated in code; `! grep -rniE "expected (return|profit|pnl)|will earn" src/pumpgrok/backtest src/pumpgrok/reporting --include=*.py` exits 0 (BT-05)
  7. `uv run pumpgrok backtest --fixture smoke-10m > /tmp/bt-a.md && uv run pumpgrok backtest --fixture smoke-10m > /tmp/bt-b.md && cmp /tmp/bt-a.md /tmp/bt-b.md` exits 0, and `grep -qi "holdout" /tmp/bt-a.md && grep -qi "trial" /tmp/bt-a.md && grep -qi "slippage" /tmp/bt-a.md && grep -qi "fees" /tmp/bt-a.md` exits 0 (BT-06)
  8. `! grep -rnE "grid|itertools\.product" src/pumpgrok/engine src/pumpgrok/backtest --include=*.py` exits 0 and `uv run pytest -q tests/backtest/test_single_search_engine.py` exits 0; the harness is the only search entry point (BT-07)
  9. `uv run pytest -q tests/backtest/test_shared_result_schema.py` exits 0; backtest results and paper ledger trades are built from one result model and compare over the same window (PAP-01)
  10. `uv run pytest -q tests/backtest/test_divergence.py` exits 0; a 2 percentage point absolute return gap and a 0.5 Sharpe gap each raise an alert and block promotion, using the D7 defaults as the configured values (PAP-02)
  11. `uv run pytest -q tests/e2e/test_autonomous_paper_recorded.py tests/safety/test_manual_ticket_no_upgrade.py` exits 0; autonomous paper runs end to end on the recorded `smoke` and `smoke-10m` datasets at the human-set autonomous-paper level, and manual-ticket never runs an upgrade (PAP-03)
  12. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && grep -qE "Phase 8: smoke-10m events.hash before: [0-9a-f]{64}" CHANGELOG.md && grep -qF "Phase 8: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0; the result schema changes replay output, so the before and after hash are both recorded
  13. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0

**Checkpoint**: `pumpgrok backtest` writes byte-identical reports for identical inputs, the divergence check blocks promotion on breach, and the replay smoke command completes one cycle.

**Deliverables**:

- [x] `src/pumpgrok/backtest/` new package: run manifest, holdout and walk-forward split, bounded metrics, and the holdout-aware harness that replaces the grid search (BT-01, BT-03, BT-05, BT-07)
- [x] Trial ledger with the 20-trial flag and 50-trial rejection in `src/pumpgrok/backtest/` (BT-04)
- [x] Per-fill result fields in `src/pumpgrok/replay/` (BT-02)
- [x] `backtest` verb in `src/pumpgrok/cli.py` with deterministic report output (BT-06)
- [x] `src/pumpgrok/engine/tune.py`: in-sample grid search removed; no second search engine remains (BT-07)
- [x] One shared result model for backtest and paper ledger trades (PAP-01)
- [x] Divergence check on the D7 defaults in `src/pumpgrok/backtest/` (PAP-02)
- [x] `tests/backtest/`, `tests/e2e/test_autonomous_paper_recorded.py` and the autonomous-paper verification on recorded datasets (PAP-03)
- [x] `CHANGELOG.md` before and after replay hash lines for Phase 8

**Plans**: 10 complete. 08-01 to 08-07 delivered the phase; 08-08 to 08-10 are a correction set that replaced the digest-scored evaluator (see 08-CORRECTION.md). Verification: `.planning/phases/08-backtest-and-paper-evaluation/08-VERIFICATION.md` (passed, 13 of 13 criteria).

### Phase 9: Bounded paper self-upgrade

**Goal**: Paper parameter sets are content-hashed and held within version-controlled bounds; a candidate is promoted only through the gate; every promotion records its evidence and one operation rolls back to the exact prior version; SAFE-4 and SAFE-8 BLIND results are advisory while no paid RPC provider is recorded; the approved constitution amendment lands with the code it describes.
**Depends on**: Phase 8
**Requirements**: UPG-01, UPG-02, UPG-03, UPG-04, UPG-05, UPG-06
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/upgrade/test_param_set_hash.py tests/upgrade/test_active_set_ledger.py` exits 0 (parameter sets are content-hashed; the active set is written to the ledger) and `uv run python -c "import tomllib; tomllib.load(open('src/pumpgrok/config/upgrade_bounds.toml','rb'))"` exits 0 (UPG-01)
  3. `uv run pytest -q tests/upgrade/test_promotion_gate.py` exits 0; an out-of-bounds candidate, a failed holdout, a divergence breach, a search above 20 trials, and a run below the autonomous-paper level each block promotion (UPG-02)
  4. `uv run pytest -q tests/upgrade/test_promotion_evidence.py` exits 0; each promotion records the candidate hash, backtest run id, holdout id, divergence result, trial count and bounds (UPG-03)
  5. `uv run pytest -q tests/upgrade/test_rollback_exact.py` exits 0; promote then roll back restores the exact prior version, verified by content hash and by the active-set ledger record (UPG-03)
  6. `uv run pytest -q tests/upgrade/test_escalation.py` exits 0; an out-of-bounds or ineligible candidate is not promoted and produces a decision request and a journal note (UPG-04)
  7. `uv run pytest -q tests/safety/test_blind_advisory.py` exits 0; SAFE-4 and SAFE-8 report BLIND as advisory with the blind reason written into the verdict while no paid RPC provider is recorded, every other BLIND result stays KILL, and the rule reverts to required when a provider is recorded (UPG-05)
  8. `python3 scripts/generate-templates.py --check` exits 0 and `uv run pytest -q tests/safety/test_constitution_amendment.py` exits 0; the test compares the amended text of `rules/pumpgrok-team.mdc` (clauses 2 and 8, ten-role correction), `agents/risk.md` clause 10, `docs/RISK_POLICY.md` (row 8 and section 2.4) and `.planning/PROJECT.md` (BLIND constraint) with the frozen approved text (UPG-06)
  9. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && grep -qE "Phase 9: smoke-10m events.hash before: [0-9a-f]{64}" CHANGELOG.md && grep -qF "Phase 9: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0; the active-set record may change replay output, so both values are recorded (equal if unchanged)
  10. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0 with the upgrade modules present

**Checkpoint**: a candidate is promoted and rolled back exactly under test, ineligible candidates escalate, the amendment text passes `generate-templates --check`, and live stays refused.

**Deliverables**:

- [x] `src/pumpgrok/config/upgrade_bounds.toml`: declared bounds in version-controlled config (UPG-01)
- [x] `src/pumpgrok/upgrade/` new package: content-hashed parameter sets, the promotion gate, the evidence record, exact rollback and escalation (UPG-01 to UPG-04)
- [x] Ledger event for the active parameter set in `src/pumpgrok/ledger/` (UPG-01, UPG-03)
- [x] SAFE-4 and SAFE-8 advisory BLIND handling with the blind reason in the verdict, in `src/pumpgrok/tools/safety/` (UPG-05)
- [x] Constitution amendment applied exactly as approved on 2026-10-25: `rules/pumpgrok-team.mdc`, `agents/risk.md`, regenerated prompts and agent files via `scripts/generate-templates.py`, `docs/RISK_POLICY.md`, `.planning/PROJECT.md` (UPG-06)
- [x] Frozen copy of the approved amendment text, used as the test oracle in `tests/safety/test_constitution_amendment.py` (UPG-06)
- [x] `tests/upgrade/` and `tests/safety/test_blind_advisory.py`
- [x] `CHANGELOG.md` before and after replay hash lines for Phase 9

**Plans**: 7 complete (09-01 to 09-07; 09-06 carries the risk-only clause 3 override and the content-based locators). Verification: `.planning/phases/09-bounded-paper-self-upgrade/09-VERIFICATION.md` (passed, 10 of 10 criteria).

### Phase 10: Live readiness, kept disabled

**Goal**: Live stays refused end to end: `run --mode live` exits 3 and lists the nine preconditions, no live adapter is registered, the import graph has no path from backtest, paper or upgrade modules to a live adapter, and a deferred live-readiness record states what a future decision requires.
**Depends on**: Phase 9
**Requirements**: LIV-01, LIV-02
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0 and `uv run pytest -q tests/execution/test_live_gate_fails_fast.py tests/safety/test_live_refusal_lists_nine.py` exits 0; stderr names all nine preconditions (LIV-01)
  3. `uv run pytest -q tests/safety/test_no_live_adapter_registered.py` exits 0 (LIV-01)
  4. `uv run pytest -q tests/safety/test_import_graph_no_live.py` exits 0; no import path exists from the backtest, paper or upgrade modules to a live adapter (LIV-01)
  5. `for f in src/pumpgrok/config/overlays/*.toml; do uv run python -c "import tomllib,sys; d=tomllib.load(open('$f','rb')); assert d.get('live',{}).get('enabled') is False, '$f'" || exit 1; done` exits 0 (live disabled in every overlay)
  6. `uv run pytest -q tests/safety` exits 0; the signing and custody AST guard passes and no signing or custody code was added (LIV-02)
  7. `test -f docs/LIVE_READINESS.md && grep -qi "status: deferred" docs/LIVE_READINESS.md && grep -qi "custody" docs/LIVE_READINESS.md && grep -qi "venue" docs/LIVE_READINESS.md && grep -qi "legal" docs/LIVE_READINESS.md && grep -qi "nine" docs/LIVE_READINESS.md` exits 0; the record lists the custody model, venue, legal review and nine-precondition evidence as requirements of a future decision (LIV-02)
  8. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && grep -qF "Phase 10: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0; the replay output is unchanged from Phase 9

**Checkpoint**: on a fresh checkout, `run --mode live` exits 3, the live-readiness record is present and deferred, and the canonical gate set is green.

**Deliverables**:

- [x] `src/pumpgrok/execution/live/live_gate.py`: refusal output lists the nine preconditions (LIV-01)
- [x] `tests/safety/test_no_live_adapter_registered.py`, `tests/safety/test_import_graph_no_live.py`, `tests/safety/test_live_refusal_lists_nine.py` (LIV-01)
- [x] `docs/LIVE_READINESS.md`: deferred record of custody model, venue, legal review and nine-precondition evidence (LIV-02)
- [x] `CHANGELOG.md` v3 closeout entry and the Phase 10 replay hash line

**Plans**: 3 complete (10-01 to 10-03). Verification: `.planning/phases/10-live-readiness-kept-disabled/10-VERIFICATION.md` (passed, 8 of 8 criteria). Live stays refused: exit 3, no live adapter registered, no live import reachable from the guarded roots.

## Progress

**Execution Order:**
Phases execute in numeric order: 6 -> 7 -> 8 -> 9 -> 10

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 6. Integrity closure | 9/9 (+ fix-up 06-01b) | Complete | 2026-10-26 |
| 7. Documentation upgrade | 6/6 | Complete | 2026-10-25 |
| 8. Backtest and paper evaluation | 10/10 | Complete | 2026-10-25 |
| 9. Bounded paper self-upgrade | 7/7 | Complete | 2026-10-25 |
| 10. Live readiness, kept disabled | 3/3 | Complete | 2026-10-25 |
| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 11. Engineering foundation and quality | 11/11 | Complete (PR #55 merged 2026-11-03) | 2026-11-03 |
| 12. Event runtime core | 5/5 | Complete: PRs #61, #62 and #63 merged to main 2026-11-10 | 2026-11-10 |
| 13. Curve truth, live market data and recorder | 11/11 | Complete (merged to local main 8354ee6 2026-11-26 via PRs #64-#70, #73; VERIFIED flip human:Ove per 13-VERIFICATION; local-only, not pushed to origin) | 2026-11-26 |
| 14. Event-driven desk and Grok gateway | 9/9 | Closed merged to local main 8354ee6 2026-11-26 via integration PR #75 (branch v4-phase-14, 14-09-INTEGRATION-RECEIPT); criterion 1e OPEN (seat tool authorization, human step); local-only, not pushed to origin | 2026-11-26 |
| 15. Strategy framework and multi-strategy paper | 8/8 | Closed merged to local main 8354ee6 2026-11-26 via integration PR #75 (15-08-SUMMARY); criterion 1 deferred to deployment; local-only, not pushed to origin | 2026-11-26 |
| 16. Backtest v2 and autonomous evaluation | 8/8 | Implemented and merged to local main 8354ee6 2026-11-26 via integration PR #75; 16-SUMMARY.md and 16-VERIFICATION.md added; criterion 1 deferred to deployment | 2026-11-26 |
| 17. Risk hardening and promotion lifecycle | 7/7 | Partial: core code on origin/main and local main via 2026-11-22 integration commits c96e993 (17-05 event desk root) and cb91cf6 (17-06 restart recovery). PRs #98-#100 still OPEN on GitHub; their stale tip commits (d44cf93, cd68a68, 71ac14d) not merged. Absent on main: tests/desk/test_event_desk_holder_flag.py, tests/desk/test_exit_sell_guard.py, tests/desk/test_promotion_cursor_restart.py, Phase 17 CHANGELOG narrative (only hash pairs on main). Criterion 1 deferred (D17-2). Close when absent files land and gates pass; local-only merges unpushed. | - |
| 18. Dormant live path, amendment-gated | 0/11 | Not started | - |
| 19. Observability, docs, hardening and milestone audit | 0/9 | Not started | - |

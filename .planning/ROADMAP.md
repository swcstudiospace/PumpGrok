# Roadmap: PumpGrok Desk v4

## Overview

PumpGrok Desk v4 makes the paper desk event-driven and multi-strategy, and builds a fully tested but DORMANT live path that only a human can arm. Live trading stays disabled throughout: `run --mode live` exits 3 on every default start, no key or signing code enters the desk package, and the constitution amendment is drafted for the owner and applied only by a human-approved pull request. Nine phases continue the v3 numbering. Phase 11 lays the quality foundation first (pinned replay hashes, no PR-number waivers, a fast test path, coverage and complexity ratchets, the six hotspots split behind characterization tests), so every later phase edits small, pinned code. Phase 12 adds the typed event runtime as a library. Phase 13 corrects the curve layout and adds the read-only live feed and recorder. Phase 14 wakes seats on events and puts every Grok call behind one gateway. Phase 15 adds the strategy framework and four baseline strategies in paper. Phase 16 adds Metrics v2 and autonomous strategy backtests. Phase 17 adds per-strategy risk, the promotion lifecycle and the event desk composition root. Phase 18 builds the dormant live path and the segregated signer. Phase 19 adds observability, documentation, a nightly soak and the milestone audit. Every phase closes with the replay hash pairs recorded in CHANGELOG.md; the smoke-10m hash never moves, and the trading-smoke hash moves exactly once, in Phase 15.

Coverage: all 111 v4 requirements map to exactly one phase (see Traceability in `.planning/REQUIREMENTS.md`).

## Shipped

- [x] **v2: PumpGrok Desk v2** - shipped 2026-10-23, 5 phases, 44 plans. Archived: [roadmap](milestones/v2-ROADMAP.md), [requirements](milestones/v2-REQUIREMENTS.md), [audit](milestones/v2-MILESTONE-AUDIT.md).
- [x] **v3: PumpGrok Desk v3** - closed 2026-10-26, 5 phases, 35 plans, 34 requirements. Archived: [roadmap](milestones/v3-ROADMAP.md), [requirements](milestones/v3-REQUIREMENTS.md).

## Phases

- [ ] **Phase 11: Engineering foundation and quality** - Pinned replay hashes, waivers removed, soak split, coverage and complexity ratchet, six hotspots split behind characterization tests, v4 planning adopted (15 requirements)
- [ ] **Phase 12: Event runtime core** - Settings skeleton, single event catalog, EventBus with P0 lane, DLQ, deterministic drain and SourceSupervisor (10 requirements)
- [ ] **Phase 13: Curve truth, live market data and recorder** - Token-first curve layout, read-only live feed, fail-closed LivePriceSource, marks, recorder, fee model v2 selectable, human-reviewed status flips (11 requirements)
- [ ] **Phase 14: Event-driven desk and Grok gateway** - Event-mode supervisor wake, one Grok gateway, ten seat cycles, Hermes cutover, idle-zero-Grok gate and measurement (16 requirements)
- [ ] **Phase 15: Strategy framework and multi-strategy paper** - Strategy protocol and runtime, four baseline strategies, parameter identity, fee model v2 default, live-data paper root and Intent router (8 requirements)
- [ ] **Phase 16: Backtest v2 and autonomous evaluation** - Metrics v2, round trips, strategy-aware replay, gap segmentation, evidence grading, autonomous backtest scheduler, record and import verbs (8 requirements)
- [ ] **Phase 17: Risk hardening and promotion lifecycle** - Strategy slices and kills, entry checks, feed health, promotion lifecycle, event desk composition root and restart recovery (14 requirements)
- [ ] **Phase 18: Dormant live path, amendment-gated** - Dormant live path: real gate rows, arm scope, desk-signer service, instruction allowlist, shadow mode, amendment applied by a human-approved PR (21 requirements)
- [ ] **Phase 19: Observability, docs, hardening and milestone audit** - Doctor v4, health and metrics sections, alert rules, v4 docs, nightly event soak, waiver removal and the milestone audit (8 requirements)

## Phase Details

### Phase 11: Engineering foundation and quality

**Goal**: The test and quality scaffolding every later phase leans on exists before any feature lands: the trading `smoke` and smoke-10m hashes are pinned, every PR-number waiver is gone, every seat can track its receipt without touching a foreign path, the soak test is out of the default path, coverage and a complexity ratchet are measured, the six hotspots (paper_adapter sell, batch and confirm, RiskEngine._evaluate, cli/backtest, config/settings.py, supervisor/seat_task.py) are split behind characterization tests with the replay hashes unchanged, property tests, a mutation smoke target, an SBOM step, compose hardening and CI coverage of services/ are in place, and the v4 roadmap and requirements are adopted.
**Depends on**: Nothing in v4. The branches start from main after the owner-approved merge of draft PRs 16 to 20 (order 18, 19, 20, 17 for 17 to 20; tag `v4-base`); plans 11-01, 11-03 and 11-09 carry the external prerequisite EXT:PRS-16-20-MERGED
**Requirements**: QLT-01, QLT-02, QLT-03, QLT-04, QLT-05, QLT-06, QLT-07, QLT-08, QLT-09, QLT-10, PRC-03, PRC-04, PRC-05, PRC-09, PRC-10
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

**Checkpoint**: `make test` is fast, coverage and complexity are measured, both replay hashes are pinned, the hotspots are small and characterized, no PR-number waiver remains, and a non-risk seat can open a clean PR.

**Deliverables**:

- [ ] Receipt allowlist glob `!.receipts/bot-0*/v4-p*.json`, waiver removal and the two hash pins (`tests/replay/test_replay_hash_pin.py`, `tests/replay/test_trading_smoke_pin.py`, `tests/fixtures/replay/pins/trading_smoke*.json`) (PRC-03, PRC-04, PRC-05, PRC-09)
- [ ] `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `security-pr.yml` and `docker-compose.yml`: fast and soak split, coverage floor, complexity ratchet, hypothesis, mutmut, SBOM, compose hardening, services in lint, typecheck and audit (QLT-01 to QLT-03, QLT-07 to QLT-10, PRC-10)
- [ ] Characterization tests and the six hotspot splits in `src/pumpgrok/execution/paper_adapter/`, `risk/engine/`, `cli/backtest*.py`, `config/sections/` and `supervisor/seat_*.py` (QLT-04, QLT-05)
- [ ] Narrowed excepts in `tools/onchain/`, `tools/market/jupiter.py`, `doctor.py` and `core/manifests.py` with `tests/quality/test_no_plain_swallow.py` (QLT-06)
- [ ] `tools/onchain/pump_events.py` decoder and `scripts/probe_pump_accounts.py` read-only probe, pulled forward from the live-data phase (MKT-02, MKT-03)
- [ ] v4 `.planning/` adoption: archived v3 roadmap and requirements, installed v4 ROADMAP, REQUIREMENTS and PROJECT (PRC-06)
- [ ] `CHANGELOG.md` Phase 11 entry with the smoke-10m and trading-smoke before and after pairs (PRC-03)

**Plans**: 11 planned (11-01 to 11-11) in 6 waves. Plan ids: 11-01, 11-02, 11-03, 11-04, 11-05, 11-06, 11-07, 11-08, 11-09, 11-10, 11-11. Source of truth: `plans.json`; the per-plan PLAN and SUMMARY files are written under `.planning/phases/11-*/` by the GSD workflow.

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

**Plans**: 5 planned (12-01 to 12-05) in 5 waves. Plan ids: 12-01, 12-02, 12-03, 12-04, 12-05. Source of truth: `plans.json`; the per-plan PLAN and SUMMARY files are written under `.planning/phases/12-*/` by the GSD workflow.

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
- [ ] `CHANGELOG.md` Phase 13 entry with both hash pairs (PRC-03)

**Plans**: 7 planned (13-01 to 13-07) in 6 waves. Plan ids: 13-01, 13-02, 13-03, 13-04, 13-05, 13-06, 13-07. Human-gated: 13-05. Source of truth: `plans.json`; the per-plan PLAN and SUMMARY files are written under `.planning/phases/13-*/` by the GSD workflow.

### Phase 14: Event-driven desk and Grok gateway

**Goal**: The supervisor wakes seats on events instead of cadence polling (cadence mode stays the default and byte-identical), every Grok call is a consequence of an event and passes one gateway (prefilter, sanitize, cache, in-flight coalescing, layered persisted budget, fallback ladder), exits and risk can never wait on Grok, ten event-mode seat cycle bodies exist, Hermes cron sessions that duplicate events are disabled, and an idle desk makes zero Grok calls.
**Depends on**: Phase 12 (12-02, 12-03: bus, sources, drain); Phase 13 (13-02: live price source and marks); Phase 11 plans 11-01, 11-03, 11-04, 11-05 and 11-09 (pins, CI, splits, seat_task)
**Requirements**: EVT-08, EVT-10, EVT-12, EVT-13, GRK-01, GRK-02, GRK-03, GRK-04, GRK-05, GRK-06, GRK-07, GRK-08, GRK-09, GRK-10, GRK-11, RT-01
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
  12. `uv run pytest -q tests/replay/test_evidence50_fixture.py` exits 0, `uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/evidence-50 --min-candidates 50 --max-ratio 0.2` exits 0 and `uv run python scripts/measure_grok_calls.py --dataset tests/fixtures/replay/soak-3d --max-ratio 0.2` exits 0; the ratio gate runs on a fixture with at least 50 admitted candidates (GRK-11)
  13. `uv run pytest -q tests/desk/test_event_cycles.py tests/desk/test_event_cycles_aux.py tests/desk/test_journal_rollup_event.py tests/desk/test_event_golden_hashes.py` exits 0 and `! uv run pytest tests/desk/test_event_cycles.py -rs | grep -q SKIPPED` exits 0; all ten seat cycle bodies run on wakes and the event-mode golden hashes hold (RT-01)
  14. `uv run pytest -q tests/degradation tests/events tests/grok` exits 0; the failure-injection scenarios (poison handler, transient retry, exit deadline, P0 flood, P1 overflow, duplicates, crash mid-drain, disconnect storm, silent source, gap, corrupt cursor, Grok breaker, budget windows, injection corpus, hung transport, 100 concurrent requests, replay miss, ledger unwritable) pass (EVT-12)
  15. `test ! -e scripts/probe_curve_layout.py && ! grep -rn probe_curve_layout src tests docs scripts skills Makefile .github` exits 0; the superseded probe script is deleted (MKT-03)
  16. `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0` exits 0; no contract surface changed in this phase (`v4-base` is the tag on the commit where draft PRs 16 to 20 are merged) (EVT-10)
  17. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" && grep -qF "Phase 14: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md && grep -qF "Phase 14: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0, `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 14: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 14: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0; both pairs are recorded and equal, because this phase does not move either hash; `grep -qF 'events-smoke-10m events.hash' CHANGELOG.md && grep -qF 'events-soak-3d events.hash' CHANGELOG.md` also exits 0 and records the new event-mode golden hashes (PRC-03)
  18. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live stays refused (LIV-07)

**Checkpoint**: With wake_mode=event the desk runs the recorded smoke dataset through the bus to the same hash, an idle desk is silent, a hung Grok cannot delay an exit, and cadence mode is unchanged.

**Deliverables**:

- [ ] `src/pumpgrok/grok/` gateway (prefilter, sanitize, cache, budget, ledger, replay backend) and the `core/llm.py` budget surface (GRK-01 to GRK-08)
- [ ] Agents behind the gateway in `src/pumpgrok/engine/agents/` (GRK-05, GRK-09)
- [ ] `supervisor/scheduler/wake.py`, supervisor event mode, `supervisor/metrics_events.py` and `supervisor/scheduler/event_cycles*.py` (EVT-10, GRK-10, RT-01)
- [ ] Hermes cron cutover in `hermes/cron/jobs.yaml`, `docs/runbooks/events.md`, doctor refusal, time-sync probe and the `--wake-mode` flag (EVT-13)
- [ ] `scripts/measure_grok_calls.py`, the `evidence-50` fixture, `ci/gates/check_idle_grok.py` wired into `run_all.py`, the Makefile and `ci.yml` (EVT-12, GRK-11)
- [ ] `CHANGELOG.md` Phase 14 entry with both hash pairs and the `events-smoke-10m` and `events-soak-3d` golden hashes (PRC-03)

**Plans**: 9 planned (14-01 to 14-09) in 7 waves. Plan ids: 14-01, 14-02, 14-03, 14-04, 14-05, 14-06, 14-07, 14-08, 14-09. Source of truth: `plans.json`; the per-plan PLAN and SUMMARY files are written under `.planning/phases/14-*/` by the GSD workflow.

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

**Plans**: 8 planned (15-01 to 15-08) in 7 waves. Plan ids: 15-01, 15-02, 15-03, 15-04, 15-05, 15-06, 15-07, 15-08. Source of truth: `plans.json`; the per-plan PLAN and SUMMARY files are written under `.planning/phases/15-*/` by the GSD workflow.

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
  12. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" && grep -qF "Phase 16: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md && grep -qF "Phase 16: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0, `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 16: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 16: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0; both pairs are recorded and equal, because this phase does not move either hash (PRC-03)
  13. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live stays refused (LIV-07)

**Checkpoint**: A recorded or imported dataset can be backtested per strategy, graded, and the result is persisted and published to the promotion gate as an event.

**Deliverables**:

- [ ] `backtest/metrics_v2.py`, `roundtrip.py`, `event_source.py`, `strategy_run.py`, `gaps.py`, `grading.py` (BT-08 to BT-12)
- [ ] `backtest/scheduler.py`, `store.py` and `evidence.py` (BacktestEvidenceProvider) (BT-13)
- [ ] CLI verbs `run --record`, `live serve`, `replay trim|rebuild-ticks|import`, `backtest --strategy` in `src/pumpgrok/cli/` (REC-03)
- [ ] `reporting/strategy_section.py` per-strategy report section (OBS-07)
- [ ] `CHANGELOG.md` Phase 16 entry with both hash pairs (PRC-03)

**Plans**: 7 planned (16-01 to 16-07) in 6 waves. Plan ids: 16-01, 16-02, 16-03, 16-04, 16-05, 16-06, 16-07. Source of truth: `plans.json`; the per-plan PLAN and SUMMARY files are written under `.planning/phases/16-*/` by the GSD workflow.

### Phase 17: Risk hardening and promotion lifecycle

**Goal**: The risk engine enforces per-strategy slices and strategy kills on existing R34 rows (19 rows and the risk_json shape unchanged), entry checks and feed health fail closed, live failure classes feed the exec-error breaker, strategies move BACKTEST to PAPER to LIVE_ELIGIBLE and back on recorded evidence under version-controlled thresholds with no timers and no Grok, and the event desk composition root wires all of it, recovers from restarts, and refuses to build unless paper.
**Depends on**: Phase 15 (strategy core, allocation, ticket attribution); Phase 16 (backtest evidence and CLI); Phase 14 (wake, gateway, seat cycles); Phase 13 (feed, entry hook); Phases 11 and 12
**Requirements**: RSK-01, RSK-02, RSK-03, RSK-04, RSK-05, RSK-08, PRM-01, PRM-02, PRM-03, PRM-04, PRM-05, PRM-06, RT-03, RT-04
**Success Criteria** (what must be TRUE):

  1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
  2. `uv run pytest -q tests/risk/test_strategy_slice.py tests/risk/test_strategy_kill.py` exits 0; a buy above the slice is capped or rejected on `max_token_fraction`, a kill row blocks buys but not exits and clears only with a human (RSK-01, RSK-02)
  3. `uv run pytest -q tests/risk/test_feed_health.py tests/risk/test_exec_failure_breaker.py` exits 0; staleness is lazy and idle-quiet, a required feed that never ticked fails closed in live mode, live failure classes trip exec_errors, any UNKNOWN sets a halt (RSK-03, RSK-04)
  4. `uv run pytest -q tests/risk/test_entry_checks.py tests/execution/test_entry_gate_hook.py` exits 0 and `uv run python -c "import tomllib;tomllib.load(open('src/pumpgrok/config/mint_lists.toml','rb'))"` exits 0; authority, Token-2022 extension, holder concentration, list and BLIND cases are rejected (RSK-05)
  5. `uv run pytest -q tests/risk/test_step_rows_stable.py tests/characterization/risk` exits 0; STEP_IDS length is 19 and the risk_json shape is unchanged (RSK-08)
  6. `uv run pytest -q tests/promotion/test_stages.py tests/promotion/test_thresholds.py tests/promotion/test_gate_reuse.py tests/upgrade` exits 0; stages are ledger rows with a decision log, a looser threshold than the LiveGate floors refuses to load, the upgrade gate checks are reused and there is no second search (PRM-01, PRM-02, PRM-03)
  7. `uv run pytest -q tests/promotion/test_demotion.py` exits 0 and `uv run pumpgrok promotion demote --help` exits 0; a hash change resets to BACKTEST, demotion is automatic and one operation rolls a strategy back (PRM-04)
  8. `uv run pytest -q tests/promotion/test_no_timers.py tests/desk/test_live_paper_risk_wiring.py` exits 0 and `! grep -rnE 'clock\.sleep|pumpgrok\.grok' src/pumpgrok/promotion` exits 0; the evaluator is event-triggered and subscribed by the composition root (PRM-05)
  9. `uv run pytest -q tests/promotion/test_writer_discipline.py` exits 0; only is_writer callers write and stored content is verified (PRM-06)
  10. `uv run pytest -q tests/desk/test_event_desk_e2e.py tests/desk/test_event_desk_idle.py` exits 0 and `! uv run pytest tests/desk/test_event_desk_e2e.py -rs | grep -q SKIPPED` exits 0; the event desk wires bus, sources, runtime, gateway, router and promotion edges end to end on recorded data, exhausts a real LayeredBudget in e2e, and an idle desk is silent (RT-03)
  11. `uv run pytest -q tests/desk/test_restart_recovery.py tests/desk/test_restart_exit_deadlines.py` exits 0 and `! uv run pytest tests/desk/test_restart_recovery.py -rs | grep -q SKIPPED` exits 0; restart recovery re-arms exit deadlines and restores tapes, peaks, probation and the watch set (RT-04)
  12. `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0` exits 0; no contract surface changed in this phase (`v4-base` is the tag on the commit where draft PRs 16 to 20 are merged) (PRM-01)
  13. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" && grep -qF "Phase 17: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md && grep -qF "Phase 17: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0, `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 17: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 17: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0; both pairs are recorded and equal, because this phase does not move either hash (PRC-03)
  14. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live stays refused (LIV-07)

**Checkpoint**: With every new behavior config-gated off the replay hashes are unchanged; with it on, slices, kills, staleness, entry checks, promotion and restart recovery work end to end under test, and a paper strategy can reach LIVE_ELIGIBLE on evidence. This is the first point where the whole paper desk runs end to end on recorded data.

**Deliverables**:

- [ ] `risk/strategy_slice.py`, `risk/entry_checks.py`, `risk/feed_health.py`, `config/mint_lists.toml`, breaker extensions and the engine reason mapping on existing rows (RSK-01 to RSK-05, RSK-08)
- [ ] `src/pumpgrok/promotion/`, `config/promotion_thresholds.toml`, the `upgrade/gate.py` paper parameter and the `promotion demote` verb (PRM-01 to PRM-06)
- [ ] `supervisor/event_desk.py` composition root, wake subscriptions and the entry-gate wiring in `supervisor/live_paper.py` (PRM-05, RT-03)
- [ ] `supervisor/recovery.py` restart recovery wiring with crash tests (RT-04)
- [ ] `CHANGELOG.md` Phase 17 entry with both hash pairs (PRC-03)

**Plans**: 7 planned (17-01 to 17-07) in 6 waves. Plan ids: 17-01, 17-02, 17-03, 17-04, 17-05, 17-06, 17-07. Source of truth: `plans.json`; the per-plan PLAN and SUMMARY files are written under `.planning/phases/17-*/` by the GSD workflow.

### Phase 18: Dormant live path, amendment-gated

**Goal**: The five hardcoded-unmet live gate rows become real checks, a segregated desk-signer process with single-send persistence, an instruction-level transaction allowlist, chain reconciliation and shadow mode exists, the desk holds no key and no signing symbol, exit sells are never blocked by entry-only gate rows, and the constitution amendment is applied by the owner in one human-approved pull request. Live stays refused: with the overlay disabled, no env flag and no record, `run --mode live` exits 3; arming remains a human-only runbook step.
**Depends on**: Phase 17 (17-02, 17-03, 17-04: feed health, promotion, composition root); Phases 11, 12 and 15; plan 13-03; plans 18-03 to 18-06, 18-08 and 18-09 are amendment_wait and merge only after the owner approves the exact text (OD-01) and plan 18-07 merges
**Requirements**: RSK-06, RSK-09, LIV-03, LIV-04, LIV-05, LIV-06, LIV-07, LIV-08, LIV-09, LIV-10, LIV-11, LIV-12, LIV-13, LIV-14, LIV-15, LIV-16, LIV-17, LIV-18, LIV-19, LIV-20, PRC-07
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

**Plans**: 11 planned (18-01 to 18-11) in 7 waves. Plan ids: 18-01, 18-02, 18-03, 18-04, 18-05, 18-06, 18-07, 18-08, 18-09, 18-10, 18-11. Human-gated: 18-07. Amendment-wait (merge only after the approved amendment lands): 18-03, 18-04, 18-05, 18-06, 18-08, 18-09. Source of truth: `plans.json`; the per-plan PLAN and SUMMARY files are written under `.planning/phases/18-*/` by the GSD workflow.

### Phase 19: Observability, docs, hardening and milestone audit

**Goal**: Operators can see the event runtime, sources, Grok budget, strategy stages and kills, and signer attestation in doctor, health.json and metrics; alert rules name only real metrics; the docs, skills and runbooks describe v4 and every documented command runs; a nightly event-mode soak guards the idle-zero-Grok invariant; the amendment waiver is gone; and a milestone audit traces every requirement to evidence and records that live is still refused.
**Depends on**: Phases 17 and 18 (17-02, 17-03, 17-04, 18-02, 18-07, 18-10, 18-11); plans 11-03, 13-02, 14-04, 14-07 and 16-04 for CI, metrics and CLI lanes
**Requirements**: PRC-06, PRC-08, OBS-01, OBS-02, OBS-03, OBS-04, OBS-05, OBS-06
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

**Checkpoint**: The audit file exists, every requirement is traced, `make check` is green, live is refused, and the human arm procedure is the only remaining step toward live.

**Deliverables**:

- [ ] Doctor v4 report in `src/pumpgrok/doctor.py` (OBS-01)
- [ ] `health.json` event and strategy sections and per-strategy P and live L metric families in `supervisor/health.py` and `supervisor/metrics_events.py` (OBS-02)
- [ ] `docs/observability/alerts.yaml` checked by `tests/docs/test_alert_rules.py` (OBS-03)
- [ ] `ARCHITECTURE.md`, `CLAUDE.md`, `AGENTS.md`, `README.md`, `SETUP.md`, the market-data, replay-and-backtest, doctor and monitoring skills and the datafeed, recorder and promotion runbooks (OBS-04)
- [ ] Nightly event-mode soak in `.github/workflows/ci.yml` and `tests/soak/test_soak_event_mode.py` (OBS-06)
- [ ] Waiver removal in `.github/workflows/gates.yml` (PRC-08)
- [ ] `.planning/milestones/v4-MILESTONE-AUDIT.md`, v4 archive and the final `CHANGELOG.md` closeout (OBS-05, PRC-06)

**Plans**: 9 planned (19-01 to 19-09) in 5 waves. Plan ids: 19-01, 19-02, 19-03, 19-04, 19-05, 19-06, 19-07, 19-08, 19-09. Human-gated: 19-08. Source of truth: `plans.json`; the per-plan PLAN and SUMMARY files are written under `.planning/phases/19-*/` by the GSD workflow.

## Progress

**Execution Order:**
Phases are numbered in dependency order and overlap in time; a plan starts when its dependencies merge (see `.planning/STATE.md`, Dependency levels and scheduling): 11 -> 12 -> 13 -> 14 -> 15 -> 16 -> 17 -> 18 -> 19

Ship checkpoints, where the owner approves receipts in batches as human:SomeRandmGuyy: after Phase 12, after Phase 14, after Phase 17 and after Phase 19. Run every hash command in a fresh git worktree (no `var/ledger.sqlite`), because `verify` reads the active-set record from the working-directory ledger.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 11. Engineering foundation and quality | 0/11 | Not started | - |
| 12. Event runtime core | 0/5 | Not started | - |
| 13. Curve truth, live market data and recorder | 0/7 | Not started | - |
| 14. Event-driven desk and Grok gateway | 0/9 | Not started | - |
| 15. Strategy framework and multi-strategy paper | 0/8 | Not started | - |
| 16. Backtest v2 and autonomous evaluation | 0/7 | Not started | - |
| 17. Risk hardening and promotion lifecycle | 0/7 | Not started | - |
| 18. Dormant live path, amendment-gated | 0/11 | Not started | - |
| 19. Observability, docs, hardening and milestone audit | 0/9 | Not started | - |

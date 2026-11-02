# PumpGrok Desk v4

## What This Is

PumpGrok is a Solana memecoin (pump.fun launch) trading desk: ten LLM-backed seats (chief, scout, risk, whale, sniper, rug, exit, shill, signal, journal) plus a catalog of read-only and paper-write tools and a library of skills, packaged in the shape of programming-desk (`ownership.yaml`, receipts, gates G-1..G-7, contracts, prompt assembly, skill manifests) as a Python 3.12 package `src/pumpgrok/`. It is built for the operator who wants the desk to run autonomously in paper mode, under an asyncio supervisor, recording everything in an append-only ledger and replaying deterministically from fixtures. As of v4 the desk is event-driven and multi-strategy: seats wake on typed events instead of cadence polling (cadence stays the default until a later decision), every Grok call is a consequence of an event and passes one gateway, four bounded baseline strategies (legacy_screening, momentum_breakout, new_launch_sniper, mean_reversion) run in paper against a live-recorded data feed with isolated capital slices, and strategies are promoted and demoted on recorded evidence. v4 also builds a fully tested but DORMANT live path: a segregated desk-signer process holds the only key, the desk package holds no key and no signing symbol, and only a human can arm live once, after which the desk may trade autonomously inside the arm record's caps. Nothing in v4 arms live: the only enabled execution adapter is the `PaperAdapter`, `run --mode live` exits 3 on every default start behind the nine-precondition gate, and no agent or desk process can move real funds.

## Core Value

The desk reacts to events instead of polling, runs several bounded strategies in paper against live-recorded data, promotes and demotes them on recorded evidence, and carries a fully built but DORMANT live path that only a human can arm; no agent and no desk process can move real funds.

## Current State

v2 shipped 2026-10-23 (paper-only desk, ten seats, risk engine, paper adapter on the bonding-curve model, deterministic replay, supervised serve loop, desk gateway, Telegram kill channel; 71 requirements). v3 shipped (closed 2026-10-26): integer money and fail-closed state, `CLAUDE.md` and a trimmed `AGENTS.md`, the holdout-aware `pumpgrok backtest` verb and divergence check, bounded and reversible paper parameter promotion with the constitution amendment of 2026-10-25, and live kept refused (34 requirements, 35 plans). Archived under `.planning/milestones/`: `v2-ROADMAP.md`, `v2-REQUIREMENTS.md`, `v2-MILESTONE-AUDIT.md`, `v3-ROADMAP.md`, `v3-REQUIREMENTS.md`.

v4 is in progress. The roadmap (Phases 11 to 19), requirements (111) and plans (74, in 45 pull requests) were written on 2026-10-28 and none has started. The product line is main at the commit tagged `v4-base`, taken after the owner-approved merge of draft PRs 16 to 20 (order 18, 19, 20, 17 for 17 to 20). Live is still refused (exit 3).

## Current Milestone: v4 Event-Driven Multi-Strategy Desk with a Dormant Live Path

**Goal:** make the desk event-driven (typed event bus, one Grok gateway, event-mode supervisor wake, idle desk silent), run four bounded strategies in paper on live-recorded data with per-strategy slices, backtest v2 and an evidence-based promotion lifecycle, and build the live path fully but dormant (segregated signer, arm record, instruction-level policy, shadow mode, human-approved constitution amendment). Live trading is never enabled by v4.

**Status:** planned 2026-10-28 in `.planning/ROADMAP.md` and `.planning/REQUIREMENTS.md` (111 requirements, 14 families, 9 phases, 74 plans); ready to plan Phase 11 (`.planning/STATE.md`). Phase 11 plan 11-09 installs these planning files in the repository.

**Deferred beyond v4** (see `.planning/STATE.md` Deferred Items and Out of Scope):
- Manual-ticket exit approvals: a standing human `exit_rule` approval that the exit seat consults before a rule sell (PAPER-007 narrowed; see Out of Scope).
- Flipping the default `wake_mode` to event, and removing `stop_loss_poll_seconds` from the bounds: decided in the next milestone after a week of live-paper evidence (OD-20).
- PumpSwap sells (`pool=pump-amm`) and direct pump instruction building in the signer: live-eligible strategies exit before the curve completes in v4 (OD-08, OD-14).
- Telegram inbound verification against a live bot: getUpdates behaviour, webhook 409, group chats.
- Persist the pending kill and its offset across restarts, before commit (in memory today).
- The first arm itself (which strategy and parameter hash, and when): a human-only runbook step.

## Requirements

### Validated (v2, shipped 2026-10-23)

Full v2 record: `.planning/milestones/v2-REQUIREMENTS.md` (71 of 71 complete) and `.planning/milestones/v2-MILESTONE-AUDIT.md` (verdict passed).

<!-- Shipped and confirmed valuable. Inferred from the existing codebase (brownfield). -->

- [x] Eight role prompts (`agents/{chief,scout,risk,whale,sniper,rug,exit,shill}.md`) each carrying the security constitution verbatim; only sniper and exit have `writes_to_exchange: true` (`docs/DISCOVERY.md` section 3.3, `rules/pumpgrok-team.mdc`) - existing
- [x] 23 skills under `skills/` (21 of them stubs) that the seats load by name (`docs/DISCOVERY.md` section 3.3, `docs/MIGRATION_MAP.md`) - existing
- [x] Read-only stdlib CLI tools over Solana JSON-RPC and Jupiter lite-api (`tools/{jupiter_quote,authority_check,holder_check,priority_fee}.py`) with 11 root unittest cases (`docs/DISCOVERY.md` sections 3.2, 3.7) - existing
- [x] Vendored dry-run screening engine `vendor/grokbot-pumpfun/` (monitor, analyzer, scoring, LLM agents, exits, watcher, breakers, ops) with 264 pytest cases and no executable signing or sending code (`docs/DISCOVERY.md` sections 3.5, 3.7, `docs/MIGRATION_MAP.md` section 3.1) - existing
- [x] Hermes cron isolation: six cron prompts, per-seat profiles with Telegram inbound only for chief, forbidden env keys (`PRIVATE_KEY, SECRET_KEY, SEED, MNEMONIC`) and `forbidden_owners: [sniper, exit]` (`docs/DISCOVERY.md` sections 3.2, 3.3, `hermes/cron/jobs.yaml`) - existing
- [x] Plugin manifests for Claude, Grok and Cursor (`plugin.json`, `.claude-plugin/`, `.grok-plugin/`, `.cursor-plugin/`) describing the pack (`docs/DISCOVERY.md` section 6 items 4-5, `docs/MIGRATION_MAP.md` section 4.4) - existing
- [x] `scripts/check.sh` markdown-pack linter with the emoji sweep (`docs/DISCOVERY.md` sections 3.2, 6 item 20; `scripts/check.sh:138-146`) - existing
- [x] FOUND (13 requirements, FOUND-001..013): packaging, toolchain, config precedence, core interfaces and registry, ownership, ported gates, contracts, prompt assembly, workflows, network-blocked test harness, ledger skeleton and the skip-only `pumpgrok run --replay` cycle - Phase 1
- [x] STRUCT (8 requirements, STRUCT-001..008): restructure into `src/pumpgrok/`, vendor engine ported with characterization tests, vendor tree deleted (STRUCT-006), `micro-live` retired, Jito and wallet-key config removed - phases 1, 2, 4
- [x] TOOL (11 requirements, TOOL-001..011): dotted `<ns>.<verb>` tool layer, typed int-lamport schemas, least-privilege tests, per-seat MCP gateway, CLI verbs as thin wrappers; TOOL-011 narrowed by owner decision 2026-10-23 - phase 3
- [x] SKILL (4 requirements, SKILL-001..004): twelve new skills (35 total) with manifests, skill and bot manifest tests, seat prompt sources that enumerate the same skills and tool rosters - phase 3
- [x] PAPER (7 requirements, PAPER-001..007): bonding-curve `PaperAdapter` fill model, append-only hash-chained SQLite ledger, JSONL export and markdown views, deterministic replay, graduation and blind handling, daily and weekly reports, tickets and approvals; PAPER-007 narrowed by owner decision 2026-10-23 - phase 4
- [x] RISK (7 requirements, RISK-001..007): `RiskEngine` inside every order, daily-loss and drawdown halts cleared by humans only, breakers, kill switch, KILL verdicts and seat permissions, observe-only degradation, the D7 no-manipulation boundary with its static test - phases 4, 5
- [x] AUTO (8 requirements, AUTO-001..008): asyncio supervisor for ten seats, heartbeats and restart budget with escalations, graceful shutdown, `/healthz` and `/readyz`, degraded modes, the full ten-seat replay cycle, a 3-day soak and a fault-injection suite - phases 4, 5
- [x] OBS (5 requirements, OBS-001..005): JSON logs with redaction, ULID correlation chains, Prometheus metrics, operator runbooks, changelog and milestone report - phases 1, 5
- [x] SEC (5 requirements, SEC-001..005): no committed secrets and Solana-aware secret scanning, env-only secrets, AST test for signing symbols outside the live stub, live-mode fail-fast with exit 3, green security workflow - phases 1, 2, 4, 5
- [x] GOLIVE (3 requirements, GOLIVE-001..003): `pumpgrok live confirm` HMAC record, `LiveGate.validate` over `source=paper` events only, go-live runbook and per-precondition tests, shipped with `live.enabled = false` everywhere - phases 4, 5

### Validated (v3, closed 2026-10-26)

Full v3 record: `.planning/milestones/v3-REQUIREMENTS.md` (34 of 34 complete) and `.planning/milestones/v3-ROADMAP.md`.

- [x] INT (10 requirements, INT-01..010): integer money across module boundaries, fail-closed corrupt or missing state, integer daily-loss halt, one SOL-to-lamports conversion, id and RNG composition roots, injected-clock live gate, two feature-lineage review fixes, stage-function splits, persisted trailing-stop peaks, bonding-curve layout probe - Phase 6
- [x] DOC (4 requirements, DOC-01..004): `CLAUDE.md` codebase map, `AGENTS.md` cleanup and command verification, docs contradictions corrected, historical design banners - Phase 7
- [x] BT (7 requirements, BT-01..007): run manifests with whole-dataset digest, per-fill replay detail, holdout and walk-forward split, trial recording with 20 and 50 trial limits, bounded metrics, `pumpgrok backtest` verb, holdout-aware harness - Phase 8
- [x] PAP (3 requirements, PAP-01..03): one result schema for backtest and paper trades, divergence check on the D7 defaults, autonomous paper verified on recorded datasets - Phase 8
- [x] UPG (6 requirements, UPG-01..06): content-hashed parameter sets within bounds, promotion gate, evidence record with exact rollback, escalation, SAFE-4 and SAFE-8 advisory BLIND, constitution amendment of 2026-10-25 applied - Phase 9
- [x] LIV (2 requirements, LIV-01..02): live stays refused (exit 3, no live adapter, import-graph test), live-readiness record deferred - Phase 10
- [x] PRC (2 requirements, PRC-01..02): phase gates and receipts, phase branches and pull requests; closed with owner-approved deviations (V3-5) - Phase 6

### Active (v4)

<!-- Current scope. One line per requirement family; the individual ids live in .planning/REQUIREMENTS.md. -->

- [ ] EVT (13 requirements, EVT-01..10, EVT-12..14): typed frozen events in one catalog, P0 lane that never drops, dedup, coalescing, seeded retry, persisted DLQ, graceful shutdown, deterministic drain, SourceSupervisor, event-mode supervisor wake, idle desk, Hermes cutover (EVT-11 is merged into PRC-03)
- [ ] GRK (11 requirements, GRK-01..11): one Grok gateway: prefilter, sanitizer and strict parse, cache, in-flight coalescing, layered persisted budget, fallback ladder, replay backend, exits and risk never wait on Grok, metrics, measurement script
- [ ] MKT (10 requirements, MKT-01..10): token-first curve layout, pump event decoder, human-reviewed probe record and status flips, allowlist price gate, bounded read-only live feed, fail-closed LivePriceSource, marks, graduation, no-send proof for live-data paper
- [ ] REC (3 requirements, REC-01..03): self-verifying recorder with gaps, importer, trim and rebuild verbs
- [ ] STR (5 requirements, STR-01, STR-03..06): strategy protocol, registry, runtime, attribution, four baseline strategies with bounded parameters, parameter identity over strategy parameters, no LLM in any strategy hook (STR-02 is merged into PRC-03)
- [ ] BT (6 requirements, BT-08..13): Metrics v2, round trips, look-ahead canary and evidence grading, gap segmentation, strategy-aware replay, autonomous idempotent backtest scheduler (continues the v3 BT family)
- [ ] RSK (8 requirements, RSK-01..06, RSK-08..09): per-strategy slice and kill on existing rows, lazy idle-quiet feed health, live failure classes, entry checks, choke-point proof, 19 STEP_IDS unchanged, exit-sell gate rows (RSK-07 is merged into PRC-03)
- [ ] PRM (6 requirements, PRM-01..06): stage machine BACKTEST to PAPER to LIVE_ELIGIBLE on ledger rows, floors equal to the LiveGate constants, gate reuse, automatic demotion, event-triggered with no timers, writer discipline
- [ ] LIV (18 requirements, LIV-03..20): dormant live path: real gate rows 5 and 6, arm record bound to the configuration hash and (strategy, parameter hash) pairs, stop-state reader, registry, segregated desk-signer with single send and instruction-level allowlist, reconcile, shadow mode, additive live event source, amendment oracle (continues the v3 LIV family)
- [ ] QLT (10 requirements, QLT-01..10): fast and soak test split, coverage floor, complexity ratchet, six hotspot splits behind characterization tests, narrowed excepts, property tests, mutation smoke, SBOM, compose hardening
- [ ] PRC (9 requirements, PRC-03..11): replay hash pins and CHANGELOG pairs per phase, waiver removal, receipt glob, journal and chief closes per phase, amendment by a human-approved pull request, services in CI, settings skeleton (continues the v3 PRC family)
- [ ] OBS (7 requirements, OBS-01..07): doctor v4, health and metric sections, alert rules, docs, nightly event soak, milestone audit, per-strategy report section
- [ ] FEE (1 requirements, FEE-01): paper fee model v2 selectable, default flip with a recorded before and after pair
- [ ] RT (4 requirements, RT-01..04): event-mode seat cycle bodies, Intent to exec.place router, event desk composition root, restart recovery

### Out of Scope

<!-- Explicit boundaries from docs/upgrade-plan-desk-v2.md section 5.11 and the v4 requirements. -->

- Live trading enablement: arming live, live order placement and any real transaction stay out of scope until the human-approved constitution amendment is applied (plan 18-07, PRC-07) and the human arm procedure is run (`docs/runbooks/go_live.md`); v4 builds the path dormant, `run --mode live` exits 3, and no agent arms, extends or widens an arm record
- Signing and custody inside the desk package: keys exist only in the separate desk-signer process on a host the human provisions; the desk keeps zero signing symbols (INV-S-01 tightened); wallet funding is a human step
- Applying a constitution amendment by an agent: amendments are drafted for the owner and applied only by a human-approved pull request
- Web dashboard or UI beyond text/markdown reports - spec non-goal; `reporting/dashboard.py` is a text renderer only
- New chains, venues, launchpads, data vendors; post-graduation CPMM modelling and PumpSwap sells - D8 keeps the integrations exactly as today; R8/R38 document graduation as a force-close limitation; live-eligible strategies exit before the curve completes (OD-08)
- External historical data or new data vendors - data policy unchanged: self-recorded only (D8, AF-10); the recorder and importer never fabricate or back-fill evidence
- Paid RPC procurement or spend by an agent - a human may choose and record a provider (OD-05); no v4 code assumes one
- PumpPortal trade-stream key - default no (R45); user decision
- Multi-tenant, billing, SaaS packaging - spec non-goal; single-operator internal tool
- New alpha and new signal families beyond the four baseline strategies (legacy_screening, momentum_breakout, new_launch_sniper, mean_reversion), which are in scope under clause 8 as amended on 2026-10-25; paper parameter evaluation and bounded promotion stay in scope
- Engagement level `micro-live` - retired by R16; levels are `research | paper` only, `live` exists solely behind the disabled gate
- Changing `~/src/repos/programming-desk/` itself - spec non-goal; it is mirrored in shape and names only, never imported or edited
- Social posting, coordinated buying, volume tooling, wallet UI automation - forbidden by D7/R39; detection only, enforced by a static test
- Telegram live verification, G-4 consumer acknowledgements beyond the one additive contract, bot-06 exit roster change - human actions outside the code
- Manual-ticket exit approval path (PAPER-007) - deferred by owner decision 2026-10-23
- Flipping the default `wake_mode` to event - cadence stays the default through v4 (OD-20)
- Coverage threshold beyond the measured Phase 11 baseline, ed25519 confirmation signatures, Greptile as a gate, gateway OAuth - deferred (`docs/FOUNDATION_STACK.md` U-5, `docs/design/paper-engine.md` section 7.3)

## Context

**Baseline**
- v2 and v3 are closed. Milestone v4 branches from main at the commit tagged `v4-base`, after draft PRs 16 to 20 merge (owner decision V4-5); `feat/grokbot-desk-merge` stays untouched (V3-3).

**Technical environment**
- Python 3.12 only (`requires-python = ">=3.12,<3.13"`), `uv` + `uv.lock`, `ruff` (lint + format), `mypy --strict` on `src/`, `pytest` + `pytest-asyncio`, `pip-audit` via the `uv export` bridge; Dockerfile + compose, Makefile.
- Foundation libraries (D5, documented deviations from programming-desk): pydantic v2 + pydantic-settings (TOML overlays dev/paper/live, `PUMPGROK_*` env), httpx (+respx fixtures), websockets, tenacity, stdlib JSON logging with contextvars correlation ids, sqlite3 WAL ledger, asyncio supervisor, prometheus_client.
- Venues and data sources, kept exactly as today (D8): Solana mainnet JSON-RPC (public default, env override, failover list), pump.fun frontend REST (unofficial), PumpPortal WebSocket, Jupiter lite-api quote (informational only, never the fill price), x.ai Grok chat completions (`grok-4.3` and `grok-4.20-0309-non-reasoning`, R48).
- Alerts: abstract `Notifier` with stdout and file sinks always on; Telegram (Hermes chief profile token) and webhook sinks config-driven and restricted to an allowlist.

**Prior work**
- `vendor/grokbot-pumpfun/` at commit `409e74c`: the Russian-language dry-run engine. Its 264 tests were the characterization oracle through v2 Phase 4. The tree is deleted (STRUCT-006); the engine lives in `src/pumpgrok/engine/` with `LICENSE-grokbot-pumpfun`.
- Six Hermes cron prompts (`hermes/cron/prompts/`) and per-seat profiles; prompts are thin wrappers over `pumpgrok` CLI verbs and the schedule lives in the supervisor.
- Eight seat prompts generated from `prompts/bot-0N-<seat>.xml` and 35 skills (v2 SKILL-001..004).

**Historical known issues** (`docs/DISCOVERY.md` section 6, written before v2; open carry-forward items are listed in `.planning/STATE.md` Deferred Items)
- Drift: Jupiter `/v6` documented while code uses lite-api; `--max-micro` documented but unimplemented; three disagreeing skill maps (agents vs Hermes profiles vs bootstrap script); manifests say MIT while LICENSE is AGPL-3.0; `your-org` placeholders; `issues/tissue.json` version mismatch.
- Stubs and weak checks: dead `pass` checks in `scripts/check.sh`; `check.sh` runs no Python tests and validates no manifests; `rpc_call` copy-pasted three times; ImportError envelopes inconsistent; Russian log strings in every vendor module.
- No packaging or CI at the root: no `pyproject.toml`, lockfile or `.gitignore`; six tracked `*.pyc`; vendor floor Python 3.11 and `>=` ranges; `solders`/`solana` declared but unused.
- No paper ledger: persistence was a markdown file bus plus vendor JSON state; non-atomic `desk.md` rewrite on halt; ticket-id allocation race across four cron owners (duplicate `SOL-YYYYMMDD-NNN` would violate D9); no fee or impact model, no supervisor.

**Reference architecture**
- `/root/src/repos/programming-desk` is mirrored in shape and names only (layout, `ownership.yaml`, `ci/gates/`, `contracts/tool-rosters/`, `prompts/` + `scripts/assemble-prompts.sh`, `.receipts/`, skills L1/L2/L3, `services/desk-gateway/`); no cross-repo imports and the reference repo is never changed.

**Design documents** (binding precedence: resolutions R16-R43 in the upgrade plan override the others where they conflict)
- `docs/DISCOVERY.md` - what exists today in both repos, with `file:line` evidence, drift list and old-to-new skeleton.
- `docs/MIGRATION_MAP.md` - 129 old-to-new rows, keep/move/replace decisions, live-write quarantine, vendor retirement census.
- `docs/ROSTER.md` - the ten seats, manifests, least-privilege matrix, `ownership.yaml` draft.
- `docs/TOOL_CATALOG.md` - every tool as `<ns>.<verb>` with schemas, side effects, roster YAML and CLI verbs.
- `docs/FOUNDATION_STACK.md` - library choices, pinned versions, file drafts, canonical commands, gate constant retargets.
- `docs/SAFETY_INVARIANTS.md` - every non-negotiable invariant with exactly one owning test, failure modes, fault-injection harness, phase placement.
- `docs/RISK_POLICY.md` - risk defaults (all REVIEW), paper-first policy, the D7 manipulation boundary, human-in-the-loop and secrets policy.
- `docs/design/interfaces.md` - core protocols, registry invariants, skill and bot manifest shapes, least-privilege tests.
- `docs/design/paper-engine.md` - PaperAdapter fill model, ledger, replay, risk engine, supervisor, live gate, reports, test plan.
- `docs/upgrade-plan-desk-v2.md` - the v2 idea document: decisions D1-D9, resolutions R1-R43, 71 requirements in ten families, five-phase plan, verification and risks.

**v4 design records** (written by their plans, not yet present)
- `docs/design/events-grok.md` - event runtime, bus lanes, sources and the Grok gateway (plan 12-02).
- `docs/design/live-ledgers.md` - the paper and live ledgers, what the stage, kill and halt mirror is and is not (plan 18-06).
- `docs/runbooks/events.md`, `datafeed.md`, `recorder.md`, `promotion.md`, `go_live.md`, `signer.md`, `live_rollback.md` - operator runbooks (plans 14-04, 18-09, 19-07).
- `docs/CURVE_LAYOUT_PROBE.md` and `docs/mutation-testing.md` - probe record and mutation smoke notes (plans 13-02, 11-05).

## Constraints

- **Security**: Paper-only hard default; `execution.mode` defaults to `paper`, `PaperAdapter` is the only enabled adapter, live adapters raise `LiveGateError`, and `pumpgrok run --mode live` exits 3 unless all nine R21 preconditions hold (precondition 8, a registered live adapter, never holds in v3) - the core value depends on no code path being able to move real funds.
- **Security**: No private keys, seed phrases or keypairs ever enter the system; forbidden config names abort startup, secrets arrive only via env, and an AST test fails on signing symbols outside the live stub - the security constitution (`rules/pumpgrok-team.mdc`) is kept verbatim.
- **Compliance**: Detect and trade on observed public signals only; no coordinated buying, wash trades, volume generation, shilling, social posting or wallet UI automation - D7/R39, enforced by `tests/safety/test_no_manipulation_tools.py` and the `notify.alert` allowlist.
- **Compliance**: Constitution clauses are enforced in code, not prose: ticket format `SOL-YYYYMMDD-NNN`, exact human approval phrase, single-send idempotency, RISK `KILL` non-overridable, 5% daily-loss `FLOOR HALTED` with human-only clear - D9, R5, R22, R23.
- **Compatibility**: Mirror programming-desk conventions exactly in shape and names (`ownership.yaml` with one owner per tracked path, gates G-1..G-7 plus self-test, receipts per PR under `.receipts/<seat>/`, prompt assembly from `prompts/*.xml`, skills with L1/L2/L3 bodies and manifests) - D1/D2, so operators and agents move between the two desks without relearning.
- **Compatibility**: Keep the Solana integrations exactly as today (mainnet JSON-RPC, pump.fun REST, PumpPortal WS, Jupiter lite-api, x.ai Grok); nothing added, nothing dropped; Jito dead config and `wallet_private_key` removed - D8, R3.
- **Tech stack**: Python 3.12 only, `uv`, ruff, mypy --strict, pytest; money as integers in base units (lamports, token units) with `Decimal` only for ratios; ULIDs from `core/ids.py`; all time through the `Clock` (no direct `asyncio.sleep`/`time.time`) - D1, R27, R28, R29 keep replay deterministic and the ledger hash chain stable.
- **Process**: ASCII-only new docs (`scripts/check.sh` fails on emoji); constitutional strings keep their exact bytes (U+2013) in code - R7.
- **Process**: GSD workflow with code review and verification per phase; one PR per batch on `bot-0N-<seat>/phase-<n>-<unit>` branches with a receipt and `python3 ci/gates/run_all.py` green; v3 phase branches are draft-only and nothing merges to main without approval (PRC-02).
- **Process**: v2 checkpoint rule, kept for v3: `make lint`, `make typecheck`, `make test`, `./scripts/check.sh`, and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` completing one cycle on fixture data with no network - R37, SPE-18063. v3 adds a `.receipts/<seat>/<task>.json` receipt for each completion claim (PRC-01).
- **Dependencies**: pump.fun frontend REST and PumpPortal WS are unofficial with heuristic field names; upstream payloads parse with `extra="ignore"` models, and a malformed payload yields `DataStale`/`BLIND` - upgrade plan section 8.1. BLIND is treated as KILL except for SAFE-4 and SAFE-8 while no paid RPC provider is recorded (amendment approved 2026-10-25).

## Key Decisions

<!-- Decisions that constrain future work. Outcome is "Decided" or "Pending (phase N)". -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| D1: Python 3.12 only; mirror programming-desk shape and names; no cross-repo imports | One language, one operating model, no coupling between desks | Decided |
| D2: Target skeleton copies programming-desk file names (ownership.yaml, ci/gates, contracts/tool-rosters, prompts, .receipts, services/desk-gateway, docs/runbooks) | Operators and agents reuse the same conventions and gates | Decided |
| D3: Ten seats bot-00-chief .. bot-09-journal; chief never trades; sniper and exit are the only paper-write seats; RISK veto absolute | Eight existing roles kept, signal and journal added; least privilege per seat | Decided |
| D4: Mode defaults to paper; PaperAdapter is the only enabled adapter; live adapters are disabled stubs behind the live gate; no private keys ever | No code path can move real funds | Decided |
| D5: pydantic v2 + pydantic-settings, httpx, websockets, tenacity, JSON logging, sqlite3 WAL ledger, asyncio supervisor, prometheus_client, ruff, mypy, pytest, uv | Boring, pinned, testable foundation; documented deviations from programming-desk | Decided |
| D6: Conservative risk defaults (10 SOL paper equity, 2% per trade, 5% per token, 5% daily loss halt, 15% drawdown halt, liquidity floor 10x), every one REVIEW | Fewer trades, cleaner evaluation; numbers change in one TOML block | Decided |
| D7: Compliance boundary: observed signals only; no manipulation, posting or volume tooling | Legal and ethical boundary of the desk, enforced by static tests | Decided |
| D8: Chains and venues kept exactly as integrated today; nothing added or dropped | Scope control; the goal is modernisation, not new coverage | Decided |
| D9: Ticket format, approval phrase, single-send, RISK KILL, 5% daily-loss FLOOR HALTED are constitutional and enforced in code | The constitution was prose only; code must prove it | Decided |
| R16: Engagement levels are `research \| paper` only; `micro-live` retired everywhere | Removes the only prose path toward real funds | Decided |
| R19: Tool ids are dotted `<ns>.<verb>` everywhere; transport name derived at exposure time, never stored | One vocabulary across catalog, rosters, registry, gates and tests | Decided |
| R20: One risk budget schema of nine fraction-of-equity keys used in RiskBudget, rosters, TOML and check_limits output | Prevents three drifting copies of the same limits | Decided |
| R21: The one live-gate precondition list (9 items) including an HMAC-signed human confirmation and a registered adapter that never ships | Live stays documented, tested and disabled | Decided |
| R22: Kill switch set/flatten by tool, clear by CLI only with an approval record; halts human-clear only; all re-checked at CONFIRMING | A flipped safety state rejects in-flight orders; no auto-clear | Decided |
| R23: exec.place idempotency key = (ticket_id, side, decision_id); approval consumed in the same ledger transaction | Implements the single-send rule mechanically | Decided |
| R26: Single ledger writer via BEGIN IMMEDIATE with the hash chain computed inside the transaction; markdown exports via tmp + os.replace | Consistency without supervisor IPC; no torn files | Decided |
| R27: All time through the Clock; direct asyncio.sleep/timeout/time.time forbidden by a static test; replay fails on a missing LLM record | Deterministic replay; no silent divergence | Decided |
| R28: Money as integers in base units; Decimal only for ratios; no float money; canonical JSON for hashes | Exact accounting and a stable hash chain | Decided |
| R30: Config precedence CLI --mode > env PUMPGROK_MODE > TOML; in-package overlays selected by PUMPGROK_PROFILE (default paper); no root config/ | One effective mode the live gate can evaluate | Decided |
| R31: Single-truth module placement under src/pumpgrok/{execution,risk,engine,tools,ledger,supervisor,...}; live stub owned by bot-02-risk | Ends module-name drift between design docs | Decided |
| R32: Ledger schema and the eighteen CamelCase event types defined once in ledger/events.py; snake_case kinds generated from the registry | One event vocabulary for ledger, schemas, tools and reports | Decided |
| R37: Five phases re-cut so every checkpoint is buildable from Phase 1 and the checkpoint rule holds with no waiver; vendor suite is the oracle through Phase 4 | Partial ports never leave two engines alive or a red checkpoint | Decided |
| R44: Jupiter quote via api.jup.ag/swap/v2/order, quote-only (no taker), optional JUPITER_API_KEY | lite-api v1 is no longer maintained; Swap V2 is the maintained quote path (STACK V-8) | Decided |
| R45: PumpPortal free methods only (subscribeNewToken, subscribeMigration); no trade-stream key | Trade streams need a key funded with >=0.02 SOL that embeds a wallet private key (D4 forbids key material); open decision resolved as default no | Decided |
| R46: trade events from Solana JSON-RPC (logsSubscribe on bonding-curve PDAs, bounded getTransaction) | Replaces the PumpPortal trade stream without key material; bounded by signal.max_watched_mints | Decided |
| R47: pump.fun frontend REST treated as degradable (530/1016 observed) | Observed unavailable on all v1 paths; no entry may depend on it alone | Decided |
| R48: x.ai models in config: grok-4.3 (strong, low effort) and grok-4.20-0309-non-reasoning (fast) | grok-4 and grok-4-fast retired 2026-05-15 | Decided |
| R49: accepted STACK corrections V-1..V-7, V-9; PumpPortal trade key left off (default no) | Keeps dependency pins current and makes the one open financial-dependency decision explicit | Decided |
| V2-O1: The CLI refuses `pumpgrok paper buy` and `paper sell` for every seat (exit 1, no write); paper orders go through the gateway seats that hold exec grants (sniper, exit) | Owner decision from the v2 audit, 2026-10-23; narrows TOOL-011 | Decided |
| V2-O2: The replay sandbox runs autonomous-paper; the production default stays manual-ticket | Owner decision from the v2 audit, 2026-10-23; production behaviour unchanged | Decided |
| V2-O3: PAPER-007 narrowed: the manual-ticket standing `exit_rule` approval path is a deferred follow-up, not part of v2 | Owner decision from the v2 audit, 2026-10-23 ("narrow PAPER-007, then archive v2") | Decided |
| V3-1: Constitution amendment approved 2026-10-25 as drafted, with BLIND narrowed to SAFE-4 and SAFE-8 (holder concentration and deployer history) while no paid RPC provider is recorded; clause 8 permits paper-only, bounded, reversible promotion under the human-set autonomous-paper level; live trading stays disabled | Owner approval 2026-10-25. Applied in phase 9 together with its code (UPG-05, UPG-06), not in the planning step | Pending (phase 9) |
| V3-2: Backtest data is self-recorded only; no external history | Owner decision 2026-10-25; data policy D8 and AF-10 | Decided |
| V3-3: Branch bot-00-chief/v2-closeout from origin/main; feat/grokbot-desk-merge untouched; draft PRs only; no merge without approval | Owner decision 2026-10-25 (PRC-02); draft clause superseded for the Phase 6 PR by V3-5 | Decided |
| V3-4: Research skipped for v3 (repo-grounded audits completed 2026-10-25). Defaults apply: D11 max 50 trials per search, D12 flag above 20 trials, D13 final 20 percent holdout; D7 divergence defaults 2 percentage points absolute return gap or 0.5 Sharpe gap | Owner approval 2026-10-25 | Decided |
| V3-5: Phase 6 closes 2026-10-26 with two owner-approved deviations (approved_by human:SomeRandmGuyy). Criterion 17: G-1 (170 foreign-owned paths) and G-2 are waived in CI for the Phase 6 pull request only, through a PR-number condition in .github/workflows/gates.yml; run_all.py still exits 1 locally on G-1. Criterion 16: the phase pull request is ready for review, not draft, and merges to main through ultrathink-ship after CI is green and Greptile reaches 5/5 with no open threads, using squash. The 2026-10-25 re-own decision is superseded; the 170 paths stay foreign-owned until a follow-up change, and the waiver stays on main until a cleanup change removes it. | Owner decision 2026-10-26; approved_by human:SomeRandmGuyy | Decided |
| V4-1: Live is armed once by a human, then the desk is autonomous inside the arm record's caps; v4 builds that path DORMANT and never arms it | Owner decision 2026-10-28. Requires constitution clause 2 amended (draft with errata E1 to E5, see V4-4). A default live start still exits 3 listing the nine preconditions (LIV-07); arming is a human-only runbook step | Decided |
| V4-2: Live limits stay inside the current rules: notional cap at most 1.0 SOL (a larger value refuses to load) and the D6 fractions; at arm time cap_sol = min(1.0, 200 USD / SOL price minus fees) and funding never exceeds cap plus fees | Owner decision 2026-10-28; OD-12 default and errata E4; throwaway wallet limit unchanged | Decided |
| V4-3: Custody is a segregated signer process (`services/desk-signer`): own uid and container, own sqlite, key file readable only by the signer uid and placed by the human; the desk package holds no key and no signing symbol (INV-S-01 tightened); IPC over a Unix socket, mode 0660 with a client group | Owner decision 2026-10-28; a compromised desk can always call the socket, so authority lives in signer-side policy (instruction-level allowlist, signer-owned blockhash, final-bytes verification), not in a shared secret. OD-11 and OD-14 defaults | Decided |
| V4-4: Constitution amendments are drafted for the owner and applied only by a human-approved pull request: plan 18-07 is one owner-applied PR with every copy, a frozen oracle and one step-scoped G-1 waiver, and plan 19-04 removes the waiver | Owner decision 2026-10-28; the draft changes clauses 1, 2, 3, 8, 9, the SNIPER bullet and the closing paragraph; errata E1 (exit sells never suspended, arm record lists (strategy, parameter hash) pairs with a maximum expiry), E2 (failed on-chain send halts like UNKNOWN), E3 (operator-local config outside git), E4 (USD cap rule), E5 (every missed copy) apply (OD-01). Agents never apply, paraphrase or merge the text | Pending (phase 18) |
| V4-5: Draft PRs 17 to 20 are approved for merge in the order 18, 19, 20, 17 before v4 starts; the merge commit is tagged `v4-base` | Owner decision 2026-10-28; plan 11-01 preflight proves the symbols the later plans rely on (`backtest/equity.py`, `is_writer`, `verify_stored_content`) and fails until the PRs are merged | Decided |
| V4-6: Receipts are approved as human:SomeRandmGuyy in batches at four ship checkpoints, after phases 12, 14, 17 and 19; a seat never approves its own work | Owner decision 2026-10-28; human-gated plans commit receipts without approved_by and the owner adds it at the checkpoint; the Greptile score is never written into a receipt | Decided |
| V4-7: The event runtime keeps one typed catalog (`events/models.py`) with priority a pure function of kind, a P0 lane that never drops, bus state in a sidecar sqlite that never touches the ledger, a deterministic drain for replay, and one owner of source staleness; cadence mode stays the default and byte-identical | Design A as corrected by N6 (changes-applied items 11 and 12); keeps smoke-10m unchanged by construction; flipping the default is deferred (OD-20) | Decided |
| V4-8: Every Grok call is a consequence of an event and passes one gateway (prefilter, sanitizer, cache from an explicit payload, in-flight coalescing, layered persisted budget, fallback ladder); exits and risk never import or wait on it; an idle desk makes zero calls | Design A as corrected by N6 (item 14); GRK-07 and EVT-12 are enforced by static tests and an idle-Grok gate in CI; Hermes cron jobs that duplicate events are disabled in event mode (OD-13) | Decided |
| V4-9: Replay hash discipline: smoke-10m events.hash stays b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d at every phase close; the trading smoke hash is pinned in plan 11-01 and moves once, in Phase 15, with the paper fee model v2 default flip (OD-09); each phase records both before and after pairs in CHANGELOG.md; every new behavior is config-gated off | N6 items 9 and 23; no design may move a hash silently | Decided |
| V4-10: Four baseline strategies (legacy_screening, momentum_breakout, new_launch_sniper, mean_reversion) with bounded, version-controlled parameters under `[strategy.ID.PARAM]`; slice weights 0.20 each with a 0.20 reserve (OD-17); a new paper-event overlay allows 6 open positions and 40 trades per day while the live overlay stays at 3 and 20 (OD-02); parameter identity covers strategy parameters and legacy content hashes stay byte-identical | Designs B and C as corrected by N6 (items 4 and 8, 16); no new strategy beyond the four is in scope | Decided |
| V4-11: Promotion is BACKTEST to PAPER to LIVE_ELIGIBLE on ledger rows, event-triggered with no timers and no Grok; floors equal the LiveGate constants (14 days, 50 closed trades, profit factor 1.2, drawdown 0.15) and the loader refuses looser values; LIVE is derived, never stored; live-eligible strategies must exit before the curve completes (max_progress at most 0.85, exit_progress at most 0.92), and no PumpSwap sells exist in v4 | Design C and OD-08, OD-16; any parameter hash change resets the pair to BACKTEST and needs a new arm | Decided |
| V4-12: Exits are never suspended by entry-only conditions: the gate splits into check_entry (all rows) and check_exit (rows 1, 2, 5, 6, 8), and exit and flatten sells are minted autonomous_live while any live position is open, even with a halt, kill, breaker or expired arm; a failed on-chain send latches a human-clear halt like UNKNOWN; a send is persisted as SIGNED before the RPC call and UNKNOWN is never retried; arm expiry defaults to 72 hours with a hard ceiling of 168 (OD-07) | N6 blocker items 1 to 3 and errata E1 and E2; REVIEW defaults for holder fraction 0.30, strategy loss 0.25 of slice, 4 consecutive losses and drift tolerance 5_000_000 lamports (OD-03) apply until the owner replies | Decided |
| V4-13: Data policy is unchanged (self-recorded only); evidence grading lets only recorded, complete, long, gap-light data count toward promotion; no paid RPC provider is recorded, so defaults use the public endpoint with a reduced watch set (OD-05) | Owner decision 2026-10-25 (V3-2) carried forward; B-design recorder and N6 items 15 and 17 | Decided |
| V4-14: Quality first and one plan layer: Phase 11 splits six hotspots behind characterization tests, removes every PR-number waiver and adds a receipt glob; `plans.json` (74 plans, 45 pull requests, one per phase and seat, plus a journal CHANGELOG PR and a chief close PR per phase) is the single source for plans, seats, waves and acceptance commands; the amendment PR is the only pull request that is not seat-pure | pr-plan.md and changes-applied.md; the 21 open owner decisions OD-01 to OD-21 carry recommended defaults that apply when no answer arrives by their needed-by point and are listed as unverified in the receipt (`.planning/STATE.md`) | Decided |

## Evolution

PROJECT.md evolves throughout the project lifecycle.
These rules are embedded in the generated PROJECT.md (## Evolution section)
and implemented by workflows/transition.md and workflows/complete-milestone.md.

**After each phase transition:**
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone:**
1. Full review of all sections
2. Core Value check - still the right priority?
3. Business Context check (if present) - customer, revenue model, success metric still accurate?
4. Audit Out of Scope - reasons still valid?
5. Update Context with current state (users, feedback, metrics)

**v3 note (2026-10-25):** v3 phase numbering continues from v2's five phases, so phase 9 is the phase that applies the constitution amendment (V3-1). Each v3 phase closes with the PRC-01 gate set and a receipt per completion claim. As each v3 family completes, move its items from Active to Validated with the phase reference, and move any requirement the amendment or audits invalidate to Out of Scope with its reason.

**v4 note (2026-10-28):** v4 phase numbering continues from v3, so phase 11 is the first v4 phase. Each v4 phase closes with the PRC-01 gate set, a receipt per completion claim, one journal CHANGELOG pull request with both replay hash pairs and one chief `.planning` close. As each v4 family completes, move its items from Active to Validated with the phase reference. The amendment pull request (plan 18-07) is the only change that edits the Out of Scope live and custody rows and the BLIND constraint text, and only a human applies it.

---
*Last updated: 2026-10-28 after the v4 roadmap and requirements were written (owner decisions V4-1 to V4-14)*

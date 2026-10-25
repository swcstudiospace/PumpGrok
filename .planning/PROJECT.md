# PumpGrok Desk v2

## What This Is

PumpGrok is a Solana memecoin (pump.fun launch) trading desk: ten LLM-backed seats (chief, scout, risk, whale, sniper, rug, exit, shill, signal, journal) plus a catalog of read-only and paper-write tools and a library of skills, packaged in the shape of programming-desk (`ownership.yaml`, receipts, gates G-1..G-7, contracts, prompt assembly, skill manifests) as a Python 3.12 package `src/pumpgrok/`. It is built for the operator who wants the desk to run autonomously in paper mode for the first 2-4 weeks, under an asyncio supervisor, against live Solana data, recording everything in an append-only ledger and replaying deterministically from fixtures. It can never move real funds: the only enabled execution adapter is a `PaperAdapter`, live adapters are disabled stubs behind a nine-precondition gate, and private keys never enter the system.

## Core Value

The desk runs autonomously in paper mode for 2-4 weeks and produces honest, replayable reports; no code path can move real funds.

## Current State

v2 shipped 2026-10-23: a paper-only desk with ten seats, a risk engine, a paper adapter on the bonding-curve model, deterministic replay, a supervised serve loop, a desk gateway, and a Telegram kill channel. All 71 requirements are complete, with PAPER-007 narrowed by owner decision. Archived under `.planning/milestones/`: `v2-ROADMAP.md`, `v2-REQUIREMENTS.md`, `v2-MILESTONE-AUDIT.md`.

v2 is shipped on main; the product line is main `f3887bb`. Milestone v3 is defined (2026-10-25) and its roadmap is pending approval.

## Current Milestone: v3 Evaluation, Bounded Upgrade and Live Readiness

**Goal:** make paper trading autonomous and evaluable (backtest with holdout, paper divergence check, bounded and reversible paper parameter promotion), close audited invariant gaps, and document the codebase for agents. Live trading stays disabled.

**Status:** requirements defined 2026-10-25 in `.planning/REQUIREMENTS.md` (34 requirements, seven families); roadmap pending approval (`.planning/STATE.md`).

**Deferred beyond v3** (carried from the v2 next goals; see `.planning/STATE.md` Deferred Items):
- Manual-ticket exit approvals: a standing human `exit_rule` approval that the exit seat consults before a rule sell (PAPER-007 narrowed; see Out of Scope).
- A live curve source for serve and paper trading. Serve trades only on fixture curves today.
- Telegram inbound verification against a live bot: getUpdates behaviour, webhook 409, group chats.
- Persist the pending kill and its offset across restarts, before commit (in memory today).

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

### Active (v3)

<!-- Current scope. One line per requirement family; the individual ids live in .planning/REQUIREMENTS.md. -->

- [ ] INT (10 requirements, INT-01..010): integer money across module boundaries, fail-closed corrupt or missing state, integer daily-loss halt, one SOL-to-lamports conversion, id and RNG composition roots, injected-clock live gate, two feature-lineage review fixes, stage-function splits, persisted trailing-stop peaks, bonding-curve layout probe
- [ ] DOC (4 requirements, DOC-01..004): `CLAUDE.md` codebase map, `AGENTS.md` cleanup and command verification, docs contradictions from the 2026-10-25 audit corrected, historical design banners
- [ ] BT (7 requirements, BT-01..007): run manifests with whole-dataset digest, per-fill replay detail, holdout and walk-forward split, trial recording with 20 and 50 trial limits, bounded metrics, `pumpgrok backtest` verb with byte-identical reports, holdout-aware harness replaces the grid search
- [ ] PAP (3 requirements, PAP-01..03): one result schema for backtest and paper trades, divergence check on the D7 defaults, autonomous paper verified end to end on recorded datasets
- [ ] UPG (6 requirements, UPG-01..06): content-hashed parameter sets within version-controlled bounds, promotion gate (bounds, holdout, divergence, at most 20 trials, autonomous-paper level), evidence record with exact one-operation rollback, escalation for ineligible candidates, SAFE-4 and SAFE-8 advisory BLIND, constitution amendment applied
- [ ] LIV (2 requirements, LIV-01..02): live stays refused (exit 3, no live adapter, import-graph test), live-readiness record deferred with no signing or custody code
- [ ] PRC (2 requirements, PRC-01..02): phase gates and receipts for every completion claim, phase branches and draft-only PRs with no merge to main without approval

### Out of Scope

<!-- Explicit boundaries from docs/upgrade-plan-desk-v2.md section 5.11 and the v3 requirements. -->

- Live trading enablement, live order placement, signing, custody, wallet funding, any real transaction, any live adapter implementation - constitution clause 1, D4 and R21 precondition 8; GOLIVE-* ships disabled, no adapter is registered, and LIV-01/LIV-02 keep live refused and recorded as deferred
- Web dashboard or UI beyond text/markdown reports - spec non-goal; `reporting/dashboard.py` is a text renderer only
- New chains, venues, launchpads, data vendors; post-graduation CPMM modelling - D8 keeps the integrations exactly as today; R8/R38 document graduation as a force-close limitation
- External historical data or new data vendors - data policy: self-recorded only (D8, AF-10)
- Paid RPC procurement or spend - no provider approved; user decision
- PumpPortal trade-stream key - default no (R45); user decision
- Multi-tenant, billing, SaaS packaging - spec non-goal; single-operator internal tool
- New alpha and new signal families. Paper parameter evaluation and bounded promotion are in scope under clause 8 as amended on 2026-10-25.
- Engagement level `micro-live` - retired by R16; levels are `research | paper` only, `live` exists solely behind the disabled gate
- Changing `~/src/repos/programming-desk/` itself - spec non-goal; it is mirrored in shape and names only, never imported or edited
- Social posting, coordinated buying, volume tooling, wallet UI automation - forbidden by D7/R39; detection only, enforced by a static test
- Telegram live verification, G-4 consumer acknowledgements, bot-06 exit roster change - human actions outside the code
- Manual-ticket exit approval path (PAPER-007) - deferred by owner decision 2026-10-23
- Coverage threshold, ed25519 confirmation signatures, Greptile as a gate, gateway OAuth - deferred (`docs/FOUNDATION_STACK.md` U-5, `docs/design/paper-engine.md` section 7.3)

## Context

**Baseline**
- v2 is shipped on main; the product line is main `f3887bb`. Milestone v3 branches from it (Key Decisions V3-3).

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
| V3-3: Branch bot-00-chief/v2-closeout from origin/main; feat/grokbot-desk-merge untouched; draft PRs only; no merge without approval | Owner decision 2026-10-25 (PRC-02) | Decided |
| V3-4: Research skipped for v3 (repo-grounded audits completed 2026-10-25). Defaults apply: D11 max 50 trials per search, D12 flag above 20 trials, D13 final 20 percent holdout; D7 divergence defaults 2 percentage points absolute return gap or 0.5 Sharpe gap | Owner approval 2026-10-25 | Decided |

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

---
*Last updated: 2026-10-25 after v3 milestone definition*

# pumpgrok Desk v2 - Upgrade Plan (phased migration plan and GSD idea document)

Tracker: SPE-18002 https://linear.app/swcstudio/issue/SPE-18002/n8-wave-ordered-execution-plan | Notion https://app.notion.com/p/3ffbc1a0c7ae8157b613fe1ff0b0bca2?pvs=204

Status: design document. Nothing in this file has been built. Every runtime claim is a
target state unless the line says "today". Repository facts cite `file:line` or the exact
command run; inferences are tagged `[INFERENCE]`.

Audience: the GSD roadmapper (`gsd-new-project --auto` synthesises `PROJECT.md`,
`REQUIREMENTS.md` and `ROADMAP.md` from sections 2, 4, 5 and 6), bot-00-chief (kickoff),
bot-02-risk (gate and contract review), the eight other seats (owned-path work), the
operator (approvals and the REVIEW list in section 8).

Shape mirrors `programming-desk/docs/upgrade-plan-desk-v2.md:1-9` (status block, decisions
table, workstreams with evidence, appendix of unverified items). The reference plan is
organised by workstream; this one is organised by phase because the GSD roadmap is
phase-shaped (`scout-programming-desk.md:224`: one `## Phase N:` per phase).

Precedence: the binding resolutions R16-R40 (section 4) override `docs/ROSTER.md`,
`docs/TOOL_CATALOG.md`, `docs/design/*.md`, `docs/MIGRATION_MAP.md` and
`docs/FOUNDATION_STACK.md` wherever they conflict. Citations into those documents below are
for evidence and line numbers; where a resolution changed the content, the resolution id
is cited next to it.

Companion documents (source of names; this plan does not restate their content):

| Document | Node | What it fixes |
|---|---|---|
| `docs/DISCOVERY.md` | n1 | what exists today, both repos, with evidence |
| `docs/MIGRATION_MAP.md` | n2 | 129 old-to-new rows, live-write quarantine, dependency drift (batch order superseded by R37) |
| `docs/ROSTER.md` | n3 | ten seats, manifests, least-privilege matrix, `ownership.yaml` draft (sizes per R35, owners per R36) |
| `docs/TOOL_CATALOG.md` | n3 | every tool (`<ns>.<verb>`, R19), schemas, side effects, roster YAML |
| `docs/design/interfaces.md` | n3 | protocols, registry, skill manifest shape (module split superseded by R31) |
| `docs/design/paper-engine.md` | n4 | PaperAdapter, ledger, replay, risk, supervisor, live gate, reports (R20-R34 amend) |
| `docs/FOUNDATION_STACK.md` | n5 | library choices, pinned versions, file drafts, canonical commands |

## 1. Summary

### 1.1 What

Turn `pumpgrok` (`/root/src/repos/pumpgrok`, branch `feat/grokbot-desk-merge`) from a
markdown instruction pack plus a vendored Russian-language dry-run engine into a Python
3.12 package `src/pumpgrok/` that runs ten LLM-assisted seats under an asyncio supervisor,
trades only through a `PaperAdapter`, records everything in an append-only SQLite ledger,
replays deterministically from recorded fixtures, and ships with the programming-desk
operating model: `ownership.yaml`, receipts, gates G-1..G-7, contracts, prompt assembly,
skills with manifests. Layout, file names and conventions copy
`/root/src/repos/programming-desk` (`docs/DISCOVERY.md` section 2).

### 1.2 Why

Today there is no runnable desk: automation is six Hermes cron prompts
(`hermes/cron/jobs.yaml:12-71`), the root tools are eight stdlib CLIs over a markdown file
bus (`tools/desk_state.py:6,51-54`), the only engine is `vendor/grokbot-pumpfun/` with no
ledger, no fee or impact model and no supervisor (`scout-vendor-engine.md:90-92`), and the
repo has no dependency manifest, lockfile or `.gitignore` (`docs/DISCOVERY.md:285-289`).
The constitution (`rules/pumpgrok-team.mdc:28-42`) is prose only; nothing enforces it in
code.

### 1.3 Non-goals (verbatim from the spec `OUT_OF_SCOPE`, xml lines 158-166)

- Enabling live trading, funding wallets, or executing any real on-chain transaction.
- Building a web dashboard/UI beyond text/markdown reports.
- Any form of coordinated promotion, social-media posting, volume generation, or other
  market-manipulation tooling.
- Rewriting strategies for alpha beyond what is needed to make existing logic run
  correctly in the new structure.
- Changing `~/src/repos/programming-desk/` itself.
- Multi-tenant / multi-user account management, billing, or SaaS packaging.
- Supporting new chains or venues not already targeted by pumpgrok, beyond abstracting
  the adapter interface.

### 1.4 Ultrathink tracker (graph `ut-mvgfr96y-be17fc96`, spec `<ISSUES>` block, xml lines 382-460)

| Node | Title | Linear | Notion | Output |
|---|---|---|---|---|
| n1 | Discover both repos as they actually are | [SPE-17995](https://linear.app/swcstudio/issue/SPE-17995/n1-discover-both-repos-as-they-actually-are) | https://app.notion.com/p/3ffbc1a0c7ae813a926ce74afa4a8a82?pvs=204 | `docs/DISCOVERY.md` |
| n2 | Old-to-new module mapping and keep/move/replace decisions | [SPE-17996](https://linear.app/swcstudio/issue/SPE-17996/n2-old-to-new-module-mapping-and-keepmovereplace-decisions) | https://app.notion.com/p/3ffbc1a0c7ae813290dfd11526829596?pvs=204 | `docs/MIGRATION_MAP.md` |
| n3 | Target bot roster, skill manifests, tool catalog, core interfaces | [SPE-17999](https://linear.app/swcstudio/issue/SPE-17999/n3-target-bot-roster-skill-manifests-tool-catalog-core-interfaces) | https://app.notion.com/p/3ffbc1a0c7ae8190b46ced6823fa3c90?pvs=204 | `docs/ROSTER.md`, `docs/TOOL_CATALOG.md`, `docs/design/interfaces.md` |
| n4 | Paper engine, ledger, replay, risk/breakers, supervisor, live gate design | [SPE-17998](https://linear.app/swcstudio/issue/SPE-17998/n4-paper-engine-ledger-replay-riskbreakers-supervisor-live-gate-design) | https://app.notion.com/p/3ffbc1a0c7ae81fd8a30fb490682c0c2?pvs=204 | `docs/design/paper-engine.md` |
| n5 | Foundation stack choices vs programming-desk precedent | [SPE-17997](https://linear.app/swcstudio/issue/SPE-17997/n5-foundation-stack-choices-vs-programming-desk-precedent) | https://app.notion.com/p/3ffbc1a0c7ae81d58f54d92ba28f167b?pvs=204 | `docs/FOUNDATION_STACK.md` |
| n6 | Missing or ambiguous information to clarify with the user | [SPE-18000](https://linear.app/swcstudio/issue/SPE-18000/n6-missing-or-ambiguous-information-to-clarify-with-the-user) | https://app.notion.com/p/3ffbc1a0c7ae81c98ce4f6ab62c508af?pvs=204 | resolved as D1-D9 and R1-R40 (section 4) |
| n7 | Safety invariants, failure modes, and how tests prove them | [SPE-18001](https://linear.app/swcstudio/issue/SPE-18001/n7-safety-invariants-failure-modes-and-how-tests-prove-them) | https://app.notion.com/p/3ffbc1a0c7ae8170b4ddc3ff4e95cd2c?pvs=204 | `docs/SAFETY_INVARIANTS.md` (this wave) |
| n8 | Wave-ordered execution plan | [SPE-18002](https://linear.app/swcstudio/issue/SPE-18002/n8-wave-ordered-execution-plan) | https://app.notion.com/p/3ffbc1a0c7ae8157b613fe1ff0b0bca2?pvs=204 | this file |

n8 steps: SPE-18058 (wave 0 docs), SPE-18056 (foundation units), SPE-18057 (restructure is
sequential), SPE-18059 (tools and skills by package), SPE-18062 (paper and autonomy),
SPE-18061 (hardening), SPE-18060 (`src/pumpgrok` path), SPE-18063 (checkpoint rule).
Wave 0 of the spec (clarify, write DISCOVERY/MIGRATION_MAP/plan/roster) is complete with
this document; the spec's eight implementation waves (xml lines 353-373) are regrouped into
the five phases of section 6 per R37, because R15 and D2 replaced the spec's seven-bot
`P/bots/<bot>/` layout with ten seats and `contracts/tool-rosters/`.

## 2. Goal and core value

Goal: modernize pumpgrok into a paper-trading-by-default, autonomously supervised Solana
memecoin trading desk whose layout, bot/skill/tool conventions, config, tests and docs
mirror programming-desk (spec `<GOAL>`, xml line 189).

Core value: the desk runs autonomously in paper mode for 2-4 weeks and produces honest,
replayable reports; no code path can move real funds.

## 3. Current state and what is kept

Current state (all from `docs/DISCOVERY.md`; re-read for this plan):

- Repo at `/root/src/repos/pumpgrok`, branch `feat/grokbot-desk-merge`, 19 commits ahead
  of `main`, working tree clean (`docs/DISCOVERY.md:22-27`). Since DISCOVERY was written
  two commits landed: `96b8fdd docs: desk-v2 discovery and design documents` and
  `644725a chore: add project config` (adds `.planning/config.json`, 105 lines) - `git log
  --oneline -3` run 2026-10-20.
- Python 3 only; no root `pyproject.toml`, lockfile or `.gitignore`; six tracked `*.pyc`
  files (`docs/DISCOVERY.md:279-289`). Vendor engine declares `requires-python >=3.11` with
  Russian comments and log strings in every module (`docs/DISCOVERY.md:282-284,291-296`).
- Eight agent files (`agents/{chief,scout,risk,whale,sniper,rug,exit,shill}.md`), only
  sniper and exit with `writes_to_exchange: true` (`docs/DISCOVERY.md:320-331`); 23 skills
  (`ls skills | wc -l` = 24 including README.md), 21 of them stubs under 1.8 KB
  (`scout-pumpgrok-pack.md:7`).
- Venues and data sources, all kept (D8): Solana mainnet JSON-RPC, Jupiter lite-api quote,
  pump.fun frontend REST, PumpPortal WebSocket, x.ai Grok (`docs/DISCOVERY.md:348-357`).
  Jito is config only, never called (`docs/DISCOVERY.md:355`) and is removed by R3.
- No executable signing or sending code exists: `LiveExecutor.buy/sell` are
  `raise NotImplementedError` bodies; `solders`/`solana` are declared but never imported
  (`docs/DISCOVERY.md:366-372`).
- Persistence is a markdown file bus under `$PUMPGROK_DESK` plus vendor `state/*.json` and
  `logs/trades.jsonl` (`docs/DISCOVERY.md:376-382`). Tests: 11 root unittest cases, 264
  vendor pytest cases (`docs/DISCOVERY.md:386-392`).

| Kept | Replaced |
|---|---|
| Security constitution block, verbatim, in every seat prompt and `rules/pumpgrok-team.mdc` (`agents/chief.md:28`, `rules/pumpgrok-team.mdc:28-42`; D9, R7) | markdown file bus `leads/ briefs/ proposals/ positions/ incidents/ watch/ journal/` -> ledger-backed views (`docs/MIGRATION_MAP.md` section 4.5) |
| Eight roles and their names, plus two new seats SIGNAL and JOURNAL (`docs/ROSTER.md` section 1; D3) | `agents/<seat>.md` as hand-written source -> generated from `prompts/bot-0N-<seat>.xml` (`docs/ROSTER.md` section 9; generated files owned by bot-00-chief, R36) |
| 23 skills, upgraded in place with `bots`/`gates` frontmatter and L1/L2 bodies (`docs/design/interfaces.md` section 3.1) | eight stdlib `tools/*.py` CLIs -> `pumpgrok` CLI verbs over catalog tools (`docs/TOOL_CATALOG.md` section 12, R40 verbs) |
| Vendor engine logic: monitor, analyzer, scoring, agents, exits, watcher, breakers, ops - ported with characterization tests (`docs/MIGRATION_MAP.md` section 3.1) | vendor `DryRunExecutor` spot-price fill -> `PaperAdapter` with curve impact, fees, latency, partial fills (R31, R38) |
| Hermes profiles and cron jobs, prompts rewritten as thin wrappers over the CLI (`docs/MIGRATION_MAP.md` section 4.3) | vendor `Config.load` YAML + `GROKBOT_*` env -> pydantic-settings TOML overlays + `PUMPGROK_*` with R30 precedence |
| Plugin manifests, license corrected to AGPL-3.0 (`docs/MIGRATION_MAP.md` section 4.4) | vendor daily-loss auto-clear at UTC rollover -> human-only clear (R5, R22) |
| `scripts/check.sh` emoji sweep (`scripts/check.sh:138-146`), rewritten in Phase 1 | engagement level `micro-live` in `ARCHITECTURE.md`, `README.md`, `SETUP.md`, two skills and `scripts/hermes-verify-isolation.sh` -> retired; levels are `research \| paper` only (R16) |
| | `vendor/grokbot-pumpfun/` directory, deleted at the end of Phase 4 when the six-item census is zero (`docs/MIGRATION_MAP.md` section 3.4; timing per R37) |

## 4. Decisions log

Fixed decisions (orchestrator-owned). Build on them; a contradiction is reported in
section 9, never resolved here.

| Id | Decision (verbatim) |
|---|---|
| D1 | Python 3.12 only; no language migration. Mirror programming-desk SHAPE and NAMES; no cross-repo imports. |
| D2 | Target skeleton (names copied from programming-desk): README.md AGENTS.md ARCHITECTURE.md SECURITY.md CHANGELOG.md ownership.yaml openapi.yaml(optional) .pre-commit-config.yaml .gitignore desk_cli.py pyproject.toml uv.lock Makefile Dockerfile docker-compose.yml .env.example; .github/workflows/{gates.yml,security-pr.yml,ci.yml}; ci/{gates/{check_ownership,check_receipt,check_secrets,check_contracts,check_rollback,check_desk_integrity,run_all}.py, hooks/, security/, tests/}; contracts/{README.md, tool-rosters/{_core,chief,scout,risk,whale,sniper,rug,exit,shill,signal,journal}.yaml, events/ (signal, safety_report, order, fill, verdict, alert schemas), changes/}; docs/ (DISCOVERY.md MIGRATION_MAP.md ROSTER.md TOOL_CATALOG.md FOUNDATION_STACK.md SAFETY_INVARIANTS.md RISK_POLICY.md quality-gates.md desk-operating-model.md cross-bot-protocol.md design/{interfaces.md,paper-engine.md} runbooks/); prompts/{_shared/core-directives.xml, bot-00-chief.xml ... bot-09-journal.xml} -> prompts-assembled/<SEAT>.xml via scripts/assemble-prompts.sh; agents/<seat>.md regenerated by scripts/generate-templates.py (host-facing; keeps today's frontmatter contract name/title/description/seat/skills/writes_to_exchange); skills/<name>/SKILL.md (frontmatter name, description, bots:[...], gates:[...]; body L1 Summary / L2 Method / Failure modes / References); existing 23 upgraded in place, new ones added; rules/pumpgrok-team.mdc kept; plugin manifests kept (license corrected to AGPL-3.0, your-org placeholders fixed); scripts/{check.sh, assemble-prompts.sh, generate-templates.py, hermes-*.sh}; src/pumpgrok/ (src layout) subpackages: config/ logging/ core/ (interfaces, registry) tools/{market,onchain,safety,exec,portfolio,risk,notify,journal}/ engine/ (ported vendor monitor/analyzer/scoring/agents) execution/ (paper adapter, disabled live stubs) ledger/ risk/ supervisor/ replay/ reporting/ cli.py; services/desk-gateway/ (thin per-seat MCP/HTTP wrapper over the in-process registry; programming-desk precedent); tests/ (pytest; tests/fixtures/replay/<dataset>/*.jsonl; tests/desk/; characterization tests for moved code); ci/tests/ gate self-tests; .receipts/<seat>/.gitkeep (JSON gitignored); var/ gitignored runtime state (ledger.sqlite, snapshots, journal, killswitch, health); hermes/ kept; cron prompts become thin wrappers over the `pumpgrok` CLI; vendor/grokbot-pumpfun/ ported into src/pumpgrok/{engine,execution,risk,ledger} with characterization tests; removed only when zero inbound refs remain. |
| D3 | Seats (ids bot-0N-<seat>; names are pumpgrok house style): bot-00-chief (LEAD/supervisor-orchestrator; never trades), bot-01-scout (discovery), bot-02-risk (risk/portfolio, kill switch; owns ci/gates, contracts, ownership.yaml, SECURITY.md = QUALITY analogue; veto absolute), bot-03-whale (holder/flow), bot-04-sniper (entry execution, paper-write), bot-05-rug (pre-trade safety/due-diligence + post-fill monitor), bot-06-exit (exit rules + exit execution, paper-write), bot-07-shill (social sentiment DETECTION only; never posts), bot-08-signal (momentum/confidence scoring; ports vendor scoring + checker), bot-09-journal (post-trade, ledger, daily/weekly reports). Trading Floor channel (6): chief, scout, risk, whale, sniper, rug; the other four are DM/off-channel seats. Only sniper and exit hold paper-write exec tools; NO seat can resolve a live-write tool. |
| D4 | Execution: config `mode` defaults to paper; PaperAdapter is the only enabled ExecutionAdapter; live adapters are disabled stubs raising LiveGateError; live gate preconditions: min_paper_days>=14, performance thresholds, PUMPGROK_LIVE_ENABLE flag, non-empty wallet allowlist, notional cap, signed human confirmation record; startup lists every unmet precondition and exits non-zero. No code path submits a real transaction. Private keys never enter the system (existing Security Constitution stays verbatim). |
| D5 | Foundation libs: pydantic v2 + pydantic-settings (TOML overlays dev/paper/live, env PUMPGROK_*), httpx (+respx fixtures), websockets, tenacity (jittered retries, failover), stdlib logging JSON formatter + contextvars correlation IDs, sqlite3 WAL ledger (append-only events + snapshots) + JSONL journal export, asyncio supervisor, prometheus_client text exposition + /healthz, ruff (lint+format), mypy --strict on src/, pytest + pytest-asyncio, pip-audit, uv + uv.lock, Dockerfile + compose, Makefile. x.ai Grok via httpx (vendor pattern); LLM failure degrades to rule-based/observe-only. |
| D6 | Risk defaults (every one marked REVIEW): paper equity 10 SOL; max 2% equity per trade; max 5% per token; 5% daily loss halt (constitution); 15% drawdown halt; liquidity floor 10x order size; partial fill above 2% of pool liquidity; breakers data-stale / loss-velocity / exec-errors with cooldowns; kill switch via env, file (var/KILLSWITCH), or alert-channel command, checked every cycle, optional flatten. Alerts: abstract Notifier, stdout+file sinks always on, Telegram + webhook adapters config-driven (hermes/profiles.yaml already has a Telegram token profile). |
| D7 | Compliance boundary: detect and trade on observed signals only; no coordinated buying, wash trades, volume generation, shilling, or social posting. Documented in docs/RISK_POLICY.md. |
| D8 | Chains/venues kept exactly as integrated today: Solana mainnet; pump.fun frontend REST + PumpPortal WS; Jupiter lite-api quote; Solana JSON-RPC (public default, env/flag override, failover list); x.ai Grok. Nothing added, nothing dropped. |
| D9 | Ticket format SOL-YYYYMMDD-NNN, exact human approval phrase, single-send rule, RISK KILL non-overridable, 5% daily-loss FLOOR HALTED remain constitutional and must be enforced in code, not only prose. |

Orchestrator resolutions of contradictions reported by the Wave 1-2 writers (binding):

| Id | Resolution (verbatim) |
|---|---|
| R1 | D5 libraries (pydantic-settings, prometheus_client, sqlite3 ledger, JSON logging, ruff, mypy) have no programming-desk precedent: adopted as documented deviations under "mirror shape and names only". FOUNDATION_STACK.md section 1 already states this. |
| R2 | pip-audit on a uv project: `uv export --format requirements-txt --no-hashes \| uv run pip-audit -r /dev/stdin` (FOUNDATION_STACK bridge). security-pr.yml trigger paths widened to pyproject.toml/uv.lock. |
| R3 | `JitoConfig` and `solana.wallet_private_key` are REMOVED (D4: private keys never enter the system; Jito is dead config, not a venue). D8 covers venues and data sources only. Recorded as MIGRATION_NOTES M-10. |
| R4 | TOML overlays live in-package: src/pumpgrok/config/overlays/{dev,paper,live}.toml; operator override via PUMPGROK_CONFIG=<file> plus PUMPGROK_* env vars. Secrets only via env. |
| R5 | Daily-loss halt (5% of start-of-day equity) is cleared by a human only (`pumpgrok state halt --clear` with approval record); no auto-clear at UTC rollover. Vendor behaviour is not carried. |
| R6 | Liquidity floor 10x and partial-fill fraction 2% stand (full fills only for size <= L/50; partial in (L/50, L/10]; rejected above L/10). All REVIEW-marked. |
| R7 | Constitutional strings keep their exact bytes (U+2013 en dash) in code constants and rules/pumpgrok-team.mdc; the ASCII rule applies to new docs only. scripts/check.sh sweeps emoji, not en dashes. |
| R8 | Bonding-curve graduation (migration event) force-closes the paper position at the last curve price with reason `graduated` and freezes MTM; post-graduation venues are not modelled (D8). Documented limitation. |
| R9 | Reports render with str.format (no templating dependency). |
| R10 | Tool names are dotted `<ns>.<verb>` everywhere (catalog, roster YAML `name`, registry). Ported check_desk_integrity: TOOL_NAME_RE allows dots, SEAT_RE = ^bot-0[0-9]-[a-z-]+$, roster size 8-15; check_receipt and gates.yml seat regexes widened to 10 seats in the same change. |
| R11 | RISK stays in the Trading Floor channel (veto visibility is a domain requirement); reviewer independence rests on G-2 approved_by != author and RISK's absolute veto. |
| R12 | Extra CLI verbs accepted: `pumpgrok live confirm`, `pumpgrok replay trim\|rebuild-ticks`. |
| R13 | requires-python >= 3.12 (D1); vendor's 3.11 floor is not carried. |
| R14 | Jupiter v6 references in skills/docs are rewritten to lite-api during Restructure; `--max-micro` is dropped from docs; tools/README gains desk_state.py. |
| R15 | Seven-bot roster in the ultrathink spec is superseded by D3 (ten seats); sniper/exit are the only paper-write seats. |

Orchestrator resolutions after the three adversarial reviews of the Wave 2 documents
(binding; override the design documents where they conflict; `local://resolutions-R16-R40.md`):

| Id | Resolution (verbatim) |
|---|---|
| R16 | Engagement levels are `research \| paper` only. `live` exists solely as a config mode behind the live gate and is disabled. `micro-live` is retired everywhere (ARCHITECTURE.md, README.md, SETUP.md, skills/desk-operating-model, skills/pumpgrok-setup, scripts/hermes-verify-isolation.sh get rewritten in the Restructure phase). MIGRATION_MAP gains an "engagement level" row and a markdown-prose quarantine table (the earlier search wrongly excluded *.md instruction surfaces). |
| R17 | Exit automation: in paper mode the EXIT seat's rule engine is the autonomous paper-write path. Under autonomy_level=autonomous-paper it is always on; under manual-ticket an exit rule must be approved per ticket (ApprovalRecord kind exit_rule). "Auto-exit pre-authorised in writing" prose is replaced by this. No live auto-exit exists (LiveGateError). |
| R18 | skills/jupiter-routing becomes quote/route preparation feeding exec.quote and exec.place (paper). The single-send rule is implemented as PaperAdapter idempotency (R23). Row marked quarantine: paper-write procedure. |
| R19 | Tool identifiers are dotted `<ns>.<verb>` and nothing else: catalog, roster YAML `name`, registry, tests, ownership. The MCP/gateway transport name is the same id with `.` replaced by `_`, derived at exposure time, never stored or documented as an alias. Ported G-7 TOOL_NAME_RE = ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$ ; SEAT_RE = ^bot-0[0-9]-[a-z-]+$ ; roster size 8..15 inclusive (ROSTER_MIN_TOOLS = 8). |
| R20 | Risk budget keys and units (fractions of equity, 0..1) - the ONLY schema: max_trade_fraction=0.02, max_token_fraction=0.05, daily_loss_halt_fraction=0.05, drawdown_halt_fraction=0.15, max_open_positions=3, max_trades_per_day=20, liquidity_floor_multiple=10, partial_fill_fraction=0.02, paper_equity_sol=10. Same keys in RiskBudget (interfaces), per-seat risk_budget (ROSTER), TOML [risk] block, risk.check_limits output. All REVIEW-marked. |
| R21 | Live gate - the ONE precondition list (9): (1) effective execution.mode == live (R30 precedence); (2) env PUMPGROK_LIVE_ENABLE=1; (3) live.min_paper_days >= 14 elapsed, measured ONLY on ledger events with source=paper (never replay); (4) performance thresholds on the same source=paper events: closed_trades >= 50, profit_factor >= 1.2, max_drawdown <= drawdown_halt_fraction; (5) live.wallet_allowlist non-empty (public addresses only); (6) 0 < live.notional_cap_sol <= 1.0; (7) live.confirmation_record = HMAC-signed human confirmation produced by `pumpgrok live confirm` with an operator secret that no seat/tool can read, bound to the config hash; (8) live.adapter explicitly named AND an implementation registered (none ships -> always unmet); (9) no active kill switch, halt, or open breaker. Any unmet -> startup exits 3 printing every unmet item. Replay runs write var/replay/<dataset>/ledger.sqlite; every ledger event carries `source` in {paper, replay, manual}; LiveGate refuses any ledger containing source=replay for its metrics. |
| R22 | Kill switch: tool risk.kill_switch supports actions set and flatten_request only. clear is CLI-only (`pumpgrok killswitch clear --by <human> --reason <text>`) and appends KillSwitchCleared with an ApprovalRecord kind killswitch_clear. Halts are human-clear only (`pumpgrok state halt --clear --by --reason`, kind halt_clear). Kill switch, halts, breakers and risk limits are re-checked at CONFIRMING (immediately before a fill); in-flight orders are rejected with reason kill_switch/halted/breaker_open. flatten waits on an in-flight barrier, then closes every open position (reason kill_flatten). Env source PUMPGROK_KILLSWITCH is read at start only; file var/KILLSWITCH and the alert-channel command are live sources polled every cycle. |
| R23 | Idempotency: exec.place key = (ticket_id, side, decision_id); decision_id is a ULID minted per decision. Approval consumption is persisted as an ApprovalRecorded/consumed update inside the same ledger transaction as the order. |
| R24 | RISK seat observe-only: RiskEngine.check is library code executed inside PaperAdapter.place for every order regardless of seat health and owns HaltSet/BreakerTripped appends (idempotent per reason+utc_day). The RISK seat monitors, alerts and sets the kill switch. If bot-02-risk is observe-only after restart exhaustion, the desk enters observe-only for BUYS (no new entries) while exits continue. |
| R25 | Blind exit policy: after blind_max_s=300 without a price, EXIT force-closes at last_good (conservative MTM) with reason blind_flatten and escalates. Missing data never leaves a position unprotected. |
| R26 | Single writer: every ledger append (supervisor or CLI process) goes through ledger/store.py using BEGIN IMMEDIATE; the hash chain (prev_hash, seq) is computed inside that transaction. No supervisor IPC is required. desk.md and other markdown exports are written via tmp file + os.replace. |
| R27 | Virtual time: all sleeps, timeouts and retry waits go through the Clock (clock.sleep, clock.timeout, tenacity sleep=clock.sleep). Direct asyncio.timeout/asyncio.sleep/time.time in src/pumpgrok is forbidden (static test). LLM recorder stores canonical_request_hash (prompt without timestamps/ids), outcome in {ok, timeout, error}, virtual latency_s, and response; replay returns the recorded outcome and a missing record FAILS the replay (no silent rule fallback). Recorder stamps its clock's ts into fixtures; replay ledger ts comes from the fixture. |
| R28 | Money types: integers in base units (lamports: int; token base units: int) in all core models, tool schemas and ledger payloads; Decimal only for derived ratios; no float money anywhere. Hash chain over canonical JSON (sorted keys, ints/strings). |
| R29 | IDs: ULIDs from src/pumpgrok/core/ids.py (clock + seeded rng) for correlation_id, decision_id, order_id, event ids. The uuid module is banned in src/pumpgrok (static test). CorrelationId format = ULID; child spans = `<ulid>.<n>`. |
| R30 | Config precedence: effective mode = CLI --mode > env PUMPGROK_MODE > TOML execution.mode. Overlays live in-package at src/pumpgrok/config/overlays/{dev,paper,live}.toml selected by PUMPGROK_PROFILE (default paper); optional PUMPGROK_CONFIG=<file> is applied last as an operator overlay. The live gate evaluates the merged effective mode. There is no config/ directory at the repo root. |
| R31 | Module placement (single truth): src/pumpgrok/execution/paper_adapter.py (PaperAdapter), execution/curve_math.py, execution/fees.py, execution/latency.py; src/pumpgrok/execution/live/live_adapter.py (stub) and execution/live/live_gate.py, owned by bot-02-risk via an ownership rule placed AFTER src/pumpgrok/execution/**; src/pumpgrok/risk/engine.py (RiskEngine), risk/limits.py, risk/sizing.py, risk/breakers.py, risk/killswitch.py; src/pumpgrok/engine/exits.py (ExitSignal, exit rules; owned by bot-06-exit) and engine/watcher.py (PositionWatcher; owned by bot-05-rug); src/pumpgrok/tools/onchain/rpc.py (shared RPC client); tools/onchain/authorities.py; tools/social/ is an approved D2 addition (bot-07-shill, read-only); src/pumpgrok/ledger/{store,events,reducer,views,reconcile}.py; src/pumpgrok/replay/{clock,rng,fixtures,sources,recorder,runner}.py; src/pumpgrok/supervisor/{scheduler,seat_task,health}.py; src/pumpgrok/core/{interfaces,registry,ids,approvals}.py. The class is RiskEngine (not RiskManager). |
| R32 | Ledger schema and events: events(seq, ts_utc, source, correlation_id, idempotency_key, type, payload_json, prev_hash, hash) + snapshots(seq, ts_utc, state_json). Event types are CamelCase, defined once in ledger/events.py: OrderPlaced, OrderRejected, FillRecorded, PositionOpened, PositionClosed, MarkToMarket, HaltSet, HaltCleared, KillSwitchSet, KillSwitchCleared, BreakerTripped, BreakerReset, DailyRollover, ConfigChanged, LiveWriteAttempted, Escalation, JournalNote, ApprovalRecorded. PositionClosed.reason in {stop_loss, take_profit, trailing_stop, max_hold, rug_alert, kill_flatten, blind_flatten, graduated, manual}. desk.event_emit and journal.append `kind` use the snake_case form of the same type (order_placed, ...), generated from the registry; contracts/events/<snake>.schema.json carries one JSON Schema per type. No third vocabulary. |
| R33 | Approval kinds: human_buy, human_sell, exit_rule, autonomous_paper, killswitch_clear, halt_clear, live_gate. ApprovalRecord is persisted in the ledger (ApprovalRecorded), not as a JournalNote. |
| R34 | risk.check_limits rule ids = the RiskEngine step ids, one vocabulary: ledger_inconsistent, kill_switch, halted, breaker_open, live_gate, approval_missing, approval_mismatch, seat_may_trade, max_trades_per_day, max_open_positions, already_open, creator_already_open, max_trade_fraction, max_token_fraction, daily_loss_halt, drawdown_halt, data_stale, size_too_small, below_liquidity_floor. |
| R35 | Roster sizes 8..15 including the core eight. RISK = core 8 + portfolio.{ledger_read,exposure,pnl} + risk.{check_limits,drawdown,kill_switch,halt_status} = 15. RUG = core 8 + safety.score_report + onchain.{token_metadata,authorities,lp_status,top_holders} + market.{price,liquidity} = 15. onchain.{deployer_history,large_transfers} move to WHALE. SCOUT's grant of onchain.authorities is kept and the matrix cell added. Recount every seat and the matrix. |
| R36 | Ownership: every tracked path resolves to exactly one owner (a G-1 self-test walks `git ls-files`). skills/desk-post-trade-review/** -> bot-09-journal (EXIT is a consumer). src/pumpgrok/core/**, replay/**, ledger/**, config/**, logging/** -> bot-02-risk (infrastructure owner). Characterization tests follow the owner of the module they pin. Generated files agents/*.md and prompts-assembled/* -> bot-00-chief. rules/pumpgrok-team.mdc, SECURITY.md, ownership.yaml, ci/** , contracts/** -> bot-02-risk. The rule for src/pumpgrok/execution/live/** comes after src/pumpgrok/execution/**. |
| R37 | Batches re-cut so every checkpoint is buildable and the CHECKPOINT_RULE holds from batch 1 (no waiver): batch 1 (Phase 1 Foundation) = pyproject/toolchain, config (overlays, precedence, live-gate validation), logging + ids, core interfaces + registry, ledger store skeleton (schema, append, hash chain), replay clock/rng/fixture loader, CLI skeleton where `pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` executes a skip-only cycle (fixture events read, no engine, one JournalNote appended) and `pumpgrok doctor` reports present subsystems and marks absent ones `not-yet-implemented` (warning until the owning phase lands, then failing). batch 2 (Phase 2 Restructure) = tools + RPC client + recorded fixtures + engine port (monitor/analyzer/scoring/agents, English strings) + exits/watcher + instruction-pack regeneration. batch 3 (Phase 3 Tools & Skills) = complete tool catalog, registry least-privilege enforcement, skills, gateway, rosters. batch 4 (Phase 4 Paper & Autonomy) = PaperAdapter, RiskEngine, ledger reducer/views/reconcile, supervisor, reporting, live gate. batch 5 (Phase 5 Hardening) = metrics/spans, runbooks, fault injection, soak, security CI. Every module named in paper-engine.md and interfaces.md appears in exactly one batch. |
| R38 | Quote source: one per fill. Pre-graduation BUY and SELL fills are computed from the bonding-curve reserves; the Jupiter quote is informational (route, priority) and never the fill price. A BUY on a graduated token is rejected post_graduation_no_reserves; an OPEN position whose token graduates is force-closed per R8 (reason graduated, MTM frozen). The partial-fill slippage threshold is recomputed for the executed size. Day attribution of PnL uses the fill timestamp. |
| R39 | notify.alert destinations are restricted to a configured allowlist (Telegram chat ids, webhook URLs); notify.* is inside the no-manipulation static test scope (no public social posting). skills/browser-ops is detection/research only and listed in the forbidden-actions test scope (no posting, no wallet UI). |
| R40 | Misc: requires-python ">=3.12,<3.13" (R13 amended). Weekly report Monday 00:15Z; daily 00:05Z. Signal kind literal is `signal`. alert kind enum includes escalation kinds (bot_restart_exhausted, heartbeat_stale, persistence_down, clock_skew, ledger_inconsistent). Drop all "--max-micro" phrasing (field max_micro_lamports stays). Registry invariants are labelled I1-I5 (never R-numbers). `pumpgrok paper buy\|sell --ticket --mint --size-sol --slippage-bps --approval-id`. Canonical CLI list adds: `live confirm`, `replay trim\|rebuild-ticks`, `run --record <dataset> --duration <s>`, `verify --fixture <dataset>`, `state halt --clear --by --reason`, `state autonomy <manual-ticket\|autonomous-paper>`. Key-custody wording: "no key material exists in paper mode; nothing to custody". Citation line numbers corrected to the real files. |
| R41 | `paper_started_at` = `ts_utc` of the first `source=paper` event in `var/ledger.sqlite`; the 14-day window (R21 precondition 3) is measured from it. |
| R42 | `rules/pumpgrok-team.mdc` is updated in the Restructure phase: the micro-live clause (line 46) becomes "live mode exists only behind the live gate (docs/RISK_POLICY.md) and is disabled"; every other constitutional clause keeps its exact bytes (R7). "Kept" in D2 means not deleted, not frozen. |
| R43 | Vendor `ops.py` split homes (single truth, batch 2): `RateLimiter` -> `src/pumpgrok/core/ratelimit.py`; `CallBudget` -> `core/budget.py`; `GrokOps` precheck + x.ai client + LLM recorder -> `core/llm.py`; `CircuitBreaker` base -> `risk/breakers.py`; `drain`/`install_signal_handlers`/`cancel_and_wait`/`Heartbeat` -> `supervisor/lifecycle.py`; metrics/health rewrite -> `supervisor/metrics.py`, `supervisor/health.py` (metrics in batch 5). There is no `engine/ops.py` or `engine/llm.py`. |
| R44 | Jupiter quote adapter (venue kept, endpoint replaced): targets `GET https://api.jup.ag/swap/v2/order` without `taker` (quote only). It never calls `/execute`, `/build`, `/submit`, or any order with `taker`. The optional key comes from env `JUPITER_API_KEY` as header `x-api-key` (SecretStr). Keyless use is 0.5 RPS, so the `jupiter` rate-limit key runs at concurrency 1 with quote TTL cache, and autonomous-paper startup logs a WARNING when the key is absent. `lite-api.jup.ag/swap/v1` is removed, not kept behind a flag (Metis V1 is no longer maintained; Jupiter Developer Platform migration). Evidence: .planning/research/STACK.md V-8 and Jupiter section (observed live 2026-10-21). |
| R45 | PumpPortal scope: free methods only, `subscribeNewToken` and `subscribeMigration`, on `wss://pumpportal.fun/api/data` with no api-key parameter. `subscribeTokenTrade` and `subscribeAccountTrade` are never sent. Since 2026-05-01 they require an API key linked to a wallet funded with at least 0.02 SOL (refusal observed live 2026-10-21), and the PumpPortal FAQ states the key contains the wallet private key encrypted with AES-256. D4 forbids key material in the system, so the desk never reads, stores, or requests such a key. Enabling it is a user decision (see R49 open decisions). |
| R46 | Trade-event source (replaces PumpPortal trade subscriptions): Solana JSON-RPC only. `logsSubscribe` with `mentions` on the bonding-curve PDA of candidate mints, followed by bounded `getTransaction` decoding for buy and sell events. Concurrency is capped by `signal.max_watched_mints` (REVIEW default 20), with an endpoint failover list in config. Trade-derived fields (unique buyers, trade velocity, whale flow) are `data_unavailable` until this source is live; signal and sniper gates fail closed on missing trade evidence (constitution: missing data = KILL). ASSUMPTION to verify with a live probe in Tools & Skills: `logsSubscribe` works on the configured RPC plan. Price and curve progress come from bonding-curve account reads (`getAccountInfo`) at the position-watch cadence, decoded with Decimal and integer base units (R28). |
| R47 | pump.fun frontend REST is degradable only. v1 `frontend-api.pump.fun` returned HTTP 530 with Cloudflare error 1016 on every path during the 2026-10-21 probe. Holders come from RPC `getTokenLargestAccounts` through the paid provider list (public RPC fails holder queries). The unofficial v3 top-holders endpoint is an optional secondary only. Every pump.fun source reports health; DataStale applies per source. No entry decision may depend solely on a pump.fun response. |
| R48 | x.ai model identifiers are config values, never hard-coded: strong (checker, scoring) `grok-4.3` with reasoning effort `low`; fast (narrative, timing) `grok-4.20-0309-non-reasoning`. `grok-4`, `grok-4-fast`, `grok-4-1-fast*` are retired (xAI notice, effective 2026-05-15, redirects to grok-4.3 are not relied on). At startup the configured IDs are resolved against `GET /v1/models`, and the resolved ID is recorded in the ledger for replay. Base URL convention: `https://api.x.ai/v1` (SDK base), never a full endpoint path. Evidence: .planning/research/STACK.md V-10 and x.ai section. |
| R49 | Accepted STACK.md corrections (.planning/research/STACK.md verdict table): V-1 pydantic-settings `>=2.16.1,<3`; V-2 uv 0.13.4 with `uv_build>=0.13.4,<0.14.0`; V-3 committed `.python-version` = `3.12`; V-4 `uv export --no-emit-project` before pip-audit; V-5 drop the prometheus_client and respx mypy overrides (both ship py.typed); V-6 keep httpx 0.28.1 and record maintenance risk; V-7 websockets `proxy=None` and explicit `max_queue` on every connection; V-9 pytest-asyncio settings with explicit `asyncio_default_fixture_loop_scope`. V-8, V-10, V-11, V-12 are superseded by R44, R48, R45, R47. OPEN USER DECISION (non-blocking, default applied): whether to enable a funded PumpPortal key for trade streams. Default is no (R45); the user may override in writing, which adds an approval record and a separate threat-model note. |

## 5. Requirement families

Each requirement is one testable sentence. Ids are stable; the roadmapper copies them into
`REQUIREMENTS.md` as `- [ ] **<ID>**: <text>` and each id lands in exactly one phase
(section 6.7 is the coverage table). "The desk" means the `pumpgrok` process; "Operator"
means a human at the CLI. Numeric defaults carry REVIEW where D6/R20 say so.

### 5.1 FOUND - packaging, toolchain, config, interfaces, desk skeleton

| Id | Requirement |
|---|---|
| FOUND-001 | The desk is a `uv_build` src-layout package with `pyproject.toml` (`requires-python = ">=3.12,<3.13"`, R40) and a committed `uv.lock`; `uv sync --frozen` succeeds on a clean checkout with the pins of `docs/FOUNDATION_STACK.md` section 2. |
| FOUND-002 | Operator can run `make lint typecheck test audit` and each target executes the canonical command of `docs/FOUNDATION_STACK.md` section 6 (ruff check, ruff format --check, mypy --strict src/, pytest -q, pip-audit over the `uv export` bridge of R2) with exit 0. |
| FOUND-003 | `docker compose up pumpgrok` builds the multi-stage non-root image and starts the desk with effective mode `paper`; the compose healthcheck passes (`pumpgrok doctor` until `/healthz` lands in AUTO-004). |
| FOUND-004 | The desk loads settings through pydantic-settings with the R30 precedence (CLI `--mode` > env `PUMPGROK_MODE` > TOML `execution.mode`), overlays `src/pumpgrok/config/overlays/{dev,paper,live}.toml` selected by `PUMPGROK_PROFILE` (default `paper`), `PUMPGROK_CONFIG=<file>` applied last, `PUMPGROK_*` env with `__` nesting; with no overrides the effective mode is `paper`, there is no root `config/` directory, and startup refuses any forbidden key name (`PRIVATE_KEY`, `SECRET_KEY`, `SEED`, `MNEMONIC`, `WALLET_PRIVATE_KEY`; `hermes/profiles.yaml:18-22` carried into the loader). |
| FOUND-005 | `src/pumpgrok/core/{interfaces,registry,ids,approvals}.py` (R31) define `SideEffect`, the error classes, `Tool`/`ToolSpec`, `DataSource`, `ExecutionAdapter`, `SkillManifest`, `BotManifest`/`RiskBudget` (keys of R20), `ApprovalRecord` (kinds of R33), `ToolRegistry`/`GrantAudit` with invariants labelled I1-I5 (R40); `ToolRegistry.find` raises `LiveGateError` for any `LIVE_WRITE` spec regardless of caller; ULIDs come only from `core/ids.py` and `uuid` is banned in `src/pumpgrok` by a static test (R29). |
| FOUND-006 | `ownership.yaml` declares the ten seats of D3 and owns every tracked path per R36 (`core/ replay/ ledger/ config/ logging/` -> bot-02-risk; generated `agents/*.md` and `prompts-assembled/*` -> bot-00-chief; `src/pumpgrok/execution/live/**` rule after `src/pumpgrok/execution/**`); `python3 ci/gates/check_ownership.py --validate-manifest` exits 0 and a G-1 self-test walking `git ls-files` finds no UNOWNED path. |
| FOUND-007 | `ci/gates/{check_ownership,check_receipt,check_secrets,check_contracts,check_rollback,check_desk_integrity,run_all}.py` are ported with the retargeted constants of `docs/FOUNDATION_STACK.md` section 4 and R19 (`TOOL_NAME_RE = ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`, `SEAT_RE = ^bot-0[0-9]-[a-z-]+$`, `ROSTER_MIN_TOOLS = 8`, max 15, Solana/RPC/Telegram secret shapes, trading DEPLOY/DESTRUCTIVE patterns); `python3 -m pytest ci/tests/ -q` passes; `.receipts/<seat>/.gitkeep` exists for all ten seats with JSON gitignored; `.gitignore` ignores `var/`, `.venv/`, `*.pyc`; `.pre-commit-config.yaml` runs G-3 `--staged`, the manifest check and the gate self-test as local hooks. |
| FOUND-008 | `contracts/` holds `README.md`, `tool-rosters/_core.yaml` (desk core eight) plus ten seat rosters whose tool names are exactly those of `docs/TOOL_CATALOG.md` with the R35 sizes, one JSON Schema per ledger event type `contracts/events/<snake>.schema.json` for the eighteen R32 types (`order_placed` .. `approval_recorded`, generated from `ledger/events.py`, no third vocabulary; seat messages LEAD/whale/social/signal/verdict/safety_report are `JournalNote` payloads discriminated by `note_kind`, RUG alerts are `Escalation` payloads), and `changes/`; `python3 ci/gates/check_desk_integrity.py --repo .` exits 0. |
| FOUND-009 | `prompts/_shared/core-directives.xml` (audiences `trading-seats \| chief \| risk`) and ten `prompts/bot-0N-<seat>.xml` sources assemble via `bash scripts/assemble-prompts.sh --check` into `prompts-assembled/<SEAT>.xml` with no `{{...}}` left, and `python3 scripts/generate-templates.py --check` regenerates `agents/<seat>.md` preserving the frontmatter keys `name,title,description,seat,skills,writes_to_exchange` (`agents/chief.md:1-17`) so `./scripts/check.sh` keeps passing. |
| FOUND-010 | `.github/workflows/{gates.yml,security-pr.yml,ci.yml}` exist; `gates.yml` derives the acting bot from the branch prefix with the ten-seat regex, overlays `ci/gates/` from the base ref, selects the receipt added under `.receipts/$BOT/`, and runs G-1..G-7 plus the `gate-self-test` job; `ci.yml` runs the canonical commands; `security-pr.yml` triggers on `pyproject.toml`/`uv.lock` changes (R2). |
| FOUND-011 | `AGENTS.md`, `SECURITY.md` (key-custody wording "no key material exists in paper mode; nothing to custody", R40), `CHANGELOG.md`, `docs/quality-gates.md`, `docs/desk-operating-model.md` and `docs/cross-bot-protocol.md` exist in programming-desk shape, name the ten seats, engagement levels `research \| paper` (R16) and G-1..G-7, and pass `./scripts/check.sh` (no emoji). |
| FOUND-012 | `tests/conftest.py` blocks all network (an `httpx` transport that raises on un-mocked requests plus a `websockets` connect monkeypatch, `docs/design/paper-engine.md` section 9); `src/pumpgrok/replay/{clock,rng,fixtures}.py` provide the `Clock` protocol with `WallClock`/`FixtureClock`, the single seeded RNG constructor and the fixture loader; `tests/harness/faults.py` provides `FaultInjector` (modes stale, timeout, rate_limit, raise, unwritable); a static test fails on any direct `asyncio.sleep`, `asyncio.timeout` or `time.time` in `src/pumpgrok` (R27). |
| FOUND-013 | `src/pumpgrok/ledger/{store,events}.py` implement the R32 schema (`events(seq, ts_utc, source, correlation_id, idempotency_key, type, payload_json, prev_hash, hash)`, `snapshots`), `BEGIN IMMEDIATE` single-writer appends with the hash chain computed inside the transaction over canonical JSON (R26, R28) and the eighteen CamelCase event models; `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` executes a skip-only cycle (fixture events read, no engine, one `JournalNote` appended, `source=replay`, ledger at `var/replay/smoke/ledger.sqlite`) and exits 0; `uv run pumpgrok doctor` reports present subsystems and marks absent ones `not-yet-implemented` as warnings until their owning phase lands, then as failures (R37). |

### 5.2 STRUCT - restructure, port, retire

| Id | Requirement |
|---|---|
| STRUCT-001 | Tracked `*.pyc` (`docs/DISCOVERY.md:287-289`) and `issues/tissue.json` are removed, `scripts/check.sh` is rewritten without vendor paths and with the `your-org` placeholder check, and `docs/VENDOR_PIN.md` records the vendor commit `409e74c` (`docs/MIGRATION_MAP.md` section 7 batch 1). |
| STRUCT-002 | `tools/{jupiter_quote,authority_check,holder_check,priority_fee}.py` are re-implemented as `src/pumpgrok/tools/{market/jupiter.py,onchain/authorities.py,onchain/holders.py,onchain/priority_fee.py}` (R31) over the single RPC client `src/pumpgrok/tools/onchain/rpc.py` (httpx + tenacity with `sleep=clock.sleep` + ordered failover, D8, R27), with `tests/characterization/test_{authority_check,holder_check,jupiter_quote,priority_fee}.py` reproducing the 11 root unittest cases against recorded fixtures in `tests/fixtures/replay/smoke/` and `tests/fixtures/http/`. |
| STRUCT-003 | Vendor `monitor, analyzer, scoring, reputation, agents/*, tune` are ported to `src/pumpgrok/engine/` and vendor `risk.py` exit rules and `PositionWatcher` to `src/pumpgrok/engine/{exits,watcher}.py` (R31) with every Russian string translated and reason codes unchanged; the 1:1 characterization tests for these modules are green while `cd vendor/grokbot-pumpfun && python3 -m pytest -q` still passes as the oracle; `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` prints one `skip` or `buy` decision from the engine. |
| STRUCT-004 | Vendor `executor, risk (RiskManager -> RiskEngine), ops, state, log` are ported into `src/pumpgrok/{execution,risk,supervisor,ledger}/` using the R31 module names with adapted characterization tests, bringing `tests/characterization/` to all 13 vendor modules with at least 164 1:1 tests (`docs/MIGRATION_MAP.md` section 3.1); the vendor daily-loss auto-clear (`risk.py:106-117`) is intentionally not ported (R5) and its test is marked as such; ported tests assert reason codes, never free text. |
| STRUCT-005 | `cli.py` exposes every verb of `docs/DISCOVERY.md:11-16` plus R12 and R40 (`live confirm`, `replay trim\|rebuild-ticks`, `run --record <dataset> --duration <s>`, `verify --fixture <dataset>`, `state halt --clear --by --reason`, `state autonomy <manual-ticket\|autonomous-paper>`, `paper buy\|sell --ticket --mint --size-sol --slippage-bps --approval-id`), verbs whose subsystem is absent return `not-yet-implemented`; the six Hermes cron prompts wrap `pumpgrok` subcommands only (`docs/MIGRATION_MAP.md` section 4.3), `jobs.yaml` `forbidden_owners: [sniper, exit]` is also enforced by the CLI; `scripts/hermes-*.sh` are rewritten for `PUMPGROK_*` env and `micro-live` is retired from `ARCHITECTURE.md`, `README.md`, `SETUP.md`, `skills/desk-operating-model`, `skills/pumpgrok-setup` and `scripts/hermes-verify-isolation.sh` (R16); `docs/MIGRATION_MAP.md` gains the engagement-level row and the markdown-prose quarantine table (R16). |
| STRUCT-006 | `vendor/grokbot-pumpfun/` is deleted only when all six retirement checks of `docs/MIGRATION_MAP.md` section 3.4 hold (`rg -l -F "vendor/grokbot-pumpfun" . --glob '!vendor/**'` empty, `409e74c` cited only by `docs/VENDOR_PIN.md`, `src/pumpgrok/engine/LICENSE-grokbot-pumpfun` present, all 13 characterization modules green, `check.sh` no longer excludes `vendor/`). |
| STRUCT-007 | All 23 existing skills gain `bots: [...]` and `gates: [...]` frontmatter and the `L1 - Summary / L2 - Method / Failure modes / References` body (`docs/design/interfaces.md` section 3); `skills/jupiter-routing` becomes quote/route preparation feeding `exec.quote` and `exec.place` (R18); `skills/browser-ops` is detection/research only (R39); every Jupiter v6 reference becomes lite-api and `--max-micro` phrasing is removed (R14, R40); `tools/README.md` lists `desk_state.py` until `tools/` is deleted; the four plugin manifests say `"license": "AGPL-3.0"` and no `your-org` placeholder remains; `README.md`, `ARCHITECTURE.md` and `docs/runbooks/setup.md` describe `src/pumpgrok/`. |
| STRUCT-008 | `JitoConfig` and `solana.wallet_private_key` do not exist in the settings model (R3), recorded as `docs/FOUNDATION_STACK.md` MIGRATION_NOTES M-10; `solders` and `solana` are not declared in `pyproject.toml`. |

### 5.3 TOOL - the tool layer (names from `docs/TOOL_CATALOG.md`, R19)

| Id | Requirement |
|---|---|
| TOOL-001 | `market.{price,ohlcv,liquidity,trades,holders_snapshot}` (`docs/TOOL_CATALOG.md` section 1) return typed outputs carrying `freshness` and `source` fields and pass tests on recorded respx fixtures with no live network. |
| TOOL-002 | `onchain.{token_metadata,authorities,lp_status,top_holders,deployer_history,large_transfers,priority_fee}` (section 2) go through the single RPC client `src/pumpgrok/tools/onchain/rpc.py` with tenacity jittered retries and ordered failover over `rpc.endpoints[]`; the API key travels in `solana.rpc_api_key`, never inside a URL or a log line; `deployer_history` and `large_transfers` are WHALE grants (R35). |
| TOOL-003 | `safety.score_report` (section 3) produces a scored report with per-check reasons and thresholds read from config; a check without data returns `BLIND`, never an exception. |
| TOOL-004 | `exec.{quote,simulate,place,cancel,positions}` (section 4) call the configured `ExecutionAdapter`; `exec.place` and `exec.cancel` carry `g6` and require `approval_id`; `exec.place` input carries `decision_id` (a ULID minted per decision) and the idempotency key is derived by the tool from `(ticket_id, side, decision_id)`, never caller-supplied; approval consumption is written in the same ledger transaction as the order (R23); `exec.simulate` writes no ledger event. |
| TOOL-005 | `portfolio.{ledger_read,ledger_write,exposure,pnl}`, `risk.{check_limits,drawdown,kill_switch,halt_status}` and `journal.{append,render_report}` (sections 5, 6, 8) exist with the catalog schemas; `risk.check_limits` reports the R34 rule ids; `risk.kill_switch` accepts only `set` and `flatten_request` (R22); `journal.append` and `desk.event_emit` `kind` is the snake_case form of an R32 event type and seats may write only `journal_note` and `escalation` (every other type is appended by the engine, risk, adapter or supervisor); `portfolio.ledger_write` is `PermissionDenied` for all ten seats (`docs/design/interfaces.md` section 4). |
| TOOL-006 | `notify.alert` (section 7) dispatches through an abstract `Notifier` whose stdout and file sinks are always on and whose Telegram and webhook sinks are enabled only by config and send only to a configured allowlist of chat ids and URLs (R39); RISK and RUG rosters do not carry `notify.alert` (R35) and escalate via `desk.event_emit kind=escalation`, which the supervisor relays to `notify.alert`; the alert `kind` enum includes the escalation kinds `bot_restart_exhausted, heartbeat_stale, persistence_down, clock_skew, ledger_inconsistent` (R40); sends are rate limited and idempotent. |
| TOOL-007 | The desk core eight `desk.{brief,docs_search,memory_retain,memory_recall,ownership_resolve,receipt_check,event_emit,doctor}` (section 9) are resolvable by every seat, `desk.event_emit` `kind` follows R32 snake_case, and `desk.doctor check` is the same code path as `pumpgrok doctor`. |
| TOOL-008 | Every registered tool has a pydantic v2 input and output model (`additionalProperties: false`), a `side_effect` in `{read, paper-write}`, `timeout_s`, a `RetryPolicy` and a `rate_limit_key`; money fields are integers in base units named `<x>_lamports: int` and `<x>_units: int` (token base units), prices and ratios are `Decimal` strings, no float money anywhere, and only the CLI boundary accepts `--size-sol` (R28); untrusted upstream payloads (pump.fun, PumpPortal, Jupiter, RPC, x.ai) are parsed with `extra="ignore"` models and a malformed payload yields a typed error (`DataStale`/`BLIND`), never an escaping exception. |
| TOOL-009 | The least-privilege tests of `docs/design/interfaces.md` section 4 pass: no seat resolves a live-write tool, only sniper and exit resolve `exec.place`, exit cannot place a BUY, chief has no exposure tools, shill's only write is `journal.append`, every roster name exists in the registry, and `tools/social/` (bot-07-shill, R31) issues GET only. |
| TOOL-010 | `services/desk-gateway/` serves `/mcp/<seat>` from the in-process registry so that `tools/list` equals `contracts/tool-rosters/<seat>.yaml` plus `_core.yaml`, transport names are the dotted ids with `.` replaced by `_` derived at exposure time and never stored (R19), and a token for seat A on `/mcp/<seat B>` is 403. |
| TOOL-011 | Operator can run every verb of `docs/TOOL_CATALOG.md` section 12 plus the R12 and R40 additions; each verb is a thin wrapper over catalog tools and prints JSON by default; `pumpgrok paper buy\|sell` requires `--ticket --mint --size-sol --slippage-bps --approval-id`. |

### 5.4 SKILL - skills, manifests, least privilege

| Id | Requirement |
|---|---|
| SKILL-001 | The twelve new skills of `docs/design/interfaces.md` section 3.2 exist (35 skills total) with frontmatter `name, description, bots, gates, required_tools, permissions.max_side_effect` and the L1/L2 body; `skills/desk-post-trade-review/**` is owned by bot-09-journal (R36). |
| SKILL-002 | `tests/test_skill_manifests.py` passes: every `skills/*/SKILL.md` parses into `SkillManifest`, `name == dirname`, every `required_tools` entry is granted to every listed bot, and `permissions.max_side_effect != LIVE_WRITE`. |
| SKILL-003 | `tests/test_bot_manifests.py` passes: exactly ten `BotManifest`s load from `contracts/tool-rosters/*.yaml`, ids `bot-00-chief` .. `bot-09-journal`, `writes_to_exchange` true only for sniper and exit, each with the R20 `risk_budget` keys and forbidden actions, every roster 8..15 tools including the core eight with RISK = 15 and RUG = 15 exactly as R35 lists them. |
| SKILL-004 | Each seat prompt source lists its `load="always"` skills and a `<tools contract="contracts/tool-rosters/<seat>.yaml">` section; `agents/<seat>.md` and the plugin manifests enumerate the same skills (description count updated from "23 skills"); `./scripts/check.sh` passes. |

### 5.5 PAPER - paper engine, ledger, replay, reports

| Id | Requirement |
|---|---|
| PAPER-001 | `PaperAdapter` (`src/pumpgrok/execution/paper_adapter.py`, R31) computes every pre-graduation BUY and SELL fill from the bonding-curve reserves (the Jupiter quote is informational only, never the fill price, R38) with price impact, venue + base + priority fee (and optional tip), seeded confirmation latency, `slippage_exceeded` with the threshold recomputed for the executed size, full fill for size <= L/50, partial fill in (L/50, L/10], `below_liquidity_floor` above L/10 (R6, R20 `liquidity_floor_multiple`/`partial_fill_fraction`, REVIEW), seeded `tx_dropped` with no cash change, and day attribution of PnL by fill timestamp. |
| PAPER-002 | `var/ledger.sqlite` (paper) and `var/replay/<dataset>/ledger.sqlite` (replay) are append-only WAL event logs with the R32 schema and the eighteen event types, a hash chain over canonical JSON (R28), `source` in `{paper, replay, manual}` on every event (R21), periodic snapshots and a pure reducer; restart = snapshot + tail replay + verify; a tampered payload yields `INCONSISTENT`, `HaltSet(ledger_inconsistent)` and refused orders; a duplicate `idempotency_key` is refused (`docs/design/paper-engine.md` section 9). |
| PAPER-003 | JSONL journal export under `var/journal/` resumes from `meta.export_seq` without duplicates and also emits the vendor-shape `trades.jsonl` lines; `desk.md` and every markdown view under `var/desk/` is written via tmp file + `os.replace` (R26), derived and never read back (`docs/MIGRATION_MAP.md` section 4.5). |
| PAPER-004 | Replay runs the full desk over `tests/fixtures/replay/<dataset>/` with `FixtureClock`, one seeded RNG and fixture timestamps as ledger `ts_utc`; LLM calls are served from the recorder's `canonical_request_hash` records (`outcome` in `{ok, timeout, error}`, virtual `latency_s`) and a missing record fails the replay (R27); two runs over `smoke-10m` give identical `events.hash`, JSONL bytes and final state, a different seed differs, and a 180 s hole trips `DataStale` (section 9); `pumpgrok run --record <dataset> --duration <s>` writes new datasets from live transports stamping the clock's ts (R40). |
| PAPER-005 | A bonding-curve graduation event force-closes the open paper position at the last curve price with reason `graduated` and freezes MTM, a BUY on a graduated token is rejected `post_graduation_no_reserves` (R8, R38), and after `blind_max_s = 300` without a price EXIT force-closes at `last_good` with reason `blind_flatten` and escalates (R25); open positions are marked to market at liquidation value every 60 s. |
| PAPER-006 | `pumpgrok report --daily` (00:05Z) and `--weekly` (Monday 00:15Z, R40) render the sections of `docs/design/paper-engine.md` section 8.3 (summary, trades, open positions, rejected signals by R34 reason, safety outcomes, risk events, bot health, data freshness, live gate on weekly, unverified) with `str.format` only (R9), ASCII only, snapshot-tested from a fixture ledger (section 9). |
| PAPER-007 | Tickets are `SOL-YYYYMMDD-NNN` sequence-allocated in the ledger; approvals are persisted as `ApprovalRecorded` with kind in `{human_buy, human_sell, exit_rule, autonomous_paper, killswitch_clear, halt_clear, live_gate}` (R33); under `manual-ticket` a buy needs a human phrase matching the ticket token-for-token (`rules/pumpgrok-team.mdc:28`, mismatch -> `OrderRejected reason=approval_mismatch`) and each exit rule needs a per-ticket `exit_rule` approval, while under `autonomous-paper` the EXIT rule engine is always on (R17); sniper and exit send once per ticket because `exec.place` is idempotent on `(ticket_id, side, decision_id)` (R18, R23) and an unknown or timed-out result enters state `UNKNOWN` and is never auto-retried (D9, `rules/pumpgrok-team.mdc:30`). |

### 5.6 RISK - limits, halts, breakers, kill switch

| Id | Requirement |
|---|---|
| RISK-001 | `RiskEngine.check(order)` (`src/pumpgrok/risk/engine.py`, R31) is library code executed inside `PaperAdapter.place` for every order regardless of seat health (R24), binds the decision to `order_hash`, evaluates the R34 steps in one vocabulary, and enforces the R20 budget `max_trade_fraction=0.02, max_token_fraction=0.05, max_open_positions=3, max_trades_per_day=20, liquidity_floor_multiple=10, partial_fill_fraction=0.02, paper_equity_sol=10` (REVIEW) read from the TOML `[risk]` block. |
| RISK-002 | Daily loss >= `daily_loss_halt_fraction` (0.05) of start-of-day equity appends `HaltSet(daily_loss)` (idempotent per reason + utc_day, R24), posts the constant `FLOOR HALTED <U+2013> DAILY LOSS LIMIT` with its exact bytes (R7, `rules/pumpgrok-team.mdc:34`) and refuses new entries; drawdown >= `drawdown_halt_fraction` (0.15) from peak equity halts with reason `drawdown`; a halt is cleared only by `pumpgrok state halt --clear --by <human> --reason <text>` which appends `HaltCleared` with an `ApprovalRecorded` of kind `halt_clear` (R5, R22). |
| RISK-003 | Breakers `DataStale`, `LossVelocity` and `ExecErrors` trip on configured thresholds, reject buys while open, allow sells, admit one half-open probe after cooldown, reset after `reset_after_ok` successes, and reconstruct their state from ledger events after restart (`docs/design/paper-engine.md` section 9); kill switch, halts, breakers and limits are re-checked at `CONFIRMING` immediately before a fill and an in-flight order is rejected with reason `kill_switch`/`halted`/`breaker_open` (R22). |
| RISK-004 | The kill switch reads env `PUMPGROK_KILLSWITCH` at start only and polls file `var/KILLSWITCH` and the alert-channel command every risk cycle (5 s); zero buys occur after it is set within one cycle; `flatten_request` waits on the in-flight barrier then closes every open position with reason `kill_flatten`; clear is CLI-only `pumpgrok killswitch clear --by <human> --reason <text>` appending `KillSwitchCleared` with an `ApprovalRecorded` of kind `killswitch_clear` and refused while any live source is still set (R22, section 9). |
| RISK-005 | A RISK verdict `KILL` on a mint blocks that token path for the session for every seat (`rules/pumpgrok-team.mdc:32`) and the `seat_may_trade` step rejects a BUY from exit and a SELL from sniper (R34). |
| RISK-006 | A seat in observe-only (restart budget exhausted, LLM required but down, clock skew) cannot resolve its paper-write tools; when sniper or bot-02-risk is observe-only the desk enters observe-only for BUYS while exits continue (R24), and when exit is observe-only `HaltSet(manual, "exit seat observe-only")` is appended (`docs/design/paper-engine.md` section 6.4). |
| RISK-007 | `docs/RISK_POLICY.md` states the D7 compliance boundary and `tests/safety/test_no_manipulation_tools.py` passes over `tools/social/`, `notify.*` and the `browser-ops` forbidden-actions scope (R39): no registered tool name matches `post\|reply\|like\|follow\|dm\|broadcast\|wash\|volume`, no social module issues anything but GET, and `notify.alert` sends only to the configured allowlist. |

### 5.7 AUTO - supervisor, health, degraded modes

| Id | Requirement |
|---|---|
| AUTO-001 | `src/pumpgrok/supervisor/{scheduler,seat_task,health}.py` (R31) run the ten seats as one asyncio task each on the cadences of `docs/design/paper-engine.md` section 6.2, start due seats in roster order within a 1 s tick, treat a cycle exceeding its `clock.timeout` as a crash (R27), and support `autonomy_level` `manual-ticket` and `autonomous-paper` (live forces `manual-ticket`; `pumpgrok state autonomy <level>` appends `ConfigChanged`; no live auto-exit exists, R17). |
| AUTO-002 | Heartbeats are recorded by the task wrapper; a seat stale for 3 cadences degrades health and emits one edge-triggered `Escalation(heartbeat_stale)`; a crashing seat is restarted at most 5 times per hour with backoff 1,2,4,8,16 s plus jitter through `clock.sleep`, then latched observe-only with `Escalation(bot_restart_exhausted)` while the other seats keep ticking; the supervisor relays every `Escalation` event (its own and seat-emitted `kind=escalation`) to `notify.alert`; `pumpgrok state resume --seat <seat> --by human:<name>` clears the latch (section 9). |
| AUTO-003 | SIGTERM/SIGINT stops scheduling, drains running cycles within 30 s, writes a ledger snapshot, flushes the JSONL export, writes `var/health.json status=stopped` and exits 0; a second signal does not force; a hard kill mid-append leaves the ledger consistent (R26). |
| AUTO-004 | `GET /healthz` returns 200 only when status is ok (503 while any seat is stale), `GET /readyz` returns 200 only after the ledger reconciled CONSISTENT and every seat completed one cycle, and `var/health.json` is rewritten atomically every 10 s for Hermes prompts. |
| AUTO-005 | The degraded modes of `docs/design/paper-engine.md` section 6.7 hold: LLM failure degrades bot-08-signal to rule-based scoring in live paper runs only (observe-only for buys when `signal.require_llm`; in replay a missing LLM record fails the run, R27), RPC failure fails over then marks `BLIND`, WebSocket loss reconnects with backoff and trips `DataStale` after 120 s, an unwritable ledger refuses orders into a bounded buffer with `Escalation(persistence_down)`, and clock skew refuses appends with `Escalation(clock_skew)`. |
| AUTO-006 | `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` runs one full cycle of all ten seats on fixture data through the engine, risk and paper adapter, writes `var/replay/smoke/ledger.sqlite`, and exits 0 with no network access. |
| AUTO-007 | `tests/soak/test_soak_multiday_replay.py` replays `soak-3d`: peak memory growth after the first virtual hour is under 20 MB (REVIEW), no unhandled exception reaches the loop handler, at least one `DailyRollover` per day, the ledger verifies, and a report renders for each day. |
| AUTO-008 | A fault-injection suite under `tests/degradation/` drives each AUTO-005 row through `FaultInjector` on replay and asserts the stated behaviour and recovery. |

### 5.8 OBS - logs, correlation, metrics, runbooks

| Id | Requirement |
|---|---|
| OBS-001 | Every log record is one JSON line with the fields of `docs/FOUNDATION_STACK.md` section 5.1, secrets and key-shaped values are redacted before emission (`tests/test_logging.py::test_log_redaction`), and `PUMPGROK_LOG_JSON=false` restores text only in the `dev` overlay. |
| OBS-002 | A cycle bound to a ULID correlation id yields child spans `<ulid>.<n>` on every tool call, log record and ledger event (R29; `tests/test_correlation.py::test_correlation_id_chain`). |
| OBS-003 | `GET /metrics` exposes `pumpgrok_cycle_seconds{seat}`, `pumpgrok_bot_crashes_total{seat}`, `pumpgrok_orders_total{side,outcome}`, `pumpgrok_equity_sol`, `pumpgrok_drawdown_pct`, `pumpgrok_data_age_seconds{source}`, `pumpgrok_breaker_state{breaker}`, `pumpgrok_kill_switch`, `pumpgrok_ledger_seq` (`docs/design/paper-engine.md` section 6.6) and span timings for every tool call are logged. |
| OBS-004 | `docs/runbooks/{setup,engine,start_stop,kill_switch,breaker_reset,outage,rollback,reading_reports,go_live}.md` exist, each command in them is one of the canonical commands or a `pumpgrok` verb, and they pass `./scripts/check.sh`. |
| OBS-005 | `CHANGELOG.md` records every phase, `AGENTS.md` indexes the rules a cloud agent must read, and the milestone report (phase reports appended to this file, section 6.6) lists the final test, gate and audit results. |

### 5.9 SEC - secrets, quarantine, live gate, scanning

| Id | Requirement |
|---|---|
| SEC-001 | No secret is committed: `.env.example` contains placeholders only, `python3 ci/gates/check_secrets.py --base origin/main` exits 0 on every PR, and G-3 recognises Solana base58 64-byte keys, JSON byte arrays, Helius/QuickNode keyed URLs and Telegram tokens. |
| SEC-002 | Secrets reach the desk only through env (or a secret manager injecting env); `--rpc https://...?api-key=` style CLI flags are refused and the operator confirmation secret is readable only by `pumpgrok live confirm` and `LiveGate.validate`, never by a seat or tool (R21). |
| SEC-003 | `tests/safety/test_no_signing_outside_live_stub.py` walks the AST and fails on any `sign`, `send_transaction`, `sendTransaction` or `Keypair` symbol outside `src/pumpgrok/execution/live/`, and the live stub itself builds no transaction. |
| SEC-004 | `pumpgrok run --mode live` (or env `PUMPGROK_MODE=live`, R30) with any of the nine R21 preconditions unmet exits 3 listing every unmet line and sends nothing; precondition 8 (a registered live adapter implementation) is always unmet because none ships; `LiveAdapter.place`/`cancel` (`src/pumpgrok/execution/live/live_adapter.py`) always raise `LiveGateError` after appending `LiveWriteAttempted` and a critical alert; every registry grant decision is a `GrantAudit` row. |
| SEC-005 | `security-pr.yml` (gitleaks, semgrep, bandit, pip-audit via the R2 bridge, trivy) is green on `main` or every exception is listed in `SECURITY.md` with an expiry. |

### 5.10 GOLIVE - documented, tested, disabled

| Id | Requirement |
|---|---|
| GOLIVE-001 | `pumpgrok live confirm --by human:<name> --notional-cap <sol> --expires <iso>` writes the HMAC-signed confirmation record bound to the config hash using an operator secret no seat or tool can read (R21) and appends `ApprovalRecorded(kind=live_gate)` plus `ConfigChanged(keys_changed=["live.confirmation"])`; it never changes `execution.mode`. |
| GOLIVE-002 | `LiveGate.validate` (`src/pumpgrok/execution/live/live_gate.py`) evaluates the paper window and the thresholds `closed_trades >= 50`, `profit_factor >= 1.2`, `max_drawdown <= drawdown_halt_fraction` only over ledger events with `source=paper`, refuses any ledger containing `source=replay` for its metrics, and `0 < live.notional_cap_sol <= 1.0` (R21, REVIEW); the weekly report prints each precondition with OK/unmet. |
| GOLIVE-003 | `docs/runbooks/go_live.md` documents the full procedure, `tests/execution/test_live_gate_fails_fast.py` proves each of the nine preconditions independently, and the milestone ships with `live.enabled = false` in every overlay. |

### 5.11 Out of scope / v2 (listed so the roadmapper does not invent phases for them)

| Item | Disposition |
|---|---|
| Web dashboard or UI | out of scope (spec xml line 160); `reporting/dashboard.py` is a text renderer only |
| Live trading enablement, wallet funding, any real transaction, any live adapter implementation | out of scope (xml 159, R21 precondition 8); GOLIVE-* ships disabled |
| New chains, venues, launchpads, data vendors; post-graduation CPMM modelling | out of scope (xml 165, D8, R8, R38) |
| Multi-tenant, billing, SaaS packaging | out of scope (xml 164) |
| Strategy research, new alpha, tuning beyond making ported logic run | out of scope (xml 162); `engine/tune.py` is ported as-is |
| Social posting, coordinated buying, volume tooling, wallet UI automation | forbidden (xml 161, D7, R39) |
| Engagement level `micro-live` | retired (R16) |
| Coverage threshold, ed25519 confirmation signatures, Greptile as a gate, gateway OAuth | deferred (`docs/FOUNDATION_STACK.md` U-5, `docs/design/paper-engine.md` section 7.3, section Unverified 6) |

## 6. Phase plan

Five phases, in order, cut per R37 so that every checkpoint is buildable from Phase 1
with no waiver. Each phase is one GSD phase and one or more PRs on branches
`bot-0N-<seat>/phase-<n>-<unit>`; each PR carries a receipt under `.receipts/<seat>/` and
passes `python3 ci/gates/run_all.py`. Work units inside a phase are file-disjoint and may
run in parallel unless a sequencing constraint says otherwise. Owners follow R36.

Common checkpoint (ends every phase, R37 CHECKPOINT_RULE): all canonical commands of
section 7.1 exit 0; `uv run pumpgrok run --mode paper --once --replay
tests/fixtures/replay/smoke` completes one cycle on fixture data (skip-only in Phase 1,
engine decision from Phase 2, full ten-seat cycle from Phase 4); `uv run pumpgrok doctor`
exits 0 with every subsystem owned by a completed phase present (absent subsystems of
later phases are `not-yet-implemented` warnings); a phase report is appended to section
6.6 of this file.

Common rollback: `git revert` of the phase's merge commits in reverse order. There are no
data migrations in any phase: `var/` is gitignored runtime state and the ledger is created
on first run (`docs/design/paper-engine.md` section 3.5); old paths (`tools/`, `vendor/`) are
deleted only at the end of Phase 2 and Phase 4 respectively, so every earlier revert
restores a runnable tree (`docs/MIGRATION_MAP.md` section 7 rollback note).

### 6.1 Phase 1 - Foundation (R37 batch 1)

Goal: a runnable, gated, empty desk. `uv sync` works, the skip-only replay cycle appends
one `JournalNote`, `pumpgrok doctor` reports paper mode, every gate passes on the skeleton,
and the harness every later test needs exists.

Requirements: FOUND-001, FOUND-002, FOUND-003, FOUND-004, FOUND-005, FOUND-006, FOUND-007,
FOUND-008, FOUND-009, FOUND-010, FOUND-011, FOUND-012, FOUND-013, STRUCT-001, STRUCT-008,
OBS-001, OBS-002, SEC-001, SEC-002.

| Unit | Paths (disjoint) | Owner (R36) | Source draft |
|---|---|---|---|
| 1A deps + toolchain + containers + hygiene | `pyproject.toml`, `uv.lock`, `Makefile`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `.gitignore`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`; delete tracked `*.pyc` and `issues/tissue.json`; rewrite `scripts/check.sh`; `docs/VENDOR_PIN.md` | bot-00-chief (manifest, containers); bot-02-risk (`.gitignore`, pre-commit, `check.sh`) | `docs/FOUNDATION_STACK.md` section 3; `docs/MIGRATION_MAP.md` section 7 batch 1 |
| 1B config schema + precedence + live-gate validation | `src/pumpgrok/__init__.py`, `src/pumpgrok/config/{settings.py,overlays/{dev,paper,live}.toml}`, `tests/test_config.py` (`test_mode_defaults_paper`, precedence cases of R30, `test_live_gate_fails_fast` config half: nine R21 lines printed, exit 3) | bot-02-risk | `docs/design/paper-engine.md` section 7.1 amended by R20, R21, R30; `docs/FOUNDATION_STACK.md` M-2, M-7, M-10 |
| 1C logging + ids + correlation | `src/pumpgrok/logging/`, `src/pumpgrok/core/ids.py` (ULID from clock + seeded rng, R29), `tests/test_logging.py`, `tests/test_correlation.py`, `tests/safety/test_no_uuid_no_wall_time.py` (R27, R29 static tests) | bot-02-risk | `docs/FOUNDATION_STACK.md` section 5 |
| 1D core interfaces + registry + approvals | `src/pumpgrok/core/{interfaces,registry,approvals,__init__}.py`, `tests/test_registry.py` (invariants I1-I5), `tests/test_idempotency.py` | bot-02-risk | `docs/design/interfaces.md` section 2 listing, split per R31; R20 `RiskBudget`; R33 kinds |
| 1E ledger store skeleton | `src/pumpgrok/ledger/{__init__,store,events}.py` (R32 schema, eighteen event models, `BEGIN IMMEDIATE` append + hash chain, R26, R28), `tests/ledger/test_store_append_chain.py` | bot-02-risk | `docs/design/paper-engine.md` sections 3.2-3.3 amended by R32 |
| 1F replay clock/rng/fixtures + harness | `src/pumpgrok/replay/{__init__,clock,rng,fixtures}.py`, `tests/conftest.py` (network block), `tests/harness/faults.py`, `tests/fixtures/replay/smoke/` (manifest + the one-decision streams of `docs/MIGRATION_MAP.md` Unverified Items 9) | bot-02-risk (replay); bot-01-scout (smoke dataset content) | `docs/design/paper-engine.md` section 4 |
| 1G CLI skeleton | `src/pumpgrok/cli.py` (`run --mode paper --once --replay` skip-only cycle: read fixture events, append one `JournalNote` with `source=replay`; `doctor` with `not-yet-implemented` rows; `--version`), `src/pumpgrok/__main__.py`, `desk_cli.py`, `tests/desk/test_cli.py` | bot-00-chief | R37; `docs/DISCOVERY.md:11-16` |
| 1H ownership + gates + receipts | `ownership.yaml`, `ci/gates/*.py`, `ci/hooks/`, `ci/security/{semgrep.yml,gitleaks.toml,bandit.ini}`, `ci/tests/test_gates.py` (incl. the `git ls-files` G-1 self-test of R36), `.receipts/bot-0N-<seat>/.gitkeep` (ten), `.github/workflows/{gates.yml,security-pr.yml}` | bot-02-risk | `docs/ROSTER.md` section 7 amended by R36; `docs/FOUNDATION_STACK.md` section 4; R19 |
| 1I contracts skeleton | `contracts/README.md`, `contracts/tool-rosters/{_core,chief,scout,risk,whale,sniper,rug,exit,shill,signal,journal}.yaml` (R35 sizes), `contracts/events/<snake>.schema.json` x18 generated from `ledger/events.py` (R32), `contracts/changes/README.md` | bot-02-risk | `docs/TOOL_CATALOG.md` sections 9-11; `docs/ROSTER.md` section 8 amended by R32 |
| 1J prompts + generators | `prompts/_shared/core-directives.xml`, `prompts/bot-00-chief.xml` .. `prompts/bot-09-journal.xml`, `scripts/assemble-prompts.sh`, `scripts/generate-templates.py`, `prompts-assembled/`, regenerated `agents/*.md` | each seat owns its own `prompts/bot-0N-<seat>.xml`; bot-00-chief owns `_shared`, the scripts and the generated files (R36) | `docs/MIGRATION_MAP.md` section 4.1; `docs/ROSTER.md` section 9 |
| 1K desk docs | `AGENTS.md`, `SECURITY.md`, `CHANGELOG.md`, `docs/quality-gates.md`, `docs/desk-operating-model.md`, `docs/cross-bot-protocol.md` | bot-02-risk | programming-desk `docs/{quality-gates,desk-operating-model,cross-bot-protocol}.md` (`scout-programming-desk.md:251-253`); R16, R40 wording |

Sequencing: 1A first (everything else needs `uv sync`); 1H's `ownership.yaml` next so
G-1 owns the paths 1B-1K create before they exist (programming-desk rule,
`programming-desk/docs/upgrade-plan-desk-v2.md:299`); then 1B, 1C, 1D, 1E, 1F, 1I, 1J, 1K
in parallel; 1G last because the skip-only cycle imports config, ids, ledger store and
the fixture loader. 1E's `events.py` must land before 1I generates the schemas. 1J's
`generate-templates.py` must reproduce today's eight `agents/<seat>.md` byte-for-byte
(allowing only `skills:` ordering, Unverified 5) before it is trusted.

Checkpoint: common checkpoint (skip-only cycle) plus `python3 ci/gates/check_ownership.py
--validate-manifest`, `python3 ci/gates/check_desk_integrity.py --repo .`,
`bash scripts/assemble-prompts.sh --check`, `python3 scripts/generate-templates.py
--check`, `python3 -m pytest ci/tests/ -q` all exit 0; `tests/test_config.py` precedence
and live-gate cases pass; `make audit` exits 0; `var/replay/smoke/ledger.sqlite` contains
exactly one `JournalNote` with a verified hash chain.

Rollback: common. Pre-existing files touched: `scripts/check.sh` (rewritten),
`agents/*.md` (regenerated byte-identical), six `*.pyc` and `issues/tissue.json`
(deleted). Revert is clean.

Acceptance commands: section 7.1 lines 1-11 plus the checkpoint list above.

### 6.2 Phase 2 - Restructure (R37 batch 2)

Goal: the root tools and the vendor engine's discovery, analysis, scoring, agents, exit
rules and watcher live at their R31 targets with English strings and pinned behaviour;
the instruction pack (prompts, hermes, skills, manifests, README/ARCHITECTURE) describes
the new tree; `tools/` is gone.

Requirements: STRUCT-002, STRUCT-003, STRUCT-005, STRUCT-007, SEC-003.

| Batch | MIGRATION_MAP rows | Paths | Owner (R36) |
|---|---|---|---|
| 2.1 tools + RPC client + recorded fixtures | 71, 73, 74, 77, 105 (partial) | `src/pumpgrok/tools/onchain/{rpc,authorities,holders,priority_fee}.py`, `src/pumpgrok/tools/market/jupiter.py`, `src/pumpgrok/tools/notify/{base,stdout,file}.py`, `src/pumpgrok/tools/social/__init__.py` (read-only package, R31), `tests/characterization/test_{authority_check,holder_check,jupiter_quote,priority_fee}.py`, `tests/fixtures/http/`, recorded responses in `tests/fixtures/replay/smoke/`; `tools/README.md` gains `desk_state.py` (R14) | bot-05-rug (onchain), bot-01-scout (market), bot-00-chief (notify), bot-07-shill (social) |
| 2.2 engine port + exits/watcher | 84, 97-104, 106, 110-115 (engine half) | `src/pumpgrok/engine/{__init__,pipeline,models,monitor,analyzer,scoring,reputation,tune,exits,watcher}.py`, `src/pumpgrok/engine/agents/{__init__,base,auditor,checker,narrative,timing}.py`, `src/pumpgrok/engine/LICENSE-grokbot-pumpfun`, `src/pumpgrok/core/llm.py` (vendor `GrokOps.precheck`, recorder hooks of R27), `tests/characterization/test_{agents,analyzer,monitor,reputation,scoring,tune,exits,watcher,pipeline}.py`; `pumpgrok run --once --replay` wired to the engine with the Phase 1 ledger store (decision logged, no fills yet) | bot-08-signal (engine, agents), bot-01-scout (monitor, analyzer), bot-05-rug (reputation, watcher), bot-06-exit (exits), bot-00-chief (pipeline wiring, llm) |
| 2.3 instruction-pack regeneration | 1-29, 36-37, 40-62, 65, 71-78 (old paths), 88 | `src/pumpgrok/cli.py` seat verbs (R40 list; absent subsystems return `not-yet-implemented`); `hermes/cron/prompts/*.md`, `hermes/cron/jobs.yaml`, `hermes/profiles.yaml`, `scripts/hermes-{bootstrap,install-cron,verify-isolation}.sh` (micro-live retired, R16); `skills/*/SKILL.md` (23) frontmatter + body upgrade, `skills/jupiter-routing` (R18), `skills/browser-ops` (R39), `skills/grokbot-pipeline` retarget; `plugin.json`, `.claude-plugin/*`, `.cursor-plugin/*`, `.grok-plugin/*`; `README.md`, `ARCHITECTURE.md`, `SETUP.md` -> `docs/runbooks/setup.md`, `docs/runbooks/engine.md`; `docs/MIGRATION_MAP.md` engagement-level row and markdown-prose quarantine table (R16); `tests/safety/test_no_signing_outside_live_stub.py`; delete `tools/` and `tools/README.md` | bot-00-chief (cli, hermes, README, ARCHITECTURE, runbooks), bot-02-risk (skills, manifests, MIGRATION_MAP, safety test, deletions) |

Sequencing: 2.1 -> 2.2 -> 2.3, sequential because each batch rewrites imports across the
tree (spec rationale 3, xml line 344). Inside 2.3 the bot-02-risk rows and the
bot-00-chief rows are file-disjoint and run in parallel; the `tools/` deletion is the
last commit of the phase and requires every Hermes prompt and skill to reference
`pumpgrok` verbs only (`rg -l 'tools/[a-z_]+\.py' hermes skills agents README.md
ARCHITECTURE.md` empty). `vendor/grokbot-pumpfun/` stays until Phase 4 (its `executor`,
`risk` engine, `ops`, `state`, `log` halves are ported there) and `cd vendor/grokbot-pumpfun
&& python3 -m pytest -q` must keep passing as the oracle (`docs/MIGRATION_MAP.md` section 7).

Checkpoint: common checkpoint; `uv run pumpgrok run --mode paper --once --replay
tests/fixtures/replay/smoke` prints one engine `skip` or `buy` decision and appends the
decision as `JournalNote` (fills arrive in Phase 4); `tests/characterization/` holds the
engine, exits, watcher and four tool modules green; `uv run pumpgrok doctor` lists
`execution`, `risk`, `supervisor`, `reporting` as `not-yet-implemented`; `./scripts/check.sh`
passes with upgraded skills; `rg -n 'micro-live' . --glob '!vendor/**' --glob
'!docs/upgrade-plan-desk-v2.md'` is empty.

Rollback: one PR per batch on `bot-0N-<seat>/phase-2-batch-N`; reverting a batch's merge
commit restores the previous checkpoint because `tools/` is deleted only in the last
commit of 2.3 and `vendor/` is untouched.

Acceptance commands: section 7.1 lines 1-11 plus
`cd vendor/grokbot-pumpfun && python3 -m pytest -q` and
`python3 ci/gates/run_all.py --bot bot-08-signal --base origin/main --receipt .receipts/bot-08-signal/phase-2-batch-2.json`
(`docs/MIGRATION_MAP.md` section 7 batch 3).

### 6.3 Phase 3 - Tools and Skills (R37 batch 3)

Goal: the complete tool layer of `docs/TOOL_CATALOG.md` with recorded-fixture tests, the
registry enforcing least privilege against ten validated manifests, 35 skills with
manifests, the per-seat gateway and the full CLI.

Requirements: TOOL-001, TOOL-002, TOOL-003, TOOL-004, TOOL-005, TOOL-006, TOOL-007,
TOOL-008, TOOL-009, TOOL-010, TOOL-011, SKILL-001, SKILL-002, SKILL-003, SKILL-004.

| Unit | Paths (disjoint) | Owner (R36) |
|---|---|---|
| 3A market + onchain tools | `src/pumpgrok/tools/market/{price,ohlcv,liquidity,trades,holders_snapshot}.py`, `src/pumpgrok/tools/onchain/{token_metadata,lp_status,top_holders,deployer_history,large_transfers}.py` (+ `rpc.py`, `authorities.py`, `holders.py`, `priority_fee.py` from 2.1), `tests/tools/{market,onchain}/`, `tests/fixtures/http/` | bot-01-scout (market), bot-05-rug (onchain), bot-03-whale (`deployer_history`, `large_transfers`, `top_holders`; R35) |
| 3B safety tool | `src/pumpgrok/tools/safety/{score_report,checks/*}.py`, `tests/tools/safety/` | bot-05-rug |
| 3C exec tools | `src/pumpgrok/tools/exec/{quote,simulate,place,cancel,positions}.py` (against the `ExecutionAdapter` protocol; the Phase 1 registry serves a `NotYetImplementedAdapter` until Phase 4), `tests/tools/exec/` | bot-04-sniper |
| 3D portfolio + risk + journal + notify + social tools | `src/pumpgrok/tools/portfolio/`, `src/pumpgrok/tools/risk/`, `src/pumpgrok/tools/journal/`, `src/pumpgrok/tools/notify/{telegram,webhook,allowlist}.py` (R39), `src/pumpgrok/tools/social/*.py` (GET only), `tests/tools/{portfolio,risk,journal,notify,social}/` | bot-09-journal (portfolio, journal), bot-02-risk (risk), bot-00-chief (notify), bot-07-shill (social) |
| 3E desk core eight + gateway | `src/pumpgrok/tools/desk/`, `services/desk-gateway/{pyproject.toml,uv.lock,src/desk_gateway/{server,config,tools/core}.py,tests/}`, `tests/tools/desk/` | bot-00-chief |
| 3F manifests + least privilege | `tests/test_registry_least_privilege.py`, `tests/test_bot_manifests.py`, `tests/test_skill_manifests.py`, `tests/safety/test_no_manipulation_tools.py` (skeleton; RISK-007 completes it in Phase 5), roster YAML recount under `contracts/tool-rosters/` (R35) | bot-02-risk |
| 3G new skills | `skills/{verification-receipts,paper-broker,replay-and-backtest,live-gate-procedure,kill-switch,rpc-hygiene,key-custody,safety-scoring,momentum-signals,portfolio-ledger,daily-report,desk-doctor}/SKILL.md`, `skills/README.md`, prompt `<skills>` sections, manifest skill lists | bot-02-risk (skills), bot-09-journal (`desk-post-trade-review`, `daily-report`, `portfolio-ledger` bodies), each seat (own prompt) |
| 3H CLI verbs | `src/pumpgrok/cli.py` (every verb of `docs/TOOL_CATALOG.md` section 12 + R12 + R40 wired to tools), `tests/desk/test_cli.py` | bot-00-chief |

Sequencing: 3A-3H run in parallel; the registry and roster YAML already exist from Phase 1
so no shared file is edited (spec rationale 4, xml line 345). 3F's tests are written first
and expected red until 3A-3E register their tools; 3H merges last because it imports every
tool package. `contracts/tool-rosters/*.yaml` edits in 3F require a `contracts/changes/`
doc and G-4 acks from every consuming seat (`docs/ROSTER.md` section 8).

Checkpoint: common checkpoint plus every test file in `docs/design/interfaces.md` section 4
green, `tests/tools/` runs with the network block active (any live request fails the
suite), `cd services/desk-gateway && uv sync && uv run pytest -q` green,
`python3 ci/gates/check_desk_integrity.py --repo .` exits 0 with ten rosters in the 8..15
band and RISK = RUG = 15, `./scripts/check.sh` passes with 35 skills.

Rollback: common; new packages under `src/pumpgrok/tools/`, `services/`, `skills/<new>/`
and `tests/tools/` are additive. The only shared files touched are `cli.py`, roster YAML
and prompt `<skills>` sections; each unit's revert is self-contained.

Acceptance commands: section 7.1 lines 1-11 plus
`cd services/desk-gateway && uv sync && uv run pytest -q` and
`uv run pumpgrok tools exec.quote --help` (`docs/MIGRATION_MAP.md` section 7 batch 2 with the catalog
name, Unverified 8).

### 6.4 Phase 4 - Paper Trading and Autonomy (R37 batch 4)

Goal: the desk trades on paper with a realistic fill model, keeps an honest ledger,
replays deterministically, enforces every constitutional rule in code, supervises itself,
refuses live mode, and the vendor tree is retired.

Requirements: PAPER-001, PAPER-002, PAPER-003, PAPER-004, PAPER-005, PAPER-006, PAPER-007,
RISK-001, RISK-002, RISK-003, RISK-004, RISK-005, RISK-006, AUTO-001, AUTO-002, AUTO-003,
AUTO-004, AUTO-005, AUTO-006, SEC-004, GOLIVE-001, GOLIVE-002, STRUCT-004, STRUCT-006.

| Unit | Paths (disjoint) | Owner (R36) |
|---|---|---|
| 4A PaperAdapter | `src/pumpgrok/execution/{__init__,paper_adapter,curve_math,fees,latency}.py` (R31, R38), `tests/execution/test_paper_fill_model.py`, `tests/characterization/test_executor.py` | bot-04-sniper |
| 4B ledger reducer/views/reconcile/export | `src/pumpgrok/ledger/{reducer,views,reconcile,export}.py` (`export.py` is the JSONL/`trades.jsonl`/`desk.md` writer; not named in R31, [INFERENCE] placement), `tests/ledger/test_ledger_restart_reconcile.py`, `tests/ledger/test_tickets.py`, `tests/characterization/test_{state,log}.py` | bot-02-risk (ledger package, R36); bot-09-journal reviews views/export |
| 4C risk engine, breakers, kill switch, halts | `src/pumpgrok/risk/{__init__,engine,limits,sizing,breakers,killswitch}.py` (R20, R22, R24, R34), `tests/risk/{test_kill_switch_one_cycle,test_breaker_trip_and_cooldown,test_daily_loss_halt,test_kill_verdict,test_seat_may_trade,test_confirming_recheck}.py`, `tests/characterization/test_risk.py` | bot-02-risk |
| 4D supervisor, health, degraded modes | `src/pumpgrok/supervisor/{__init__,scheduler,seat_task,health}.py` (R31; heartbeats, restarts, escalation and lifecycle live inside `seat_task.py`/`scheduler.py`), `tests/supervisor/test_supervisor_bounded_restart.py`, `tests/supervisor/test_graceful_shutdown.py`, `tests/supervisor/test_health.py`, `tests/characterization/test_ops.py` | bot-00-chief |
| 4E replay sources/recorder/runner + datasets | `src/pumpgrok/replay/{sources,recorder,runner,trim}.py`, `tests/fixtures/replay/{smoke-10m,soak-3d}/`, `tests/replay/test_replay_determinism.py`, `tests/replay/test_llm_record_required.py` (R27) | bot-02-risk (replay package); bot-01-scout (datasets) |
| 4F reports | `src/pumpgrok/reporting/{__init__,daily,weekly,render}.py`, `tests/reporting/test_reporting_render.py` | bot-09-journal |
| 4G live gate + confirm + autonomy | `src/pumpgrok/execution/live/{__init__,live_adapter,live_gate}.py` (R31 quarantine package, ownership rule after `execution/**`), `pumpgrok live confirm` and `pumpgrok state autonomy` verbs in `cli.py`, `tests/execution/test_live_gate_fails_fast.py` (nine R21 cases), `tests/safety/test_live_adapter_raises.py` | bot-02-risk |
| 4H wiring + vendor retirement | `src/pumpgrok/cli.py` `run` verb (full cycle), seat `cycle()` implementations under `src/pumpgrok/engine/seats/bot_0N_<seat>.py`, `tests/desk/test_run_once.py`; delete `vendor/grokbot-pumpfun/` when the six-item census of `docs/MIGRATION_MAP.md` section 3.4 is zero; `scripts/check.sh` stops excluding `vendor/` | bot-00-chief (wiring), each seat (own `cycle()`), bot-02-risk (deletion) |

Sequencing: 4A, 4B, 4C, 4D run in parallel (spec rationale 5, xml line 346) against the
protocols fixed in Phase 1 (`ExecutionAdapter`, `LedgerStore`, `Clock`, `Notifier`,
`docs/design/paper-engine.md` section 10). 4E, 4F, 4G and 4H import all four and start when the
four are merged; 4E and 4F are mutually disjoint; 4H merges last and its vendor deletion is
the final commit of the phase. RISK-002's constant carries the U+2013 bytes (R7) and lives
in `src/pumpgrok/risk/engine.py`, not in docs.

Checkpoint: common checkpoint plus every test in `docs/design/paper-engine.md` section 9
except the soak test green; `uv run pumpgrok run --mode paper --once --replay
tests/fixtures/replay/smoke` writes a `FillRecorded` into `var/replay/smoke/ledger.sqlite`
and `uv run pumpgrok report --daily` renders it; two consecutive replays over `smoke-10m`
print the same ledger sha256; `uv run pumpgrok run --mode live --once` exits 3 listing
nine `[ ]` lines under default config; `touch var/KILLSWITCH && uv run pumpgrok run --mode
paper --once --replay tests/fixtures/replay/smoke` records zero buys; `tests/characterization/`
holds all 13 vendor modules; `rg -l -F "vendor/grokbot-pumpfun" . --glob '!vendor/**'` is
empty and `rg -l -F 409e74c .` returns only `docs/VENDOR_PIN.md`.

Rollback: common; all new packages are additive and `var/` is disposable. Reverting 4H
alone restores `vendor/` from git and returns `run` to the Phase 2 decision-only cycle.

Acceptance commands: section 7.1 lines 1-11 plus `uv run pumpgrok report --daily`,
`uv run pumpgrok run --mode live --once` (expect exit 3), `uv run pumpgrok verify
--fixture smoke-10m` (R40), and the kill-switch sequence above.

### 6.5 Phase 5 - Hardening (R37 batch 5)

Goal: observable, documented, soak-proven, security-scanned; the milestone can be handed
to the operator for the 2-4 week paper run.

Requirements: OBS-003, OBS-004, OBS-005, SEC-005, RISK-007, AUTO-007, AUTO-008, GOLIVE-003.

| Unit | Paths (disjoint) | Owner (R36) |
|---|---|---|
| 5A metrics + spans | `src/pumpgrok/supervisor/metrics.py` (prometheus registry; module not named in R31, [INFERENCE] placement beside `health.py`), `src/pumpgrok/logging/spans.py`, `tests/test_metrics.py` | bot-00-chief (metrics), bot-02-risk (`logging/`) |
| 5B runbooks + policy + docs | `docs/runbooks/{start_stop,kill_switch,breaker_reset,outage,rollback,reading_reports,go_live}.md`, `docs/RISK_POLICY.md` (D7 clause; produced by the design wave, edited here), `README.md`, `CHANGELOG.md`, `AGENTS.md` rules index, `SECURITY.md` exceptions table | bot-02-risk (docs), bot-00-chief (README, CHANGELOG) |
| 5C safety, degradation and soak suites | `tests/safety/{test_no_manipulation_tools,test_secrets_never_logged,test_constitution_constants}.py` (R39 scope), `tests/degradation/test_*.py` (one per AUTO-005 row), `tests/soak/test_soak_multiday_replay.py` (marker `slow`, nightly job in `ci.yml`) | bot-02-risk (safety), bot-00-chief (degradation, soak) |
| 5D security CI | `.github/workflows/security-pr.yml` final (pin `astral-sh/setup-uv` by SHA, `docs/FOUNDATION_STACK.md` U-4), `ci/security/*` tuned to the `src/pumpgrok` tree, `SECURITY.md` exception list | bot-02-risk |
| 5E milestone report | section 6.6 of this file, `.receipts/bot-00-chief/complete-phase-5.json` | bot-00-chief |

Sequencing: 5A-5D run in parallel; they add files under `tests/`, `docs/`, `ci/security/`
and two new modules (spec rationale 6, xml line 347). 5E is last and needs the nightly soak
run to have completed once with `soak-3d` present (`docs/design/paper-engine.md` Unverified Items).

Checkpoint: common checkpoint plus `uv run pytest -q -m slow tests/soak` green once in CI
with the memory bound met; `security-pr.yml` green on a PR touching `pyproject.toml`;
every runbook command verified by running it (receipt `commands[]`); `curl
127.0.0.1:8080/metrics` lists the nine metric families of OBS-003 during a paper run;
`uv run pumpgrok doctor` reports no `not-yet-implemented` rows.

Rollback: common; nothing in this phase changes runtime behaviour except metrics
registration, which is additive.

Acceptance commands: section 7.1 lines 1-12 plus `uv run pytest -q -m slow tests/soak`.

### 6.6 Phase reports

Appended by bot-00-chief at each checkpoint: phase, date, PR list, receipt paths, the
output tail of every canonical command, open REVIEW items. Empty until Phase 1 completes.

### Phase 5 milestone report (2026-10-22, plan 05-08, branch `feat/grokbot-desk-merge`)

Receipt: `.receipts/bot-00-chief/complete-phase-5.json` (tracked via `.gitignore`
exception; the `*.json` ignore rule otherwise covers receipts).
No PR opened and nothing merged: the hard constraint forbids push/merge/PR, so
this report lands as commits on the feature branch for the orchestrator to verify.

Per-criterion commands and outcomes (canonical literals, exit codes real):

- 5-SC1 (soak/degradation): `uv run pytest -q tests/soak/test_soak_multiday_replay.py
  tests/degradation/` green (plan 05-05); nightly `schedule` soak job in `ci.yml`
  under `PUMPGROK_REQUIRE_SOAK=1` (plan 05-07).
- 5-SC2 (metrics): `grep -rhoE` nine-family count is 9; `/metrics` served during
  `run --mode paper --serve` with `pumpgrok_cycle_seconds` present (plan 05-07 verify).
- 5-SC3a (runbooks): `for f in setup engine start_stop kill_switch breaker_reset
  outage rollback reading_reports go_live; do test -f docs/runbooks/$f.md || exit 1;
  done && ./scripts/check.sh` exit 0 (this plan).
- 5-SC3b (changelog): `for p in 1 2 3 4 5; do grep -q "Phase $p" CHANGELOG.md ||
  exit 1; done` exit 0 (this plan).
- 5-SC3c (container): `docker compose up -d --build pumpgrok && docker compose ps
  pumpgrok` healthy; host `/healthz` ok and `/metrics` 200 (plan 05-07 verify).
- 5-SC4a (manipulation scan + live gate): `uv run pytest -q
  tests/safety/test_no_manipulation_tools.py tests/execution/test_live_gate_fails_fast.py`
  green; `tests/test_live_gate.py` pins the D4 precondition-1 contract (this plan).
- 5-SC4b (live overlays): `live.enabled is false` in dev, paper and live overlays
  (asserted in-suite; plan 05-04).
- 5-SC5 (security workflow): BLOCKED. `gh run list --workflow security-pr.yml --branch
  main --limit 1` is HTTP 404 (no workflow file on any branch yet) and `gh run list
  --branch main` prints `[]`; the push trigger only lands on main after merge, which the
  hard constraint forbids. Real evidence captured verbatim in 05-07-SUMMARY; nothing
  invented in SECURITY.md (zero exception rows; `ci/security/check_exceptions.py` gates
  expiry). First main-branch run remains the post-merge step.
- 5-CP (checkpoint smoke): `uv run pumpgrok run --mode paper --once --replay
  tests/fixtures/replay/smoke` exit 0, `engine decision=skip reason=data_unavailable`
  (this plan).
- 5-MS (invariant matrix): `uv run pytest -q
  ci/tests/test_gates.py::test_invariant_matrix_tests_exist` green (63 invariants).
- Census: the plan literal `rg -n --hidden -P ... tools/(...)` (plus `--hidden`,
  minus `docs/**`, `vendor/**`, `.git/**`, `.planning/**`) prints nothing;
  `test ! -d tools` exits 0 (oracle deleted: 8 modules, README, pycache, no shim).
- Full suite: `uv run pytest -q` exit 0 — 1529 collected, 1527 passed, 2 skipped
  (both pre-existing intentional R5 non-ports in `tests/characterization/test_vendor_risk.py`).

Carry-over resolutions (this plan):

- `tests/test_skip_cycle.py` 3 pre-existing failures (identical on clean base 9ce2695):
  root cause is product evolution, not test rot. The D6 DailyRollover row (one per UTC
  day, including the first) makes CLI replay ledgers hold exactly JournalNote +
  DailyRollover, so `[(1,)]` expectations went stale; `test_live_is_refused...` encoded
  the pre-D4 contract where `--mode live` alone met precondition 1. Fixed by pinning the
  new exact contracts (rollover type/key/day, D4 reason string) — no weakening, no skips.
- Collection anomaly: bare `uv run pytest` intermittently mis-collected in this sandbox.
  In-repo root cause found and fixed: `tests/tools/test_money_types.py` duplicated the
  `tests/safety/test_money_types.py` basename with no `__init__.py` anywhere, so pytest's
  prepend import mode raised `import file mismatch` (exit 2) depending on order. Renamed to
  `tests/tools/test_money_registry_tracer.py` (matrix references only the safety path).
  Post-fix with-sync and `--no-sync` collects agree.
- Pre-existing product bugs fixed under Rule 1 (undefined names at HEAD, any `--by
  human:*` or `killswitch clear` CLI path raised NameError): `src/pumpgrok/cli.py` now
  imports `SEAT_RE` and `KillSwitch` from `pumpgrok.risk.killswitch`; the D4-era
  `tests/test_live_gate.py` expectations updated to the enabled-flag contract plus a
  positive `live_enabled=True` case; `tests/desk/test_doctor_and_once.py` pins the second
  documented doctor warning shape (`not served: health.port=0`, no network attempted).
- `replay/runner.py` lazy ledger and `tools/notify/notifier.py` fan-out redaction
  untouched per the 05-06 note. Health port stays `PUMPGROK_HEALTH__PORT`.

Open REVIEW items: SC5 first main-branch run (post-merge); soak-3d wall-time on PR
runners (05-07 REVIEW); no live RPC probe per D8.

### 6.7 Requirement-to-phase coverage (each id exactly once)

| Phase | Ids | Count |
|---|---|---|
| 1 Foundation | FOUND-001 FOUND-002 FOUND-003 FOUND-004 FOUND-005 FOUND-006 FOUND-007 FOUND-008 FOUND-009 FOUND-010 FOUND-011 FOUND-012 FOUND-013 STRUCT-001 STRUCT-008 OBS-001 OBS-002 SEC-001 SEC-002 | 19 |
| 2 Restructure | STRUCT-002 STRUCT-003 STRUCT-005 STRUCT-007 SEC-003 | 5 |
| 3 Tools and Skills | TOOL-001 TOOL-002 TOOL-003 TOOL-004 TOOL-005 TOOL-006 TOOL-007 TOOL-008 TOOL-009 TOOL-010 TOOL-011 SKILL-001 SKILL-002 SKILL-003 SKILL-004 | 15 |
| 4 Paper Trading and Autonomy | PAPER-001 PAPER-002 PAPER-003 PAPER-004 PAPER-005 PAPER-006 PAPER-007 RISK-001 RISK-002 RISK-003 RISK-004 RISK-005 RISK-006 AUTO-001 AUTO-002 AUTO-003 AUTO-004 AUTO-005 AUTO-006 SEC-004 GOLIVE-001 GOLIVE-002 STRUCT-004 STRUCT-006 | 24 |
| 5 Hardening | OBS-003 OBS-004 OBS-005 SEC-005 RISK-007 AUTO-007 AUTO-008 GOLIVE-003 | 8 |
| Total | | 71 |

Module-to-batch check (R37 "every module named in paper-engine.md and interfaces.md
appears in exactly one batch", using the R31 names): `core/*` 1C-1D; `config/*` 1B;
`logging/*` 1C, 5A; `ledger/{store,events}` 1E, `ledger/{reducer,views,reconcile,export}`
4B; `replay/{clock,rng,fixtures}` 1F, `replay/{sources,recorder,runner,trim}` 4E;
`tools/onchain/{rpc,authorities,holders,priority_fee}`, `tools/market/jupiter`,
`tools/notify/{base,stdout,file}` 2.1, every other tool module Phase 3;
`engine/*` incl. `exits`, `watcher`, `agents/*`, `core/llm` 2.2; `engine/seats/*` 4H;
`execution/{paper_adapter,curve_math,fees,latency}` 4A; `execution/live/*` 4G; `risk/*`
4C; `supervisor/{scheduler,seat_task,health}` 4D, `supervisor/metrics` 5A; `reporting/*`
4F; `cli.py` skeleton 1G, seat verbs 2.3, tool verbs 3H, `run` full cycle 4H.

## 7. Verification and definition of done

### 7.1 Canonical commands (`docs/FOUNDATION_STACK.md` section 6, verbatim)

```
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pytest -q
uv run pip-audit
uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
uv run pumpgrok doctor
python3 ci/gates/run_all.py --bot bot-00-chief --base origin/main --receipt .receipts/bot-00-chief/<task>.json
bash scripts/assemble-prompts.sh --check
./scripts/check.sh
docker compose up pumpgrok
```

Line numbers used above: 1 `uv sync`, 2 ruff check, 3 ruff format, 4 mypy, 5 pytest,
6 pip-audit, 7 run --once --replay, 8 doctor, 9 run_all.py, 10 assemble --check,
11 check.sh, 12 compose. `uv run pip-audit` audits the synced environment; the Makefile
`audit` target is the stricter R2 lockfile bridge (`docs/FOUNDATION_STACK.md` section 6 notes).
`run_all.py` is executed with system `python3` + `pyyaml` on purpose
(`docs/FOUNDATION_STACK.md` section 6 notes). Line 7 works from Phase 1 (skip-only cycle, R37).

### 7.2 Definition of done (spec `ACCEPTANCE_CRITERIA`, xml lines 142-156, as a checklist)

| # | Acceptance criterion (verbatim) | Satisfied by |
|---|---|---|
| 1 | A discovery document exists mapping pumpgrok's old structure to the programming-desk-mirrored structure, with a dependency drift table and a list of replaced/deprecated items. | done: `docs/DISCOVERY.md` sections 3, 5; `docs/MIGRATION_MAP.md` sections 1, 6 (engagement row and prose quarantine table added by STRUCT-005, R16) |
| 2 | Repo layout and conventions visibly mirror programming-desk; deviations are documented. | FOUND-001, FOUND-006..011, STRUCT-001..007; deviations `docs/MIGRATION_MAP.md` section 5, `docs/FOUNDATION_STACK.md` section 1 (R1), R31 |
| 3 | Dependencies upgraded and pinned; lint, format, typecheck (if applicable), unit tests, and CI run clean. | FOUND-001, FOUND-002, FOUND-010, SEC-005 |
| 4 | Every bot has a manifest with role, skills, allowed tools, and risk budget; every tool has a typed schema, tests on recorded fixtures, and a side-effect classification. | SKILL-001..004, TOOL-001..009 |
| 5 | Starting the desk with default config runs in paper mode; attempting to enable live mode without all gate preconditions fails at startup with a clear message; no code path can submit a real transaction. | FOUND-004, FOUND-013, STRUCT-008, SEC-003, SEC-004, GOLIVE-001..003 |
| 6 | Paper engine models slippage, fees, latency, partial fills, and liquidity floors; ledger persists across restart and reconciles. | PAPER-001, PAPER-002, PAPER-003, PAPER-005 |
| 7 | Replay mode runs the full desk deterministically over a fixture dataset and produces a report. | PAPER-004, PAPER-006, AUTO-006 |
| 8 | Kill switch halts new orders within one cycle; circuit breakers trip and recover per configured thresholds; all of this is covered by tests. | RISK-001..006 |
| 9 | Supervisor restarts a crashed bot within bounds, escalates on repeated failure, and shuts down gracefully with state flushed. | AUTO-001..005 |
| 10 | Daily/weekly reports generate with PnL, drawdown, win rate, rejected-signal reasons, and bot health. | PAPER-006, PAPER-007 (ticket and reason fields) |
| 11 | Structured logs carry correlation IDs end to end; runbooks exist for start/stop, kill switch, breaker reset, outage, and rollback. | OBS-001..005 |
| 12 | No secrets in the repo; CI vulnerability scan passes or exceptions are documented. | SEC-001, SEC-002, SEC-005 |
| 13 | A soak/replay test simulating a multi-day run completes without unbounded memory growth or unhandled exceptions. | AUTO-007, AUTO-008 |

Plus the compliance boundary (D7, R39): RISK-007. Plus the constitution in code (D9):
PAPER-007, RISK-002, RISK-005. Plus the engagement-level retirement (R16): STRUCT-005.

## 8. Risks, mitigations, human review points

### 8.1 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Data-source fragility: pump.fun frontend REST and PumpPortal WS are unofficial (`docs/DISCOVERY.md:352-353`); field names for graduation and LP are heuristic (`docs/TOOL_CATALOG.md` Unverified Items) | fixtures stop matching live shapes; replay diverges from reality | `extra="ignore"` models (TOOL-008), `run --record` re-records datasets (PAPER-004), `DataStale` breaker (RISK-003), `BLIND` is treated as `KILL` (AUTO-005), blind positions are force-closed after 300 s (R25); R8/R38 document the graduation limitation |
| LLM cost and outage (x.ai Grok, `grok-4`/`grok-4-fast`, `docs/DISCOVERY.md:354`) | scoring stalls or bills grow during a 2-4 week unattended run; replay silently diverges when the LLM is unavailable | rule-based fallback only in live paper runs with `signal.require_llm = false` default; replay fails loudly on a missing LLM record (R27, AUTO-005); vendor `GrokOps` budget breaker ported to `core/llm.py`; cost line in the daily report (REVIEW: add a daily token budget key) |
| Scope size: 71 requirements, 129 move rows, 264 vendor tests to port | phases slip; partial ports leave two engines alive | R37 batches with the vendor suite as oracle through Phase 4, deletions only at batch ends, one PR per batch, receipts per PR; a phase may close with REVIEW items listed in 6.6 but not with a red canonical command |
| Gate false positives: G-3 Solana/base58 regexes (`docs/FOUNDATION_STACK.md` U-7), `check_receipt` bypass patterns matching legitimate `--dry-run` in docs, the `git ls-files` G-1 self-test on generated files | contributors route around gates | G-3 fixtures are synthetic and `# pragma: allowlist secret` annotated; `ci/tests/test_gates.py` gains one test per changed constant (`docs/FOUNDATION_STACK.md` section 4); generated files have explicit owners (R36); waivers go through `contracts/changes/` not through editing the gate |
| Characterization tests that assert Russian text (`docs/MIGRATION_MAP.md` section 3.3) | 1:1 count below 164 | rule: ported tests assert reason codes, never free text; adapted count reported per batch |
| `pydantic-settings` multi-TOML layering (`docs/FOUNDATION_STACK.md` U-2) and `websockets` 14+ import path (`docs/MIGRATION_MAP.md` Unverified Items 1) | Phase 1/2 blocked on library behaviour | fallback custom settings source (15 lines) and explicit `websockets.asyncio.client.connect` import, both already specified |
| Virtual-time discipline (R27): a single stray `asyncio.sleep` or `time.time` makes replay non-deterministic | determinism test flakes late | static test lands in Phase 1 (FOUND-012) before any engine code is ported; tenacity is constructed with `sleep=clock.sleep` in the shared RPC client |
| Hermes cron prompts keep calling deleted `tools/*.py` | cron silently fails after Phase 2 | prompts rewritten in the same batch as the deletion (2.3) with an `rg` guard; `scripts/hermes-verify-isolation.sh` extended to run `pumpgrok doctor` in each profile |

### 8.2 Human review points

| Item | Where | Default until reviewed |
|---|---|---|
| Every R20 risk default (`paper_equity_sol 10`, `max_trade_fraction 0.02`, `max_token_fraction 0.05`, `daily_loss_halt_fraction 0.05`, `drawdown_halt_fraction 0.15`, `max_open_positions 3`, `max_trades_per_day 20`, `liquidity_floor_multiple 10`, `partial_fill_fraction 0.02`) | `src/pumpgrok/risk/limits.py`, `docs/RISK_POLICY.md` | R20 values, each marked REVIEW |
| Fee and latency parameters (`venue_fee_bps 100`, `compute_units 200000`, lognormal 1.2 s / 0.5, `p_drop 0.02`) | `docs/design/paper-engine.md` Unverified Items | as listed, REVIEW |
| Live-gate thresholds (`closed_trades 50`, `profit_factor 1.2`, `max_drawdown <= drawdown_halt_fraction`, `notional_cap_sol <= 1.0`) and HMAC vs ed25519 | R21; `docs/design/paper-engine.md` section 7.3 | R21 values; HMAC |
| Trading Floor membership: chief, scout, risk, whale, sniper, rug in channel; exit, shill, signal, journal in DM | `docs/ROSTER.md` section 2, R11 | as D3 |
| Report format and delivery (markdown sections of PAPER-006; Telegram delivery via chief profile to the allowlisted chat ids) | `docs/design/paper-engine.md` section 8.3, R39 | markdown to stdout + `var/journal/`; Telegram when `alerts.telegram` is configured |
| Seat cadences, restart budget (5/h), blind flatten 300 s, soak memory bound (20 MB) | `docs/design/paper-engine.md` sections 6.2, 6.4, 9, R25 | as listed, REVIEW |
| Organisation name replacing `your-org` in manifests, GitHub URL for `[project.urls]` | `docs/MIGRATION_MAP.md` Unverified Items 5, `docs/FOUNDATION_STACK.md` U-9 | `swcstudiospace` (remote `origin https://github.com/swcstudiospace/PumpGrok.git`, `docs/DISCOVERY.md:25`) |
| Coverage threshold | `docs/FOUNDATION_STACK.md` U-5 | none |

## 9. Contradictions found (reported, not resolved)

Resolved by R16-R40 since the first draft of this plan and therefore no longer open:
module-name drift between n2 and n4 (R31), live-gate exit code 2 vs 3 (R21: 3), G-7 band
8 vs 10 (R19: 8..15), the Phase 1 checkpoint waiver (R37 skip-only cycle), and the
`JournalNote`-as-approval shape (R33).

Still open:

1. Context says HEAD `8f7ae72`; `git log --oneline -3` shows HEAD `644725a chore: add
   project config` on top of `96b8fdd docs: ...` on top of `8f7ae72`. `.planning/config.json`
   therefore already exists before `gsd-new-project --auto` runs.
2. R14 "tools/README gains desk_state.py" versus `docs/MIGRATION_MAP.md` section 7 batch 5 deleting
   `tools/` and `tools/README.md`: compatible only as a transient edit (batch 2.1 adds the
   row, batch 2.3 deletes the file); STRUCT-007 says so explicitly.
3. The spec's n8 CONCLUSION (xml lines 353-373) lays out eight waves with
   `P/bots/<bot>/{manifest,skills/*}` and "7 manifests validate"; D2, D3, R15 and R37
   supersede it. Mapping: spec wave 1 -> Phase 1; waves 2-3 -> Phase 2 (minus the
   execution/risk/ledger halves, which R37 moves to Phase 4); wave 4 -> Phase 3; waves 5-6
   -> Phase 4; wave 7 -> Phase 5.
4. `docs/MIGRATION_MAP.md` section 7 batch 2 requires `uv run pumpgrok tools market.quote --help` but
   `docs/TOOL_CATALOG.md` has no `market.quote` (the quote tool is `exec.quote`, section 4)
   and the canonical CLI list (`docs/DISCOVERY.md:11-16`, R40) has no `tools` verb. This
   plan uses `exec.quote` in the Phase 3 acceptance line and treats `pumpgrok tools` as a
   hidden developer verb (Unverified 8).
5. R37 batch 2 lists "exits/watcher" in Restructure while R31 places the vendor `risk.py`
   exit rules in `engine/exits.py`; the remaining half of vendor `risk.py` (RiskManager ->
   RiskEngine) and `executor.py`, `ops.py`, `state.py`, `log.py` are therefore ported in
   Phase 4, so the vendor tree and its oracle suite survive until the end of Phase 4, two
   phases later than `docs/MIGRATION_MAP.md` section 7 batch 5 planned. STRUCT-006 is placed in Phase 4.
6. R31 names `ledger/{store,events,reducer,views,reconcile}.py` and
   `supervisor/{scheduler,seat_task,health}.py` only; D5's JSONL export and
   prometheus_client metrics need a home. This plan uses `ledger/export.py` and
   `supervisor/metrics.py` tagged [INFERENCE]; the orchestrator should confirm or amend R31.
7. R21 precondition 3 ("`live.min_paper_days` elapsed") versus `docs/design/paper-engine.md` section 7.1
   (`paper_started_at` defaults to the ledger's `meta.created_ts_utc`): R21 measures only
   `source=paper` events, so the paper window must start at the first `source=paper`
   `FillRecorded`, not at ledger creation. GOLIVE-002 follows R21.
8. R35 recounts RUG to 15 with `market.{price,liquidity}` and RISK to 15 with
   `portfolio.{ledger_read,exposure,pnl}`; `docs/TOOL_CATALOG.md` sections 1 and 5 assign `market.*`
   to Scout's package and `portfolio.*` to Journal's package. Package ownership (who writes
   the module) and roster grants (who may call it) differ; this plan keeps package owners
   per TOOL_CATALOG and grants per R35.

## Unverified Items

| # | Unknown | Default assumed |
|---|---|---|
| 1 | Whether `docs/SAFETY_INVARIANTS.md` and `docs/RISK_POLICY.md` are produced by the current design wave (sibling writers) or by Phase 5 unit 5B | Written in this wave; 5B edits them to add runbook cross-references and the final test names |
| 2 | Whether `gsd-new-project --auto` accepts this file as the idea document or needs `.planning/PROJECT.md` seeded first | This file is the input; `.planning/config.json` (commit 644725a) is kept as committed |
| 3 | Final `ownership.yaml` rules for engine modules split between bot-08-signal, bot-01-scout, bot-05-rug and bot-06-exit (`docs/MIGRATION_MAP.md` section 3.2 marked [INFERENCE]; R36 fixes only the infrastructure packages) | The split in section 6.2 batch 2.2; `docs/ROSTER.md` section 7 is authoritative after the R36 edit |
| 4 | Whether the nightly soak job can run on the self-hosted runner within its time budget (`docs/FOUNDATION_STACK.md` U-3 runner uncertainty) | `soak-3d` replays in under 30 minutes wall clock with `FixtureClock`; the job is `schedule: cron` in `ci.yml` and skips if the dataset is absent |
| 5 | Exact byte-identical regeneration of the eight existing `agents/<seat>.md` by `generate-templates.py` (Phase 1 unit 1J) given `hermes/profiles.yaml` skill lists differ from the frontmatter (`docs/ROSTER.md` Unverified Items) | Frontmatter is the source; a diff is allowed only in `skills:` ordering and is recorded in the receipt |
| 6 | Whether `services/desk-gateway/` needs OAuth in paper mode (programming-desk precedent `scout-programming-desk.md:142`) | Header key `x-desk-seat-key` from env per seat in this milestone; OAuth deferred (section 5.11) |
| 7 | Size of `tests/fixtures/replay/{smoke,smoke-10m,soak-3d}` in git (JSONL may be large) | `smoke` and `smoke-10m` committed; `soak-3d` stored as a CI artifact or git LFS, path configurable via `PUMPGROK_SOAK_DATASET` |
| 8 | Whether a `pumpgrok tools <name>` generic verb is wanted (contradiction 4) | Provided as a hidden developer verb; not listed in `docs/TOOL_CATALOG.md` section 12 or R40 |
| 9 | Telegram inbound command path for the alert-channel kill switch (`docs/design/paper-engine.md` Unverified Items) | Enabled only when `alerts.telegram.allowed_chat_ids` is non-empty (R39 allowlist); file source always works; env source is start-only (R22) |
| 10 | Whether each phase is one GSD phase or Phase 2's three batches become three GSD phases | One GSD phase per section-6 phase; batches are plans inside Phase 2 (`phases/02-restructure/02-0N-PLAN.md`) |
| 11 | Home of the JSONL export and the metrics module (contradiction 6) | `ledger/export.py` (bot-02-risk) and `supervisor/metrics.py` (bot-00-chief) |
| 12 | Whether the Phase 1 skip-only cycle should also exercise `exec.simulate` against a `NotYetImplementedAdapter` so that Phase 3 exec tools have a target | No; Phase 3 unit 3C registers the placeholder adapter itself and Phase 4 replaces it |
| 13 | Line numbers inside `docs/{MIGRATION_MAP,ROSTER,TOOL_CATALOG,FOUNDATION_STACK}.md` and `docs/design/*.md`, which sibling convergence writers were editing while this plan was written (`git status --short docs` showed all six modified, uncommitted) | Those documents are cited by section heading, not line; `docs/DISCOVERY.md` and real repository files are cited by line as read at HEAD 644725a |

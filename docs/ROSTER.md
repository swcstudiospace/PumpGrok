# ROSTER - Target bot roster for the pumpgrok trading desk

Tracker: SPE-17999 https://linear.app/swcstudio/issue/SPE-17999/n3-target-bot-roster-skill-manifests-tool-catalog-core-interfaces | Notion https://app.notion.com/p/3ffbc1a0c7ae8190b46ced6823fa3c90?pvs=204

Design document only. Defines the ten seats (D3), their manifests, the `ownership.yaml`
draft, the Trading Floor membership, and the mapping from today's eight `agents/*.md`
files. Companion documents: `docs/TOOL_CATALOG.md` (every tool, schemas, side effects)
and `docs/design/interfaces.md` (Python protocols, registry, skill manifest shape).

Conventions used below:

- Seat id form `bot-0N-<seat>` copies `programming-desk/ownership.yaml:22-64`
  (`bot-00-programming-lead` .. `bot-06-quality-security`).
- Side-effect classes are `read`, `paper-write`, `live-write` (spec
  `CORE_INTERFACES`, session xml line 71). No seat may resolve `live-write`
  (D3, D4); the registry enforces this regardless of roster
  (`docs/design/interfaces.md`, `ToolRegistry.find`).
- Tool names are written `<namespace>.<verb>` in this document and in
  `docs/TOOL_CATALOG.md`. On the gateway roster they are spelled with `_`
  (`market_price`) because G-7 validates tool names against
  `^[a-z][a-z0-9_]{2,60}$` (`programming-desk/ci/gates/check_desk_integrity.py:46`).
- Risk budget values are desk defaults from D6 and are marked REVIEW; every one
  is a config field, not a constant.
- "Constitution" means the 10-clause block that every agent file carries verbatim
  (`agents/chief.md:27-37`, identical in the other seven files) plus
  `rules/pumpgrok-team.mdc:24-42`.

## 1. Seat summary

| Seat id | Display name (house style) | Channel | Writes exchange | Purpose (one line) | Old agent |
|---|---|---|---|---|---|
| bot-00-chief | CHIEF - Desk Orchestrator | Trading Floor | no | Supervisor/orchestrator; schedules cycles, routes, halts, escalates; never trades | agents/chief.md |
| bot-01-scout | SCOUT - Alpha Hunter | Trading Floor | no | Discovery of new launches and volume anomalies; emits LEADs | agents/scout.md |
| bot-02-risk | RISK - Absolute Safety Gate | Trading Floor | no | Risk/portfolio limits, kill switch, veto; QUALITY analogue (owns gates, contracts, ownership.yaml, SECURITY.md) | agents/risk.md |
| bot-03-whale | WHALE - Smart-Money Analyst | Trading Floor | no | Holder quality and capital-flow analysis after RISK CLEAR/CONDITIONAL | agents/whale.md |
| bot-04-sniper | SNIPER - Single-Write Execution | Trading Floor | paper-write | Entry execution: quote, simulate, place one paper buy per approved ticket | agents/sniper.md |
| bot-05-rug | RUG - Safety Monitor | Trading Floor | no | Pre-trade safety due diligence (scored report) and post-fill rug monitoring | agents/rug.md (post-fill) + risk.md checklist items 1-9 (pre-trade) |
| bot-06-exit | EXIT - Position Manager | DM / off-channel | paper-write | Exit rules (TP/SL/trailing/max-hold) and paper sell execution | agents/exit.md |
| bot-07-shill | SHILL - Sentiment and Velocity | DM / off-channel | no | Social sentiment detection only; never posts | agents/shill.md |
| bot-08-signal | SIGNAL - Momentum Scorer | DM / off-channel | no | Momentum/confidence scoring; ports vendor scoring + checker | new (vendor `src/scoring.py`, `src/agents/checker.py`) |
| bot-09-journal | JOURNAL - Post-Trade Ledger | DM / off-channel | no | Ledger of record, post-trade review, daily/weekly reports | new (CHIEF SOP 7 `agents/chief.md:58`, skill desk-post-trade-review, cron chief-journal-rollup `hermes/cron/jobs.yaml:57-66`) |

Only `bot-04-sniper` and `bot-06-exit` hold paper-write execution tools, carrying forward
`writes_to_exchange: true` from `agents/sniper.md:13` and `agents/exit.md:12`.

## 2. Trading Floor membership and the six-member cap

- `SETUP.md:109-113`: "Create a group chat named Trading Floor containing: CHIEF, SCOUT,
  RISK, WHALE, SNIPER, RUG (EXIT and SHILL can be added later or kept in DMs if the
  platform limit is six Bots.)"
- `programming-desk/docs/desk-operating-model.md:3-5`: "The six members are LEAD, SYSTEMS,
  WEB, ANDROID, IOS, and INFRA. QUALITY is off-channel for post-build merge-gate (platform
  max 6)."

Both desks are built on the same Grok Bot group-chat limit of six Bots. pumpgrok's channel
set is therefore fixed at the six seats `SETUP.md` already names; the four remaining
seats operate 1:1 with CHIEF (DM) and their human-visible output is relayed by CHIEF
into the channel, the same relay pattern programming-desk uses for its off-channel seat
(`desk-operating-model.md:17-18`).

| Channel | Seats |
|---|---|
| Trading Floor (6) | bot-00-chief, bot-01-scout, bot-02-risk, bot-03-whale, bot-04-sniper, bot-05-rug |
| DM / off-channel (4) | bot-06-exit, bot-07-shill, bot-08-signal, bot-09-journal |

Observation (reported, not resolved): programming-desk keeps its reviewer seat (QUALITY)
off-channel so that "a reviewer that can quietly reshape the interface it is reviewing is
not a reviewer" (`programming-desk/contracts/README.md:9`). D3 places RISK, the QUALITY
analogue, in channel because `SETUP.md:111` already does and because RISK verdicts are
channel-visible by constitution. The review-independence property is preserved by
`approved_by != self` in G-2 (`programming-desk/ci/gates/check_receipt.py` via
`scout-programming-desk.md` G-2 row) rather than by channel placement.

## 3. Old agent to new seat mapping

| Old (`agents/`) | frontmatter name/title | New seat | What moves | What changes |
|---|---|---|---|---|
| chief.md | CHIEF / Desk Orchestrator (`agents/chief.md:2-3`) | bot-00-chief | Constitution, SOPs 1-7, "Process compliance: PASS / FAIL" footer (`chief.md:71`) | Journal SOP 7 ownership of the ledger moves to bot-09-journal; CHIEF keeps the halt and routing authority and becomes the supervisor process owner |
| scout.md | SCOUT / Alpha Hunter (`scout.md:2-3`) | bot-01-scout | LEAD schema (`scout.md:47-59`), decision tree, pipeline consumption rules | Pipeline candidates come from `market.*`/`onchain.*` tools and the ported engine monitor instead of `tools/pipeline_evidence.py` |
| risk.md | RISK / Absolute Safety Gate (`risk.md:2-3`) | bot-02-risk | Verdict schema (`risk.md:51-57`), KILL finality, decision tree | The 10-check list (`risk.md:39-49`) becomes `safety.score_report`, executed by bot-05-rug pre-trade; RISK consumes the report and adds portfolio limits, kill switch, gate ownership |
| whale.md | WHALE / Smart-Money Analyst (`whale.md:2-3`) | bot-03-whale | Smart-Money schema (`whale.md:44-50`) | `holder_check.py` becomes `onchain.top_holders` + `market.holders_snapshot` |
| sniper.md | SNIPER / Single-Write Execution (`sniper.md:2-3`) | bot-04-sniper | Preconditions 1-4 (`sniper.md:40-44`), post-send rules, UNKNOWN RESULT (`sniper.md:54`) | Routing via `exec.quote/simulate/place`; the PaperAdapter is the only adapter; precondition 2 becomes a structured approval record checked by `risk.check_limits` |
| rug.md | RUG / Post-Entry Safety Monitor (`rug.md:2-3`) | bot-05-rug | Alert schema (`rug.md:45-49`), red-flag triggers (`rug.md:38-43`) | Gains the pre-trade due-diligence role (`safety.score_report`); still never closes (`rug.md:54`) |
| exit.md | EXIT / Position Manager (`exit.md:2-3`) | bot-06-exit | Rules (`exit.md:39-43`), NEVERs (`exit.md:45-48`) | Exit evaluator ported from vendor `src/risk.py:238` `exit_signal`; emergency exit still needs pre-authorised rule or human confirmation |
| shill.md | SHILL / Sentiment and Velocity (`shill.md:2-3`) | bot-07-shill | Output schema (`shill.md:37-43`) | Detection only (D7): no posting tool exists in any roster; vendor narrative agent output is a prior only |
| (none) | - | bot-08-signal | New | Ports vendor `compute_scores` (`vendor/grokbot-pumpfun/src/scoring.py:35`), `passes_threshold` (`scoring.py:58`), `CheckerAgent` (`src/agents/checker.py:53`) |
| (none) | - | bot-09-journal | New | Ledger, `journal.append`, `journal.render_report`; absorbs `tools/paper_sim.py` journal append (`tools/paper_sim.py:25-43`) and cron `chief-journal-rollup` (`hermes/cron/jobs.yaml:57-66`) |

## 4. Shared output schemas carried forward

These are the message shapes every seat must keep using. They become the
`contracts/events/*` JSON schemas (owned by bot-02-risk) listed in section 7.

| Schema | Source | Lines kept verbatim | Event file |
|---|---|---|---|
| LEAD | `agents/scout.md:47-59` | LEAD-ID, Mint, Source, Age, Initial Liquidity, Mint Authority (visible), Early Signals, Why this lead, Hand-off to RISK, UTC Timestamp, Total score (optional), Checker approve (optional) | `contracts/events/signal.schema.json` (`kind: lead`) |
| AUDIT (verdict) | `agents/risk.md:51-57` | LEAD / TICKET-ID, Verdict CLEAR/CONDITIONAL/KILL, Residual Risks, Evidence, Conditions, Self-Audit | `contracts/events/verdict.schema.json` |
| Smart-Money | `agents/whale.md:44-50` | LEAD-ID, Smart-Money Signal High/Medium/Low/None, Supporting Addresses, Clusters Detected, UTC Timestamp, Hand-off | `contracts/events/signal.schema.json` (`kind: whale`) |
| RUG alert | `agents/rug.md:45-49` | POSITION / TICKET-ID, Red Flag, Evidence, Recommended Action Emergency Exit/Watch/Escalate | `contracts/events/alert.schema.json` |
| EXIT report | `agents/exit.md:42` | signature, realised P&L, reason code, holding time, remaining balance | `contracts/events/fill.schema.json` (`side: sell`) |
| SNIPER fill report | `agents/sniper.md:53` | exact signature, fill amounts, realised slippage, priority fee paid, route | `contracts/events/fill.schema.json` (`side: buy`) |
| SHILL | `agents/shill.md:37-43` | LEAD / POSITION-ID, Velocity Score, Quality Organic/Mixed/Coordinated-Paid, Sources, Notes, Hand-off | `contracts/events/signal.schema.json` (`kind: social`) |
| Ticket | `rules/pumpgrok-team.mdc:28`, `tools/ticket_helper.py:28` (`SOL-\d{8}-\d{3}`) | ticket id, mint, size, slippage_bps, status | `contracts/events/order.schema.json` (`ticket_id` field) |
| Safety report (new) | `agents/risk.md:39-49` checklist items as `checks[]` | score 0..100, verdict, checks[{id, status, value, threshold, reason}], evidence[] | `contracts/events/safety_report.schema.json` |

The exact human approval phrase stays `approve <ticket> <mint> <size> <slippage>`
(`rules/pumpgrok-team.mdc:28`; `agents/sniper.md:42`). In code it is a parsed
`ApprovalRecord` (`docs/design/interfaces.md` section 9) that `risk.check_limits` requires
before `exec.place` can succeed (D9).

## 5. Seat manifests

Each manifest has the same field list (spec `PER_BOT_SKILL_MANIFEST`, xml line 90):
id, display, channel, purpose, inputs, outputs, skills, allowed_tools (with side-effect
class), risk_budget, forbidden, fail_safe, schedule, escalation, owned_paths, receipts,
prompt source, generated agent file. The YAML form of the same fields lives in the
`BotManifest` model in `docs/design/interfaces.md`.

Risk budget fields are shared by every seat so that `risk.check_limits` can evaluate any
seat's request uniformly: `max_position_pct` (of paper equity per trade),
`max_token_pct` (per token), `max_daily_loss_pct`, `max_drawdown_pct`,
`max_open_positions`. A seat that never trades carries zeros, which the registry treats as
"no exposure may be created by this seat".

### 5.1 bot-00-chief - CHIEF, Desk Orchestrator

| Field | Value |
|---|---|
| channel | Trading Floor |
| purpose | Supervisor and process guardian: runs the scheduler, routes SCOUT -> RUG(safety) -> RISK -> (WHALE, SIGNAL, SHILL) -> ticket -> human approval -> SNIPER -> RUG + EXIT -> JOURNAL (`agents/chief.md:49`); assigns ticket ids (`chief.md:52`); posts `FLOOR HALTED - DAILY LOSS LIMIT` (`chief.md:56`); restarts failed seats; escalates |
| inputs | all `contracts/events/*` events; `risk.halt_status`; seat heartbeats (`src/pumpgrok/supervisor`) |
| outputs | tickets (`order.schema.json`, status PENDING_RISK/PENDING_HUMAN/APPROVED/CLOSED), desk status block (skill desk-monitoring), halt notices, `Process compliance: PASS / FAIL` footer (`chief.md:71`) |
| skills (existing) | desk-operating-model, desk-trade-lifecycle, desk-risk-limits, desk-monitoring, desk-incident-response, pumpgrok-setup, tool-connections, grokbot-pipeline, hermes-cron-desk, desk-folders-and-journal (`agents/chief.md:6-15`; `hermes/profiles.yaml` adds the last two per `scout-pumpgrok-pack.md:41`) |
| skills (new) | verification-receipts, desk-doctor, kill-switch (status/clear only), live-gate-procedure (read: CHIEF reports preconditions, never flips the flag) |
| allowed_tools | desk.* core eight (read; `desk.event_emit`, `desk.memory_retain`, `desk.doctor` are paper-write per catalog); `risk.halt_status` (read); `risk.check_limits` (read); `portfolio.exposure` (read); `portfolio.pnl` (read); `exec.positions` (read); `notify.alert` (paper-write); `journal.append` (paper-write, kinds ticket/halt/escalation only) |
| risk_budget | max_position_pct 0, max_token_pct 0, max_daily_loss_pct 5 (halt trigger it enforces, REVIEW), max_drawdown_pct 15 (REVIEW), max_open_positions 0 |
| forbidden | trade, size, approve spends, override RISK, handle keys (`chief.md:60-69`); create tickets from pipeline output alone (`chief.md:74`); clear a halt without a human reset (`rules/pumpgrok-team.mdc:34`); D7 list |
| fail_safe | On any seat heartbeat miss, breaker trip, or `risk.halt_status.halted == true`: stop dispatching new leads, keep EXIT/RUG monitoring running, post observe-only status; never guesses |
| schedule | `pumpgrok run --mode paper` supervisor loop (always on); `pumpgrok chief pickup` every 15m (`hermes/cron/jobs.yaml:34-43`); health check every cycle |
| escalation | Human (Telegram via `notify.alert`, token profile `chief` per `hermes/profiles.yaml:16`) on: RISK KILL on an open ticket, daily-loss halt, breaker trip, repeated seat restarts (>3 in 10m REVIEW), stale data beyond threshold, any live-write attempt in the audit log |
| owned_paths | `docs/desk-operating-model.md`, `docs/cross-bot-protocol.md`, `docs/runbooks/**`, `prompts/bot-00-chief.xml`, `skills/desk-operating-model/**`, `skills/desk-trade-lifecycle/**`, `skills/desk-monitoring/**`, `skills/desk-incident-response/**`, `skills/pumpgrok-setup/**`, `skills/tool-connections/**`, `skills/hermes-cron-desk/**`, `skills/desk-folders-and-journal/**`, `scripts/generate-templates.py`, `scripts/assemble-prompts.sh`, `scripts/hermes-*.sh`, `hermes/**`, `src/pumpgrok/supervisor/**`, `src/pumpgrok/cli.py`, `desk_cli.py`, `README.md`, `.receipts/bot-00-chief/**` |
| receipts | `.receipts/bot-00-chief/` |
| prompt source | `prompts/bot-00-chief.xml` -> `prompts-assembled/CHIEF.xml` |
| generated | `agents/chief.md` (frontmatter name CHIEF, title Desk Orchestrator, seat Trading Floor, writes_to_exchange false) |

### 5.2 bot-01-scout - SCOUT, Alpha Hunter

| Field | Value |
|---|---|
| channel | Trading Floor |
| purpose | Continuous discovery: new launches (PumpPortal WS `subscribeNewToken`, `vendor/grokbot-pumpfun/src/monitor.py:219`), early-volume anomalies, launch-platform monitoring; emits structured LEADs (`agents/scout.md:47-59`) |
| inputs | `market.trades`, `market.liquidity`, `market.holders_snapshot`, `onchain.token_metadata`, `onchain.authorities`; ported engine monitor filter (`monitor.py:95` `passes_filter`); social priors from SHILL |
| outputs | LEAD events (`signal.schema.json`, kind lead) with mint, source, age, liquidity, visible mint authority, early signals, optional pipeline score |
| skills (existing) | discovery-tools, grokbot-pipeline, solana-market-data, social-sentiment, desk-trade-lifecycle (`agents/scout.md:6-11`), hermes-cron-desk |
| skills (new) | verification-receipts, rpc-hygiene, momentum-signals (consumer), desk-doctor |
| allowed_tools | desk.* core eight; `market.price`, `market.trades`, `market.liquidity`, `market.holders_snapshot` (read); `onchain.token_metadata`, `onchain.authorities` (read); `journal.append` (paper-write, kind lead) |
| risk_budget | all zero; max_open_positions 0 |
| forbidden | recommend size or urgency, clear risk, surface leads without verifiable mint + source, flood (`scout.md:75-79`); treat pipeline score as clearance (`scout.md:71`); D7 |
| fail_safe | Data source stale or WS disconnected -> emit no leads, set `data_stale` on heartbeat; never invents scores (`scout.md:72`) |
| schedule | `pumpgrok scout discover` every 60m; `pumpgrok scout pipeline` every 60m (`hermes/cron/jobs.yaml:12-21`, `:68-77`); event-driven on monitor stream in `pumpgrok run` |
| escalation | To CHIEF on data-source outage > 2 cycles (REVIEW); never to human directly |
| owned_paths | `src/pumpgrok/engine/monitor.py`, `src/pumpgrok/tools/market/**`, `skills/discovery-tools/**`, `skills/solana-market-data/**`, `skills/grokbot-pipeline/**`, `prompts/bot-01-scout.xml`, `tests/engine/test_monitor*.py`, `.receipts/bot-01-scout/**` |
| receipts | `.receipts/bot-01-scout/` |
| prompt source | `prompts/bot-01-scout.xml` -> `prompts-assembled/SCOUT.xml` |
| generated | `agents/scout.md` |

### 5.3 bot-02-risk - RISK, Absolute Safety Gate (QUALITY analogue)

| Field | Value |
|---|---|
| channel | Trading Floor |
| purpose | Portfolio risk limits, drawdown, breakers, kill switch; issues CLEAR/CONDITIONAL/KILL on every ticket (`agents/risk.md:51-57`); veto absolute (`risk.md:35`); independent reviewer: owns `ci/gates/**`, `contracts/**`, `ownership.yaml`, `SECURITY.md`; stamps `approved_by` on other seats' receipts |
| inputs | safety reports from RUG (`safety_report.schema.json`), LEADs, WHALE/SIGNAL/SHILL signals, `portfolio.exposure`, `portfolio.pnl`, `risk.drawdown`, breaker states |
| outputs | verdict events (`verdict.schema.json`), limit decisions (`risk.check_limits` result), kill switch state, halt notices, receipt approvals |
| skills (existing) | risk-audit, desk-risk-limits, grokbot-pipeline, solana-market-data, solana-rpc-and-wallet (`agents/risk.md:6-11`), holder-and-flow-analysis, desk-incident-response, hermes-cron-desk (`hermes/profiles.yaml` per `scout-pumpgrok-pack.md:43`) |
| skills (new) | verification-receipts, kill-switch, live-gate-procedure, key-custody, safety-scoring (consumer), portfolio-ledger (reader), desk-doctor |
| allowed_tools | desk.* core eight; `risk.check_limits`, `risk.drawdown`, `risk.halt_status` (read); `risk.kill_switch` (paper-write: set/clear/flatten request); `portfolio.exposure`, `portfolio.pnl`, `portfolio.ledger_read` (read); `safety.score_report` (read; may re-run); `onchain.authorities`, `onchain.lp_status`, `onchain.top_holders` (read, for spot re-checks); `notify.alert` (paper-write) |
| risk_budget | Owner of the desk-level budget (D6, all REVIEW): paper equity 10 SOL; max_position_pct 2; max_token_pct 5; max_daily_loss_pct 5 (constitutional floor halt, `rules/pumpgrok-team.mdc:34`); max_drawdown_pct 15; max_open_positions 3; liquidity floor 10x order size; partial-fill above 2% of pool liquidity |
| forbidden | soften a KILL, allow any seat past a KILL, skip or approximate a check (`risk.md:64-67`); place or cancel orders; raise its own limits without a human-signed config change; self-approve its own receipts (G-2 `approved_by != self`); D7 |
| fail_safe | Missing or stale data for any required check -> KILL / `BLIND - cannot proceed` (`risk.md:60`, constitution clause 10); kill switch set -> all `exec.place` calls refused at registry level; unwritable ledger -> refuse new orders |
| schedule | `pumpgrok risk audit` every 15m (`hermes/cron/jobs.yaml:23-32`); `risk.check_limits` is called synchronously on every order; kill switch file/env/command checked every supervisor cycle (D6) |
| escalation | Human on KILL of an approved ticket, daily-loss halt, drawdown halt, breaker trip, any live-write attempt |
| owned_paths | `ci/**`, `contracts/**` (contract_surface), `ownership.yaml`, `SECURITY.md`, `AGENTS.md`, `.gitignore`, `.pre-commit-config.yaml`, `.github/workflows/security-pr.yml`, `docs/quality-gates.md`, `docs/SAFETY_INVARIANTS.md`, `docs/RISK_POLICY.md`, `docs/ROSTER.md`, `docs/TOOL_CATALOG.md`, `docs/design/**`, `skills/README.md`, `skills/risk-audit/**`, `skills/desk-risk-limits/**`, `skills/verification-receipts/**`, `skills/kill-switch/**`, `skills/live-gate-procedure/**`, `skills/key-custody/**`, `skills/rpc-hygiene/**`, `skills/solana-rpc-and-wallet/**`, `src/pumpgrok/risk/**`, `src/pumpgrok/core/**`, `src/pumpgrok/config/**`, `src/pumpgrok/tools/risk/**`, `src/pumpgrok/execution/live/**` (disabled stubs), `tests/test_registry_least_privilege.py`, `tests/safety/**`, `prompts/bot-02-risk.xml`, `prompts/_shared/core-directives.xml`, `.receipts/bot-02-risk/**` |
| receipts | `.receipts/bot-02-risk/` |
| prompt source | `prompts/bot-02-risk.xml` -> `prompts-assembled/RISK.xml` |
| generated | `agents/risk.md` |

### 5.4 bot-03-whale - WHALE, Smart-Money Analyst

| Field | Value |
|---|---|
| channel | Trading Floor |
| purpose | Holder quality and capital-flow analysis after RISK CLEAR/CONDITIONAL (`agents/whale.md:36-42`) |
| inputs | verdict event (must be CLEAR or CONDITIONAL), `onchain.top_holders`, `onchain.large_transfers`, `onchain.deployer_history`, `market.holders_snapshot`, vendor priors `metrics.top5_share`, `creator_share`, `wallet_diversity`, `audit.organic_buyer_share` (`whale.md:53`) |
| outputs | Smart-Money signal event (`signal.schema.json`, kind whale) per `whale.md:44-50` |
| skills (existing) | holder-and-flow-analysis, solana-market-data, discovery-tools, grokbot-pipeline (`whale.md:6-10`) |
| skills (new) | verification-receipts, rpc-hygiene, desk-doctor |
| allowed_tools | desk.* core eight; `onchain.top_holders`, `onchain.large_transfers`, `onchain.deployer_history` (read); `market.holders_snapshot`, `market.trades` (read); `journal.append` (paper-write, kind whale) |
| risk_budget | all zero |
| forbidden | authorise a buy, override or upgrade a RISK KILL, treat social mentions as smart-money evidence (`whale.md:57-60`); D7 |
| fail_safe | `onchain.top_holders` unavailable -> signal `None` with `blind: true`; never skips live holder analysis because pipeline priors exist (`whale.md:54`) |
| schedule | Event-driven: on verdict CLEAR/CONDITIONAL; no cron |
| escalation | To CHIEF + RISK only (`whale.md:50`) |
| owned_paths | `src/pumpgrok/tools/onchain/holders.py`, `src/pumpgrok/tools/onchain/transfers.py`, `skills/holder-and-flow-analysis/**`, `prompts/bot-03-whale.xml`, `tests/tools/onchain/test_holders*.py`, `.receipts/bot-03-whale/**` |
| receipts | `.receipts/bot-03-whale/` |
| prompt source | `prompts/bot-03-whale.xml` -> `prompts-assembled/WHALE.xml` |
| generated | `agents/whale.md` |

### 5.5 bot-04-sniper - SNIPER, Single-Write Execution (paper)

| Field | Value |
|---|---|
| channel | Trading Floor |
| purpose | The only seat that places a buy. Executes exactly once per approved ticket with the approved parameters (`agents/sniper.md:38`) through `exec.quote -> exec.simulate -> exec.place` on the PaperAdapter |
| inputs | approved ticket (order event with `approval` record), verdict CLEAR/CONDITIONAL-satisfied, `risk.check_limits` pass, `market.price` (precondition 4 tolerance, `sniper.md:44`), `onchain.priority_fee` |
| outputs | fill event (`fill.schema.json`, side buy) with signature (paper: `paper:<idempotency_key>`), fill amounts, realised slippage, fee, route (`sniper.md:53`); `UNKNOWN RESULT - reconcile by signature` on timeout (`sniper.md:54`) |
| skills (existing) | jupiter-routing, desk-execution-protocol, solana-rpc-and-wallet, solana-api-reference, solana-market-data, grokbot-pipeline (`sniper.md:6-12`) |
| skills (new) | verification-receipts, paper-broker, rpc-hygiene, key-custody, desk-doctor |
| allowed_tools | desk.* core eight; `exec.quote`, `exec.simulate` (read); `exec.place` (paper-write, g6: `approval_id` required); `exec.cancel` (paper-write, own pending orders only); `exec.positions` (read); `market.price` (read); `onchain.priority_fee` (read). Roster total 8 + 7 = 15 (G-7 ceiling, `check_desk_integrity.py:41-42`) |
| risk_budget | max_position_pct 2 (REVIEW), max_token_pct 5 (REVIEW), max_daily_loss_pct 5, max_drawdown_pct 15, max_open_positions 3 (REVIEW); these are ceilings checked by `risk.check_limits`, SNIPER cannot raise them |
| forbidden | retry without new approval, change size or mint, execute a different token, hold the position after the fill (`sniper.md:57-61`); sell (`exit` only); resolve `risk.kill_switch`; call vendor LiveExecutor (`sniper.md:67`); any live-write; D7 |
| fail_safe | Any precondition unmet -> no call to `exec.place`; `exec.place` error or timeout -> single `UNKNOWN RESULT` report, no retry, ticket parked for human; kill switch or halt -> registry refuses `exec.place` |
| schedule | Never scheduled (`hermes/cron/jobs.yaml:79` `forbidden_owners: [sniper, exit]`); event-driven on `order.approved` |
| escalation | To CHIEF + human on UNKNOWN RESULT; to RISK on price outside tolerance |
| owned_paths | `src/pumpgrok/execution/paper_adapter.py`, `src/pumpgrok/execution/__init__.py`, `src/pumpgrok/tools/exec/**`, `skills/jupiter-routing/**`, `skills/desk-execution-protocol/**`, `skills/solana-api-reference/**`, `skills/paper-broker/**`, `prompts/bot-04-sniper.xml`, `tests/execution/test_paper_fill_model.py`, `tests/tools/exec/**`, `.receipts/bot-04-sniper/**` |
| receipts | `.receipts/bot-04-sniper/` |
| prompt source | `prompts/bot-04-sniper.xml` -> `prompts-assembled/SNIPER.xml` |
| generated | `agents/sniper.md` (writes_to_exchange true) |

### 5.6 bot-05-rug - RUG, Safety Monitor (pre-trade and post-fill)

| Field | Value |
|---|---|
| channel | Trading Floor |
| purpose | Pre-trade due diligence: runs `safety.score_report` (mint/freeze authority, LP status, tax, honeypot heuristics, concentration, bundler, deployer history, Token-2022 extensions, liquidity depth: the 10 checks at `agents/risk.md:39-49`) and hands the scored report to RISK. Post-fill: watches every open position for LP removal, mint events, insider sells, freeze/tax changes, suspicious programs (`agents/rug.md:38-43`) and raises structured alerts (`rug.md:45-49`) |
| inputs | LEAD events; fill events; `onchain.*`; `market.liquidity`; `market.trades` |
| outputs | safety report events (`safety_report.schema.json`); alert events (`alert.schema.json`) with Recommended Action Emergency Exit / Watch / Escalate |
| skills (existing) | position-monitoring, desk-monitoring, grokbot-pipeline, solana-market-data (`rug.md:6-10`), risk-audit (checklist procedure moves here), hermes-cron-desk |
| skills (new) | safety-scoring, verification-receipts, rpc-hygiene, desk-doctor |
| allowed_tools | desk.* core eight; `safety.score_report` (read); `onchain.token_metadata`, `onchain.authorities`, `onchain.lp_status`, `onchain.top_holders`, `onchain.deployer_history`, `onchain.large_transfers` (read); `market.liquidity` (read); `notify.alert` (paper-write) |
| risk_budget | all zero |
| forbidden | close a position, delay an alert because the position is in profit (`rug.md:53-55`); issue a CLEAR (only RISK issues verdicts); D7 |
| fail_safe | Any check without live data -> that check `status: blind`, report verdict `KILL` recommended (constitution clause 10); monitor poll failure 3x -> `blind` alert to CHIEF + EXIT (mirrors vendor `BLIND_AFTER=3`, `vendor/grokbot-pumpfun/src/risk.py` PositionWatcher) |
| schedule | `pumpgrok rug watch` every 30m when positions are open (`hermes/cron/jobs.yaml:45-55`, `require_open_positions: true`); in `pumpgrok run` the watcher polls every `stop_loss_poll_seconds` (REVIEW 15s, vendor default) |
| escalation | Alert to CHIEF + EXIT + human on any red flag (`rug.md:51`) |
| owned_paths | `src/pumpgrok/tools/safety/**`, `src/pumpgrok/tools/onchain/authorities.py`, `src/pumpgrok/tools/onchain/lp.py`, `src/pumpgrok/tools/onchain/metadata.py`, `src/pumpgrok/tools/onchain/deployer.py`, `src/pumpgrok/engine/watcher.py`, `skills/position-monitoring/**`, `skills/safety-scoring/**`, `prompts/bot-05-rug.xml`, `tests/tools/safety/**`, `.receipts/bot-05-rug/**` |
| receipts | `.receipts/bot-05-rug/` |
| prompt source | `prompts/bot-05-rug.xml` -> `prompts-assembled/RUG.xml` |
| generated | `agents/rug.md` |

### 5.7 bot-06-exit - EXIT, Position Manager (paper)

| Field | Value |
|---|---|
| channel | DM / off-channel (relayed by CHIEF) |
| purpose | Owns the sell side only (`agents/exit.md:35`). Evaluates pre-agreed take-profit / stop-loss / trailing / max-hold rules (vendor `exit_signal`, `vendor/grokbot-pumpfun/src/risk.py:238-280`, priority stop_loss -> take_profit -> trailing_stop -> max_hold) and executes paper sells through `exec.quote -> exec.simulate -> exec.place(side=sell)` |
| inputs | open positions (`exec.positions`), `market.price`, RUG alerts, exit-rule config, human emergency-exit confirmation |
| outputs | fill events (side sell) with signature, realised P&L, reason code, holding time, remaining balance (`exit.md:42`); emergency exit ticket requests |
| skills (existing) | position-monitoring, desk-execution-protocol, desk-post-trade-review, jupiter-routing, grokbot-pipeline (`exit.md:6-11`) |
| skills (new) | paper-broker, verification-receipts, rpc-hygiene, key-custody, desk-doctor |
| allowed_tools | desk.* core eight; `exec.quote`, `exec.simulate` (read); `exec.place` (paper-write, side sell only, g6 `approval_id` = rule id or human approval); `exec.cancel` (paper-write, own pending orders); `exec.positions` (read); `market.price` (read); `onchain.priority_fee` (read). Roster 8 + 7 = 15 |
| risk_budget | max_position_pct 0 (cannot increase exposure), max_token_pct 0, max_daily_loss_pct 5, max_drawdown_pct 15, max_open_positions 0 (never opens) |
| forbidden | open new positions, increase size, emergency exit without pre-authorised rules or fresh human confirmation (`exit.md:45-48`); auto-sell because the dry-run engine closed (`exit.md:53`); any live-write; D7 |
| fail_safe | Price blind for 3 polls -> `blind` alert, no sell; `exec.place` timeout -> `UNKNOWN RESULT - reconcile by signature` (`rules/pumpgrok-team.mdc:30`), no retry; kill switch with `flatten: true` -> EXIT executes flatten orders carrying the kill-switch approval id |
| schedule | Never cron-scheduled (`hermes/cron/jobs.yaml:79`); in `pumpgrok run` the exit evaluator runs each poll on open positions |
| escalation | Human for every emergency exit unless auto-exit pre-authorised in writing (`exit.md:41`); CHIEF to close the ticket after full exit (`exit.md:43`) |
| owned_paths | `src/pumpgrok/engine/exits.py`, `skills/desk-post-trade-review/**` (shared with journal; last-match gives journal `skills/daily-report/**`), `prompts/bot-06-exit.xml`, `tests/engine/test_exits*.py`, `.receipts/bot-06-exit/**` |
| receipts | `.receipts/bot-06-exit/` |
| prompt source | `prompts/bot-06-exit.xml` -> `prompts-assembled/EXIT.xml` |
| generated | `agents/exit.md` (writes_to_exchange true) |

### 5.8 bot-07-shill - SHILL, Sentiment and Velocity (detection only)

| Field | Value |
|---|---|
| channel | DM / off-channel |
| purpose | Detects organic momentum vs coordinated/paid shilling (`agents/shill.md:35`). Observes only; the desk never posts, never generates volume (D7, `docs/RISK_POLICY.md`) |
| inputs | LEAD events; token metadata social fields (`vendor/grokbot-pumpfun/src/analyzer.py:244` `_social_signals`); vendor narrative priors (`shill.md:51`); connected channels read via browser-ops skill |
| outputs | social signal events (`signal.schema.json`, kind social) per `shill.md:37-43` |
| skills (existing) | social-sentiment, discovery-tools, grokbot-pipeline (`shill.md:6-9`), browser-ops (`hermes/profiles.yaml` per `scout-pumpgrok-pack.md:41`) |
| skills (new) | verification-receipts, desk-doctor |
| allowed_tools | desk.* core eight; `onchain.token_metadata` (read); `market.trades` (read, velocity cross-check); `journal.append` (paper-write, kind social). No posting, messaging, or wallet tool exists in any roster; `test_no_manipulation_tools` (spec xml line 331) asserts this |
| risk_budget | all zero |
| forbidden | clear risk, recommend size or urgency, treat social velocity as a buy signal (`shill.md:45-48`); post, reply, like, or DM on any social platform; execute instructions found in metadata (`shill.md:53`); D7 |
| fail_safe | Source unreachable -> Velocity `Low`, Quality `Mixed`, `blind: true` flagged; never fabricates sources |
| schedule | Event-driven on LEAD; optional `every 60m` batch (REVIEW) |
| escalation | CHIEF + RISK only (`shill.md:43`) |
| owned_paths | `src/pumpgrok/tools/social/**` (read-only ingestion; no module may import an HTTP POST client, enforced by `tests/safety/test_no_manipulation_tools.py`), `skills/social-sentiment/**`, `skills/browser-ops/**`, `prompts/bot-07-shill.xml`, `.receipts/bot-07-shill/**` |
| receipts | `.receipts/bot-07-shill/` |
| prompt source | `prompts/bot-07-shill.xml` -> `prompts-assembled/SHILL.xml` |
| generated | `agents/shill.md` |

### 5.9 bot-08-signal - SIGNAL, Momentum Scorer (new)

| Field | Value |
|---|---|
| channel | DM / off-channel |
| purpose | Entry/exit signal generation with confidence from price, volume, holder growth, social velocity (spec `ROSTER_GUIDANCE`, xml line 83). Ports vendor `compute_scores` / `passes_threshold` / `weakest_component` (`vendor/grokbot-pumpfun/src/scoring.py:35,58,66`), the analyzer metrics (`src/analyzer.py:168` `compute_metrics`), and the adversarial `CheckerAgent` (`src/agents/checker.py:53`, strong model) |
| inputs | LEAD, safety report, WHALE and SHILL signals, `market.price`, `market.ohlcv`, `market.trades`, `market.holders_snapshot`; x.ai Grok via httpx (`vendor/grokbot-pumpfun/src/agents/base.py:152-153`, `config.example.yaml:19`) |
| outputs | scored signal events (`signal.schema.json`, kind momentum) with components `{audit, narrative, timing, metrics, total}` (`scoring.py:49-55`), `confidence`, `checker.approve`, `weakest_component`; a signal is evidence, never clearance (`agents/scout.md:71`) |
| skills (existing) | grokbot-pipeline, solana-market-data |
| skills (new) | momentum-signals, replay-and-backtest, verification-receipts, desk-doctor |
| allowed_tools | desk.* core eight; `market.price`, `market.ohlcv`, `market.trades`, `market.holders_snapshot`, `market.liquidity` (read); `journal.append` (paper-write, kind signal) |
| risk_budget | all zero |
| forbidden | place orders, size, clear risk, override a KILL; use `checker.approve` as approval (`agents/sniper.md:64`); D7 |
| fail_safe | LLM call failure after retries -> rule-based score with `llm_degraded: true` (vendor `GrokAgent.run` pessimistic fallback, `src/agents/base.py:89`; D5); missing component counts as 0.0 (`scoring.py:18` `MISSING_COMPONENT`) |
| schedule | Event-driven on LEAD + safety report; `pumpgrok run --replay <dir>` for backtests |
| escalation | CHIEF on LLM budget exhausted or breaker open (vendor `GrokOps`, `src/ops.py:235`) |
| owned_paths | `src/pumpgrok/engine/scoring.py`, `src/pumpgrok/engine/analyzer.py`, `src/pumpgrok/engine/agents/**`, `src/pumpgrok/replay/**`, `skills/momentum-signals/**`, `skills/replay-and-backtest/**`, `prompts/bot-08-signal.xml`, `tests/engine/test_scoring*.py`, `tests/engine/test_agents*.py`, `tests/replay/**`, `tests/fixtures/replay/**`, `.receipts/bot-08-signal/**` |
| receipts | `.receipts/bot-08-signal/` |
| prompt source | `prompts/bot-08-signal.xml` -> `prompts-assembled/SIGNAL.xml` |
| generated | `agents/signal.md` (new; frontmatter name SIGNAL, title Momentum Scorer, seat DM, writes_to_exchange false) |

### 5.10 bot-09-journal - JOURNAL, Post-Trade Ledger (new)

| Field | Value |
|---|---|
| channel | DM / off-channel |
| purpose | Ledger of record (sqlite WAL append-only events + snapshots, D5), post-trade review grading (skill desk-post-trade-review: Process Grade A/B/C/F, Outcome Win/Scratch/Loss per `scout-pumpgrok-pack.md:55`), PnL attribution, daily/weekly reports that the 2-4 week paper evaluation is judged on (spec `REPORTING`, xml line 108) |
| inputs | every event on the bus (lead, safety_report, verdict, order, fill, alert); `portfolio.ledger_read`; `portfolio.pnl` |
| outputs | journal entries (`journal.append`), JSONL export, daily report (`journal.render_report --daily`), weekly report, ticket close records for CHIEF |
| skills (existing) | desk-post-trade-review, desk-folders-and-journal, hermes-cron-desk |
| skills (new) | portfolio-ledger, daily-report, verification-receipts, desk-doctor |
| allowed_tools | desk.* core eight; `journal.append` (paper-write, all kinds); `journal.render_report` (paper-write: writes report file); `portfolio.ledger_read`, `portfolio.pnl`, `portfolio.exposure` (read); `exec.positions` (read); `notify.alert` (paper-write, report delivery only) |
| risk_budget | all zero |
| forbidden | place or cancel orders; mutate past journal entries (append-only, skill desk-folders-and-journal); write `portfolio.ledger_write` (only the execution path writes fills); D7 |
| fail_safe | Ledger unwritable -> raises `LedgerUnavailable`, supervisor sets `orders_refused` and alerts; report rendering failure -> alert, no silent skip (cron heartbeat semantics of `chief-journal-rollup`, `hermes/cron/jobs.yaml:57-66`) |
| schedule | `pumpgrok journal rollup` daily `0 12 * * *` (`hermes/cron/jobs.yaml:60`); `pumpgrok report --daily` at UTC day roll; `pumpgrok report --weekly` Monday 00:10 UTC (REVIEW); `journal.append` is synchronous on every event |
| escalation | Human via `notify.alert` on ledger reconciliation mismatch after restart |
| owned_paths | `src/pumpgrok/ledger/**`, `src/pumpgrok/reporting/**`, `src/pumpgrok/tools/journal/**`, `src/pumpgrok/tools/portfolio/**`, `skills/portfolio-ledger/**`, `skills/daily-report/**`, `skills/desk-post-trade-review/**`, `prompts/bot-09-journal.xml`, `CHANGELOG.md`, `tests/ledger/**`, `tests/reporting/**`, `.receipts/bot-09-journal/**` |
| receipts | `.receipts/bot-09-journal/` |
| prompt source | `prompts/bot-09-journal.xml` -> `prompts-assembled/JOURNAL.xml` |
| generated | `agents/journal.md` (new) |

## 6. Least-privilege matrix

`x` = resolvable through `ToolRegistry.find`; `w` = resolvable as paper-write; blank =
`PermissionDenied`. `live-write` has no column: it is never resolvable (D3, D4). The core
eight `desk.*` tools are granted to every seat and omitted here.

| Tool | chief | scout | risk | whale | sniper | rug | exit | shill | signal | journal |
|---|---|---|---|---|---|---|---|---|---|---|
| market.price | | x | | | x | | x | | x | |
| market.ohlcv | | | | | | | | | x | |
| market.liquidity | | x | | | | x | | | x | |
| market.trades | | x | | x | | | | x | x | |
| market.holders_snapshot | | x | | x | | | | | x | |
| onchain.token_metadata | | x | | | | x | | x | | |
| onchain.authorities | | x | x | | | x | | | | |
| onchain.lp_status | | | x | | | x | | | | |
| onchain.top_holders | | | x | x | | x | | | | |
| onchain.deployer_history | | | | x | | x | | | | |
| onchain.large_transfers | | | | x | | x | | | | |
| onchain.priority_fee | | | | | x | | x | | | |
| safety.score_report | | | x | | | x | | | | |
| exec.quote | | | | | x | | x | | | |
| exec.simulate | | | | | x | | x | | | |
| exec.place | | | | | w | | w | | | |
| exec.cancel | | | | | w | | w | | | |
| exec.positions | x | | | | x | | x | | | x |
| portfolio.ledger_read | | | x | | | | | | | x |
| portfolio.ledger_write | | | | | (adapter) | | (adapter) | | | |
| portfolio.exposure | x | | x | | | | | | | x |
| portfolio.pnl | x | | x | | | | | | | x |
| risk.check_limits | x | | x | | (registry) | | (registry) | | | |
| risk.drawdown | | | x | | | | | | | |
| risk.kill_switch | | | w | | | | | | | |
| risk.halt_status | x | | x | | | | | | | |
| notify.alert | w | | w | | | w | | | | w |
| journal.append | w | w | | w | | | | w | w | w |
| journal.render_report | | | | | | | | | | w |

Notes:

- `portfolio.ledger_write` is not granted to any seat. The PaperAdapter calls it in-process
  under the sniper/exit correlation id; a seat prompt cannot invoke it
  (`docs/TOOL_CATALOG.md` section 5).
- `risk.check_limits` is invoked by the registry wrapper around `exec.place` for sniper
  and exit (`docs/design/interfaces.md` section 7), so those seats do not need it in their
  roster and the roster stays at 15.
- Tests that prove this matrix: `tests/test_registry_least_privilege.py` (see
  `docs/design/interfaces.md` section 12).

## 7. ownership.yaml draft

Mirrors `programming-desk/ownership.yaml` (header `:1-19`, `bots:` `:21-70`,
`ownership:` `:73-433`, `contract_consumers:` `:441-466`). Semantics: last match wins,
unowned path fails G-1, duplicate patterns rejected by `--validate-manifest`
(`scout-programming-desk.md:49`). General suffix rules first, directory and file overrides
after, `**/*.proto` last.

```yaml
# Path ownership manifest for the pumpgrok trading desk.
# Every file resolves to EXACTLY ONE owning seat. LAST matching pattern wins.
# A path matching nothing is UNOWNED and ci/gates/check_ownership.py fails the build.
# Validate:  python3 ci/gates/check_ownership.py --validate-manifest
version: 1

bots:
  bot-00-chief:
    name: CHIEF - Desk Orchestrator
    description: >
      Supervisor and process guardian. Routes, halts, escalates, owns the scheduler and
      orchestration docs. Never trades, never sizes, never holds keys. In channel.
  bot-01-scout:
    name: SCOUT - Alpha Hunter
    languages: [python]
    description: Discovery of new launches and volume anomalies. Read-only market tools.
  bot-02-risk:
    name: RISK - Absolute Safety Gate
    languages: [python]
    description: >
      Portfolio limits, drawdown, breakers, kill switch, verdicts. Independent reviewer:
      owns gates, contracts, ownership.yaml, SECURITY.md. Veto is absolute. In channel.
  bot-03-whale:
    name: WHALE - Smart-Money Analyst
    languages: [python]
    description: Holder quality and capital-flow analysis. Read-only on-chain tools.
  bot-04-sniper:
    name: SNIPER - Single-Write Execution
    languages: [python]
    description: Entry execution through the PaperAdapter. Paper-write only. Owns execution/.
  bot-05-rug:
    name: RUG - Safety Monitor
    languages: [python]
    description: Pre-trade safety scoring and post-fill rug monitoring. Owns tools/safety.
  bot-06-exit:
    name: EXIT - Position Manager
    languages: [python]
    description: Exit rules and paper sell execution. Paper-write only. Off-channel.
  bot-07-shill:
    name: SHILL - Sentiment and Velocity
    languages: [python]
    description: Social sentiment detection only. Never posts. Off-channel.
  bot-08-signal:
    name: SIGNAL - Momentum Scorer
    languages: [python]
    description: Momentum and confidence scoring; ported vendor scoring and checker. Off-channel.
  bot-09-journal:
    name: JOURNAL - Post-Trade Ledger
    languages: [python]
    description: Ledger of record, post-trade review, daily and weekly reports. Off-channel.

ownership:
  # --- General suffix rules (first, so directory rules below override) ----
  - pattern: "**/*.py"
    owner: bot-02-risk
  - pattern: "**/*.md"
    owner: bot-02-risk
  - pattern: "**/*.yaml"
    owner: bot-02-risk
  - pattern: "**/*.yml"
    owner: bot-02-risk
  - pattern: "**/*.toml"
    owner: bot-02-risk
  - pattern: "**/*.json"
    owner: bot-02-risk
  - pattern: "**/*.jsonl"
    owner: bot-09-journal
  - pattern: "**/*.xml"
    owner: bot-00-chief
  - pattern: "**/*.sh"
    owner: bot-00-chief
  - pattern: "**/*.mdc"
    owner: bot-02-risk
  - pattern: "**/.gitkeep"
    owner: bot-02-risk

  # --- Root files ----------------------------------------------------------
  - pattern: "README.md"
    owner: bot-00-chief
  - pattern: "AGENTS.md"
    owner: bot-02-risk
  - pattern: "ARCHITECTURE.md"
    owner: bot-02-risk
  - pattern: "SECURITY.md"
    owner: bot-02-risk
  - pattern: "CHANGELOG.md"
    owner: bot-09-journal
  - pattern: "SETUP.md"
    owner: bot-00-chief
  - pattern: "LICENSE"
    owner: bot-02-risk
  - pattern: "ownership.yaml"
    owner: bot-02-risk
  - pattern: "openapi.yaml"
    owner: bot-02-risk
    contract_surface: true
  - pattern: ".pre-commit-config.yaml"
    owner: bot-02-risk
  - pattern: ".gitignore"
    owner: bot-02-risk
  - pattern: ".devcontainer.json"
    owner: bot-02-risk
  - pattern: "desk_cli.py"
    owner: bot-00-chief
  - pattern: "pyproject.toml"
    owner: bot-02-risk
  - pattern: "uv.lock"
    owner: bot-02-risk
  - pattern: "Makefile"
    owner: bot-02-risk
  - pattern: "Dockerfile"
    owner: bot-02-risk
  - pattern: "docker-compose.yml"
    owner: bot-02-risk
  - pattern: ".env.example"
    owner: bot-02-risk
  - pattern: "plugin.json"
    owner: bot-00-chief
  - pattern: ".claude-plugin/**"
    owner: bot-00-chief
  - pattern: ".grok-plugin/**"
    owner: bot-00-chief
  - pattern: ".cursor-plugin/**"
    owner: bot-00-chief
  - pattern: "issues/**"
    owner: bot-00-chief

  # --- CI, gates, security (RISK = QUALITY analogue) ----------------------
  - pattern: ".github/workflows/**"
    owner: bot-02-risk
  - pattern: "ci/**"
    owner: bot-02-risk

  # --- Contracts: the only shared surface ---------------------------------
  - pattern: "contracts/**"
    owner: bot-02-risk
    contract_surface: true

  # --- Docs: RISK owns by default; CHIEF owns orchestration docs ----------
  - pattern: "docs/**"
    owner: bot-02-risk
  - pattern: "docs/desk-operating-model.md"
    owner: bot-00-chief
  - pattern: "docs/cross-bot-protocol.md"
    owner: bot-00-chief
  - pattern: "docs/runbooks/**"
    owner: bot-00-chief
  - pattern: "docs/design/paper-engine.md"
    owner: bot-04-sniper

  # --- Prompts: shared core is RISK; each seat owns its own source --------
  - pattern: "prompts/**"
    owner: bot-02-risk
  - pattern: "prompts/bot-00-chief.xml"
    owner: bot-00-chief
  - pattern: "prompts/bot-01-scout.xml"
    owner: bot-01-scout
  - pattern: "prompts/bot-02-risk.xml"
    owner: bot-02-risk
  - pattern: "prompts/bot-03-whale.xml"
    owner: bot-03-whale
  - pattern: "prompts/bot-04-sniper.xml"
    owner: bot-04-sniper
  - pattern: "prompts/bot-05-rug.xml"
    owner: bot-05-rug
  - pattern: "prompts/bot-06-exit.xml"
    owner: bot-06-exit
  - pattern: "prompts/bot-07-shill.xml"
    owner: bot-07-shill
  - pattern: "prompts/bot-08-signal.xml"
    owner: bot-08-signal
  - pattern: "prompts/bot-09-journal.xml"
    owner: bot-09-journal
  - pattern: "prompts-assembled/**"
    owner: bot-00-chief
  - pattern: "agents/**"
    owner: bot-00-chief
  - pattern: "rules/**"
    owner: bot-02-risk
  - pattern: "scripts/**"
    owner: bot-00-chief
  - pattern: "scripts/check.sh"
    owner: bot-02-risk
  - pattern: "hermes/**"
    owner: bot-00-chief

  # --- Skills: RISK by default; seat-specific overrides -------------------
  - pattern: "skills/**"
    owner: bot-02-risk
  - pattern: "skills/desk-operating-model/**"
    owner: bot-00-chief
  - pattern: "skills/desk-trade-lifecycle/**"
    owner: bot-00-chief
  - pattern: "skills/desk-monitoring/**"
    owner: bot-00-chief
  - pattern: "skills/desk-incident-response/**"
    owner: bot-00-chief
  - pattern: "skills/pumpgrok-setup/**"
    owner: bot-00-chief
  - pattern: "skills/tool-connections/**"
    owner: bot-00-chief
  - pattern: "skills/hermes-cron-desk/**"
    owner: bot-00-chief
  - pattern: "skills/desk-folders-and-journal/**"
    owner: bot-00-chief
  - pattern: "skills/desk-doctor/**"
    owner: bot-00-chief
  - pattern: "skills/discovery-tools/**"
    owner: bot-01-scout
  - pattern: "skills/solana-market-data/**"
    owner: bot-01-scout
  - pattern: "skills/grokbot-pipeline/**"
    owner: bot-01-scout
  - pattern: "skills/holder-and-flow-analysis/**"
    owner: bot-03-whale
  - pattern: "skills/jupiter-routing/**"
    owner: bot-04-sniper
  - pattern: "skills/desk-execution-protocol/**"
    owner: bot-04-sniper
  - pattern: "skills/solana-api-reference/**"
    owner: bot-04-sniper
  - pattern: "skills/paper-broker/**"
    owner: bot-04-sniper
  - pattern: "skills/position-monitoring/**"
    owner: bot-05-rug
  - pattern: "skills/safety-scoring/**"
    owner: bot-05-rug
  - pattern: "skills/desk-strategy-lab/**"
    owner: bot-06-exit
  - pattern: "skills/social-sentiment/**"
    owner: bot-07-shill
  - pattern: "skills/browser-ops/**"
    owner: bot-07-shill
  - pattern: "skills/momentum-signals/**"
    owner: bot-08-signal
  - pattern: "skills/replay-and-backtest/**"
    owner: bot-08-signal
  - pattern: "skills/desk-post-trade-review/**"
    owner: bot-09-journal
  - pattern: "skills/portfolio-ledger/**"
    owner: bot-09-journal
  - pattern: "skills/daily-report/**"
    owner: bot-09-journal

  # --- Source: RISK owns core/config/risk; seats own their modules --------
  - pattern: "src/pumpgrok/**"
    owner: bot-02-risk
  - pattern: "src/pumpgrok/cli.py"
    owner: bot-00-chief
  - pattern: "src/pumpgrok/supervisor/**"
    owner: bot-00-chief
  - pattern: "src/pumpgrok/logging/**"
    owner: bot-00-chief
  - pattern: "src/pumpgrok/tools/market/**"
    owner: bot-01-scout
  - pattern: "src/pumpgrok/tools/onchain/**"
    owner: bot-05-rug
  - pattern: "src/pumpgrok/tools/onchain/holders.py"
    owner: bot-03-whale
  - pattern: "src/pumpgrok/tools/onchain/transfers.py"
    owner: bot-03-whale
  - pattern: "src/pumpgrok/tools/safety/**"
    owner: bot-05-rug
  - pattern: "src/pumpgrok/tools/exec/**"
    owner: bot-04-sniper
  - pattern: "src/pumpgrok/execution/**"
    owner: bot-04-sniper
  - pattern: "src/pumpgrok/execution/live/**"
    owner: bot-02-risk
  - pattern: "src/pumpgrok/tools/social/**"
    owner: bot-07-shill
  - pattern: "src/pumpgrok/engine/**"
    owner: bot-08-signal
  - pattern: "src/pumpgrok/engine/monitor.py"
    owner: bot-01-scout
  - pattern: "src/pumpgrok/engine/watcher.py"
    owner: bot-05-rug
  - pattern: "src/pumpgrok/engine/exits.py"
    owner: bot-06-exit
  - pattern: "src/pumpgrok/replay/**"
    owner: bot-08-signal
  - pattern: "src/pumpgrok/ledger/**"
    owner: bot-09-journal
  - pattern: "src/pumpgrok/reporting/**"
    owner: bot-09-journal
  - pattern: "src/pumpgrok/tools/journal/**"
    owner: bot-09-journal
  - pattern: "src/pumpgrok/tools/portfolio/**"
    owner: bot-09-journal
  - pattern: "src/pumpgrok/tools/notify/**"
    owner: bot-00-chief
  - pattern: "src/pumpgrok/tools/risk/**"
    owner: bot-02-risk
  - pattern: "src/pumpgrok/risk/**"
    owner: bot-02-risk
  - pattern: "src/pumpgrok/core/**"
    owner: bot-02-risk
  - pattern: "src/pumpgrok/config/**"
    owner: bot-02-risk
  - pattern: "services/desk-gateway/**"
    owner: bot-00-chief
  - pattern: "tools/**"
    owner: bot-02-risk
  - pattern: "vendor/**"
    owner: bot-02-risk

  # --- Tests follow the module they pin -----------------------------------
  - pattern: "tests/**"
    owner: bot-02-risk
  - pattern: "tests/engine/**"
    owner: bot-08-signal
  - pattern: "tests/engine/test_monitor*.py"
    owner: bot-01-scout
  - pattern: "tests/engine/test_watcher*.py"
    owner: bot-05-rug
  - pattern: "tests/engine/test_exits*.py"
    owner: bot-06-exit
  - pattern: "tests/replay/**"
    owner: bot-08-signal
  - pattern: "tests/fixtures/replay/**"
    owner: bot-08-signal
  - pattern: "tests/execution/**"
    owner: bot-04-sniper
  - pattern: "tests/tools/exec/**"
    owner: bot-04-sniper
  - pattern: "tests/tools/market/**"
    owner: bot-01-scout
  - pattern: "tests/tools/safety/**"
    owner: bot-05-rug
  - pattern: "tests/tools/onchain/**"
    owner: bot-05-rug
  - pattern: "tests/ledger/**"
    owner: bot-09-journal
  - pattern: "tests/reporting/**"
    owner: bot-09-journal
  - pattern: "tests/desk/**"
    owner: bot-00-chief
  - pattern: "tests/safety/**"
    owner: bot-02-risk
  - pattern: "tests/test_registry_least_privilege.py"
    owner: bot-02-risk
  - pattern: "tests/characterization/**"
    owner: bot-02-risk

  # --- Receipts: one rule per seat ----------------------------------------
  - pattern: ".receipts/bot-00-chief/**"
    owner: bot-00-chief
  - pattern: ".receipts/bot-01-scout/**"
    owner: bot-01-scout
  - pattern: ".receipts/bot-02-risk/**"
    owner: bot-02-risk
  - pattern: ".receipts/bot-03-whale/**"
    owner: bot-03-whale
  - pattern: ".receipts/bot-04-sniper/**"
    owner: bot-04-sniper
  - pattern: ".receipts/bot-05-rug/**"
    owner: bot-05-rug
  - pattern: ".receipts/bot-06-exit/**"
    owner: bot-06-exit
  - pattern: ".receipts/bot-07-shill/**"
    owner: bot-07-shill
  - pattern: ".receipts/bot-08-signal/**"
    owner: bot-08-signal
  - pattern: ".receipts/bot-09-journal/**"
    owner: bot-09-journal

  # --- Runtime state is gitignored; the .gitkeep that pins it is RISK's ----
  - pattern: "var/**"
    owner: bot-02-risk

  # --- Always LAST (programming-desk/ownership.yaml:431-433) ---------------
  - pattern: "**/*.proto"
    owner: bot-02-risk
    contract_surface: true

contract_consumers:
  "contracts/events/**":
    - bot-00-chief
    - bot-01-scout
    - bot-02-risk
    - bot-03-whale
    - bot-04-sniper
    - bot-05-rug
    - bot-06-exit
    - bot-07-shill
    - bot-08-signal
    - bot-09-journal
  "contracts/tool-rosters/**":
    - bot-00-chief
    - bot-01-scout
    - bot-02-risk
    - bot-03-whale
    - bot-04-sniper
    - bot-05-rug
    - bot-06-exit
    - bot-07-shill
    - bot-08-signal
    - bot-09-journal
  "openapi.yaml":
    - bot-00-chief
    - bot-09-journal
```

`contract_consumers` for `contracts/events/**` and `contracts/tool-rosters/**` list all ten
seats because every seat reads the event envelope and sees a roster
(`programming-desk/ownership.yaml:454-461` lists all seven for tool-rosters).

## 8. Contracts directory contents (owned by bot-02-risk)

| Path | Purpose | Consumers |
|---|---|---|
| `contracts/README.md` | Copy of the programming-desk layout text adapted to events + tool-rosters | all |
| `contracts/tool-rosters/_core.yaml` | desk.* core eight | all |
| `contracts/tool-rosters/{chief,scout,risk,whale,sniper,rug,exit,shill,signal,journal}.yaml` | per-seat tools; effective roster = core 8 + seat tools, 10..15 | the named seat |
| `contracts/events/signal.schema.json` | LEAD, whale, social, momentum signals (discriminator `kind`) | all |
| `contracts/events/safety_report.schema.json` | scored safety report | risk, rug, signal, sniper, journal |
| `contracts/events/order.schema.json` | ticket + order + approval record | chief, risk, sniper, exit, journal |
| `contracts/events/fill.schema.json` | paper fills, buy and sell | chief, risk, rug, exit, journal |
| `contracts/events/verdict.schema.json` | CLEAR/CONDITIONAL/KILL | all |
| `contracts/events/alert.schema.json` | RUG alerts, breaker, halt, kill-switch, escalation | all |
| `contracts/changes/` | one change doc per contract change (G-4) | - |

## 9. Receipts and prompts

- Receipts: `.receipts/<seat-id>/<task-id>.json`, `.gitkeep` tracked, JSON gitignored
  (`programming-desk/.gitignore` per `scout-programming-desk.md:42`). Required fields
  `task_id, bot, commands, claims, unverified` (`programming-desk/ci/gates/check_receipt.py:48`
  per `scout-programming-desk.md:101`). Trading-specific claims cite ledger-query commands
  (`pumpgrok paper ...`, `pumpgrok state status`).
- Prompts: `prompts/_shared/core-directives.xml` (audiences `trading-seats | chief | risk`)
  + `prompts/bot-0N-<seat>.xml` -> `scripts/assemble-prompts.sh` ->
  `prompts-assembled/<SEAT>.xml` with SEAT in
  `CHIEF SCOUT RISK WHALE SNIPER RUG EXIT SHILL SIGNAL JOURNAL`.
- `scripts/generate-templates.py` renders `agents/<seat>.md` keeping today's frontmatter
  contract (`name`, `title`, `description`, `seat`, `skills`, `writes_to_exchange`;
  `agents/chief.md:1-17`) so `scripts/check.sh:60-80` keeps passing. `seat:` becomes
  `Trading Floor` or `DM`.

## Unverified Items

| Item | Default assumed |
|---|---|
| Grok Bot group-chat limit is exactly six (`SETUP.md:113` says "if the platform limit is six"; `desk-operating-model.md:5` states "platform max 6") | Six; four seats stay in DM |
| programming-desk `check_receipt.py:48` REQUIRED_FIELDS and `.gitignore` receipt rules were taken from `scout-programming-desk.md`, not re-read here | As the scout reports |
| Whether `hermes/profiles.yaml` seat-skill lists or `agents/*.md` frontmatter is canonical (they differ, `scout-pumpgrok-pack.md:43`) | Union of both, listed under "skills (existing)" per seat |
| Vendor `BLIND_AFTER=3` and `PositionWatcher` line numbers (`scout-vendor-engine.md:36`) | Not re-read; cited via scout |
| Exact restart threshold (3 restarts / 10 min) and SHILL batch cadence | REVIEW values; config fields |
| G-7 `SEAT_RE` is `^bot-0[0-6]-[a-z-]+$` (`check_desk_integrity.py:47`) and must be widened to `bot-0[0-9]` in the ported gate | Ported gate widens the regex |
| `openapi.yaml` is optional in D2; consumers listed only if the gateway exposes HTTP | chief + journal as consumers |
| Vendor line numbers `src/ops.py:235` `GrokOps`, `src/agents/base.py:89` `GrokAgent.run`, `src/risk.py:238-280` `exit_signal` body end, `BLIND_AFTER=3` come from `scout-vendor-engine.md:36-37,46` (only `:238` and the function head were re-read) | as the scout reports |

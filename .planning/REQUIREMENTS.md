# Requirements: PumpGrok Desk v2

**Defined:** 2026-10-21
**Core Value:** The desk runs autonomously in paper mode for 2-4 weeks and produces honest, replayable reports; no code path can move real funds.

## v1 Requirements

Requirements for the v1 milestone. Each maps to exactly one roadmap phase (see Traceability). Source: `docs/upgrade-plan-desk-v2.md` section 5.

### Foundation (FOUND)

- [x] **FOUND-001**: The desk is a `uv_build` src-layout package with `pyproject.toml` (`requires-python = ">=3.12,<3.13"`, R40) and a committed `uv.lock`; `uv sync --frozen` succeeds on a clean checkout with the pins of `docs/FOUNDATION_STACK.md` section 2.
- [x] **FOUND-002**: Operator can run `make lint typecheck test audit` and each target executes the canonical command of `docs/FOUNDATION_STACK.md` section 6 (ruff check, ruff format --check, mypy --strict src/, pytest -q, pip-audit over the `uv export` bridge of R2) with exit 0.
- [x] **FOUND-003**: `docker compose up pumpgrok` builds the multi-stage non-root image and starts the desk with effective mode `paper`; the compose healthcheck passes (`pumpgrok doctor` until `/healthz` lands in AUTO-004).
- [x] **FOUND-004**: The desk loads settings through pydantic-settings with the R30 precedence (CLI `--mode` > env `PUMPGROK_MODE` > TOML `execution.mode`), overlays `src/pumpgrok/config/overlays/{dev,paper,live}.toml` selected by `PUMPGROK_PROFILE` (default `paper`), `PUMPGROK_CONFIG=<file>` applied last, `PUMPGROK_*` env with `__` nesting; with no overrides the effective mode is `paper`, there is no root `config/` directory, and startup refuses any forbidden key name (`PRIVATE_KEY`, `SECRET_KEY`, `SEED`, `MNEMONIC`, `WALLET_PRIVATE_KEY`; `hermes/profiles.yaml:18-22` carried into the loader).
- [x] **FOUND-005**: `src/pumpgrok/core/{interfaces,registry,ids,approvals}.py` (R31) define `SideEffect`, the error classes, `Tool`/`ToolSpec`, `DataSource`, `ExecutionAdapter`, `SkillManifest`, `BotManifest`/`RiskBudget` (keys of R20), `ApprovalRecord` (kinds of R33), `ToolRegistry`/`GrantAudit` with invariants labelled I1-I5 (R40); `ToolRegistry.find` raises `LiveGateError` for any `LIVE_WRITE` spec regardless of caller; ULIDs come only from `core/ids.py` and `uuid` is banned in `src/pumpgrok` by a static test (R29).
- [x] **FOUND-006**: `ownership.yaml` declares the ten seats of D3 and owns every tracked path per R36 (`core/ replay/ ledger/ config/ logging/` -> bot-02-risk; generated `agents/*.md` and `prompts-assembled/*` -> bot-00-chief; `src/pumpgrok/execution/live/**` rule after `src/pumpgrok/execution/**`); `python3 ci/gates/check_ownership.py --validate-manifest` exits 0 and a G-1 self-test walking `git ls-files` finds no UNOWNED path.
- [x] **FOUND-007**: `ci/gates/{check_ownership,check_receipt,check_secrets,check_contracts,check_rollback,check_desk_integrity,run_all}.py` are ported with the retargeted constants of `docs/FOUNDATION_STACK.md` section 4 and R19 (`TOOL_NAME_RE = ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`, `SEAT_RE = ^bot-0[0-9]-[a-z-]+$`, `ROSTER_MIN_TOOLS = 8`, max 15, Solana/RPC/Telegram secret shapes, trading DEPLOY/DESTRUCTIVE patterns); `python3 -m pytest ci/tests/ -q` passes; `.receipts/<seat>/.gitkeep` exists for all ten seats with JSON gitignored; `.gitignore` ignores `var/`, `.venv/`, `*.pyc`; `.pre-commit-config.yaml` runs G-3 `--staged`, the manifest check and the gate self-test as local hooks.
- [x] **FOUND-008**: `contracts/` holds `README.md`, `tool-rosters/_core.yaml` (desk core eight) plus ten seat rosters whose tool names are exactly those of `docs/TOOL_CATALOG.md` with the R35 sizes, one JSON Schema per ledger event type `contracts/events/<snake>.schema.json` for the eighteen R32 types (`order_placed` .. `approval_recorded`, generated from `ledger/events.py`, no third vocabulary; seat messages LEAD/whale/social/signal/verdict/safety_report are `JournalNote` payloads discriminated by `note_kind`, RUG alerts are `Escalation` payloads), and `changes/`; `python3 ci/gates/check_desk_integrity.py --repo .` exits 0.
- [x] **FOUND-009**: `prompts/_shared/core-directives.xml` (audiences `trading-seats | chief | risk`) and ten `prompts/bot-0N-<seat>.xml` sources assemble via `bash scripts/assemble-prompts.sh --check` into `prompts-assembled/<SEAT>.xml` with no `{{...}}` left, and `python3 scripts/generate-templates.py --check` regenerates `agents/<seat>.md` preserving the frontmatter keys `name,title,description,seat,skills,writes_to_exchange` (`agents/chief.md:1-17`) so `./scripts/check.sh` keeps passing.
- [x] **FOUND-010**: `.github/workflows/{gates.yml,security-pr.yml,ci.yml}` exist; `gates.yml` derives the acting bot from the branch prefix with the ten-seat regex, overlays `ci/gates/` from the base ref, selects the receipt added under `.receipts/$BOT/`, and runs G-1..G-7 plus the `gate-self-test` job; `ci.yml` runs the canonical commands; `security-pr.yml` triggers on `pyproject.toml`/`uv.lock` changes (R2).
- [x] **FOUND-011**: `AGENTS.md`, `SECURITY.md` (key-custody wording "no key material exists in paper mode; nothing to custody", R40), `CHANGELOG.md`, `docs/quality-gates.md`, `docs/desk-operating-model.md` and `docs/cross-bot-protocol.md` exist in programming-desk shape, name the ten seats, engagement levels `research | paper` (R16) and G-1..G-7, and pass `./scripts/check.sh` (no emoji).
- [x] **FOUND-012**: `tests/conftest.py` blocks all network (an `httpx` transport that raises on un-mocked requests plus a `websockets` connect monkeypatch, `docs/design/paper-engine.md` section 9); `src/pumpgrok/replay/{clock,rng,fixtures}.py` provide the `Clock` protocol with `WallClock`/`FixtureClock`, the single seeded RNG constructor and the fixture loader; `tests/harness/faults.py` provides `FaultInjector` (modes stale, timeout, rate_limit, raise, unwritable); a static test fails on any direct `asyncio.sleep`, `asyncio.timeout` or `time.time` in `src/pumpgrok` (R27).
- [x] **FOUND-013**: `src/pumpgrok/ledger/{store,events}.py` implement the R32 schema (`events(seq, ts_utc, source, correlation_id, idempotency_key, type, payload_json, prev_hash, hash)`, `snapshots`), `BEGIN IMMEDIATE` single-writer appends with the hash chain computed inside the transaction over canonical JSON (R26, R28) and the eighteen CamelCase event models; `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` executes a skip-only cycle (fixture events read, no engine, one `JournalNote` appended, `source=replay`, ledger at `var/replay/smoke/ledger.sqlite`) and exits 0; `uv run pumpgrok doctor` reports present subsystems and marks absent ones `not-yet-implemented` as warnings until their owning phase lands, then as failures (R37).

### Restructure (STRUCT)

- [x] **STRUCT-001**: Tracked `*.pyc` (`docs/DISCOVERY.md:287-289`) and `issues/tissue.json` are removed, `scripts/check.sh` is rewritten without vendor paths and with the `your-org` placeholder check, and `docs/VENDOR_PIN.md` records the vendor commit `409e74c` (`docs/MIGRATION_MAP.md` section 7 batch 1).
- [x] **STRUCT-002**: `tools/{jupiter_quote,authority_check,holder_check,priority_fee}.py` are re-implemented as `src/pumpgrok/tools/{market/jupiter.py,onchain/authorities.py,onchain/holders.py,onchain/priority_fee.py}` (R31) over the single RPC client `src/pumpgrok/tools/onchain/rpc.py` (httpx + tenacity with `sleep=clock.sleep` + ordered failover, D8, R27), with `tests/characterization/test_{authority_check,holder_check,jupiter_quote,priority_fee}.py` reproducing the 11 root unittest cases against recorded fixtures in `tests/fixtures/replay/smoke/` and `tests/fixtures/http/`.
- [x] **STRUCT-003**: Vendor `monitor, analyzer, scoring, reputation, agents/*, tune` are ported to `src/pumpgrok/engine/` and vendor `risk.py` exit rules and `PositionWatcher` to `src/pumpgrok/engine/{exits,watcher}.py` (R31) with every Russian string translated and reason codes unchanged; the 1:1 characterization tests for these modules are green while `cd vendor/grokbot-pumpfun && python3 -m pytest -q` still passes as the oracle; `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` prints one `skip` or `buy` decision from the engine.
- [x] **STRUCT-004**: Vendor `executor, risk (RiskManager -> RiskEngine), ops, state, log` are ported into `src/pumpgrok/{execution,risk,supervisor,ledger}/` using the R31 module names with adapted characterization tests, bringing `tests/characterization/` to all 13 vendor modules with at least 164 1:1 tests (`docs/MIGRATION_MAP.md` section 3.1); the vendor daily-loss auto-clear (`risk.py:106-117`) is intentionally not ported (R5) and its test is marked as such; ported tests assert reason codes, never free text.
- [x] **STRUCT-005**: `cli.py` exposes every verb of `docs/DISCOVERY.md:11-16` plus R12 and R40 (`live confirm`, `replay trim | rebuild-ticks`, `run --record <dataset> --duration <s>`, `verify --fixture <dataset>`, `state halt --clear --by --reason`, `state autonomy <manual-ticket | autonomous-paper>`, `paper buy | sell --ticket --mint --size-sol --slippage-bps --approval-id`), verbs whose subsystem is absent return `not-yet-implemented`; the six Hermes cron prompts wrap `pumpgrok` subcommands only (`docs/MIGRATION_MAP.md` section 4.3), `jobs.yaml` `forbidden_owners: [sniper, exit]` is also enforced by the CLI; `scripts/hermes-*.sh` are rewritten for `PUMPGROK_*` env and `micro-live` is retired from `ARCHITECTURE.md`, `README.md`, `SETUP.md`, `skills/desk-operating-model`, `skills/pumpgrok-setup` and `scripts/hermes-verify-isolation.sh` (R16); `docs/MIGRATION_MAP.md` gains the engagement-level row and the markdown-prose quarantine table (R16).
- [x] **STRUCT-006**: `vendor/grokbot-pumpfun/` is deleted only when all six retirement checks of `docs/MIGRATION_MAP.md` section 3.4 hold (`rg -l -F "vendor/grokbot-pumpfun" . --glob '!vendor/**'` empty, `409e74c` cited only by `docs/VENDOR_PIN.md`, `src/pumpgrok/engine/LICENSE-grokbot-pumpfun` present, all 13 characterization modules green, `check.sh` no longer excludes `vendor/`).
- [x] **STRUCT-007**: All 23 existing skills gain `bots: [...]` and `gates: [...]` frontmatter and the `L1 - Summary / L2 - Method / Failure modes / References` body (`docs/design/interfaces.md` section 3); `skills/jupiter-routing` becomes quote/route preparation feeding `exec.quote` and `exec.place` (R18); `skills/browser-ops` is detection/research only (R39); every Jupiter v6 reference becomes the quote-only `api.jup.ag/swap/v2/order` path (R44) and `--max-micro` phrasing is removed (R14, R40); `tools/README.md` lists `desk_state.py` until `tools/` is deleted; the four plugin manifests say `"license": "AGPL-3.0"` and no `your-org` placeholder remains; `README.md`, `ARCHITECTURE.md` and `docs/runbooks/setup.md` describe `src/pumpgrok/`.
- [x] **STRUCT-008**: `JitoConfig` and `solana.wallet_private_key` do not exist in the settings model (R3), recorded as `docs/FOUNDATION_STACK.md` MIGRATION_NOTES M-10; `solders` and `solana` are not declared in `pyproject.toml`.

### Tools (TOOL)

- [x] **TOOL-001**: `market.{price,ohlcv,liquidity,trades,holders_snapshot}` (`docs/TOOL_CATALOG.md` section 1) return typed outputs carrying `freshness` and `source` fields and pass tests on recorded respx fixtures with no live network.
- [x] **TOOL-002**: `onchain.{token_metadata,authorities,lp_status,top_holders,deployer_history,large_transfers,priority_fee}` (section 2) go through the single RPC client `src/pumpgrok/tools/onchain/rpc.py` with tenacity jittered retries and ordered failover over `rpc.endpoints[]`; the API key travels in `solana.rpc_api_key`, never inside a URL or a log line; `deployer_history` and `large_transfers` are WHALE grants (R35).
- [x] **TOOL-003**: `safety.score_report` (section 3) produces a scored report with per-check reasons and thresholds read from config; a check without data returns `BLIND`, never an exception.
- [x] **TOOL-004**: `exec.{quote,simulate,place,cancel,positions}` (section 4) call the configured `ExecutionAdapter`; `exec.place` and `exec.cancel` carry `g6` and require `approval_id`; `exec.place` input carries `decision_id` (a ULID minted per decision) and the idempotency key is derived by the tool from `(ticket_id, side, decision_id)`, never caller-supplied; approval consumption is written in the same ledger transaction as the order (R23); `exec.simulate` writes no ledger event.
- [x] **TOOL-005**: `portfolio.{ledger_read,ledger_write,exposure,pnl}`, `risk.{check_limits,drawdown,kill_switch,halt_status}` and `journal.{append,render_report}` (sections 5, 6, 8) exist with the catalog schemas; `risk.check_limits` reports the R34 rule ids; `risk.kill_switch` accepts only `set` and `flatten_request` (R22); `journal.append` and `desk.event_emit` `kind` is the snake_case form of an R32 event type and seats may write only `journal_note` and `escalation` (every other type is appended by the engine, risk, adapter or supervisor); `portfolio.ledger_write` is `PermissionDenied` for all ten seats (`docs/design/interfaces.md` section 4).
- [x] **TOOL-006**: `notify.alert` (section 7) dispatches through an abstract `Notifier` whose stdout and file sinks are always on and whose Telegram and webhook sinks are enabled only by config and send only to a configured allowlist of chat ids and URLs (R39); RISK and RUG rosters do not carry `notify.alert` (R35) and escalate via `desk.event_emit kind=escalation`, which the supervisor relays to `notify.alert`; the alert `kind` enum includes the escalation kinds `bot_restart_exhausted, heartbeat_stale, persistence_down, clock_skew, ledger_inconsistent` (R40); sends are rate limited and idempotent.
- [x] **TOOL-007**: The desk core eight `desk.{brief,docs_search,memory_retain,memory_recall,ownership_resolve,receipt_check,event_emit,doctor}` (section 9) are resolvable by every seat, `desk.event_emit` `kind` follows R32 snake_case, and `desk.doctor check` is the same code path as `pumpgrok doctor`.
- [x] **TOOL-008**: Every registered tool has a pydantic v2 input and output model (`additionalProperties: false`), a `side_effect` in `{read, paper-write}`, `timeout_s`, a `RetryPolicy` and a `rate_limit_key`; money fields are integers in base units named `<x>_lamports: int` and `<x>_units: int` (token base units), prices and ratios are `Decimal` strings, no float money anywhere, and only the CLI boundary accepts `--size-sol` (R28); untrusted upstream payloads (pump.fun, PumpPortal, Jupiter, RPC, x.ai) are parsed with `extra="ignore"` models and a malformed payload yields a typed error (`DataStale`/`BLIND`), never an escaping exception.
- [x] **TOOL-009**: The least-privilege tests of `docs/design/interfaces.md` section 4 pass: no seat resolves a live-write tool, only sniper and exit resolve `exec.place`, exit cannot place a BUY, chief has no exposure tools, shill's only write is `journal.append`, every roster name exists in the registry, and `tools/social/` (bot-07-shill, R31) issues GET only.
- [x] **TOOL-010**: `services/desk-gateway/` serves `/mcp/<seat>` from the in-process registry so that `tools/list` equals `contracts/tool-rosters/<seat>.yaml` plus `_core.yaml`, transport names are the dotted ids with `.` replaced by `_` derived at exposure time and never stored (R19), and a token for seat A on `/mcp/<seat B>` is 403.
- [x] **TOOL-011**: Operator can run every verb of `docs/TOOL_CATALOG.md` section 12 plus the R12 and R40 additions; each verb is a thin wrapper over catalog tools and prints JSON by default; `pumpgrok paper buy | sell` requires `--ticket --mint --size-sol --slippage-bps --approval-id`. Narrowed by owner decision (2026-10-23): the CLI refuses `pumpgrok paper buy | sell` for every seat with exit 1 and writes nothing; paper orders go through the desk gateway seats that hold exec grants (sniper, exit).

### Skills (SKILL)

- [x] **SKILL-001**: The twelve new skills of `docs/design/interfaces.md` section 3.2 exist (35 skills total) with frontmatter `name, description, bots, gates, required_tools, permissions.max_side_effect` and the L1/L2 body; `skills/desk-post-trade-review/**` is owned by bot-09-journal (R36).
- [x] **SKILL-002**: `tests/test_skill_manifests.py` passes: every `skills/*/SKILL.md` parses into `SkillManifest`, `name == dirname`, every `required_tools` entry is granted to every listed bot, and `permissions.max_side_effect != LIVE_WRITE`.
- [x] **SKILL-003**: `tests/test_bot_manifests.py` passes: exactly ten `BotManifest`s load from `contracts/tool-rosters/*.yaml`, ids `bot-00-chief` .. `bot-09-journal`, `writes_to_exchange` true only for sniper and exit, each with the R20 `risk_budget` keys and forbidden actions, every roster 8..15 tools including the core eight with RISK = 15 and RUG = 15 exactly as R35 lists them.
- [x] **SKILL-004**: Each seat prompt source lists its `load="always"` skills and a `<tools contract="contracts/tool-rosters/<seat>.yaml">` section; `agents/<seat>.md` and the plugin manifests enumerate the same skills (description count updated from "23 skills"); `./scripts/check.sh` passes.

### Paper trading (PAPER)

- [x] **PAPER-001**: `PaperAdapter` (`src/pumpgrok/execution/paper_adapter.py`, R31) computes every pre-graduation BUY and SELL fill from the bonding-curve reserves (the Jupiter quote is informational only, never the fill price, R38) with price impact, venue + base + priority fee (and optional tip), seeded confirmation latency, `slippage_exceeded` with the threshold recomputed for the executed size, full fill for size <= L/50, partial fill in (L/50, L/10], `below_liquidity_floor` above L/10 (R6, R20 `liquidity_floor_multiple`/`partial_fill_fraction`, REVIEW), seeded `tx_dropped` with no cash change, and day attribution of PnL by fill timestamp.
- [x] **PAPER-002**: `var/ledger.sqlite` (paper) and `var/replay/<dataset>/ledger.sqlite` (replay) are append-only WAL event logs with the R32 schema and the eighteen event types, a hash chain over canonical JSON (R28), `source` in `{paper, replay, manual}` on every event (R21), periodic snapshots and a pure reducer; restart = snapshot + tail replay + verify; a tampered payload yields `INCONSISTENT`, `HaltSet(ledger_inconsistent)` and refused orders; a duplicate `idempotency_key` is refused (`docs/design/paper-engine.md` section 9).
- [x] **PAPER-003**: JSONL journal export under `var/journal/` resumes from `meta.export_seq` without duplicates and also emits the vendor-shape `trades.jsonl` lines; `desk.md` and every markdown view under `var/desk/` is written via tmp file + `os.replace` (R26), derived and never read back (`docs/MIGRATION_MAP.md` section 4.5).
- [x] **PAPER-004**: Replay runs the full desk over `tests/fixtures/replay/<dataset>/` with `FixtureClock`, one seeded RNG and fixture timestamps as ledger `ts_utc`; LLM calls are served from the recorder's `canonical_request_hash` records (`outcome` in `{ok, timeout, error}`, virtual `latency_s`) and a missing record fails the replay (R27); two runs over `smoke-10m` give identical `events.hash`, JSONL bytes and final state, a different seed differs, and a 180 s hole trips `DataStale` (section 9); `pumpgrok run --record <dataset> --duration <s>` writes new datasets from live transports stamping the clock's ts (R40).
- [x] **PAPER-005**: A bonding-curve graduation event force-closes the open paper position at the last curve price with reason `graduated` and freezes MTM, a BUY on a graduated token is rejected `post_graduation_no_reserves` (R8, R38), and after `blind_max_s = 300` without a price EXIT force-closes at `last_good` with reason `blind_flatten` and escalates (R25); open positions are marked to market at liquidation value every 60 s.
- [x] **PAPER-006**: `pumpgrok report --daily` (00:05Z) and `--weekly` (Monday 00:15Z, R40) render the sections of `docs/design/paper-engine.md` section 8.3 (summary, trades, open positions, rejected signals by R34 reason, safety outcomes, risk events, bot health, data freshness, live gate on weekly, unverified) with `str.format` only (R9), ASCII only, snapshot-tested from a fixture ledger (section 9).
- [ ] **PAPER-007**: Tickets are `SOL-YYYYMMDD-NNN` sequence-allocated in the ledger; approvals are persisted as `ApprovalRecorded` with kind in `{human_buy, human_sell, exit_rule, autonomous_paper, killswitch_clear, halt_clear, live_gate}` (R33); under `manual-ticket` a buy needs a human phrase matching the ticket token-for-token (`rules/pumpgrok-team.mdc:28`, mismatch -> `OrderRejected reason=approval_mismatch`) and each exit rule needs a per-ticket `exit_rule` approval, while under `autonomous-paper` the EXIT rule engine is always on (R17); sniper and exit send once per ticket because `exec.place` is idempotent on `(ticket_id, side, decision_id)` (R18, R23) and an unknown or timed-out result enters state `UNKNOWN` and is never auto-retried (D9, `rules/pumpgrok-team.mdc:30`). Partial (2026-10-23): under `manual-ticket` the exit seat refuses each rule sell with `approval_missing`, because no verb or tool records a standing human `exit_rule` approval yet; building that path or narrowing this requirement is an open owner decision.

### Risk (RISK)

- [x] **RISK-001**: `RiskEngine.check(order)` (`src/pumpgrok/risk/engine.py`, R31) is library code executed inside `PaperAdapter.place` for every order regardless of seat health (R24), binds the decision to `order_hash`, evaluates the R34 steps in one vocabulary, and enforces the R20 budget `max_trade_fraction=0.02, max_token_fraction=0.05, max_open_positions=3, max_trades_per_day=20, liquidity_floor_multiple=10, partial_fill_fraction=0.02, paper_equity_sol=10` (REVIEW) read from the TOML `[risk]` block.
- [x] **RISK-002**: Daily loss >= `daily_loss_halt_fraction` (0.05) of start-of-day equity appends `HaltSet(daily_loss)` (idempotent per reason + utc_day, R24), posts the constant `FLOOR HALTED <U+2013> DAILY LOSS LIMIT` with its exact bytes (R7, `rules/pumpgrok-team.mdc:34`) and refuses new entries; drawdown >= `drawdown_halt_fraction` (0.15) from peak equity halts with reason `drawdown`; a halt is cleared only by `pumpgrok state halt --clear --by <human> --reason <text>` which appends `HaltCleared` with an `ApprovalRecorded` of kind `halt_clear` (R5, R22).
- [x] **RISK-003**: Breakers `DataStale`, `LossVelocity` and `ExecErrors` trip on configured thresholds, reject buys while open, allow sells, admit one half-open probe after cooldown, reset after `reset_after_ok` successes, and reconstruct their state from ledger events after restart (`docs/design/paper-engine.md` section 9); kill switch, halts, breakers and limits are re-checked at `CONFIRMING` immediately before a fill and an in-flight order is rejected with reason `kill_switch`/`halted`/`breaker_open` (R22).
- [x] **RISK-004**: The kill switch reads env `PUMPGROK_KILLSWITCH` at start only and polls file `var/desk/KILLSWITCH` and the alert-channel command every risk cycle (5 s); zero buys occur after it is set within one cycle; `flatten_request` waits on the in-flight barrier then closes every open position with reason `kill_flatten`; clear is CLI-only `pumpgrok killswitch clear --by <human> --reason <text>` appending `KillSwitchCleared` with an `ApprovalRecorded` of kind `killswitch_clear` and refused while any live source is still set (R22, section 9).
- [x] **RISK-005**: A RISK verdict `KILL` on a mint blocks that token path for the session for every seat (`rules/pumpgrok-team.mdc:32`) and the `seat_may_trade` step rejects a BUY from exit and a SELL from sniper (R34).
- [x] **RISK-006**: A seat in observe-only (restart budget exhausted, LLM required but down, clock skew) cannot resolve its paper-write tools; when sniper or bot-02-risk is observe-only the desk enters observe-only for BUYS while exits continue (R24), and when exit is observe-only `HaltSet(manual, "exit seat observe-only")` is appended (`docs/design/paper-engine.md` section 6.4).
- [x] **RISK-007**: `docs/RISK_POLICY.md` states the D7 compliance boundary and `tests/safety/test_no_manipulation_tools.py` passes over `tools/social/`, `notify.*` and the `browser-ops` forbidden-actions scope (R39): no registered tool name matches `post|reply|like|follow|dm|broadcast|wash|volume`, no social module issues anything but GET, and `notify.alert` sends only to the configured allowlist.

### Autonomy (AUTO)

- [x] **AUTO-001**: `src/pumpgrok/supervisor/{scheduler,seat_task,health}.py` (R31) run the ten seats as one asyncio task each on the cadences of `docs/design/paper-engine.md` section 6.2, start due seats in roster order within a 1 s tick, treat a cycle exceeding its `clock.timeout` as a crash (R27), and support `autonomy_level` `manual-ticket` and `autonomous-paper` (live forces `manual-ticket`; `pumpgrok state autonomy <level>` appends `ConfigChanged`; no live auto-exit exists, R17).
- [x] **AUTO-002**: Heartbeats are recorded by the task wrapper; a seat stale for 3 cadences degrades health and emits one edge-triggered `Escalation(heartbeat_stale)`; a crashing seat is restarted at most 5 times per hour with backoff 1,2,4,8,16 s plus jitter through `clock.sleep`, then latched observe-only with `Escalation(bot_restart_exhausted)` while the other seats keep ticking; the supervisor relays every `Escalation` event (its own and seat-emitted `kind=escalation`) to `notify.alert`; `pumpgrok state resume --seat <seat> --by human:<name>` clears the latch (section 9).
- [x] **AUTO-003**: SIGTERM/SIGINT stops scheduling, drains running cycles within 30 s, writes a ledger snapshot, flushes the JSONL export, writes `var/health.json status=stopped` and exits 0; a second signal does not force; a hard kill mid-append leaves the ledger consistent (R26).
- [x] **AUTO-004**: `GET /healthz` returns 200 only when status is ok (503 while any seat is stale), `GET /readyz` returns 200 only after the ledger reconciled CONSISTENT and every seat completed one cycle, and `var/health.json` is rewritten atomically every 10 s for Hermes prompts.
- [x] **AUTO-005**: The degraded modes of `docs/design/paper-engine.md` section 6.7 hold: LLM failure degrades bot-08-signal to rule-based scoring in live paper runs only (observe-only for buys when `signal.require_llm`; in replay a missing LLM record fails the run, R27), RPC failure fails over then marks `BLIND`, WebSocket loss reconnects with backoff and trips `DataStale` after 120 s, an unwritable ledger refuses orders into a bounded buffer with `Escalation(persistence_down)`, and clock skew refuses appends with `Escalation(clock_skew)`.
- [x] **AUTO-006**: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` runs one full cycle of all ten seats on fixture data through the engine, risk and paper adapter, writes `var/replay/smoke/ledger.sqlite`, and exits 0 with no network access.
- [x] **AUTO-007**: `tests/soak/test_soak_multiday_replay.py` replays `soak-3d`: peak memory growth after the first virtual hour is under 20 MB (REVIEW), no unhandled exception reaches the loop handler, at least one `DailyRollover` per day, the ledger verifies, and a report renders for each day.
- [x] **AUTO-008**: A fault-injection suite under `tests/degradation/` drives each AUTO-005 row through `FaultInjector` on replay and asserts the stated behaviour and recovery.

### Observability (OBS)

- [x] **OBS-001**: Every log record is one JSON line with the fields of `docs/FOUNDATION_STACK.md` section 5.1, secrets and key-shaped values are redacted before emission (`tests/test_logging.py::test_log_redaction`), and `PUMPGROK_LOG_JSON=false` restores text only in the `dev` overlay.
- [x] **OBS-002**: A cycle bound to a ULID correlation id yields child spans `<ulid>.<n>` on every tool call, log record and ledger event (R29; `tests/test_correlation.py::test_correlation_id_chain`).
- [x] **OBS-003**: `GET /metrics` exposes `pumpgrok_cycle_seconds{seat}`, `pumpgrok_bot_crashes_total{seat}`, `pumpgrok_orders_total{side,outcome}`, `pumpgrok_equity_sol`, `pumpgrok_drawdown_pct`, `pumpgrok_data_age_seconds{source}`, `pumpgrok_breaker_state{breaker}`, `pumpgrok_kill_switch`, `pumpgrok_ledger_seq` (`docs/design/paper-engine.md` section 6.6) and span timings for every tool call are logged.
- [x] **OBS-004**: `docs/runbooks/{setup,engine,start_stop,kill_switch,breaker_reset,outage,rollback,reading_reports,go_live}.md` exist, each command in them is one of the canonical commands or a `pumpgrok` verb, and they pass `./scripts/check.sh`.
- [x] **OBS-005**: `CHANGELOG.md` records every phase, `AGENTS.md` indexes the rules a cloud agent must read, and the milestone report (phase reports appended to this file, section 6.6) lists the final test, gate and audit results.

### Security (SEC)

- [x] **SEC-001**: No secret is committed: `.env.example` contains placeholders only, `python3 ci/gates/check_secrets.py --base origin/main` exits 0 on every PR, and G-3 recognises Solana base58 64-byte keys, JSON byte arrays, Helius/QuickNode keyed URLs and Telegram tokens.
- [x] **SEC-002**: Secrets reach the desk only through env (or a secret manager injecting env); `--rpc https://...?api-key=` style CLI flags are refused and the operator confirmation secret is readable only by `pumpgrok live confirm` and `LiveGate.validate`, never by a seat or tool (R21).
- [x] **SEC-003**: `tests/safety/test_no_signing_outside_live_stub.py` walks the AST and fails on any `sign`, `send_transaction`, `sendTransaction` or `Keypair` symbol outside `src/pumpgrok/execution/live/`, and the live stub itself builds no transaction.
- [x] **SEC-004**: `pumpgrok run --mode live` (or env `PUMPGROK_MODE=live`, R30) with any of the nine R21 preconditions unmet exits 3 listing every unmet line and sends nothing; precondition 8 (a registered live adapter implementation) is always unmet because none ships; `LiveAdapter.place`/`cancel` (`src/pumpgrok/execution/live/live_adapter.py`) always raise `LiveGateError` after appending `LiveWriteAttempted` and a critical alert; every registry grant decision is a `GrantAudit` row.
- [x] **SEC-005**: `security-pr.yml` (gitleaks, semgrep, bandit, pip-audit via the R2 bridge, trivy) is green on `main` or every exception is listed in `SECURITY.md` with an expiry.

### Go-live gate (GOLIVE)

- [x] **GOLIVE-001**: `pumpgrok live confirm --by human:<name> --notional-cap <sol> --expires <iso>` writes the HMAC-signed confirmation record bound to the config hash using an operator secret no seat or tool can read (R21) and appends `ApprovalRecorded(kind=live_gate)` plus `ConfigChanged(keys_changed=["live.confirmation"])`; it never changes `execution.mode`.
- [x] **GOLIVE-002**: `LiveGate.validate` (`src/pumpgrok/execution/live/live_gate.py`) evaluates the paper window and the thresholds `closed_trades >= 50`, `profit_factor >= 1.2`, `max_drawdown <= drawdown_halt_fraction` only over ledger events with `source=paper`, refuses any ledger containing `source=replay` for its metrics, and `0 < live.notional_cap_sol <= 1.0` (R21, REVIEW); the weekly report prints each precondition with OK/unmet.
- [x] **GOLIVE-003**: `docs/runbooks/go_live.md` documents the full procedure, `tests/execution/test_live_gate_fails_fast.py` proves each of the nine preconditions independently, and the milestone ships with `live.enabled = false` in every overlay.

## v2 Requirements

None in this milestone; see Out of Scope.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Web dashboard or UI | Out of scope (spec xml line 160); `reporting/dashboard.py` is a text renderer only. |
| Live trading enablement, wallet funding, any real transaction, any live adapter implementation | Out of scope (xml 159, R21 precondition 8); GOLIVE-* ships disabled. |
| New chains, venues, launchpads, data vendors; post-graduation CPMM modelling | Out of scope (xml 165, D8, R8, R38). |
| Multi-tenant, billing, SaaS packaging | Out of scope (xml 164). |
| Strategy research, new alpha, tuning beyond making ported logic run | Out of scope (xml 162); `engine/tune.py` is ported as-is. |
| Social posting, coordinated buying, volume tooling, wallet UI automation | Forbidden (xml 161, D7, R39). |
| Engagement level `micro-live` | Retired (R16). |
| Coverage threshold, ed25519 confirmation signatures, Greptile as a gate, gateway OAuth | Deferred (`docs/FOUNDATION_STACK.md` U-5, `docs/design/paper-engine.md` section 7.3, section Unverified 6). |
| Changing `~/src/repos/programming-desk/` itself | Non-goal (upgrade plan section 1.3); the desk mirrors programming-desk shape but never edits it. |

## Traceability

Which phases cover which requirements. Populated during roadmap creation from `docs/upgrade-plan-desk-v2.md` section 6.7.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-001 | Phase 1 Foundation | Complete |
| FOUND-002 | Phase 1 Foundation | Complete |
| FOUND-003 | Phase 1 Foundation | Complete |
| FOUND-004 | Phase 1 Foundation | Complete |
| FOUND-005 | Phase 1 Foundation | Complete |
| FOUND-006 | Phase 1 Foundation | Complete |
| FOUND-007 | Phase 1 Foundation | Complete |
| FOUND-008 | Phase 1 Foundation | Complete |
| FOUND-009 | Phase 1 Foundation | Complete |
| FOUND-010 | Phase 1 Foundation | Complete |
| FOUND-011 | Phase 1 Foundation | Complete |
| FOUND-012 | Phase 1 Foundation | Complete |
| FOUND-013 | Phase 1 Foundation | Complete |
| STRUCT-001 | Phase 1 Foundation | Complete |
| STRUCT-002 | Phase 2 Restructure | Complete |
| STRUCT-003 | Phase 2 Restructure | Complete |
| STRUCT-004 | Phase 4 Paper Trading and Autonomy | Complete |
| STRUCT-005 | Phase 2 Restructure | Complete |
| STRUCT-006 | Phase 4 Paper Trading and Autonomy | Complete |
| STRUCT-007 | Phase 2 Restructure | Complete |
| STRUCT-008 | Phase 1 Foundation | Complete |
| TOOL-001 | Phase 3 Tools and Skills | Complete |
| TOOL-002 | Phase 3 Tools and Skills | Complete |
| TOOL-003 | Phase 3 Tools and Skills | Complete |
| TOOL-004 | Phase 3 Tools and Skills | Complete |
| TOOL-005 | Phase 3 Tools and Skills | Complete |
| TOOL-006 | Phase 3 Tools and Skills | Complete |
| TOOL-007 | Phase 3 Tools and Skills | Complete |
| TOOL-008 | Phase 3 Tools and Skills | Complete |
| TOOL-009 | Phase 3 Tools and Skills | Complete |
| TOOL-010 | Phase 3 Tools and Skills | Complete |
| TOOL-011 | Phase 3 Tools and Skills | Complete |
| SKILL-001 | Phase 3 Tools and Skills | Complete |
| SKILL-002 | Phase 3 Tools and Skills | Complete |
| SKILL-003 | Phase 3 Tools and Skills | Complete |
| SKILL-004 | Phase 3 Tools and Skills | Complete |
| PAPER-001 | Phase 4 Paper Trading and Autonomy | Complete |
| PAPER-002 | Phase 4 Paper Trading and Autonomy | Complete |
| PAPER-003 | Phase 4 Paper Trading and Autonomy | Complete |
| PAPER-004 | Phase 4 Paper Trading and Autonomy | Complete |
| PAPER-005 | Phase 4 Paper Trading and Autonomy | Complete |
| PAPER-006 | Phase 4 Paper Trading and Autonomy | Complete |
| PAPER-007 | Phase 4 Paper Trading and Autonomy | Partial |
| RISK-001 | Phase 4 Paper Trading and Autonomy | Complete |
| RISK-002 | Phase 4 Paper Trading and Autonomy | Complete |
| RISK-003 | Phase 4 Paper Trading and Autonomy | Complete |
| RISK-004 | Phase 4 Paper Trading and Autonomy | Complete |
| RISK-005 | Phase 4 Paper Trading and Autonomy | Complete |
| RISK-006 | Phase 4 Paper Trading and Autonomy | Complete |
| RISK-007 | Phase 5 Hardening | Complete |
| AUTO-001 | Phase 4 Paper Trading and Autonomy | Complete |
| AUTO-002 | Phase 4 Paper Trading and Autonomy | Complete |
| AUTO-003 | Phase 4 Paper Trading and Autonomy | Complete |
| AUTO-004 | Phase 4 Paper Trading and Autonomy | Complete |
| AUTO-005 | Phase 4 Paper Trading and Autonomy | Complete |
| AUTO-006 | Phase 4 Paper Trading and Autonomy | Complete |
| AUTO-007 | Phase 5 Hardening | Complete |
| AUTO-008 | Phase 5 Hardening | Complete |
| OBS-001 | Phase 1 Foundation | Complete |
| OBS-002 | Phase 1 Foundation | Complete |
| OBS-003 | Phase 5 Hardening | Complete |
| OBS-004 | Phase 5 Hardening | Complete |
| OBS-005 | Phase 5 Hardening | Complete |
| SEC-001 | Phase 1 Foundation | Complete |
| SEC-002 | Phase 1 Foundation | Complete |
| SEC-003 | Phase 2 Restructure | Complete |
| SEC-004 | Phase 4 Paper Trading and Autonomy | Complete |
| SEC-005 | Phase 5 Hardening | Complete |
| GOLIVE-001 | Phase 4 Paper Trading and Autonomy | Complete |
| GOLIVE-002 | Phase 4 Paper Trading and Autonomy | Complete |
| GOLIVE-003 | Phase 5 Hardening | Complete |

**Coverage:**

- v1 requirements: 71 total
- Mapped to phases: 71
- Unmapped: 0

---
*Requirements defined: 2026-10-21*
*Last updated: 2026-10-21 after initial definition*

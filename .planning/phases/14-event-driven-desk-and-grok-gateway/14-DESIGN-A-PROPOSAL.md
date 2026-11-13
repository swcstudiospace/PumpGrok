# Phase 14 Design A policy decision record (PROPOSAL)

**Status: PROPOSED - not owner-approved.**

No owner decision, RISK review, or independent review is recorded for any value in this file. This draft does not claim that one occurred.

- Drafted 2026-11-13 in worktree `/root/src/repos/pumpgrok-wt/v4-phase-14`, branch `bot-00-chief/v4-phase-14`, base commit c84e802.
- Answers the input gap behind plan 14-01 checkpoint "Resolve missing Design A policy before implementation" (`bot-00-chief/phase-13-planning:.planning/phases/14-event-driven-desk-and-grok-gateway/14-01-PLAN.md:40-46`).
- Bare planning filenames (`14-01-PLAN.md`, `14-RESEARCH.md`, `14-VALIDATION.md`, `STATE.md`) live on `bot-00-chief/phase-13-planning` under `.planning/phases/14-event-driven-desk-and-grok-gateway/` (or `.planning/STATE.md`).
- Nothing is implemented. No gate, test, make target, or formatter was run.
- Hash constraint: smoke-10m `events.hash` stays `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` (`.planning/PROJECT.md:221`, V4-9; `tests/replay/pin_support.py:37`).

## 0. Provenance and marking

| Ref | Source | Use |
|---|---|---|
| A | `.planning/research/v4/A-events-grok.md` at commit fc3af56 (2026-11-02, branch `v4/plan-scratch`; not an ancestor of this branch; absent from this worktree) | Design A draft. Cited "A s.N". |
| N6 | `.planning/research/v4/N6-critique.md` at fc3af56 | Owner-review corrections. Cited "N6 s.N item N" or "N6 s.2 claim N". Written against repo HEAD 641927c, so its line numbers are stale. Every repo line cited here was re-checked at c84e802. |
| OD | `.planning/research/v4/owner-decisions.md` at fc3af56 | Decision register. Each entry is a recommended default, not a recorded owner answer. Cited "OD-nn". |
| B | `.planning/research/v4/B-strategies-backtest-data.md` at fc3af56, line 33 | Source of the 45 s MTM refresh timer only. |
| C | `.planning/research/v4/C-risk-promotion-live.md` at fc3af56, line 97 | Reconcile-on-start, cited only to show it is event-triggered. |
| repo | tracked files at c84e802 | Cited as path:line. |

Findings:

1. `.planning/PROJECT.md:219-223` (V4-7 to V4-11) cites "Design A as corrected by N6" with status Decided. Those rows fix architecture only. No Design A numeric value is recorded in any file on this branch.
2. Every Design A parameter value exists only in the fc3af56 draft (A s.4 and s.5). No owner review of those values is recorded. OD-01 to OD-21 are all recommended defaults.
3. `bot-00-chief/phase-13-planning:.planning/phases/14-event-driven-desk-and-grok-gateway/14-VALIDATION.md:116` lists "Design A policy" as Pending.

Marking used below:

- **REPO**: already in tracked repo source, with citation.
- **DESIGN-A**: appears only in A, N6, or B. Not yet a repo constant. Not owner-approved.
- **CONFLICT**: a repo or legacy value disagrees with the proposal. The owner must choose.
- **UNKNOWN**: no source value exists. The cell is left for the owner. No value is invented.

## 1. Event wake matrix (EVT-10)

Proposed: A s.4.3, with the corrections in 1.1.

| Seat | Old cadence | Proposed wake events | Marking | Status |
|---|---|---|---|---|
| bot-00-chief | 60 s (`supervisor.py:44`) | RiskEdge; SourceStatus change; escalation and ticket rows (relay); Heartbeat | DESIGN-A | PROPOSED - not owner-approved |
| bot-01-scout | 10 s (`supervisor.py:45`) | TokenLaunched; Migration; SourceStatus(pumpportal resynced) | DESIGN-A | PROPOSED - not owner-approved |
| bot-02-risk | 5 s (`supervisor.py:46`) | CandidateReady; PositionTick (coalesced to 1/s); OrderOutcome; RiskEdge(halt/breaker) | DESIGN-A | PROPOSED - not owner-approved |
| bot-03-whale | 120 s (`supervisor.py:47`) | LargeTransfer; CandidateReady (whale-eligible); SourceStatus(rpc) | DESIGN-A | PROPOSED - not owner-approved |
| bot-04-sniper | 1 s (`supervisor.py:48`) | StrategySignal, or CandidateReady with BUY verdict; OrderOutcome(partial/retry) | DESIGN-A | PROPOSED - not owner-approved |
| bot-05-rug | 30 s (`supervisor.py:49`) | PositionTick (held); HolderShift; Migration (held); SourceStatus(blind) | DESIGN-A | PROPOSED - not owner-approved |
| bot-06-exit | 15 s (`supervisor.py:50`) | PositionTick; ExitDeadline; OrderOutcome(sell); RiskEdge(halt) | DESIGN-A | PROPOSED - not owner-approved |
| bot-07-shill | 300 s (`supervisor.py:51`) | SocialMention. No source exists, so heartbeat only. | DESIGN-A | PROPOSED - not owner-approved |
| bot-08-signal | 1 s (`supervisor.py:52`) | TokenLaunched that passed `passes_filter` (CandidateReady); GrokVerdict; SourceStatus(llm) | DESIGN-A | PROPOSED - not owner-approved |
| bot-09-journal | 300 s (`supervisor.py:53`) | OrderOutcome; PositionChange(closed); Timer(daily_rollover); flush only when dirty | DESIGN-A | PROPOSED - not owner-approved |

Cadence reference: `SEAT_CADENCES` (`src/pumpgrok/supervisor/scheduler/supervisor.py:43-54`) is the table this replaces in event mode only. Cadence mode keeps it unchanged (`REQUIREMENTS.md:21`, EVT-10).

Ten seats: `supervisor.py:56` (`ROSTER = EXPECTED_SEAT_IDS`).

### 1.1 Corrections to A s.4.3

a. **Journal rollup (CONFLICT with A s.6).** The daily rollup runs in the journal cycle on `Timer(daily_rollover)`. It has no separate Hermes job. Basis: OD-13 (`owner-decisions.md` line 19) and N6 s.8 item 13.

b. **Event kind names (CONFLICT).** The matrix uses CandidateReady, PositionTick, OrderOutcome, ExitDeadline, RiskEdge, SourceStatus, Timer, Heartbeat, HolderShift, StrategySignal, GrokVerdict, PositionChange, LargeTransfer, SocialMention, TokenLaunched, and Migration. The repo `EventKind` (`src/pumpgrok/events/models.py:24-38`) has only: kill_switch, halt, exit_signal, risk_veto, token_created, migration, trade, position_opened, position_closed, strategy_intent, curve_tick, mark. A's `ExitDeadline` appears in s.4.2 and s.4.3 but not in its own kind table (N6 s.1). N6 s.1 and s.8 item 11 require one catalog in `events/models.py`. The final kind list is UNKNOWN until the owner chooses it.

c. **Degraded field (REPO check).** A s.2.2 sets `degraded.bus_backlog=True`. No such field exists in `src/pumpgrok/supervisor/scheduler/degraded.py` (zero matches). Use `Escalation(event_backlog)` only (N6 s.2 claim 5).

Reasons: EVT-10 requires wakes per SEAT_WAKES, unchanged cadence, and the exact allowed timer set (`REQUIREMENTS.md:21`; `ROADMAP.md:153`). Sniper and signal wake on candidates that pass the existing filter (`src/pumpgrok/engine/monitor.py:129`).

## 2. Permitted timers (EVT-10)

The allowed set is exactly the rows below. No other timer may exist in event mode. The 1 s tick is removed in event mode only.

| Timer | Proposed value | Marking | Reason and citation | Status |
|---|---|---|---|---|
| Seat heartbeat | 30 s per seat. Seat stale after 3 missed beats (90 s). | DESIGN-A | A s.4.2. Replaces cadence-derived staleness (`stale_cadence_s=SEAT_CADENCES[seat]`, `supervisor.py:125`). | PROPOSED - not owner-approved |
| Health file write | 10 s | REPO | `HEALTH_FILE_INTERVAL_S = 10.0` (`src/pumpgrok/supervisor/health.py:38`), used at `supervisor.py:285`. | PROPOSED - not owner-approved |
| Daily rollover | Next UTC midnight, then once at start. `rollover_key` keeps it idempotent. | DESIGN-A; UTC day REPO | A s.4.2. UTC calendar day is the repo budget basis (`src/pumpgrok/core/budget.py:16-18`, rollover at `:31-36`). | PROPOSED - not owner-approved |
| Reconciliation | 300 s (`store.verify()`, position and ledger fold) | DESIGN-A | A s.4.2. No repo constant. | PROPOSED - not owner-approved |
| Kill-source poll | 2 s | DESIGN-A | A s.4.2 cites RISK-004. That ID is not in `.planning/REQUIREMENTS.md` (searched). No repo constant. | PROPOSED - not owner-approved |
| Relay tail | 2 s | DESIGN-A | A s.4.2. Ledger has no notifier. | PROPOSED - not owner-approved |
| ExitDeadline(mint) | One per open position, set at open, fires at max hold | REPO value | `max_hold_seconds = 3600.0` (`src/pumpgrok/config/sections/engine.py:58`). Replaces exit polling. `stop_loss_poll_seconds = 15.0` (`engine.py:59`) stays until OD-20. | PROPOSED - not owner-approved |
| Position watchdog | Held mint silent for 30 s triggers a direct curve read and a PositionTick. Runs only while positions are open. | DESIGN-A; key name UNKNOWN | A s.4.2 names `exits.max_silence_s`. No such field exists in the repo (searched). The key name is UNKNOWN. | PROPOSED value; key name UNKNOWN |
| Dedup and DLQ TTL sweep | 60 s | DESIGN-A | A s.4.2. | PROPOSED - not owner-approved |
| MTM refresh | 45 s, limit 60 s | DESIGN-B draft; limit REPO | Required by N6 s.1 and s.8 item 12. Value from B line 33 (`mtm_refresh_s` 45, limit 60). The 60 s limit matches `src/pumpgrok/risk/limits.py:30` (`mtm_interval_s` default 60.0) and `src/pumpgrok/risk/engine/steps.py:384-387`. | PROPOSED - not owner-approved |
| Source staleness | 120 s (`STALE_AFTER_S`) | REPO; CONFLICT | `src/pumpgrok/events/constants.py:12`. Same value as `WS_STALE_S = 120.0` (`src/pumpgrok/supervisor/scheduler/degraded.py:20`). Two owners exist. N6 s.8 item 12 requires one. Proposed owner: `events/sources.py` SourceSupervisor. | CONFLICT |
| 1 s supervisor tick | Removed in event mode | REPO | `TICK_S = 1.0` (`supervisor.py:39`). A s.4.1 says no 1 s TICK_S loop in event mode. Cadence mode keeps it. | PROPOSED - not owner-approved |
| Reconcile on start (Design C) | No timer. Event-triggered at construction, on each fill, before each place, and on `Timer(daily_rollover)`. | DESIGN-A (C draft) | `C-risk-promotion-live.md` line 97, fc3af56. Adds zero timers. | PROPOSED - not owner-approved |

### 2.1 Hermes cron cutover (EVT-13)

Enabled lines and names from `hermes/cron/jobs.yaml`. Each job disabled in event mode.

| Job (name line) | Enabled line | Proposed | Marking | Reason | Status |
|---|---|---|---|---|---|
| [bot:scout] discover (16) | 14 | Disable | DESIGN-A; OD-13 | TokenLaunched and Migration events replace it (A s.6). | PROPOSED - not owner-approved |
| [bot:risk] audit-open-leads (27) | 25 | Disable | DESIGN-A; OD-13 | CandidateReady wakes the risk seat (A s.6). | PROPOSED - not owner-approved |
| [bot:chief] pickup (38) | 36 | Disable | DESIGN-A; OD-13 | Relay of Escalation, HaltSet and BreakerTripped already notifies (A s.6). | PROPOSED - not owner-approved |
| [bot:rug] watch-paper (49) | 47 | Disable | DESIGN-A; OD-13 | PositionTick and HolderShift wake the rug seat (A s.6). | PROPOSED - not owner-approved |
| [bot:scout] pipeline (72) | 70 | Disable | DESIGN-A; OD-13 | Reads archived JSONL with no event source (A s.6). | PROPOSED - not owner-approved |
| [bot:chief] journal-rollup (61) | 59 | Disable. CONFLICT with A s.6, which keeps it with `require_activity`. | OD-13; N6 s.8 item 13 | N6 s.2 claim 15: `[SILENT]` is printed inside a running session, so `require_activity` does not avoid the call. | CONFLICT |

Doctor refuses event mode while any superseded job is enabled (`REQUIREMENTS.md:23`, EVT-13; A s.6). The static YAML does not prove installed state (`bot-00-chief/phase-13-planning:.planning/phases/14-event-driven-desk-and-grok-gateway/14-RESEARCH.md:198`).

## 3. Prefilter thresholds (GRK-01)

The prefilter runs before any budget is spent (`REQUIREMENTS.md:28`, GRK-01; `ROADMAP.md:148`).

| Gate | Proposed value | Marking | Reason and citation | Status |
|---|---|---|---|---|
| Metadata present | Required | REPO | `require_metadata = True` (`src/pumpgrok/config/sections/engine.py:20`); check at `src/pumpgrok/engine/monitor.py:137`. | PROPOSED - not owner-approved |
| Curve progress | Below 0.40 | REPO | `max_curve_progress = 0.40` (`engine.py:19`); check at `monitor.py:139`. | PROPOSED - not owner-approved |
| Minimum token age | At least 120 s | REPO | `min_age_seconds = 120.0` (`engine.py:21`); check at `monitor.py:141`. | PROPOSED - not owner-approved |
| Unique buyers | Present and at least 5 | REPO | `min_unique_buyers = 5` (`engine.py:18`); checks at `monitor.py:143-145`. | PROPOSED - not owner-approved |
| Creator reputation | Block after 1 rug | REPO | `block_creator_after_rugs = 1` (`engine.py:24`). A s.5 step 1 requires "reputation not blocked". | PROPOSED - not owner-approved |
| Age upper bound | UNKNOWN | UNKNOWN | A s.5 step 1 says "age within window" and gives no value. The repo has only a minimum (`monitor.py:141`). | UNKNOWN - owner value required |
| Rule pre-score floor (`grok.min_prerank`) | UNKNOWN | UNKNOWN | A s.5 step 1 names the setting. No `min_prerank` exists in the repo (searched). `compute_scores` exists (`src/pumpgrok/engine/scoring.py:41`). Do not reuse `min_total_score = 0.65` (`engine.py:23`; `scoring.py:64-69`). That gate runs on full totals after verdicts, not on a neutral LLM pre-score. | UNKNOWN - owner value required |
| Timing market-window definition | UNKNOWN | UNKNOWN | A s.5 step 1 uses "market-window event". Not defined in the repo or in A. | UNKNOWN - owner value required |
| Mint cooldown after exit | UNKNOWN duration | UNKNOWN | A s.5 step 1 says "no open position or cooldown for the mint". No duration in the repo or A. | UNKNOWN - owner value required |
| Checker gate (logic) | Runs only after earlier verdicts, and only when RiskEngine would not refuse for a non-LLM reason | DESIGN-A | A s.5 step 1. No numeric value. | PROPOSED - not owner-approved |
| GRK-11 admitted-candidate floor | At least 50 admitted candidates on the evidence dataset | REPO requirement | `REQUIREMENTS.md:38`, GRK-11. soak-3d admits none, so its ratio is vacuous (N6 s.3 item 8). | PROPOSED - not owner-approved |

## 4. Per-agent cache TTLs and cache key (GRK-02)

| Item | Proposed value | Marking | Reason and citation | Status |
|---|---|---|---|---|
| narrative TTL | 86400 s (24 h), keyed on text digest | DESIGN-A | A s.5 step 3. | PROPOSED - not owner-approved |
| auditor TTL | 300 s | DESIGN-A | A s.5 step 3. | PROPOSED - not owner-approved |
| timing TTL | 900 s | REPO | `timing_cache_seconds = 900.0` (`engine.py:47`) already names this TTL. A s.5 uses the same value. | PROPOSED - not owner-approved |
| checker TTL | 60 s | DESIGN-A | A s.5 step 3. | PROPOSED - not owner-approved |
| Transport-error negative cache | 30 s | DESIGN-A | A s.5 step 3. Stops retry storms. | PROPOSED - not owner-approved |
| Fallback results | Never cached | REPO requirement | GRK-02 (`REQUIREMENTS.md:29`); A s.5 step 3. | PROPOSED - not owner-approved |
| Cache store | Sidecar sqlite, LRU 5000 rows. In-memory on replay. | DESIGN-A | A s.5 step 3. Sidecar rule: A s.0. | PROPOSED - not owner-approved |
| Cache key form | Explicit payload of ints and strings only. Decimal stringified. | DESIGN-A, corrected by N6 | N6 s.8 item 14 and s.3 item 6. Repo hazards: `_VOLATILE_RE` (`src/pumpgrok/replay/recorder.py:38-41`) drops keys matching `_at`, `seed`, `span`; `_freeze` raises TypeError on Decimal (`recorder.py:55-65`). | PROPOSED - not owner-approved |
| Key hash function | `canonical_request_hash` | REPO | `recorder.py:68-71`; GRK-02 (`REQUIREMENTS.md:29`). | PROPOSED - not owner-approved |
| Key field names | kind, agent, model, prompt_sha, schema, sanitizer version, input | DESIGN-A names | A s.5 step 3. | PROPOSED - not owner-approved |
| Exact `input` field list | UNKNOWN | UNKNOWN | A names the payload but does not list its fields. | UNKNOWN - owner value required |
| Sanitizer version constant | UNKNOWN value | UNKNOWN | A names `SANITIZER_VERSION`. No repo value exists. | UNKNOWN - owner value required |

## 5. In-flight bound (GRK-03)

| Item | Proposed value | Marking | Reason and citation | Status |
|---|---|---|---|---|
| Coalescing mechanism | One shared future per key. Identical concurrent requests share one call. | REPO requirement; DESIGN-A mechanism | GRK-03 (`REQUIREMENTS.md:30`); A s.5 step 4. | PROPOSED - not owner-approved |
| Numeric in-flight bound | UNKNOWN | UNKNOWN | A gives no number. Existing GrokOps semaphore defaults to 1 (`src/pumpgrok/core/llm.py:24,27`). A's `events.max_concurrency = 4` (A s.2.1) bounds event lanes, not Grok calls. | UNKNOWN - owner value required |
| Identical-request replay check | 100 concurrent identical requests produce 1 call | REPO requirement | `ROADMAP.md:148` (criterion 2) and `ROADMAP.md:160` (criterion 14). | PROPOSED - not owner-approved |

## 6. Daily and window budgets (GRK-04)

| Layer | Proposed value | Marking | Reason and citation | Status |
|---|---|---|---|---|
| Minute | 6 calls | DESIGN-A | A s.5 step 5. | PROPOSED - not owner-approved |
| Hour | 60 calls | DESIGN-A | A s.5 step 5. | PROPOSED - not owner-approved |
| Day (UTC) | 400 calls. CONFLICT with legacy 2000. | DESIGN-A; CONFLICT | Legacy vendor `max_grok_calls_per_day = 2000` (`ef2f2f6^:vendor/grokbot-pumpfun/src/models.py:387`; `config.example.yaml:96`). Five times the proposal. | CONFLICT |
| Atomicity and restart | All-or-nothing across layers. Window start from `clock.now()`. Survives restart. Fails closed if unreadable. | REPO requirement; DESIGN-A | GRK-04 (`REQUIREMENTS.md:31`); A s.5 step 5. Plan 14-01 requires unwritable persistence to refuse transport (`14-01-PLAN.md:59`). | PROPOSED - not owner-approved |
| Day boundary | UTC calendar day | REPO | `src/pumpgrok/core/budget.py:16-18` (`utc_day`), rollover at `:31-36`. | PROPOSED - not owner-approved |
| Current repo default | None | REPO | `CallBudget` requires `max_per_day` with no default (`budget.py:24-25`). `GrokGatewaySettings` (`src/pumpgrok/config/sections/v4.py:25-29`) has only `enabled` and `allowlist`. | Fact recorded |
| Exhaustion escalation | One `Escalation(grok_budget_exhausted)` per transition | DESIGN-A; kind is free text REPO | A s.5 step 6. `Escalation.kind` is a plain `str` (`src/pumpgrok/ledger/events.py:283`). | PROPOSED - not owner-approved |

## 7. Reserve share (GRK-04)

| Item | Proposed value | Marking | Reason and citation | Status |
|---|---|---|---|---|
| Reserve share | Top 20 percent of each layer, usable only by reserve-priority calls | DESIGN-A | A s.5 step 5. GRK-04 requires honoring the reserve share (`REQUIREMENTS.md:31`). | PROPOSED - not owner-approved |
| Reserve caller | Checker only, immediately before a sniper buy | DESIGN-A | A s.5 (last paragraph of s.5). | PROPOSED - not owner-approved |
| Different reserve | OD-17 slice reserve of 0.20 is a separate strategy reserve | OD-17 | Not the Grok reserve. Do not conflate. | Fact recorded |

## 8. Fallback ladder and breaker (GRK-06, GRK-07)

| Item | Proposed value | Marking | Reason and citation | Status |
|---|---|---|---|---|
| Ladder order | fresh, cache_hit, or coalesced; then prefilter_skip; then rule_fallback; then observe_only_buys (if require_llm); then pessimistic | DESIGN-A labels; repo modes REPO | A s.5 "Fallback ladder". `signal_scoring_mode` returns replay, llm, observe_only_buys, or rule_fallback (`src/pumpgrok/supervisor/scheduler/degraded.py:89-97`). The ladder labels fresh, cache_hit, prefilter_skip, and pessimistic have no repo constant. | PROPOSED - not owner-approved |
| Rule-based fallback | Missing LLM components score 0.0 | REPO | `docs/SAFETY_INVARIANTS.md:142`. | PROPOSED - not owner-approved |
| Checker default | Rejection is the pessimistic default | REPO | `docs/SAFETY_INVARIANTS.md:142`. | PROPOSED - not owner-approved |
| LLM availability flag | Set `llm_available = False` on breaker trip, restore on half-open success | REPO field; DESIGN-A rule | `llm_available` (`degraded.py:73`). A s.5 step 6. | PROPOSED - not owner-approved |
| require_llm | Existing flag, unchanged | REPO | `degraded.py:76` and `:95`. | PROPOSED - not owner-approved |
| Attempts per call | 3 (existing default), backoff between attempts | REPO | `max_retries: int = 3` (`src/pumpgrok/engine/agents/base.py:71`); attempt loop `:163`; backoff `:172`, `:207`. | PROPOSED - not owner-approved |
| Total call deadline | 20 s on `clock.timeout`. A hung transport must not delay an exit. | DESIGN-A; REPO requirement | A s.5 "Never blocking". GRK-07 (`REQUIREMENTS.md:34`). | PROPOSED - not owner-approved |
| Breaker failure threshold | 3 consecutive failures. CONFLICT with legacy 8. | DESIGN-A; CONFLICT | A s.5 step 6. Legacy `breaker_failures: int = 8` (`ef2f2f6^:vendor/grokbot-pumpfun/src/models.py:390`; `config.example.yaml:99`). Repo `src/pumpgrok/core/llm.py` has no breaker (docstring lines 1-4). `docs/SAFETY_INVARIANTS.md:142` says a breaker was ported to `core/llm.py`. The two disagree. | CONFLICT |
| Breaker cooldown | 60 s on injected Clock. CONFLICT with legacy 120 s. | DESIGN-A; CONFLICT | A s.5 step 6. Legacy `breaker_cooldown_seconds: float = 120.0` (`models.py:391`; `config.example.yaml:100`). | CONFLICT |
| Half-open probe | One probe after cooldown. Success closes the breaker. | DESIGN-A | A s.5 step 6. Legacy half-open logic at `ef2f2f6^:vendor/grokbot-pumpfun/src/ops.py:131-185`. | PROPOSED - not owner-approved |
| Budget-exhaustion fallback | rule_fallback until the window rolls | DESIGN-A | A s.5 step 6. | PROPOSED - not owner-approved |

## 9. Bus constants that bound wake and source behavior (EVT-08, EVT-09)

The repo constants are the tracked Phase 12 design. `docs/design/events-grok.md:121-141` states them, and says "The bus reads these names". Proposed column = repo value unless marked otherwise.

| Constant | Repo value | Design A value | Proposed | Marking | Status |
|---|---|---|---|---|---|
| P0_LANE_CAP | None (`src/pumpgrok/events/constants.py:9`) | Soft bound 10000 with producer blocking (A s.2.2) | None | CONFLICT | CONFLICT - owner choice |
| P1_LANE_CAP | 1000 (`constants.py:10`; `docs/design/events-grok.md:128`) | Per lane 256; P1+P2 total 4096 (A s.2.2) | 1000 | CONFLICT | CONFLICT - owner choice |
| P0_DEDUP_TTL_S | 86400 (`constants.py:15`) | Per-kind TTLs of 1 h, 10 min, 24 h (A s.2.2) | 86400 | CONFLICT | CONFLICT - owner choice |
| P1_DEDUP_TTL_S | 300 (`constants.py:16`) | Per-kind TTLs as above | 300 | CONFLICT | CONFLICT - owner choice |
| P2_DEBOUNCE_S | 1.0 (`constants.py:17`) | SocialMention 30 s; HolderShift 5 s (A s.2.2) | 1.0; per-kind windows UNKNOWN | CONFLICT | CONFLICT - owner choice |
| BACKOFF_MAX_S | 16.0 (`constants.py:23`) | backoff_cap_s 60 (A s.3) | 16.0 | CONFLICT | CONFLICT - owner choice |
| BACKOFF_INITIAL_S, BACKOFF_FACTOR, BACKOFF_JITTER_S | 1.0, 2, 1.0 (`constants.py:21,22,24`) | Base 1; jitter `0.5 + rng` (A s.3) | Repo values | CONFLICT on jitter form | CONFLICT - owner choice |
| STABLE_S | 30.0 (`constants.py:13`) | stable_s 30 (A s.3) | 30.0 | Agree | PROPOSED - not owner-approved |
| STALE_AFTER_S | 120.0 (`constants.py:12`) | WS stale 120 (A s.3) | 120.0 | Agree | PROPOSED - not owner-approved |
| SHUTDOWN_TIMEOUT_S | 5.0 (`constants.py:20`) | `close(grace_s)`, no value (A s.2.2) | 5.0 | UNKNOWN for A's grace | UNKNOWN - owner value required |
| events.max_concurrency, priority_workers | None in repo | 4 and 2 (A s.2.1) | UNKNOWN | DESIGN-A | UNKNOWN - owner value required |
| Event kind catalog | 12 kinds (`models.py:24-38`) | About 20 kinds (A s.1) | UNKNOWN | CONFLICT | UNKNOWN - owner value required |

## 10. Preconditions still open (not values)

- Baseline capture on the exact clean starting tree (`14-01-PLAN.md:42`). Not performed here.
- Phase 12 status. `bot-00-chief/phase-13-planning:.planning/STATE.md:26-42` says Phase 12 completion and current-head verification remain unresolved. The 12-02 and 12-03 artifacts required by 14-01 are not verified here.
- Owner and RISK reviews. None recorded (`bot-00-chief/phase-13-planning:.planning/phases/14-event-driven-desk-and-grok-gateway/14-VALIDATION.md:116`, Pending).
- Trading-smoke pin. N6 s.3 item 1 says smoke-10m is nearly blind. N6 s.8 item 9 requires pinning the trading `smoke` ledger hash and rows.

## 11. Decisions the owner must approve

1. Adopt A (fc3af56) with the N6 corrections as the policy source of record, or name an owner-reviewed replacement. Record a RISK review as the 14-01 gate requires.
2. Event kind catalog: one catalog in `events/models.py`, with the final kind list (section 1.1 b and section 9).
3. Wake matrix in section 1, including the journal rollup change (section 1.1 a).
4. Allowed timers in section 2: include the 45 s MTM refresh, and make `STALE_AFTER_S` the single staleness owner.
5. Hermes: disable all six superseded jobs, including the daily rollup (OD-13), rather than keep it with `require_activity` (section 2.1).
6. Prefilter UNKNOWNs in section 3: age upper bound, `grok.min_prerank`, market-window definition, and mint cooldown duration.
7. Cache TTLs of 24 h, 300 s, 900 s, 60 s, and a 30 s negative cache; LRU of 5000 rows; the exact `input` key fields and the sanitizer version (section 4).
8. In-flight numeric bound (section 5, UNKNOWN).
9. Budgets: minute 6, hour 60, day 400 (Design A) versus legacy 2000 per day.
10. Reserve share of 20 percent, usable by the checker only.
11. Breaker: 3 failures and a 60 s cooldown with one half-open probe (Design A), versus legacy 8 and 120 s. Also resolve the conflict between `docs/SAFETY_INVARIANTS.md:142` and `src/pumpgrok/core/llm.py:1-4`.
12. Bus constants in section 9: keep the repo values or adopt Design A values. Most important is `BACKOFF_MAX_S` (16 versus 60).
13. GRK-11 evidence: use a synthetic dataset with at least 50 admitted candidates instead of soak-3d, which admits none (N6 s.3 item 8; `REQUIREMENTS.md:38`).
14. Preconditions in section 10: baseline capture and Phase 12 current-head verification before any implementation.

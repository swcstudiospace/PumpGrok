---
gsd_state_version: "1.0"
milestone: v4
milestone_name: PumpGrok Desk v4
status: ready_to_plan
stopped_at: v4 roadmap, requirements and plans written; ready to plan Phase 11.
last_updated: "2026-10-28T00:00:00Z"
last_activity: 2026-10-28
last_activity_desc: v4 planning artifacts written (roadmap, requirements, project, state, 74 plans in plans.json); no plan started.
current_phase: 11
progress:
  total_phases: 9
  completed_phases: 0
  blocked_phases: 0
  total_plans: 74
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (v4 section). Core value: the desk reacts to events instead of polling, runs several bounded strategies in paper against live-recorded data, promotes and demotes them on recorded evidence, and carries a fully built but DORMANT live path that only a human can arm; no agent and no desk process can move real funds.

## Current Position

- Milestone: v4 (PumpGrok Desk v4), the only open milestone. v2 is shipped and archived; v3 is closed and archived on main by PR 27 (merge 0ca794d): .planning/milestones/v3-ROADMAP.md, v3-REQUIREMENTS.md, v3-MILESTONE-AUDIT.md.
- Phase: 11 of 19 (Engineering foundation and quality), ready to plan. Status: ready to plan Phase 11. No plan has started, no SUMMARY file exists.
- Progress: 0 of 9 phases, 0 of 74 plans (11, 5, 7, 9, 8, 7, 7, 11 and 9 plans in phases 11 to 19). Percent 0.
- Plan source: `.planning/research/v4/final/plans.json` is the single source for plans, seats, waves, dependencies, requirement ids and acceptance commands; `.planning/research/v4/final/pr-plan.md` lists the 45 pull requests. The GSD workflow writes each plan's PLAN and SUMMARY files under `.planning/phases/NN-*/`.
- Replay hashes at planning time: smoke-10m events.hash b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d (seq 2, 41 events, two runs identical). The trading `smoke` replay in a clean cwd gave bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54 (verify CONSISTENT, seq 11, 5 events) at repo HEAD 641927c; plan 11-01 re-measures it at the `v4-base` tag.
- Repository facts at planning time (HEAD 641927c): draft PRs 17 to 20 are not on main, so `backtest/equity.py`, a public `is_writer` and `verify_stored_content` are not yet there; plan 11-01 carries preflight commands that fail until they merge. `VENUE_FEE_BPS = 100` in `execution/fees.py`. Live is refused (exit 3).
- Integration branch: `v4/integration` collects merged plan PRs for the checkpoint runs; each plan has its own branch `bot-0N-seat/v4-pPHASE-slug` and receipt `.receipts/bot-0N-seat/slug.json`.

## Discovery (2026-10-25, carried forward)

- Gates, verified present in Makefile and pyproject.toml:
  - format and lint: make lint (ruff check; ruff format --check)
  - type check: make typecheck (mypy --strict src/)
  - test: make test (pytest -q)
  - repository check: ./scripts/check.sh
  - replay smoke: uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
  - replay hash: uv run pumpgrok verify --fixture smoke-10m, run twice; hashes must match
  - live refusal: uv run pumpgrok run --mode live --once; exit 3 required
  - gateway: cd services/desk-gateway && uv run pytest -q
  - gate runner: python3 ci/gates/run_all.py --bot bot-00-chief --base origin/main --receipt .receipts/bot-00-chief/phase-N.json (G-1 to G-7)
  - dependency audit: make audit (pip-audit). Run at milestone close, not per phase.
  - build: defined by Dockerfile and docker-compose.yml; no make target; not run per phase; manual.
  - Absent gates: none. Format, lint, type check and test all exist.
  - Gates added by v4 plans (not present yet): `make cov` and `make test-all` and `make test-soak` and `make mutation-smoke` (plans 11-03, 11-05); `uv run python ci/gates/check_idle_grok.py` wired into `ci/gates/run_all.py`, the Makefile and `ci.yml` (plan 14-07); signer suite `cd services/desk-signer && uv run pytest -q` with its own lint, mypy and audit (plan 18-03); `python3 scripts/generate-templates.py --check` already exists and gates the amendment (plan 18-07).
  - Run every hash command in a fresh git worktree (no `var/ledger.sqlite`): `verify` reads the active-set record from the working-directory ledger, which changes the hash.
- The G-2 bypass family (collect-only test runs, tolerated failures, discarded stderr, forced or dry runs, inline live-enable variables) never appears in any plan or receipt command. Skip checks use `! uv run pytest PATH -rs | grep -q SKIPPED`.

## Owner decisions

Settled 2026-10-28 (not open): live is armed once by a human, then autonomous inside caps; live limits stay inside the current rules (notional cap at most 1.0 SOL, D6 fractions); custody is a segregated signer process; amendments are drafted for the owner and applied only by a human-approved pull request; draft PRs 17 to 20 are approved for merge in the order 18, 19, 20, 17; receipts are approved as human:SomeRandmGuyy in batches at the ship checkpoints after phases 12, 14, 17 and 19.

Open decisions below carry a recommended default. If no answer arrives by the needed-by point the default applies and the plan's receipt lists it in `unverified`, so execution is never blocked on a silent gap. Source: `.planning/research/v4/final/owner-decisions.md`.

| ID | Decision | Default | Plans | Needed by | If undecided | Status |
|----|----------|---------|-------|-----------|--------------|--------|
| OD-01 | Approve the exact amendment text: `C-AMENDMENT-DRAFT.md` as corrected by `amendment-errata.md` (E1 to E5). | Approve with the errata. | 18-07 and all amendment_wait plans (18-03 to 18-06, 18-08, 18-09) | Checkpoint 17 (before Phase 18 merges) | Only 18-01 and 18-02 can land; signer, live adapter, shadow, runbooks stay drafts. Phases 11 to 17 and the rest of 19 are unaffected. | Open, default applies |
| OD-02 | Desk caps for the multi-strategy paper desk: `max_open_positions` (today 3) and `max_trades_per_day` (today 20) cannot serve four strategies. | New overlay `paper-event.toml`: 6 open positions, 40 trades per day. Live overlay unchanged at 3 and 20 (live stays inside current rules). | 15-02 (B10), 12-01 | Start of Phase 15 | Overlay ships with 3 and 20; strategies starve each other, backtests show it. | Open, default applies |
| OD-03 | REVIEW defaults the designs left open: holder concentration fraction, strategy daily loss fraction, consecutive losses, drift tolerance. | Holder fraction 0.30; strategy loss 0.25 of slice; 4 consecutive losses; `live.drift_tolerance_lamports` 5_000_000 (0.005 SOL, above ATA rent 2_039_280 plus creator-fee vault effects). | 12-01, 17-01, 17-02, 18-02, 18-05 | Before 17-01 (loss, losses), 17-02 (holder), 18-05 (drift); binding before any arm | Defaults apply and stay REVIEW-marked in the code and receipts. | Open, default applies |
| OD-04 | Human review of the curve layout probe and the event decode record, and the two VERIFIED flips (LAYOUT_STATUS, EVENT_DECODE_STATUS). | Owner runs `scripts/probe_pump_accounts.py` read-only against mainnet (plan 11-09 delivers it), reviews the record in `docs/CURVE_LAYOUT_PROBE.md` and the decode fixtures, sets `reviewed_by: human:NAME`; plan 13-05 then flips both. | 11-09, 13-02, 13-05 | Checkpoint 14 | Both stay ASSUMED; prices from logs and curve reads are unverified and live-fed paper buys fail closed. The event desk then runs recorded datasets only; nothing else in v4 needs VERIFIED. | Open, default applies |
| OD-05 | Paid RPC provider (HTTP and WebSocket). The public endpoint cannot carry 128 curve log subscriptions or about 100 MB per 30 s. | Choose a paid provider; endpoint and key via environment on the operator host, never git. Without a decision: public endpoint with `datafeed.watch_max` 32, logsSubscribe only for held mints, PumpPortal for new tokens. | 13-01, 13-02, 17-04 | Before the first live-fed paper run (after checkpoint 17) | Reduced watch set; recorded evidence grade stays research for coverage. | Open, default applies |
| OD-06 | Ticket number width `SOL-YYYYMMDD-NNN` (3 digits) versus four strategies. | Keep 3 digits; tickets allocated for approved intents only (at most `max_trades_per_day`); C-01 refuses at 999 with a typed error. Widening needs a contract change acknowledged by all ten seats. | 15-01 | Start of Phase 15 | Default applies. | Open, default applies |
| OD-07 | Maximum arm expiry. | `live.arm_max_expiry_hours` 72, hard ceiling 168; every arm is re-signed after expiry. | 12-01, 18-02 | Before 18-02 | Default applies. | Open, default applies |
| OD-08 | Strand risk: live strategies exit before the curve completes (no PumpSwap sells in v4) versus supporting `pool=pump-amm` sells in the signer. | Exit before completion: `max_progress at most 0.85`, `exit_progress at most 0.92`, required for LIVE_ELIGIBLE. PumpSwap sells are a later milestone. | 15-04, 15-05, 17-03 | Start of Phase 15 | Default applies. | Open, default applies |
| OD-09 | Paper fee model v2 constants and the Phase 15 trading-smoke re-pin. | v2 = current venue 100 bps plus PumpPortal 50 bps when the builder is PumpPortal, ATA rent 2_039_280 lamports on the first buy of a mint, signer priority-fee cap; a human checks them against the official fee pages (REVIEW). Approve the before and after pair at checkpoint 17. | 13-03, 15-01, 15-07 | Before 15-01 merges | FEE2 does not merge; v1 stays default and backtests understate live cost (documented). | Open, default applies |
| OD-10 | Autonomy level for the live-paper desk: a human sets `autonomous-paper` (otherwise paper approvals are missing). | Owner sets it once on the live-paper ledger when the first live-fed run starts. Below it, RT2 journals refused intents and approves nothing. | 15-06, 17-04 | First live-fed paper run | Event desk runs but places no paper orders. | Open, default applies |
| OD-11 | Signer deployment: separate container or host, uid and socket group, key file path. | Separate container on the same host, shared socket volume, group `desk-signer-clients`, socket mode 0660, key at `DESK_SIGNER_CREDENTIAL_PATH` (0400, signer uid), placed by the human. | 18-01, 18-03, 18-09 | Before 18-03 | Default compose service ships. | Open, default applies |
| OD-12 | Funding rule versus the 200 USD throwaway limit when SOL is above 200 USD. | `cap_sol = min(1.0, 200 USD / SOL price minus fees)` computed at arm time; fund at most cap plus fees. Runbook and errata E4 state it. | 18-09, 18-07 | Before 18-09 | Runbook states the stricter reading (do not fund above 200 USD). | Open, default applies |
| OD-13 | Hermes cutover in event mode: disable scout-discover, scout-pipeline, risk-audit-open-leads, chief-pickup, rug-watch-paper and the daily rollup. | Disable all six; the journal cycle performs the rollup on `Timer(daily_rollover)`. | 14-04, 14-06 | Checkpoint 14 | Cadence mode (default) is unchanged; event mode refuses to start (doctor) while a superseded job is enabled. | Open, default applies |
| OD-14 | Transaction builder for the signer: PumpPortal trade-local behind a TxBuilder interface (third party) versus direct pump instruction building. | PumpPortal trade-local with the instruction-level allowlist and a pinned fee recipient; direct building is a later option behind the same interface. | 18-04 | Before 18-04 | Default applies. | Open, default applies |
| OD-15 | Initial mint block and allow lists (`mint_lists.toml`, human-required file). | Empty blocklist, allowlist disabled. | 17-02 | Before 17-02 merges | Default applies. | Open, default applies |
| OD-16 | Promotion thresholds beyond the LiveGate floors (the loader refuses looser values). | Floors: 14 days, 50 closed trades, profit factor 1.2, drawdown 0.15; plus `min_shadow_orders` 20, `max_shadow_slippage_gap_bps` 150, demotion when profit factor below 1.0 over the last 20 closed. | 17-03 | Before 17-03 merges | Default applies. | Open, default applies |
| OD-17 | Strategy slice weights for four enabled strategies (sum at most 1). | legacy_screening, momentum_breakout, new_launch_sniper, mean_reversion at 0.20 each, 0.20 unallocated reserve. | 15-02 | Start of Phase 15 | Default applies. | Open, default applies |
| OD-18 | Nightly soak schedule and CI minutes (3 virtual days of event-mode soak, about 50 minutes with the other soaks). | GitHub Actions `schedule` at 03:00 UTC. | 19-04 | Before 19-04 | Soak stays manual. | Open, default applies |
| OD-19 | Owner reads the v4 milestone audit (AUDIT-19 is human-gated) and confirms live is refused on the final tree. | Read at checkpoint 19. | 19-08 | Checkpoint 19 | Milestone not closed. | Open, default applies |
| OD-20 | Event mode as the default (`wake_mode`) and removal of `stop_loss_poll_seconds` from bounds. | Keep `cadence` the default through v4 (config-gated everything); decide the flip in the next milestone after a week of live-paper evidence. | 15-04 | After checkpoint 17 | Default applies. | Open, default applies |
| OD-21 | Confirm the four ship checkpoints (after Phases 12, 14, 17, 19) and the batch approval of receipts. | Confirm. | all human-gated PRs (pr-plan.md sections 4 and 5) | Now | Receipts are approved PR by PR. | Settled 2026-10-28: four checkpoints confirmed; receipts approved as human:SomeRandmGuyy |
| OD-22 | Re-home the ten files merged under the PR 27 waiver (8 bot-02-risk, 1 bot-04-sniper, 1 bot-09-journal) to their owning seats, or accept them | accept and record as debt | none | before the v4 cleanup change | the files stay on main without owner review, recorded as debt | Open, default applies |

Not decided here because they are not v4 scope: which strategy and parameter hash the owner arms first, and when; all arm and rollback steps (human-only runbooks).

## Ship checkpoints

| Checkpoint | Phases | Human receipts (PRs) | Decisions due |
|------------|--------|----------------------|---------------|
| CP12 | 11, 12 | PR-01, PR-05, PR-06, PR-09 | OD-02, OD-03 defaults, OD-09 review starts, OD-21 confirmed; OD-04 probe run may start |
| CP14 | 13, 14 | PR-14, PR-20 | OD-04 (probe review and the two status flips), OD-05, OD-10, OD-13; OD-01 text circulating |
| CP17 | 15, 16, 17 | PR-23, PR-30 | OD-01 (approved in writing before Phase 18 merges), OD-03, OD-06, OD-08, OD-09 (trading-smoke re-pin pair), OD-11, OD-14, OD-15, OD-16, OD-17 |
| CP19 | 18, 19 | PR-34, PR-35, PR-36, PR-37, PR-43, PR-45 | OD-07, OD-12, OD-18, OD-19 (owner reads the audit) |

## Dependency levels and scheduling

Plan levels (longest chain of depends_on; plans on one level are independent and may run in parallel, subject to the shared-file order below):

| Level | Plans |
|-------|-------|
| 0 | 11-01, 11-03, 18-01 |
| 1 | 11-02, 11-06, 11-07, 11-08 |
| 2 | 11-04, 11-09, 13-03 |
| 3 | 11-05, 12-01, 18-07 |
| 4 | 11-10, 12-02, 15-01 |
| 5 | 11-11, 12-03, 13-01, 14-01, 16-01, 18-03 |
| 6 | 12-04, 13-02, 14-02, 14-03, 15-02, 18-04 |
| 7 | 12-05, 13-04, 14-04, 14-05, 15-03, 15-06, 19-01 |
| 8 | 13-05, 14-06, 15-04, 15-05, 16-02 |
| 9 | 13-06, 14-07, 15-07, 16-03 |
| 10 | 13-07, 14-08, 15-08, 16-04, 16-05, 17-01 |
| 11 | 14-09, 16-06, 17-02, 17-03, 19-02 |
| 12 | 16-07, 17-04, 18-02 |
| 13 | 17-05, 18-05, 19-03, 19-04 |
| 14 | 17-06, 18-06, 18-08, 19-05, 19-07 |
| 15 | 17-07, 18-09, 19-06 |
| 16 | 18-10, 19-08 |
| 17 | 18-11, 19-09 |

Phase level view:

- Level 0: Phase 11. Plans 11-01 (pins, waivers, receipt glob) and 11-03 (dev tooling, CI) start first, after draft PRs 16 to 20 are merged and tagged `v4-base`. 11-01 unblocks every other plan.
- Level 1: Phase 12 needs only 11-01 and 11-04 (the settings split); the rest of Phase 11 may run in parallel. Phase 12 is developed as a draft stacked on the Phase 11 quality PR (depth 2) and retargeted when it merges.
- Level 2: Phase 13. Plan 13-03 (sniper: fee model v2, paper factory, entry hook) needs only Phase 11 and may start early.
- Level 3: Phase 14 (needs 13-02). Plans 14-01 and 14-03 need only Phase 12 and Phase 11 and may start early.
- Level 4: Phase 15 (needs 14-03 and Phase 13). Plan 15-01 may start once Phases 12 and 13 land.
- Level 5: Phase 16 (needs Phase 15 and 14-07).
- Level 6: Phase 17 (needs Phases 15 and 16).
- Level 7: Phase 18 (needs 17-02, 17-03, 17-04 for most plans). Plans 18-01 (stop state, additive live source, signer schema) and 18-07 (the amendment pull request) depend only on Phase 11 and may start early; 18-01 first, because the contract acknowledgements take a round trip.
- Level 8: Phase 19 (needs Phases 17 and 18). Plans 19-01, 19-02 and 19-03 may start after Phases 13, 16 and 14 respectively.
- Amendment gate: plans 18-03, 18-04, 18-05, 18-06, 18-08 and 18-09 are amendment_wait. They merge only after the owner approves the exact amendment text (OD-01) and plan 18-07 merges. Until then only 18-01 and 18-02 can land and the signer, live adapter, shadow mode and runbooks stay drafts; Phases 11 to 17 and the rest of Phase 19 are unaffected.
- Human-gated plans: 13-05 (VERIFIED flips need a human reviewed_by; the default is to leave ASSUMED), 18-07 (the owner applies and merges the amendment), 19-08 (the owner reads the milestone audit).
- Rule: a plan starts when its depends_on plans have merged. Parallelism only inside a wave of file-disjoint plans and different seats. At most three phases have open PRs, three open PRs per seat and eight overall. The orchestrator is the only writer of this file and ROADMAP.md; the chief close plan of each phase updates them.

Shared-file merge order (a later plan merges only after the earlier one): `.planning/ROADMAP.md` and `.planning/STATE.md` 11-09 / 11-11 then 12-05, 13-07, 14-09, 15-08, 16-07, 17-07, 18-11, 19-09; `CHANGELOG.md` 11-10, 12-04, 13-06, 14-08, 15-07, 16-06, 17-06, 18-10, 19-06; `.github/workflows/gates.yml` 11-01, 18-07, 19-04; `src/pumpgrok/cli/dispatch.py` 12-02, 16-04, 17-03, 18-02, 18-05; `src/pumpgrok/doctor.py` 11-04, 14-07, 18-02, 19-04. The full table is in `pr-plan.md` section 8.

## Pauses and blockers (owner decisions)

1. External prerequisite EXT:PRS-16-20-MERGED: plans 11-01, 11-03, 11-09 (and later phases through their dependencies) wait for the owner-approved merge of draft PRs 16 to 20 (order 18, 19, 20, 17 for 17 to 20). Nothing in v4 starts before it.
2. EXT:OWNER-APPROVES-AMENDMENT-TEXT (OD-01): the exact text of the amendment draft as corrected by errata E1 to E5, approved in writing, before Phase 18 merges (checkpoint 17).
3. EXT:HUMAN-REVIEWS-PROBE-RECORD and EXT:HUMAN-REVIEWS-EVENT-DECODE (OD-04): the owner runs `scripts/probe_pump_accounts.py` read-only against mainnet and reviews the record before plan 13-05 flips LAYOUT_STATUS and EVENT_DECODE_STATUS; without the review both stay ASSUMED and the event desk runs recorded datasets only.
4. Tracker rows: Linear rows stay skipped (owner decision: free issue quota exceeded); Notion rows exist.

## Decisions

- v4 planning method: the three designs (events and Grok gateway, strategies backtest and data, risk promotion and live) were critiqued (N6, 29 ranked items) and every item was applied to the plan set (`changes-applied.md`); 74 plans over 127 units in 45 pull requests, seat-pure except the amendment pull request.
- Requirements: 111 across 14 families; EVT-11, STR-02 and RSK-07 are merged into PRC-03 and carried by no plan. 16 requirements were added by the plan set (PRC-09 to PRC-11, EVT-14, STR-06, FEE-01, MKT-10, RT-01 to RT-04, RSK-09, LIV-17 to LIV-20).
- Replay hash rule: smoke-10m never moves; the trading-smoke hash moves once, in Phase 15 (fee model v2 default, OD-09); every phase records both before and after pairs in CHANGELOG.md.
- Live stays refused in every phase: criterion `uv run pumpgrok run --mode live --once; test $? -eq 3` is in every phase and in the milestone audit; every overlay ships `live.enabled = false`.
- Phase commands run as orchestrated gsd-planner, gsd-executor, gsd-plan-checker and gsd-verifier subagents; one local commit per verified unit; no branch deletion (AGENTS.md); briefs use absolute worktree paths and no angle brackets.
- Receipts: one per pull request, `task_id` = slug; human-gated receipts are committed WITHOUT approved_by and the PR stays draft with a failing G-2 by design until the owner approves the batch at the checkpoint.

## Deferred and backlog (not in v3 requirements)

- Resolved in this run: the float SOL completion constant is gone. monitor.py and its characterization test use integer lamports only (R28, commit 968a733).
- Resolved in this run: the four oversized modules (paper_adapter, cli, scheduler, risk engine) are now packages, and no module in them exceeds 800 lines. Gates are green at 7a0b6eb with the replay hash unchanged, and no suppression marker was added. Other large modules were not decomposed.
- Phase 3 human actions: G-4 consumer acknowledgements; live bonding-curve confirmation (needs an account).
- Omega CI migration (commits 5b5d6a1 and 9772655): owner sign-off needed. Recorded in CHANGELOG under phase 6.
- The PR 14 waiver in .github/workflows/gates.yml is stale, since PR 14 merged. Remove it in the same change as the milestone waiver.
- Criterion 16 (draft PR) conflicts with the owner's ready-PR decision. Requirement text unchanged.

## Deferred Items (carried from v2 audit)

v2 audit tech_debt carried forward at v2 close (.planning/milestones/v2-MILESTONE-AUDIT.md). Status `deferred-to-v3` means a v3 requirement covers the item; `deferred-beyond-v3` means none does.

| Source | Item | Status | Maps to |
|--------|------|--------|---------|
| phase 4 | Trailing-stop peaks are held in memory; a serve restart re-learns them | deferred-to-v3 | INT-09 |
| phase 4 | Replay and serve hold the last curve tick after the recording ends (fixture semantics) | deferred-beyond-v3 | none |
| phase 4 | A recorded tick inside an order's latency window is skipped by the timeline; the confirmation read sees the latest tick | deferred-beyond-v3 | none |
| phase 4 | PaperAdapter.mark_to_market (per mint) keeps original stamping; replay uses the combined mark, any live caller would mix marks | deferred-beyond-v3 | none (live caller out of scope) |
| phase 4 | A held mint that stops ticking blocks buys after the 60 s staleness limit (by design) | deferred-beyond-v3 | none (by design) |
| phase 4 | Ledger-mark fallback closed before the change reported venue fee 0; marks after it carry the venue fee | deferred-to-v3 | INT-07 |
| phase 4 | bot-06-exit roster exec.place input does not list exit_reason; the gateway refuses rule sells over HTTP | deferred-beyond-v3 | Out of Scope (human-owned roster) |
| phase 5 | Kill channel: a pending KILL and the request offset live in memory until commit | deferred-beyond-v3 | none (v2 next goal) |
| phase 5 | Telegram getUpdates behaviour (webhook 409, group chats, bot privacy mode) is not verified without a live bot | deferred-beyond-v3 | Out of Scope (Telegram live verification) |
| phase 5 | The gateway kill poll can block its owner loop up to 2 s every 5 s during a Telegram outage | deferred-beyond-v3 | none |
| phase 5 | Flatten barrier is in-process only; a cross-process flatten does not wait | deferred-beyond-v3 | none |
| phase 5 | killswitch flatten exits 6 with flatten_status incomplete; exit 5 is not implemented | deferred-beyond-v3 | none |
| phase 5 | Container: DESK_GATEWAY_REPO_ROOT is set by the image; overriding it to /app brings back the missing desk-tool files | deferred-beyond-v3 | none |
| phase 5 | Two roots under ./var by decision (ledger var/ledger.sqlite, kill latch var/desk/KILLSWITCH) | deferred-beyond-v3 | none (owner decision, no action) |
| process | PR 9 shipped with --ignore-gsd by owner decision (recorded in its PR body) | deferred-beyond-v3 | none (recorded) |
| process | One-time gate waivers for PR 6, PR 8, PR 9 (all merged) and PR 11; remove PR 11's waiver after its merge | deferred-beyond-v3 | none (owner action) |
| process | Omega CI runner migration (main 5b5d6a1, 9772655) was merged by another seat and not reviewed in the v2 audit | deferred-beyond-v3 | none (needs a separate review) |
| process | Planning on main was stale until the v2 closeout merged | resolved | v2 archive on main; this branch starts from it |

## Session Continuity

- Last update: 2026-10-28, after the v4 roadmap, requirements, project and state were written from `plans.json`.
- Resume: read this file, then `.planning/ROADMAP.md` (Phase 11) and `.planning/REQUIREMENTS.md`; the plan layer is `plans.json` (74 plans) and `pr-plan.md`.
- Next: merge the owner-approved draft PRs 16 to 20 (order 18, 19, 20, 17), tag `v4-base`, then plan Phase 11 (`gsd-plan-phase 11`) and start plans 11-01 and 11-03. Plan 11-09 installs the v4 roadmap, requirements and project into the repository and archives v3.

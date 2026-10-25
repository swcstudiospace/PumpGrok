---
gsd_state_version: "1.0"
milestone: v3
milestone_name: PumpGrok Desk v3
status: in_progress
stopped_at: Phases 7-10 complete and verified; phase 6 blocked on owner decisions; milestone not shippable until resolved
last_updated: "2026-10-25T18:18:40Z"
last_activity: 2026-10-25
last_activity_desc: Phases 7-10 verified (07, 08, 09, 10 VERIFICATION.md); phase 6 blocked on owner decisions; ship waits on phase 6
current_phase: 6
progress:
  total_phases: 5
  completed_phases: 4
  blocked_phases: 1
  total_plans: 25
  completed_plans: 25
  percent: 80
---

# Project State

## Project Reference

See: .planning/PROJECT.md (v3 section). Core value unchanged: the desk runs autonomously in paper mode for 2-4 weeks and produces honest, replayable reports; no code path can move real funds.

## Current Position

- Milestone: v3 (PumpGrok Desk v3). The only open milestone. v2 is shipped and archived (.planning/MILESTONES.md).
- Phase: 6 of 10 (Integrity closure) is the only open phase, blocked on owner decisions. Phases 7, 8, 9 and 10 are complete; each has an independent verifier report (07-VERIFICATION.md, 08-VERIFICATION.md, 09-VERIFICATION.md, 10-VERIFICATION.md).
- Phase 6: code complete on the integration branch; BLOCKED on owner decisions (see Pauses).
- Phases 7 to 10: complete. Live stays refused (exit 3). Phase 6 gate state, owner decisions and the milestone PR are the remaining items.
- Integration branch: bot-00-chief/phase-6-integrity. The name predates v3 and is kept. Per-unit worktree branches bot-00-chief/p7-NN are merged into it.
- Percent 80 (4 of 5 phases complete). Known plans with SUMMARY files: 35 of 35 (phase 6 plans 01-09; phase 7 plans 01-06; phase 8 plans 01-10; phase 9 plans 01-07; phase 10 plans 01-03). Fix-up 06-01b is recorded but not counted.

## Discovery (2026-10-25)

- Milestone: v3 is the only open milestone. ROADMAP.md names it and MILESTONES.md lists v2 as shipped. No conflict.
- Discrepancy resolved: this file and the ROADMAP progress table read "Not started" for phase 6 after phase 6 artifacts existed. Artifacts win; both files now reflect them.
- Artifacts on disk: phase 6 has CONTEXT, PLAN 01-09, SUMMARY 01-09 plus 01b, and VERIFICATION (status gaps_found, corrected in that file). Phase 7 has CONTEXT and PLAN 01-06, with no SUMMARY. Phases 8-10 have no artifacts.
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
- TODO source: no tracked TODO file. Zero TODO, FIXME, HACK or XXX markers in src, tests, ci, scripts, services, skills, agents or contracts. TODO and FIXME text in docs/ and the v2 archive is historical design text, not active items. The TODO items are the session tracker, mapped below.

## TODO mapping

| TODO item | Disposition |
|---|---|
| Close v2 open items: R65 bonding-curve probe | Phase 6 INT-10. Probe script added; records ASSUMED with the exact error. VERIFIED needs a bonding-curve account, which was not supplied. |
| Close v2 open items: G-4 consumer acks | Human action outside code. Backlog (out of scope in REQUIREMENTS.md). |
| Close v2 open items: Phase 3 pending human items | TOOL-002 naming accepted; bonding-curve layout stays ASSUMED (see R65). Backlog. |
| Code quality: fix R28 float money in engine and other packages | Phase 6 INT-01 done on branch. Residual float constant CURVE_COMPLETION_SOL (engine/monitor.py:46) backlogged. |
| Code quality: decompose oversized modules with replay hash unchanged | Phase 6 INT-08 covers three functions. Wider decomposition backlogged (not in v3 requirements). |
| Create CLAUDE.md at repo root | Phase 7 DOC-01 (plan 07-01, wave 1). |
| Upgrade AGENTS.md | Phase 7 DOC-02 (plan 07-02, wave 2). |
| Upgrade README, ARCHITECTURE, SETUP, docs banners, CHANGELOG | Phase 7 DOC-03 and DOC-04 (plans 07-03 to 07-06). |
| Autonomy: verify autonomous-paper level end to end on replay | Phase 8 PAP-03. |
| Backtesting harness: holdout, walk-forward, trial count, byte-identical reports | Phase 8 BT-01 to BT-07. |
| Paper evaluation: backtest-to-paper divergence check | Phase 8 PAP-01 to PAP-03. |
| Strategy upgrade: propose-only candidates; auto-promotion after amendment | Phase 9 UPG-01 to UPG-06. |
| Live path: keep disabled, verify gate tests | Phase 10 LIV-01 and LIV-02. |

## Dependency levels and scheduling

- Level 0: phase 6. Complete in code; blocked on owner decisions.
- Level 1: phase 7. Phase 8 also depends only on phase 6, but runs after phase 7 in ROADMAP numeric order. Both edit CHANGELOG.md, so they are serialized.
- Level 2: phase 9 (depends on phase 8). Level 3: phase 10 (depends on phase 9).
- Rule: sequential by phase number. Parallelism only inside a wave of file-disjoint plans. The orchestrator is the only writer of this file and ROADMAP.md.

## Pauses and blockers (owner decisions)

1. Phase 6 receipt approved_by: you chose to hold it. Blocks phase 6 completion and the milestone PR. Phases 7-10 do not depend on it.
2. G-1 and G-2 route for the milestone PR.
   - A (recommended): a PR-bound owner waiver for G-1, G-2 and G-5/6, the mechanism .github/workflows/gates.yml uses for PR 14.
   - B: a RISK-authored ownership change merged to main first, with its own receipt.
   - The approved re-own to CHIEF cannot be done inside the PR. G-1 reads ownership.yaml from the PR checkout (ci/gates/check_ownership.py:26 and :236), so an edit would be checked against itself.
   - G-1 covers every v3 path. Docs match `**/*.md`, which is owned by bot-02-risk.
3. Tracker rows (ultrathink-kickoff, track complete): not run. They would create Notion and Linear rows for 7 issues and 52 sub-issues. Awaiting your yes or no.
4. Ship: not invoked. The ultrathink done-check would fail on two rule gaps: latest verification is gaps_found, and the roadmap is incomplete (ultrathink src/ship/assess.ts:50-53).

## Decisions

- Clarification q1 (live scope): settled by the approved v3 roadmap. Paper execution and risk code are in scope. Live stays refused (Phase 10). No live-adapter enablement.
- Clarification q2 (commits): one local commit per verified unit on the integration branch. No push. No branch deletion (AGENTS.md).
- Clarification q3 (pauses): pause only for categories a, b and c. Safe defaults otherwise.
- Phase commands run as orchestrated gsd-planner, gsd-executor, gsd-plan-checker and gsd-verifier subagents, not flat Skill() calls. Artifacts follow GSD formats. Recorded deviation.
- Phase 7 plan corrections, recorded in each SUMMARY:
  - OVERRIDE-A: the README version is 0.1.0. Plan 07-03's "plugin pack stays 1.0.0" is superseded by criterion 6.
  - OVERRIDE-B: VENDOR_PIN keeps the pin. The vendored snapshot was deleted in Phase 4, so criterion 6's snapshot clause cannot hold literally. The test asserts the pin and the retirement statement instead.
  - OVERRIDE-C: manifest descriptions say ten-seat.
- Phase 6 verification correction: criterion 17 is a FAIL, not a PASS. Criteria 1 and 11d were fixed at e770602. See 06-VERIFICATION.md.
- Phase 7 gates at HEAD 8e32f14: lint, typecheck, full test, check.sh, verify_doc_commands.sh and the smoke replay exit 0. The smoke-10m events.hash is b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d on both runs, identical to Phase 6. Live run exits 3. Criterion 5 is narrowed to the offline subset and recorded as such.
- Phase 7 execution incidents: four executor runs wrote into the main checkout (07-04 first attempt, 07-03, 07-05, 07-06). Each write was reverted or moved to its worktree, and main was checked clean after every merge. Briefs now require absolute worktree paths and no angle brackets, because angle brackets in task text caused dispatch to fail.
- Phase 8 correction set: the first Phase 8 evaluator scored candidates with a SHA-256 digest of the seed, parameter hash and fold ids. No fills fed it, and the report showed zero fees and no metrics. That was a fabricated evaluator. The correction set (08-08 to 08-10, see 08-CORRECTION.md) replaced it with replayed net realized lamports, measured metrics, and conservative eligibility (promotion_eligible false without a passing paper comparison). The plan checker had not caught it; its checklist now includes a hash-as-score check.
- Phase 8 result: smoke-10m replay hash unchanged (b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d). Per-fill fields are in memory only (G-10), so the ledger bytes did not change. Criterion 12's rationale wording is inaccurate; the recording obligation is met.

## Deferred and backlog (not in v3 requirements)

- engine/monitor.py:46 CURVE_COMPLETION_SOL is a float SOL constant that backs a characterization pin.
- Codebase-wide module decomposition beyond INT-08's three functions.
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

- Last update: 2026-10-25T18:18:40Z, after Phase 10 verification.
- Resume: read this file, then .planning/phases/06-integrity-closure/06-VERIFICATION.md (corrected) and the four VERIFICATION reports for phases 7 to 10.
- Next: owner decisions (see Pauses): approved_by for the phase 6 receipt; G-1 and G-2 route (option A owner waiver or option B RISK ownership change). Then the phase 6 gate, the milestone audit, and ultrathink-ship. Tracker rows (Notion and Linear) remain unanswered.

#!/usr/bin/env python3
"""Generate STATE.md for the start of v4 (ASCII only)."""
import json
import re
import sys
import collections

sys.path.insert(0, "/tmp/v4/final/gsd")
import _gen_roadmap as g

CUR = open("/root/src/repos/pumpgrok/.planning/STATE.md").read().split("\n")
OD = open("/tmp/v4/final/owner-decisions.md").read().split("\n")
PL = g.PL
BY = g.BYID


def line(i):
    return CUR[i - 1]


def asc(s):
    return s.replace("\u2013", "-").replace("\u2014", "-").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')


L = []
A = L.append
A("---")
A('gsd_state_version: "1.0"')
A("milestone: v4")
A("milestone_name: PumpGrok Desk v4")
A("status: ready_to_plan")
A("stopped_at: v4 roadmap, requirements and plans written; ready to plan Phase 11.")
A('last_updated: "2026-10-28T00:00:00Z"')
A("last_activity: 2026-10-28")
A("last_activity_desc: v4 planning artifacts written (roadmap, requirements, project, state, 74 plans in plans.json); no plan started.")
A("current_phase: 11")
A("progress:")
A("  total_phases: 9")
A("  completed_phases: 0")
A("  blocked_phases: 0")
A("  total_plans: %d" % len(PL))
A("  completed_plans: 0")
A("  percent: 0")
A("---")
A("")
A("# Project State")
A("")
A("## Project Reference")
A("")
A("See: .planning/PROJECT.md (v4 section). Core value: the desk reacts to events instead of polling, runs several bounded strategies in paper against live-recorded data, promotes and demotes them on recorded evidence, and carries a fully built but DORMANT live path that only a human can arm; no agent and no desk process can move real funds.")
A("")
A("## Current Position")
A("")
A("- Milestone: v4 (PumpGrok Desk v4), the only open milestone. v2 is shipped and archived; v3 is closed and archived by plan 11-09 (.planning/milestones/v3-ROADMAP.md, v3-REQUIREMENTS.md).")
A("- Phase: 11 of 19 (Engineering foundation and quality), ready to plan. Status: ready to plan Phase 11. No plan has started, no SUMMARY file exists.")
A("- Progress: 0 of 9 phases, 0 of 74 plans (11, 5, 7, 9, 8, 7, 7, 11 and 9 plans in phases 11 to 19). Percent 0.")
A("- Plan source: `/tmp/v4/final/plans.json` is the single source for plans, seats, waves, dependencies, requirement ids and acceptance commands; `pr-plan.md` lists the 45 pull requests. The GSD workflow writes each plan's PLAN and SUMMARY files under `.planning/phases/NN-*/`.")
A("- Replay hashes at planning time: smoke-10m events.hash b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d (seq 2, 41 events, two runs identical). The trading `smoke` replay in a clean cwd gave bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54 (verify CONSISTENT, seq 11, 5 events) at repo HEAD 641927c; plan 11-01 re-measures it at the `v4-base` tag.")
A("- Repository facts at planning time (HEAD 641927c): draft PRs 17 to 20 are not on main, so `backtest/equity.py`, a public `is_writer` and `verify_stored_content` are not yet there; plan 11-01 carries preflight commands that fail until they merge. `VENUE_FEE_BPS = 100` in `execution/fees.py`. Live is refused (exit 3).")
A("- Integration branch: `v4/integration` collects merged plan PRs for the checkpoint runs; each plan has its own branch `bot-0N-seat/v4-pPHASE-slug` and receipt `.receipts/bot-0N-seat/slug.json`.")
A("")
A("## Discovery (2026-10-25, carried forward)")
A("")
for i in range(40, 53):
    A(line(i))
A("  - Gates added by v4 plans (not present yet): `make cov` and `make test-all` and `make test-soak` and `make mutation-smoke` (plans 11-03, 11-05); `uv run python ci/gates/check_idle_grok.py` wired into `ci/gates/run_all.py`, the Makefile and `ci.yml` (plan 14-07); signer suite `cd services/desk-signer && uv run pytest -q` with its own lint, mypy and audit (plan 18-03); `python3 scripts/generate-templates.py --check` already exists and gates the amendment (plan 18-07).")
A("  - Run every hash command in a fresh git worktree (no `var/ledger.sqlite`): `verify` reads the active-set record from the working-directory ledger, which changes the hash.")
A("- The G-2 bypass family (collect-only test runs, tolerated failures, discarded stderr, forced or dry runs, inline live-enable variables) never appears in any plan or receipt command. Skip checks use `! uv run pytest PATH -rs | grep -q SKIPPED`.")
A("")
A("## Owner decisions")
A("")
A("Settled 2026-10-28 (not open): live is armed once by a human, then autonomous inside caps; live limits stay inside the current rules (notional cap at most 1.0 SOL, D6 fractions); custody is a segregated signer process; amendments are drafted for the owner and applied only by a human-approved pull request; draft PRs 17 to 20 are approved for merge in the order 18, 19, 20, 17; receipts are approved as human:SomeRandmGuyy in batches at the ship checkpoints after phases 12, 14, 17 and 19.")
A("")
A("Open decisions below carry a recommended default. If no answer arrives by the needed-by point the default applies and the plan's receipt lists it in `unverified`, so execution is never blocked on a silent gap. Source: `/tmp/v4/final/owner-decisions.md`.")
A("")
A("| ID | Decision | Default | Plans | Needed by | If undecided | Status |")
A("|----|----------|---------|-------|-----------|--------------|--------|")
rows = 0
for l in OD:
    m = re.match(r"^\| (OD-\d+) \| (.*) \| (.*) \| (.*) \| (.*) \| (.*) \|$", l)
    if not m:
        continue
    oid, dec, dflt, plans, needed, undec = [asc(x).strip() for x in m.groups()]
    status = "Open, default applies"
    if oid == "OD-21":
        status = "Settled 2026-10-28: four checkpoints confirmed; receipts approved as human:SomeRandmGuyy"
    A("| %s | %s | %s | %s | %s | %s | %s |" % (oid, dec, dflt, plans, needed, undec, status))
    rows += 1
assert rows == 21, rows
A("")
A("Not decided here because they are not v4 scope: which strategy and parameter hash the owner arms first, and when; all arm and rollback steps (human-only runbooks).")
A("")
A("## Ship checkpoints")
A("")
A("| Checkpoint | Phases | Human receipts (PRs) | Decisions due |")
A("|------------|--------|----------------------|---------------|")
A("| CP12 | 11, 12 | PR-01, PR-05, PR-06, PR-09 | OD-02, OD-03 defaults, OD-09 review starts, OD-21 confirmed; OD-04 probe run may start |")
A("| CP14 | 13, 14 | PR-14, PR-20 | OD-04 (probe review and the two status flips), OD-05, OD-10, OD-13; OD-01 text circulating |")
A("| CP17 | 15, 16, 17 | PR-23, PR-30 | OD-01 (approved in writing before Phase 18 merges), OD-03, OD-06, OD-08, OD-09 (trading-smoke re-pin pair), OD-11, OD-14, OD-15, OD-16, OD-17 |")
A("| CP19 | 18, 19 | PR-34, PR-35, PR-36, PR-37, PR-43, PR-45 | OD-07, OD-12, OD-18, OD-19 (owner reads the audit) |")
A("")
A("## Dependency levels and scheduling")
A("")
by = BY
lvl = {}


def L_(i):
    if i in lvl:
        return lvl[i]
    p = by[i]
    lvl[i] = 0 if not p["depends_on"] else 1 + max(L_(d) for d in p["depends_on"])
    return lvl[i]


for p in PL:
    L_(p["id"])
grp = collections.defaultdict(list)
for i, l in lvl.items():
    grp[l].append(i)
A("Plan levels (longest chain of depends_on; plans on one level are independent and may run in parallel, subject to the shared-file order below):")
A("")
A("| Level | Plans |")
A("|-------|-------|")
for l in sorted(grp):
    A("| %d | %s |" % (l, ", ".join(sorted(grp[l]))))
A("")
A("Phase level view:")
A("")
A("- Level 0: Phase 11. Plans 11-01 (pins, waivers, receipt glob) and 11-03 (dev tooling, CI) start first, after draft PRs 16 to 20 are merged and tagged `v4-base`. 11-01 unblocks every other plan.")
A("- Level 1: Phase 12 needs only 11-01 and 11-04 (the settings split); the rest of Phase 11 may run in parallel. Phase 12 is developed as a draft stacked on the Phase 11 quality PR (depth 2) and retargeted when it merges.")
A("- Level 2: Phase 13. Plan 13-03 (sniper: fee model v2, paper factory, entry hook) needs only Phase 11 and may start early.")
A("- Level 3: Phase 14 (needs 13-02). Plans 14-01 and 14-03 need only Phase 12 and Phase 11 and may start early.")
A("- Level 4: Phase 15 (needs 14-03 and Phase 13). Plan 15-01 may start once Phases 12 and 13 land.")
A("- Level 5: Phase 16 (needs Phase 15 and 14-07).")
A("- Level 6: Phase 17 (needs Phases 15 and 16).")
A("- Level 7: Phase 18 (needs 17-02, 17-03, 17-04 for most plans). Plans 18-01 (stop state, additive live source, signer schema) and 18-07 (the amendment pull request) depend only on Phase 11 and may start early; 18-01 first, because the contract acknowledgements take a round trip.")
A("- Level 8: Phase 19 (needs Phases 17 and 18). Plans 19-01, 19-02 and 19-03 may start after Phases 13, 16 and 14 respectively.")
A("- Amendment gate: plans 18-03, 18-04, 18-05, 18-06, 18-08 and 18-09 are amendment_wait. They merge only after the owner approves the exact amendment text (OD-01) and plan 18-07 merges. Until then only 18-01 and 18-02 can land and the signer, live adapter, shadow mode and runbooks stay drafts; Phases 11 to 17 and the rest of Phase 19 are unaffected.")
A("- Human-gated plans: 13-05 (VERIFIED flips need a human reviewed_by; the default is to leave ASSUMED), 18-07 (the owner applies and merges the amendment), 19-08 (the owner reads the milestone audit).")
A("- Rule: a plan starts when its depends_on plans have merged. Parallelism only inside a wave of file-disjoint plans and different seats. At most three phases have open PRs, three open PRs per seat and eight overall. The orchestrator is the only writer of this file and ROADMAP.md; the chief close plan of each phase updates them.")
A("")
A("Shared-file merge order (a later plan merges only after the earlier one): `.planning/ROADMAP.md` and `.planning/STATE.md` 11-09 / 11-11 then 12-05, 13-07, 14-09, 15-08, 16-07, 17-07, 18-11, 19-09; `CHANGELOG.md` 11-10, 12-04, 13-06, 14-08, 15-07, 16-06, 17-06, 18-10, 19-06; `.github/workflows/gates.yml` 11-01, 18-07, 19-04; `src/pumpgrok/cli/dispatch.py` 12-02, 16-04, 17-03, 18-02, 18-05; `src/pumpgrok/doctor.py` 11-04, 14-07, 18-02, 19-04. The full table is in `pr-plan.md` section 8.")
A("")
A("## Pauses and blockers (owner decisions)")
A("")
A("1. External prerequisite EXT:PRS-16-20-MERGED: plans 11-01, 11-03, 11-09 (and later phases through their dependencies) wait for the owner-approved merge of draft PRs 16 to 20 (order 18, 19, 20, 17 for 17 to 20). Nothing in v4 starts before it.")
A("2. EXT:OWNER-APPROVES-AMENDMENT-TEXT (OD-01): the exact text of the amendment draft as corrected by errata E1 to E5, approved in writing, before Phase 18 merges (checkpoint 17).")
A("3. EXT:HUMAN-REVIEWS-PROBE-RECORD and EXT:HUMAN-REVIEWS-EVENT-DECODE (OD-04): the owner runs `scripts/probe_pump_accounts.py` read-only against mainnet and reviews the record before plan 13-05 flips LAYOUT_STATUS and EVENT_DECODE_STATUS; without the review both stay ASSUMED and the event desk runs recorded datasets only.")
A("4. Tracker rows: Linear rows stay skipped (owner decision: free issue quota exceeded); Notion rows exist.")
A("")
A("## Decisions")
A("")
A("- v4 planning method: the three designs (events and Grok gateway, strategies backtest and data, risk promotion and live) were critiqued (N6, 29 ranked items) and every item was applied to the plan set (`changes-applied.md`); 74 plans over 127 units in 45 pull requests, seat-pure except the amendment pull request.")
A("- Requirements: 111 across 14 families; EVT-11, STR-02 and RSK-07 are merged into PRC-03 and carried by no plan. 16 requirements were added by the plan set (PRC-09 to PRC-11, EVT-14, STR-06, FEE-01, MKT-10, RT-01 to RT-04, RSK-09, LIV-17 to LIV-20).")
A("- Replay hash rule: smoke-10m never moves; the trading-smoke hash moves once, in Phase 15 (fee model v2 default, OD-09); every phase records both before and after pairs in CHANGELOG.md.")
A("- Live stays refused in every phase: criterion `uv run pumpgrok run --mode live --once; test $? -eq 3` is in every phase and in the milestone audit; every overlay ships `live.enabled = false`.")
A("- Phase commands run as orchestrated gsd-planner, gsd-executor, gsd-plan-checker and gsd-verifier subagents; one local commit per verified unit; no branch deletion (AGENTS.md); briefs use absolute worktree paths and no angle brackets.")
A("- Receipts: one per pull request, `task_id` = slug; human-gated receipts are committed WITHOUT approved_by and the PR stays draft with a failing G-2 by design until the owner approves the batch at the checkpoint.")
A("")
for i in range(107, 115):
    A(line(i))
A("")
for i in range(116, 140):
    A(line(i))
A("")
A("## Session Continuity")
A("")
A("- Last update: 2026-10-28, after the v4 roadmap, requirements, project and state were written from `plans.json`.")
A("- Resume: read this file, then `.planning/ROADMAP.md` (Phase 11) and `.planning/REQUIREMENTS.md`; the plan layer is `plans.json` (74 plans) and `pr-plan.md`.")
A("- Next: merge the owner-approved draft PRs 16 to 20 (order 18, 19, 20, 17), tag `v4-base`, then plan Phase 11 (`gsd-plan-phase 11`) and start plans 11-01 and 11-03. Plan 11-09 installs the v4 roadmap, requirements and project into the repository and archives v3.")
A("")
txt = "\n".join(L)
open("/tmp/v4/final/gsd/STATE.md", "w").write(txt)
print(len(txt), "bytes")

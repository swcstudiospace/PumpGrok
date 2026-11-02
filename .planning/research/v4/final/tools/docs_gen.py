"""Generate pr-plan.md, changes-applied.md, owner-decisions.md and amendment-errata.md from plans.json and _model.json."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

P = json.load(open("/tmp/v4/final/plans.json"))
MOD = json.load(open("/tmp/v4/final/_model.json"))
BY = {p["id"]: p for p in P}
plan_of = MOD["plan_of"]
pr_order = MOD["pr_order"]
pr_meta = {k: tuple(v) for k, v in MOD["pr_meta"].items()}
pr_plans = MOD["pr_plans"]
pr_deps = MOD["pr_deps"]
PRN = {k: f"PR-{i + 1:02d}" for i, k in enumerate(pr_order)}
H = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d"
CP = {11: 12, 12: 12, 13: 14, 14: 14, 15: 17, 16: 17, 17: 17, 18: 19, 19: 19}


def pl(*units: str) -> str:
    return ", ".join(sorted({plan_of[u] for u in units}))


def branch(k: str) -> str:
    seat, slug = pr_meta[k]
    return f"{seat}/{slug}"


def receipt(k: str) -> str:
    seat, slug = pr_meta[k]
    return f".receipts/{seat}/{slug}.json"


def pr_phase(k: str) -> int:
    return int(k[1:3])


def pr_human(k: str) -> list[str]:
    cats: list[str] = []
    for pid in pr_plans[k]:
        for r in BY[pid]["human_approver_reasons"]:
            c = re.sub(r"\s*\(.*$", "", r)
            if c not in cats:
                cats.append(c)
    return cats


def pr_seat(k: str) -> str:
    return pr_meta[k][0]


def agent_approver(k: str) -> str:
    return "bot-00-chief" if pr_seat(k) == "bot-02-risk" else ("bot-02-risk" if pr_seat(k) != "bot-02-risk" else "bot-00-chief")


def short(seat: str) -> str:
    return seat.replace("bot-", "")



def sanitize(t: str) -> str:
    for a_, b_ in (
        (" -> ", " then "), ("<=", "at most"), ("2>/dev/null", "stderr discard to /dev/null"), ("2>&1", "stderr merged"),
        ("<seat>", "SEAT"), ("<parent>", "PARENT"), ("<receipt>", "RECEIPT"), ("<name>", "NAME"), ("<old pin>", "OLD_PIN"), ("<new pin>", "NEW_PIN"),
    ):
        t = t.replace(a_, b_)
    return t

n_plans = len(P)
n_prs = len(pr_order)
per_phase = Counter(p["phase"] for p in P)
pr_per_phase = Counter(pr_phase(k) for k in pr_order)

# ============================================================================================ pr-plan.md
L: list[str] = []
a = L.append
a("# PumpGrok v4: pull request plan")
a("")
a(f"Inputs: `/tmp/v4/final/plans.json` ({n_plans} plans, nine phases), `/tmp/v4/planning/pr-topology.md`, `/tmp/v4/design/N6-critique.md` section 8. Every statement about code was checked against repo HEAD `641927c`; statements about PRs 17 to 20 assume the owner-approved merge (owner decision, settled) and are enforced by the preflight commands in plan 11-01. "
  "Seat ownership of every path of every plan was verified with `resolve_owner(path, load_manifest(DEFAULT_MANIFEST))`; the PR graph below was checked acyclic by `/tmp/v4/final/tools/build.py`.")
a("")
a("## 1. Summary")
a("")
a(f"- **{n_prs} pull requests** for **{n_plans} plans** (target was at most 45 PRs and about 60 plans). Per phase, plans: " + ", ".join(f"P{k} {v}" for k, v in sorted(per_phase.items())) + ". Per phase, PRs: " + ", ".join(f"P{k} {v}" for k, v in sorted(pr_per_phase.items())) + ".")
a("- Grouping rule: one PR per (phase, seat); a group is split only when a cross-seat dependency forces an order. The splits that occurred: Phase 11 risk (pins first, quality foundation last, because Q09 needs the sniper, rug, scout and chief splits), Phase 14 risk (gateway first, doctor and idle gate after the chief PR), Phase 19 chief (health metrics before the risk PR, docs and audit after it). "
  "The amendment PR is the only PR that is not seat-pure.")
a(f"- {n_plans} plans = 18 closers (one journal CHANGELOG plan and one chief `.planning` plan per phase) + {n_plans - 18} feature plans. The 127 units (111 sequencer units minus 4 deleted or split parents, plus 16 new units and 4 split halves) average 1.7 units per plan after bundling by (seat, phase); the new units and split halves add about a dozen plans (for example 12-01 SET0, 14-05 and 14-06 seat cycles, 17-05 recovery, 18-04 signer tx policy). Phase 11 (11 plans) and Phase 18 (11 plans) are above the 5 to 9 band because they carry 30 and 14 sequencer units; every other phase is inside it.")
a("- Pull-forwards used to save PRs (all sanctioned by `phases.md` pull-forward candidates): B01 (rug decoder) and B02 (chief probe script) ride in the Phase 11 rug and chief PRs; C-03s (sniper entry hook) rides in the Phase 13 sniper PR against a Protocol, which removes a Phase 17 sniper PR; B04c moves from Phase 13 to the Phase 14 chief PR.")
a("- Ship checkpoints (owner approves a batch of receipts): after Phase 12, after 14, after 17, after 19 (section 5). Plans only list which PRs need the human approver; no plan, receipt or script records that approval.")
a("")
a("## 2. Pull requests")
a("")
a("Columns: PR number (merge order), branch `bot-0N-seat/v4-pPHASE-slug`, seat, plans in the order they are committed, depends on (PR numbers, transitive reduction of the plan graph plus shared-file order), receipt path (one receipt per PR, `task_id` = slug, `branch` = the branch, `.gitignore` glob from PRC-RECEIPTS covers it), approver.")
a("")
a("| PR | Branch | Seat | Plans | Depends on | Receipt | Approver | Checkpoint |")
a("|----|--------|------|-------|------------|---------|----------|------------|")
for k in pr_order:
    hum = pr_human(k)
    if k == "P18-AMEND":
        appr = "human (owner applies and merges)"
    elif hum:
        appr = "human:owner (batch); agent review first"
    else:
        appr = f"{agent_approver(k)} (agent)"
    seat = short(pr_seat(k))
    deps = ", ".join(PRN[d] for d in pr_deps[k]) or "none"
    a(f"| {PRN[k]} | `{branch(k)}` | {seat} | {', '.join(pr_plans[k])} | {deps} | `{receipt(k)}` | {appr} | CP{CP[pr_phase(k)]} |")
a("")
a("Merge order inside a phase follows the table top to bottom; across phases follow the Depends column. A scheduler may start any PR whose dependencies are merged; development may run earlier on a stacked draft (depth 2, retarget to main through REST before the parent merges, `git merge origin/main` not rebase after the parent squash, skill `ultrathink-ship-stacked-prs`). "
  "At most three phases have open PRs, three open PRs per seat, eight overall.")
a("")
a("### Per-phase notes that change what a scheduler does")
a("")
a(f"- **Phase 11.** {PRN['P11-RISK-A']} (receipt glob, waiver removal, both hash pins, Q14c) merges first and unblocks everyone. {PRN['P11-SNIPER']}, {PRN['P11-RUG']}, {PRN['P11-SCOUT']}, {PRN['P11-CHIEF']} run in parallel. {PRN['P11-RISK-B']} contains Q09 (ratchet-down) and therefore merges last, after the four of them; it also contains Q13s, which Phase 12 needs, so Phase 12 is developed as a draft stacked on {PRN['P11-RISK-B']} (depth 2) and retargeted when it merges.")
a(f"- **Phase 13.** Order: {PRN['P13-SNIPER']} (status-agnostic execution tests, fee model v2 selectable, paper factory, entry hook) and {PRN['P13-RISK']} (datafeed, sources, probe docs with status-agnostic tests) first, then {PRN['P13-RUG']} (layout rewrite, then the human flips). Agnostic tests before the rewrite removes the rug to risk to rug cycle. If the human declines the flips, the flip commit is dropped from {PRN['P13-RUG']} and the phase closes ASSUMED.")
a(f"- **Phase 14.** {PRN['P14-RISK-1']} (gateway) then {PRN['P14-SIGNAL']} (agents) then {PRN['P14-CHIEF']} (wake, metrics, measurement, Hermes cutover, probe-script deletion, seat cycles) then {PRN['P14-RISK-2']} (doctor, failure suite, idle gate in CI). The chief PR is large (7 units); the seat-cycle plans (14-05, 14-06) are separate commits so a reviewer can stop after the wake core.")
a(f"- **Phase 15.** {PRN['P15-RISK']} then {PRN['P15-CHIEF']}. Plan 15-01 contains the only deliberate hash move of the milestone (FEE2: trading-smoke hash; smoke-10m unchanged) and its before and after pair is recorded by {PRN['P15-JOURNAL']}.")
a(f"- **Phase 17.** {PRN['P17-RISK']} (slice, kill, entry checks, feed health, promotion) then {PRN['P17-CHIEF']} (event desk composition root, restart recovery). Checkpoint 17 is the first point where the whole paper desk runs end to end on recorded data.")
a(f"- **Phase 18.** {PRN['P18-AMEND']} (owner-applied amendment) is independent of code; {PRN['P18-RISK']} contains plans that do not need it (18-01, 18-02) and plans that do (18-03 to 18-06): the PR as a whole merges after the amendment, but 18-01 may be developed and reviewed first (the contract acknowledgement round trip). {PRN['P18-SNIPER']}, {PRN['P18-CHIEF']} follow. Nothing in Phase 18 arms anything; live stays exit 3.")
a(f"- **Phase 19.** {PRN['P19-SCOUT']}, {PRN['P19-SIGNAL']}, {PRN['P19-CHIEF-1']} first; {PRN['P19-RISK']} after {PRN['P19-CHIEF-1']} (alerts need the metric names) and after the amendment; {PRN['P19-JOURNAL']}; then {PRN['P19-CHIEF-2']} (docs, milestone audit, close). The audit reads every phase's CHANGELOG lines, so it follows the journal PR.")
a("")
a("## 3. The amendment pull request (single exception)")
a("")
a(f"{PRN['P18-AMEND']} = plan 18-07 = units C-13 and C-14 plus the missed copies. It spans three seats (risk, chief, sniper), so it cannot pass G-1 as seat-pure. It carries ONE waiver (below) and nothing else in v4 does. N6 item 6: a human applies and merges it.")
a("")
a("**Preconditions.** (1) The owner approves, in writing, the exact text of `/tmp/v4/design/C-AMENDMENT-DRAFT.md` as corrected by `/tmp/v4/final/amendment-errata.md` (OD-01). (2) PRC-WAIVER (plan 11-01) and PLN-00 (plan 11-09) are merged. No other plan is required; the PR is independent of all code and may merge any time after both, recommended at the start of Phase 18 once checkpoint 17 passed.")
a("")
a("**Procedure.**")
a("1. The owner, or an executor working strictly from the approved text on a branch the owner opens, creates `bot-00-chief/v4-p18-amendment` from main. The `bot-00-chief` prefix satisfies the branch regex; agents never apply, paraphrase or merge the text on their own.")
a("2. Commit 1 (risk-owned files): `rules/pumpgrok-team.mdc`, `prompts/_shared/core-directives.xml`, `docs/RISK_POLICY.md` including section 3.3 line 128 (`R17: no live auto-exit exists`), `SECURITY.md`, `docs/LIVE_READINESS.md`, `docs/SAFETY_INVARIANTS.md`, `AGENTS.md:91`, `ARCHITECTURE.md:170`, `docs/ROSTER.md:116` and the key-custody rows at 196, 238, 280, `skills/key-custody/SKILL.md:24`, plus the new frozen oracle `tests/safety/amendment_2026_10_28_frozen.txt`, its test, the updated 2026-10-25 test, and `tests/safety/test_amendment_copies_complete.py` (greps every quoting file for the superseded phrases).")
a("3. Commit 2 (chief-owned files): `make prompts` regenerates `agents/*.md` and `prompts-assembled/*.xml` (including `agents/chief.md:72`, `agents/sniper.md` item 3); hand edits to `prompts/bot-00-chief.xml:65`, `skills/desk-operating-model/SKILL.md` lines 24 and 39, `.planning/PROJECT.md` out-of-scope rows, `README.md`, `SETUP.md:120,203,241`, `docs/runbooks/setup.md:27`. Commit 3 (sniper-owned): `prompts/bot-04-sniper.xml:6,27`.")
a("4. Open the PR. Once the number N exists, commit 4 changes `.github/workflows/gates.yml` so that exactly one step, `G-1 - Path ownership`, has `if: github.event.pull_request.number != N || github.event.pull_request.head.repo.full_name != github.repository` and sets the pinned waiver set in `ci/tests/test_no_pr_waivers.py` to `(N,)`. G-1 manifest self-check, bot derivation, G-2 through G-7 stay enforced (the 2026-10-26 waiver covered G-1, G-2, G-5 and G-6; this one is strictly narrower).")
a("5. Receipt: bot `bot-00-chief`, the branch, commands `uv run pytest -q tests/safety/test_constitution_amendment_2026_10_28.py tests/safety/test_constitution_amendment.py tests/safety/test_amendment_copies_complete.py`, `python3 scripts/generate-templates.py --check`, `make prompts`, `make check`; the `unverified` list names the single waived step, the PR number N and the approver. The owner supplies `approved_by` and merges.")
a("6. After merge, every `amendment_wait` plan unblocks (18-03 to 18-06, 18-08, 18-09). Plan 19-04 (PRC-19) is the only plan allowed to follow it in gates.yml: it removes the waiver and restores the empty set. A PR that fails G-1 anywhere else is split, never waived.")
a("")
a("## 4. Human approver (who needs `human:owner` and why)")
a("")
a("A seat never approves its own work. For PRs below, the agent reviewer (chief for risk-authored, risk for every other seat) reads the diff first; the owner then adds `approved_by` and `approved_at` in a single-file commit, in a batch at the checkpoint. Receipts for human-gated plans are committed WITHOUT `approved_by` and the PR stays draft with a failing G-2 by design (as PRs 17 to 20 did).")
a("")
a("| PR | Plans | Why a human approver |")
a("|----|-------|----------------------|")
for k in pr_order:
    hum = pr_human(k)
    if hum:
        a(f"| {PRN[k]} `{k}` | {', '.join(pr_plans[k])} | {'; '.join(hum)} |")
a("")
a("PRs not listed use an agent approver and are merged by an agent after green CI and the Greptile bar (V3-5; the score is never written into a receipt).")
a("")
a("## 5. Ship checkpoints")
a("")
a("The owner approves receipts in batches. Each checkpoint lists the PRs of its window that need `human:owner`, the owner decisions due (`owner-decisions.md`), and the integration check that must be green first (success criteria of the phases in the window, run on `v4/integration` per `pr-topology.md` section 10).")
a("")
for cp, phases in ((12, (11, 12)), (14, (13, 14)), (17, (15, 16, 17)), (19, (18, 19))):
    a(f"### Checkpoint {cp} (phases {', '.join(map(str, phases))})")
    a("")
    batch = [k for k in pr_order if pr_phase(k) in phases and (pr_human(k) or k == "P18-AMEND")]
    a("Human receipts in this batch: " + (", ".join(f"{PRN[k]} (`{k}`)" for k in batch) or "none") + ".")
    due = {
        12: "OD-02 and OD-03 (defaults), OD-09 (fee constants review starts), OD-21 (confirm these checkpoints). Also the one-time mainnet read-only probe run for OD-04 may start here (script from plan 11-09).",
        14: "OD-04 (probe review and the two status flips, plan 13-05), OD-05 (RPC provider), OD-13 (Hermes cutover), OD-10 (autonomy level for live-paper). OD-01 (amendment text) should already be circulating.",
        17: "OD-01 (amendment text approved in writing: required before Phase 18 merges), OD-03, OD-06, OD-08, OD-09 (Phase 15 trading-smoke re-pin pair), OD-11, OD-14, OD-15, OD-16, OD-17. The first live-fed paper run (needs OD-04, OD-05, OD-10) is the checkpoint demonstration.",
        19: "OD-07, OD-12, OD-18, OD-19 (the milestone audit is read by the owner). After this checkpoint nothing remains but the human arm procedure from the runbooks; live is still exit 3.",
    }[cp]
    a(f"Decisions due: {due}")
    a("")
a("## 6. Closing PRs per phase")
a("")
a("| Phase | Journal CHANGELOG PR | Chief `.planning` close PR |")
a("|-------|----------------------|-----------------------------|")
for ph in range(11, 20):
    j = [k for k in pr_order if pr_phase(k) == ph and pr_seat(k) == "bot-09-journal"]
    c = [k for k in pr_order if pr_phase(k) == ph and k.endswith("CLOSE")] or [k for k in pr_order if pr_phase(k) == ph and k == "P19-CHIEF-2"]
    a(f"| {ph} | {', '.join(f'{PRN[x]} plans {pr_plans[x]}' for x in j)} | {', '.join(f'{PRN[x]} plans {pr_plans[x]}' for x in c)} |")
a("")
a("Each journal PR adds one CHANGELOG section with `Phase N: smoke-10m events.hash before/after` AND `Phase N: trading-smoke events.hash before/after` lines (N6 section 3 item 7: equal pairs are recorded, not skipped). Phase 15 is the one phase where the trading-smoke pair differs (fee model v2); Phase 14 additionally records `events-smoke-10m` and `events-soak-3d` golden hashes; the Phase 19 PR also records the nightly soak golden hash. "
  "The chief close PR is the integration receipt for the phase (commands and exit codes of the phase success criteria run on `v4/integration`); closers merge in phase order.")
a("")
a("## 7. Receipt discipline (standard command set)")
a("")
a("Every PR receipt carries the commands of each of its plans (`acceptance_commands` in plans.json; all are written so that exit 0 means success, including the live-refusal check `uv run pumpgrok run --mode live --once; test $? -eq 3`, which is deployment-shaped and therefore carries a `rollback_plan` of 12 or more words). Rules added by N6:")
a("- Run receipts in a fresh git worktree (no `var/ledger.sqlite`): `verify` reads `operator_active_set` from the cwd ledger, which changes the hash (N6 section 3 item 3). The trading-smoke pin test also chdirs into a tmp path.")
a("- `pytest --co`, `--collect-only`, `-rs`-less skip checks, `|| true`, `2>/dev/null`, `--dry-run`, an inline `PUMPGROK_LIVE_ENABLE` never appear (G-2 bypass family). Plans use `! uv run pytest PATH -rs | grep -q SKIPPED` to prove no skips.")
a("- Plans that touch `src/` also run `make lint` and `make typecheck`; at PR level run `make check` (fast path after Q02) and `python3 ci/gates/run_all.py --bot <seat> --base <parent> --receipt <receipt>`; the full `pytest -q` including soak (about 50 minutes) is the nightly job, not a per-plan command.")
a("- Claims avoid exhaustive wording (all, every, no regressions) unless a command proves it. Hash lines: smoke-10m `" + H + "`; trading-smoke pinned in `tests/fixtures/replay/pins/trading_smoke.json` (observed at HEAD 641927c: `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54`, re-measured at `v4-base` by plan 11-01).")
a("- Foreign-test fallout: before a PR is marked ready run the whole suite; if a test owned by another seat fails, open a one-file companion plan by the owning seat and merge it first (contingent, not counted). Known contingent cases: CURVE_ACCOUNT_SIZE importers (kept stable), the narrow EventSource literals (pinned), gate reason strings (C-06).")
a("- Source of truth for GSD: `plans.json` is the input to `gsd-plan-phase`; the executor writes the PLAN.md and SUMMARY.md of each plan under `.planning/phases/NN-*/` (N6 section 6 criterion a: PLN-00 installs the phase directories, the per-plan files are produced by the workflow).")
a("")
a("## 8. Stack and shared-file merge order (computed)")
a("")
a("Files edited by more than one plan, in merge order (all same seat except the amendment PR). A later plan merges only after the earlier one.")
a("")
a("| File | Plans in order |")
a("|------|----------------|")
for f, ps in MOD["shared"]:
    a(f"| `{f}` | {' -> '.join(ps)} |")
a("")
a("Collapsed by this plan: `config/settings.py` is now touched by Q13s and SET0 only (was eight units); `cli/*.py` stays one serial lane (A1, A12, B18, C-05, C-06, C-10); `tests/conftest.py` only by B07; `gates.yml` and `ci/tests/test_no_pr_waivers.py` by PRC-WAIVER, the amendment PR and PRC-19.")
a("")
a("## 9. Risks that remain after the plan")
a("")
a("- PR size: PR 02 (quality foundation), PR 19/20 (event wake and cycles), the Phase 15 risk PR (five plans) and the Phase 18 risk PR (six plans, signer included) are large. The grouping rule keeps them as one PR each; an executor MAY cut numbered sub-PRs of the same seat for review size (`v4-p18-dormant-live-path-a`), recorded in the receipt `unverified` list; they do not change the PR count in this plan.")
a("- Review fatigue at checkpoints: batches contain between 2 and 12 human receipts; checkpoint 17 and 19 are the heavy ones.")
a("- The Phase 11 risk PR serializes the start of Phase 12; mitigated by the stacked draft.")
a("- N6 section 7 items with no plan by design: bus capacity on public RPC (OD-05 decides), pump.fun REST availability (B07 degrades), docs and runbooks for each new surface (D19c, D19r, C-15).")
open("/tmp/v4/final/pr-plan.md", "w").write(sanitize("\n".join(L) + "\n"))

# ============================================================================================ changes-applied.md
C: list[str] = []
c = C.append
c("# N6 section 8 changes applied to the plan set")
c("")
c("Method: the sequencer's 111 units (`/tmp/v4/planning/units.json`) were loaded, every N6 section 8 item was applied as a unit change (new, split, moved, deleted, re-dependent), the units were bundled into plans (`plans_def.py`), and `build.py` re-verified seat purity (`resolve_owner` for every path), dependency order (no plan depends on a later phase), shared-file order and PR acyclicity. "
  "Scripts: `/tmp/v4/final/tools/{units_v4,plans_def,build,docs_gen}.py` (reproducible: `cd tools && python3 build.py && python3 docs_gen.py`). Plan ids are `PHASE-NN`.")
c("")
c("Facts verified for this integration (not taken from the designs): repo HEAD `641927c` (PRs 17 to 20 not on main; only a private `_is_writer` exists at `ledger/active_set.py:51`); trading `smoke` replay in a clean cwd gives `events.hash=bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54`, `verify=CONSISTENT seq=11 events=5` (two runs, identical); smoke-10m gives `" + H + "` with `seq=2 events=41`; `VENUE_FEE_BPS = 100` in `execution/fees.py`; `Settings` section modules are not yet split (Q13s does it); `src/pumpgrok/supervisor/**` and `tests/desk/**` are chief-owned, `tests/**` otherwise risk, `execution/**` sniper, `cli/**` risk; EventSource literal spelled at nine sites (below).")
c("")
c("## 1. N6 section 8 ranked list")
c("")
c("| # | Sev | How the plan changed | Plans |")
c("|---|-----|----------------------|-------|")
rows = [
    (1, "BLOCKER", "LiveGate split into `check_entry` (all rows) and `check_exit` (rows 1, 2, 5, 6, 8 only); the engine calls `check_exit` for sells and mints `autonomous_live` for exit-rule and flatten sells while any live position is open, even with a halt, kill, breaker or expired arm; demotion never strands a position; amendment clause 2 last sentence rewritten to suspend entries only (errata E1). New acceptance: exit sells pass with halt set, kill file present, breaker open and arm expired; entries refused in the same states.", pl("C-06", "C-10", "C-13")),
    (2, "BLOCKER", "Arm record lists (strategy id, param hash) pairs; `live confirm --strategy id:hash`; any param hash change needs a new arm; maximum expiry `live.arm_max_expiry_hours` default 72, hard ceiling 168 (OD-07); config hash plus ledger-held param hashes bound; place frame carries `param_set_hash`; signer re-derives the current hash from stage rows. Errata E1/E2 add the pair and the maximum to the amendment text.", pl("SET0", "C-08", "C-06", "C-09a", "C-13")),
    (3, "BLOCKER", "C-09 split into C-09a (IPC, persistence, reconcile) and C-09b (TxBuilder, policy). C-09b implements the instruction-level allowlist (System Transfer to pinned recipient only; Token and Token-2022 deny list with CloseAccount only to wallet; ATA create only for wallet and intent mint; pump program discriminator allowlist with PDA equality; v0 ALT resolved or refused), signer-owned blockhash, and verification of the final signed bytes after compute-limit edits.", pl("C-09a", "C-09b")),
    (4, "BLOCKER", "New unit R0 generalizes `ParamSet`, `CandidateParams`, `load_bounds` and harness trial identity to `[strategy.ID.PARAM]`; legacy `content_hash` pinned byte-identical by a golden test; runs before B10, B12 and C-05 (all depend on it).", pl("R0")),
    (5, "BLOCKER", "New chief units: RT1a and RT1b (event-mode seat cycle bodies, Phase 14), RT2 (Intent to `exec.place` router with ticket and approval allocation, Phase 15), RT3 (full composition root: bus, sources, strategy runtime, gateway, router, promotion edges, Timer; Phase 17, dependencies A1, A3, A4, A5, A6, B07, B08, B10, C-05 plus RT1, RT2, B17), RT4 (restart recovery wiring) and risk-owned REC (strategy restore). WIRE-17 is bundled with RT3.", pl("RT1a", "RT1b", "RT2", "RT3", "RT4", "REC")),
    (6, "BLOCKER", "C-13 and C-14 become one owner-applied plan/PR (human applies and merges), list every missed copy (`prompts/bot-04-sniper.xml:6,27`, `prompts/bot-00-chief.xml:65`, `agents/chief.md:72`, `AGENTS.md:91`, `ARCHITECTURE.md:170`, `SETUP.md:120,203,241`, `docs/ROSTER.md:116`, `docs/runbooks/setup.md:27`, RISK_POLICY 3.3 R17 line 128, plus the finds `skills/key-custody/SKILL.md:24` and ROSTER key-custody rows), add `test_amendment_copies_complete.py`, record the waiver PR number N and the approver in the receipt and the pinned set; PRC-19 removes the waiver.", pl("C-13", "PRC-19")),
    (7, "BLOCKER", "C-07 now lists all nine literal sites: three risk-owned sites changed (`ledger/events.py:31`, `ledger/store.py:31`, `risk/engine/steps.py:222`) with 18 schemas, the six sniper and journal sites deliberately stay narrow and are pinned by an AST test; declared `breaking: false`, `semantic_changes: []`, every regenerated schema listed individually, `generate-event-schemas.py --check`. Contingent companion plans (not counted) cover the case where mypy forces a narrow site to widen. This chooses the first N6 alternative (list all literal files) without folding code into the waived PR.", pl("C-07")),
    (8, "BLOCKER", "`strategies/allocation.py` and `strategy_of` live in C-01 (plan 15-01); B10 and C-02 both depend on C-01 and no longer on each other for these; replay `REPLAY_TICKET` gap closed by RT2's real ticket allocation.", pl("C-01", "B10", "C-02")),
    (9, "MAJOR", "New TSMOKE unit pins the trading `smoke` ledger hash and full row dump in plan 11-01, before any engine unit (all splits depend on 11-01); A2 parity runs on `smoke`; A4 text corrected (it touches `serve.py`, hosts `run_once_replay`; claim is 'unchanged by test'); trading-smoke acceptance is added to every code plan.", pl("TSMOKE", "A2", "A4")),
    (10, "MAJOR", "T4 deleted. Wake, metrics and Hermes tests are chief-owned under `tests/desk` inside A4, A7, A8; the risk-owned idle and hang tests move into A10 after the code exists; EVT-08 is in A4's acceptance; no `importorskip`. O2t likewise deleted (item 24 of N6 section 4).", pl("A4", "A7", "A8", "A10", "O2")),
    (11, "MAJOR", "One catalog in `events/models.py` (A1) with every Design A, B and C kind and a single `EventPublisher`; B06, B07, B09 depend on A1; B07 depends on A3 and only decodes; X1 shrinks to the bridge with an explicit CurveTick-to-PositionTick mapping constant; backtest uses DeterministicBus ordering.", pl("A1", "A3", "X1", "B06", "B07", "B09")),
    (12, "MAJOR", "A3 owns staleness (SourceStateBook, SourceStatus); `DegradedState.ws_data_stale` is written by the A4 bridge from it, FeedHealth (C-04) and LivePriceSource (B08) read it; no `note_tick` call sites elsewhere. Allowed timers gain the 45 s MTM refresh (only while positions are open) and reconcile-on-start.", pl("A3", "A4", "B08", "C-04")),
    (13, "MAJOR", "Hermes daily rollup is disabled in event mode (`superseded_by: events`) and replaced by an event-triggered journal cycle on `Timer(daily_rollover)`; `require_activity` dropped; rug-watch disabled; idle desk starts zero sessions.", pl("A8", "RT1b")),
    (14, "MAJOR", "Explicit gateway cache-key payload of ints and strings, Decimals stringified, `canonical_request_hash` not fed raw requests; tests for Decimal stability and for renamed age-like fields.", pl("A5")),
    (15, "MAJOR", "New GRKFX evidence-50 fixture with at least 50 admitted candidates; A9's ratio gate runs on it and asserts the candidate count.", pl("GRKFX", "A9")),
    (16, "MAJOR", "Desk caps: owner decision OD-02 (default paper-event overlay 6 open positions, 40 trades per day; live stays 3 and 20), applied as a NEW overlay so no hash moves. Ticket width: OD-06 default keep three digits; C-01 refuses allocation at 999 with a typed error (no contract change, no silent wrap).", pl("B10", "C-01")),
    (17, "MAJOR", "Recorder manifest values are strings and every jsonl is listed; `DatasetCurveSource` uses a per-mint bisect index with a perf-shaped test.", pl("B09", "B16a")),
    (18, "MAJOR", "PF1 (sniper) adds a paper factory so B17's paper root never imports `build_adapter`; C-12 adds a separate live factory that imports the registered class by dotted path only when the gate is open; C-10 updates the import-graph test text (supervisor and CLI may reach the registry module, never the client).", pl("PF1", "B17", "C-10", "C-12")),
    (19, "MAJOR", "Socket mode 0660 plus group; attestation and identity served over the authenticated socket, never files in shared `var/`; persisted nonce window and signer-clock timestamps; time-sync check in doctor; the doc states that SO_PEERCRED across containers authenticates nothing beyond signer policy.", pl("C-08", "C-09a", "A12", "C-06")),
    (20, "MAJOR", "Stated: stage, kill and halt rows live in the paper ledger, the signer folds the live ledger; C-17 mirrors them idempotently at promotion, kill and halt edges and at arm time; C-01b reads both paths and reports provenance; the docs say this is consistency, not independence.", pl("C-01b", "C-17", "C-05")),
    (21, "MAJOR", "SET0 is the one settings skeleton plan (first in Phase 12); A0, B06, B09, B10, B16, C-02, C-06 lost their settings files; later units add no field. Unowned keys (watch_max, mtm_refresh_s, gap_haircut_bps, signer keys) are in SET0.", pl("SET0")),
    (22, "MAJOR", "Live-eligible strategies exit before completion: bounds `max_progress <= 0.85`, `exit_progress <= 0.92`, promotion threshold requires them (OD-08; PumpSwap sells out of scope); new human-gated unit B05e for `EVENT_DECODE_STATUS` beside the LAYOUT_STATUS flip.", pl("B12", "B13", "B14", "C-05", "B05e")),
    (23, "MAJOR", "Restart recovery: REC (risk library) plus RT4 (chief wiring and crash tests on `smoke` and strat-*), bus `recover()` in A1. Paper fee model: FEE1 (sniper, selectable v2, default v1, no hash move) and FEE2 (risk, default flip, trading-smoke re-pin, before and after lines in the Phase 15 CHANGELOG).", pl("REC", "RT4", "FEE1", "FEE2", "PCL-15")),
    (24, "MAJOR", "Q06 makes lint, typecheck and audit cover `services/` (path-conditional); A10 wires the idle-Grok gate into `run_all.py`, a pytest wrapper, `ci.yml` and the Makefile together; C-09a adds the signer's own lint, mypy and pip-audit over its own lock; O5 adds the nightly soak.", pl("Q06", "A10", "C-09a", "O5")),
    (25, "MINOR", "Claim errors corrected in unit notes: 5 (ladder modes: A5), 12 (`serve.py` hosts `run_once_replay`: A4), 22 (three seats import CURVE_ACCOUNT_SIZE: B03 keeps the name and value), 26 (manifest sources are `dict[str, str]`: B09, GRKFX), 40 (portal fee documented, only recipient unpinned: FEE1, C-09b).", pl("A5", "A4", "B03", "B09", "FEE1", "C-09b")),
    (26, "MINOR", "No setting name contains `seed`, `span` or an `_at` suffix (the cache-key regex drops them); `seed` renamed `rng_stream`.", pl("SET0", "B16b")),
    (27, "MINOR", "P (performance) and L (live path) metric families added to the event-mode metrics extension and the health sections.", pl("A7", "O2")),
    (28, "MINOR", "USD cap versus 1.0 SOL documented in the runbook and the errata (cap_sol = min(1.0, 200 USD / SOL price minus fees) at arm time, OD-12).", pl("C-15")),
    (29, "MINOR", "`stop_loss_poll_seconds` stays in bounds (cadence default) with a test that it has no effect in event mode; removal deferred (OD-20).", pl("B12")),
]
for r in rows:
    c(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
c("")
c("## 2. Other N6 findings applied (outside the ranked list)")
c("")
c("| N6 location | Disposition | Plans |")
c("|-------------|-------------|-------|")
more = [
    ("Verdict: PRs 17 to 20 not on main; `backtest/equity.py`, `is_writer`, `verify_stored_content` UNVERIFIED", "Preflight commands in plan 11-01 acceptance (fail until the PRs merged); B15, C-01b, C-05 rely on them.", pl("TSMOKE")),
    ("Section 1 contention: cli lane, tests/conftest.py, registry and bounds serialization, doctor chain, errors.py", "Shared-file chain computed in pr-plan.md section 8; B07 only owner of conftest.py; doctor chain Q20r, A12, C-06, O1.", pl("A12", "B07", "C-06")),
    ("Section 1 timers and ordering contradictions (EVT-10, A2 vs A4, C-05 Timer, C-04 transports)", "EVT-10 set extended (item 12); A2 proves determinism half, EVT-08 completes in A4; Timer kinds live in A1's catalog so C-05 needs no A4 dependency; C-04 depends on A3.", pl("A2", "A4", "C-04", "C-05")),
    ("Section 2 row 7, 9 (budget message, cache key hazard)", "A5 changes the precheck denial text to `budget.denial_reason()` and fixes the key.", pl("A5")),
    ("Section 2 row 25 (`run --record` is an exit-5 stub)", "B18 implements it on the B09 recorder.", pl("B18")),
    ("Section 3 items 4 and 5 (scan per call, FIFO continuation order)", "Bisect index (B16a); drain-until-quiescent (A2).", pl("B16a", "A2")),
    ("Section 3 item 7 (before and after lines per phase)", "Every journal plan records smoke-10m and trading-smoke before and after lines, including equal pairs.", pl("PCL-11", "PCL-15", "PCL-19")),
    ("Section 3 item 8 (GRK-11 vacuous on soak-3d)", "See item 15.", pl("GRKFX")),
    ("Section 4 importorskip, collect-only (T4), C-07 and G-4, tests owned by risk, import graph, dependencies", "T4 and O2t deleted; collect-only acceptance replaced (Q01, Q02); C-07 non-breaking with explicit surfaces; chief and sniper plans never edit `tests/live` or `tests/safety` (only risk plans do); signer tests only under `services/desk-signer/tests`.", pl("Q01", "Q02", "C-07", "C-09a")),
    ("Section 5.5 single send (fsync directory, finalized check for DROPPED, second RPC)", "C-09a.", pl("C-09a")),
    ("Section 5.6 UNKNOWN and drift (token balances, ATA rent, creator-fee vault)", "C-10 reconcile compares SOL and token balances inside `live.drift_tolerance_lamports` (OD-03).", pl("C-10")),
    ("Section 5.7 strand risk", "OD-08; ceilings in B12 to B14 and C-05.", pl("B12", "B13", "B14", "C-05")),
    ("Section 5.8 Token-2022 (wallet ATA extensions, re-check before send)", "C-03 (entry check) and C-09b (re-check immediately before send).", pl("C-03", "C-09b")),
    ("Section 5.9 amendment: failed on-chain result drops human wait; breaker auto-resets after 900 s", "C-10 latches `tx_failed_onchain` as a human-clear halt; errata E2 amends clause 3.", pl("C-10", "C-13")),
    ("Section 5.9 closing paragraph versus runbook step 4 (committed overlay with enabled=true)", "Runbook uses an operator-local `PUMPGROK_CONFIG` outside git; errata E3.", pl("C-15", "C-13")),
    ("Section 6 (a) no GSD phases, CONTEXT, PLAN, SUMMARY units", "plans.json is the plan layer; PLN-00 installs roadmap and requirements; per-phase CONTEXT and per-plan PLAN and SUMMARY files are produced by the GSD workflow from plans.json (not repo units).", pl("PLN-00")),
    ("Section 6 (b) no ci.yml, signer typecheck, soak split units", "Q02, Q06, C-09a, O5.", pl("Q02", "Q06", "C-09a", "O5")),
    ("Section 6 (c) vacuous fixtures, Hermes idle session, seat cycles", "Items 5, 13, 15.", pl("RT1a", "A8", "GRKFX")),
    ("Section 6 (d) verify fallback with real budget exhaustion in e2e", "RT3 e2e and A5 tests exhaust a real LayeredBudget.", pl("A5", "RT3")),
    ("Section 6 (e) autonomous-paper set by a human, EVENT_DECODE_STATUS review, restart recovery", "OD-10 (RT2 refuses and journals below the level), B05e, REC and RT4.", pl("RT2", "B05e", "REC", "RT4")),
    ("Section 6 (f) annualization under 7 days", "B15 returns annualization_valid=false and None.", pl("B15")),
    ("Section 6 (g) desk caps starve four strategies", "OD-02.", pl("B10")),
    ("Section 7 bus capacity on public RPC, paid-RPC decision", "OD-05; B06 and B07 default watch-set caps; no code assumes a paid provider.", pl("B06", "B07")),
    ("Section 7 pump.fun REST availability and Cloudflare", "B07 fallback degrades to SourceStatus(blind) and refuses buys.", pl("B07")),
    ("Section 7 time sync and `assert_no_skew`", "A12 doctor probe; C-08 hello skew check.", pl("A12", "C-08")),
]
for r in more:
    c(f"| {r[0]} | {r[1]} | {r[2]} |")
c("")
c("## 3. Unit-level delta against the sequencer (111 units)")
c("")
c("- **Deleted:** T4, O2t. **Split:** B16 into B16a and B16b; C-09 into C-09a and C-09b. **Re-scoped:** X1 (bridge only), A0 and every settings-touching unit (settings moved to SET0), C-03s (Protocol hook, Phase 13), C-07 (explicit literal list), C-13 and C-14 (one owner-applied PR with the missed copies).")
c("- **New units (16):** TSMOKE, Q06, SET0, B05e, FEE1, PF1, GRKFX, RT1a, RT1b, R0, FEE2, REC, RT2, RT3, RT4, C-17 (plus the split halves C-09a, C-09b, B16a, B16b).")
c("- **Moved between phases or PRs:** B01 and B02 pulled forward into the Phase 11 rug and chief PRs; B04c to Phase 14; C-03s to Phase 13; B04 and B04s no longer depend on B03 (agnostic tests first); B05 and B05e follow B04, B04s and the human review.")
c("- **Dependencies added:** B10 on R0, SET0, A1; B12 to B14 on R0 and FEE2; B07 on A1, A3; B08 on A3; B09 and B06 on A1 and SET0; A4 and A2 on TSMOKE; A10 on RT1b, A9, Q06; C-05 on R0, A3, B16b; C-02 on SET0, B16b; C-03 on C-03s; C-06 and C-10 on SET0; C-09a on Q06, SET0; C-11 on C-17; WIRE-18 on C-17.")
c(f"- Result: {len(P)} plans over 127 units (111 minus 2 deleted minus 2 split parents plus 4 split halves plus 16 new), {n_prs} PRs.")
c("")
c("## R. Requirement additions (for PLN-00 to install in `.planning/REQUIREMENTS.md`)")
c("")
c("| ID | Requirement | Carried by |")
c("|----|-------------|-----------|")
reqs = [
    ("PRC-09", "The trading `smoke` ledger hash and full row dump are pinned and checked in a clean cwd by every code plan.", pl("TSMOKE")),
    ("PRC-10", "CI lint, typecheck and audit cover services/ when present; the idle-Grok gate runs in CI.", pl("Q06", "A10")),
    ("PRC-11", "Every v4 settings section exists once in the settings skeleton, config-gated off.", pl("SET0")),
    ("EVT-14", "One event catalog and one source and staleness owner.", pl("A1", "A3")),
    ("STR-06", "Param identity covers strategy parameters; legacy content hashes unchanged.", pl("R0")),
    ("FEE-01", "Paper fee model v2 is selectable and the default flip records a before and after pair.", pl("FEE1", "FEE2")),
    ("MKT-10", "EVENT_DECODE_STATUS is VERIFIED only through a human-set reviewed_by.", pl("B05e")),
    ("RT-01", "Event-mode seat cycle bodies exist for all ten seats and run on wakes.", pl("RT1a", "RT1b")),
    ("RT-02", "Strategy Intents reach exec.place only through the router with ticket and approval allocation.", pl("RT2")),
    ("RT-03", "The event desk composition root wires bus, sources, runtime, gateway, router and promotion edges and refuses to build unless paper.", pl("RT3")),
    ("RT-04", "Restart recovery re-arms deadlines and restores tapes, peaks, probation and the watch set.", pl("REC", "RT4")),
    ("RSK-09", "Exit sells check only the live gate rows that make sense and are minted autonomous_live while any live position is open.", pl("C-06", "C-10")),
    ("LIV-17", "The arm record binds (strategy id, param hash) pairs with a stated maximum expiry.", pl("C-06")),
    ("LIV-18", "The signer enforces an instruction-level transaction allowlist with a signer-owned blockhash.", pl("C-09b")),
    ("LIV-19", "Stage, kill and halt are mirrored into the live ledger; signer persistence and drift checks cover tokens.", pl("C-09a", "C-10", "C-17")),
    ("LIV-20", "The literal sites of the event source are explicit, three widened, six pinned narrow.", pl("C-07")),
]
for r in reqs:
    c(f"| {r[0]} | {r[1]} | {r[2]} |")
c("")
c("## C. Amended phase success criteria (apply when PLN-00 installs the roadmap)")
c("")
c("- Phase 11 criterion 2: replace `uv run pytest tests/soak --collect-only -q 2>&1 | grep -qi deselected` by `uv run pytest -q tests/quality/test_fast_split.py` and the two `make -n` checks; add `uv run pytest -q tests/replay/test_trading_smoke_pin.py` and the three preflight commands (equity.py, is_writer, verify_stored_content); add Q06 checks (`make -n typecheck | grep -q services`).")
c("- Phase 12: add `uv run pytest -q tests/config/test_v4_settings_skeleton.py`; criterion 6 runs the parity on `smoke_trading` and the quiescence test; criterion 9 stays (no contract change).")
c("- Phase 13: replace `tests/desk/test_probe_pump_accounts.py` ownership note (B02 delivered in Phase 11); criterion 5 (probe script removal) moves to Phase 14; add `tests/tools/onchain/test_event_decode_status.py` and `tests/execution/test_fee_model_v2.py tests/execution/test_paper_factory.py tests/execution/test_entry_gate_hook.py`.")
c("- Phase 14: criteria 5, 8, 9 use `tests/desk/test_event_wake.py`, `tests/desk/test_hermes_jobs_superseded.py`, `tests/desk/test_metrics_events.py` (not `tests/supervisor` or `tests/` root); criterion 6 adds `-k smoke_trading`; criterion 7 adds `uv run pytest -q ci/tests/test_idle_grok_gate.py` and `grep -q check_idle_grok ci/gates/run_all.py`; criterion 10 runs on `tests/fixtures/replay/evidence-50` with `--min-candidates 50`; add `tests/desk/test_event_cycles.py tests/desk/test_event_cycles_aux.py tests/desk/test_event_golden_hashes.py`.")
c("- Phase 15: add `tests/upgrade/test_paramset_hash_stable.py tests/upgrade/test_paramset_strategy.py`, `tests/desk/test_intent_router.py tests/desk/test_ticket_approval_allocation.py`, `tests/strategies/test_recovery.py`, `tests/config/test_paper_fees_default.py`; criterion 10 changes: the smoke-10m pair is equal and the trading-smoke pair is `before: <old pin>`, `after: <new pin>`.")
c("- Phase 16: criterion 3 and 4 add `tests/backtest/test_dataset_curve_source_perf.py`.")
c("- Phase 17: criterion 8 adds `tests/desk/test_event_desk_e2e.py tests/desk/test_event_desk_idle.py tests/desk/test_restart_recovery.py tests/desk/test_restart_exit_deadlines.py`; criterion 4 hook test now ships in Phase 13.")
c("- Phase 18: criterion 5 becomes `cd services/desk-signer && uv run pytest -q` plus `uv run pytest -q tests/safety/test_signer_isolation.py` (no `tests/services/desk_signer`); add `tests/live/test_gate_exit_rows.py tests/live/test_arm_scope.py tests/live/test_arm_expiry_ceiling.py tests/live/test_exit_sells_autonomous_live.py tests/live/test_tx_failed_onchain_latch.py tests/live/test_stage_mirror.py tests/ledger/test_event_source_literal_sites.py tests/safety/test_amendment_copies_complete.py`; criterion 12 is the amendment oracle plus copies test.")
c("- Phase 19: criteria 3 uses `tests/desk/test_health_event_sections.py` and `tests/desk/test_metrics_strategy.py`; criterion 8 and 9 unchanged; O2t removed.")
c("")
c("## Verification performed")
c("")
c("- `resolve_owner` over every path of every plan: seat-pure for all plans except 18-07 (owners risk, chief, sniper, by design).")
c("- No plan depends on a plan of a later phase; shared explicit files are only shared within one seat (plus the amendment PR); PR graph acyclic with merge order consistent with the table in pr-plan.md.")
c("- No acceptance command matches the G-2 bypass family (`--co`, `--collect-only`, `|| true`, `2>/dev/null`, `--force`, `--dry-run`, inline `PUMPGROK_LIVE_ENABLE`).")
c("- Not exercised: any new unit's code, tests or hashes (designs only); the C-AMENDMENT-DRAFT wording; the claim that the PRs 17 to 20 symbols exist (plan 11-01 preflight proves it at v4-base).")
open("/tmp/v4/final/changes-applied.md", "w").write(sanitize("\n".join(C) + "\n"))

# ============================================================================================ owner-decisions.md
D: list[str] = []
d = D.append
d("# Owner decisions still needed")
d("")
d("Each decision has a recommended default so that execution is never blocked on a silent gap: if no answer arrives by the 'needed by' point the default applies and the plan's receipt lists it in `unverified`. Settled decisions (not repeated here): live armed once by a human then autonomous inside caps; live limits inside current rules (notional cap at most 1.0 SOL, D6 fractions); custody is a segregated signer; amendments drafted for the owner and applied only by a human-approved PR; draft PRs 17 to 20 merged before v4; the owner approves receipts as human:owner in batches per phase checkpoint.")
d("")
d("| ID | Decision | Recommended default | Plans that need it | Needed by | If undecided |")
d("|----|----------|---------------------|--------------------|-----------|--------------|")
ods = [
    ("OD-01", "Approve the exact amendment text: `C-AMENDMENT-DRAFT.md` as corrected by `amendment-errata.md` (E1 to E5).", "Approve with the errata.", "18-07 and all amendment_wait plans (18-03 to 18-06, 18-08, 18-09)", "Checkpoint 17 (before Phase 18 merges)", "Only 18-01 and 18-02 can land; signer, live adapter, shadow, runbooks stay drafts. Phases 11 to 17 and the rest of 19 are unaffected."),
    ("OD-02", "Desk caps for the multi-strategy paper desk: `max_open_positions` (today 3) and `max_trades_per_day` (today 20) cannot serve four strategies.", "New overlay `paper-event.toml`: 6 open positions, 40 trades per day. Live overlay unchanged at 3 and 20 (live stays inside current rules).", "15-02 (B10), 12-01", "Start of Phase 15", "Overlay ships with 3 and 20; strategies starve each other, backtests show it."),
    ("OD-03", "REVIEW defaults the designs left open: holder concentration fraction, strategy daily loss fraction, consecutive losses, drift tolerance.", "Holder fraction 0.30; strategy loss 0.25 of slice; 4 consecutive losses; `live.drift_tolerance_lamports` 5_000_000 (0.005 SOL, above ATA rent 2_039_280 plus creator-fee vault effects).", "12-01, 17-01, 17-02, 18-02, 18-05", "Before 17-01 (loss, losses), 17-02 (holder), 18-05 (drift); binding before any arm", "Defaults apply and stay REVIEW-marked in the code and receipts."),
    ("OD-04", "Human review of the curve layout probe and the event decode record, and the two VERIFIED flips (LAYOUT_STATUS, EVENT_DECODE_STATUS).", "Owner runs `scripts/probe_pump_accounts.py` read-only against mainnet (plan 11-09 delivers it), reviews the record in `docs/CURVE_LAYOUT_PROBE.md` and the decode fixtures, sets `reviewed_by: human:<name>`; plan 13-05 then flips both.", "11-09, 13-02, 13-05", "Checkpoint 14", "Both stay ASSUMED; prices from logs and curve reads are unverified and live-fed paper buys fail closed. The event desk then runs recorded datasets only; nothing else in v4 needs VERIFIED."),
    ("OD-05", "Paid RPC provider (HTTP and WebSocket). The public endpoint cannot carry 128 curve log subscriptions or about 100 MB per 30 s.", "Choose a paid provider; endpoint and key via environment on the operator host, never git. Without a decision: public endpoint with `datafeed.watch_max` 32, logsSubscribe only for held mints, PumpPortal for new tokens.", "13-01, 13-02, 17-04", "Before the first live-fed paper run (after checkpoint 17)", "Reduced watch set; recorded evidence grade stays research for coverage."),
    ("OD-06", "Ticket number width `SOL-YYYYMMDD-NNN` (3 digits) versus four strategies.", "Keep 3 digits; tickets allocated for approved intents only (at most `max_trades_per_day`); C-01 refuses at 999 with a typed error. Widening needs a contract change acknowledged by all ten seats.", "15-01", "Start of Phase 15", "Default applies."),
    ("OD-07", "Maximum arm expiry.", "`live.arm_max_expiry_hours` 72, hard ceiling 168; every arm is re-signed after expiry.", "12-01, 18-02", "Before 18-02", "Default applies."),
    ("OD-08", "Strand risk: live strategies exit before the curve completes (no PumpSwap sells in v4) versus supporting `pool=pump-amm` sells in the signer.", "Exit before completion: `max_progress <= 0.85`, `exit_progress <= 0.92`, required for LIVE_ELIGIBLE. PumpSwap sells are a later milestone.", "15-04, 15-05, 17-03", "Start of Phase 15", "Default applies."),
    ("OD-09", "Paper fee model v2 constants and the Phase 15 trading-smoke re-pin.", "v2 = current venue 100 bps plus PumpPortal 50 bps when the builder is PumpPortal, ATA rent 2_039_280 lamports on the first buy of a mint, signer priority-fee cap; a human checks them against the official fee pages (REVIEW). Approve the before and after pair at checkpoint 17.", "13-03, 15-01, 15-07", "Before 15-01 merges", "FEE2 does not merge; v1 stays default and backtests understate live cost (documented)."),
    ("OD-10", "Autonomy level for the live-paper desk: a human sets `autonomous-paper` (otherwise paper approvals are missing).", "Owner sets it once on the live-paper ledger when the first live-fed run starts. Below it, RT2 journals refused intents and approves nothing.", "15-06, 17-04", "First live-fed paper run", "Event desk runs but places no paper orders."),
    ("OD-11", "Signer deployment: separate container or host, uid and socket group, key file path.", "Separate container on the same host, shared socket volume, group `desk-signer-clients`, socket mode 0660, key at `DESK_SIGNER_CREDENTIAL_PATH` (0400, signer uid), placed by the human.", "18-01, 18-03, 18-09", "Before 18-03", "Default compose service ships."),
    ("OD-12", "Funding rule versus the 200 USD throwaway limit when SOL is above 200 USD.", "`cap_sol = min(1.0, 200 USD / SOL price minus fees)` computed at arm time; fund at most cap plus fees. Runbook and errata E4 state it.", "18-09, 18-07", "Before 18-09", "Runbook states the stricter reading (do not fund above 200 USD)."),
    ("OD-13", "Hermes cutover in event mode: disable scout-discover, scout-pipeline, risk-audit-open-leads, chief-pickup, rug-watch-paper and the daily rollup.", "Disable all six; the journal cycle performs the rollup on `Timer(daily_rollover)`.", "14-04, 14-06", "Checkpoint 14", "Cadence mode (default) is unchanged; event mode refuses to start (doctor) while a superseded job is enabled."),
    ("OD-14", "Transaction builder for the signer: PumpPortal trade-local behind a TxBuilder interface (third party) versus direct pump instruction building.", "PumpPortal trade-local with the instruction-level allowlist and a pinned fee recipient; direct building is a later option behind the same interface.", "18-04", "Before 18-04", "Default applies."),
    ("OD-15", "Initial mint block and allow lists (`mint_lists.toml`, human-required file).", "Empty blocklist, allowlist disabled.", "17-02", "Before 17-02 merges", "Default applies."),
    ("OD-16", "Promotion thresholds beyond the LiveGate floors (the loader refuses looser values).", "Floors: 14 days, 50 closed trades, profit factor 1.2, drawdown 0.15; plus `min_shadow_orders` 20, `max_shadow_slippage_gap_bps` 150, demotion when profit factor below 1.0 over the last 20 closed.", "17-03", "Before 17-03 merges", "Default applies."),
    ("OD-17", "Strategy slice weights for four enabled strategies (sum at most 1).", "legacy_screening, momentum_breakout, new_launch_sniper, mean_reversion at 0.20 each, 0.20 unallocated reserve.", "15-02", "Start of Phase 15", "Default applies."),
    ("OD-18", "Nightly soak schedule and CI minutes (3 virtual days of event-mode soak, about 50 minutes with the other soaks).", "GitHub Actions `schedule` at 03:00 UTC.", "19-04", "Before 19-04", "Soak stays manual."),
    ("OD-19", "Owner reads the v4 milestone audit (AUDIT-19 is human-gated) and confirms live is refused on the final tree.", "Read at checkpoint 19.", "19-08", "Checkpoint 19", "Milestone not closed."),
    ("OD-20", "Event mode as the default (`wake_mode`) and removal of `stop_loss_poll_seconds` from bounds.", "Keep `cadence` the default through v4 (config-gated everything); decide the flip in the next milestone after a week of live-paper evidence.", "15-04", "After checkpoint 17", "Default applies."),
    ("OD-21", "Confirm the four ship checkpoints (after Phases 12, 14, 17, 19) and the batch approval of receipts.", "Confirm.", "all human-gated PRs (pr-plan.md sections 4 and 5)", "Now", "Receipts are approved PR by PR."),
]
for r in ods:
    d("| " + " | ".join(r) + " |")
d("")
d("Items deliberately NOT decided here because they are not v4 scope: which strategy and parameter hash the owner arms first, and when; all arm and rollback steps (human-only runbooks).")
open("/tmp/v4/final/owner-decisions.md", "w").write(sanitize("\n".join(D) + "\n"))

# ============================================================================================ amendment-errata.md
E: list[str] = []
e = E.append
e("# Errata for the constitution amendment draft (N6 section 5 point 9 and item 1 and 2)")
e("")
e("For owner review (OD-01). The draft at `/tmp/v4/design/C-AMENDMENT-DRAFT.md` is NOT edited; these are proposed replacements for the owner to accept, reject or reword. Nothing here is applied by any agent.")
e("")
e("**E1 (clause 2, last sentences; N6 items 1 and 2).** In the replacement for the final sentence of clause 2, replace `Under an unexpired, verified arm record the desk may send autonomously for the listed strategies only ... A halt, kill switch, open breaker, strategy kill, demotion, or UNKNOWN hold suspends autonomous sends until a human clears it.` by:")
e("")
e("    A live send requires either that exact approval message, or an arm record: a standing authorization the human signs once with the operator key, bound to the exact configuration hash, the wallet allowlist, a list of (strategy, parameter-set hash) pairs, a notional cap of at most 1.0 SOL, and an expiry no later than the configured maximum. Under an unexpired, verified arm record the desk may send autonomously for the listed pairs only, inside the written risk limits and the record's caps, and each send is recorded as an ApprovalRecorded row of kind autonomous_live. Any change of a parameter-set hash requires a new arm record. Agents never create, extend, or widen an arm record. A halt, kill switch, open breaker, strategy kill, demotion, UNKNOWN hold, or arm expiry suspends autonomous ENTRIES until a human clears it or re-arms. Exits for positions already open (stop-loss, take-profit, trailing stop, maximum hold, rug alert, kill flatten) are never suspended by those conditions; they remain inside the wallet allowlist and the notional cap, and each is recorded as an ApprovalRecorded row of kind autonomous_live.")
e("")
e("**E2 (clause 3; N6 section 5 point 9).** Add to the clause 3 replacement: `A send that fails on-chain (an execution error) stops all new entries and waits for a human to clear, exactly like an UNKNOWN result; only a result the chain proves never landed (blockhash expired and finalized check) is recorded as rejected without a hold.` (The exec_errors breaker alone auto-resets after 900 s, which would let failed sends resume without a human.)")
e("")
e("**E3 (closing paragraph and runbook; N6 section 5 point 9).** Keep `Live capital exists only through the arm procedure of clause 2; no default, overlay, or agent enables it.` and state in the arm runbook that the operator uses a local configuration file outside git named by `PUMPGROK_CONFIG` (never a committed overlay with `enabled=true`).")
e("")
e("**E4 (clause 1 and runbook; N6 section 5 point 9, item 28).** The throwaway limit stays 200 USD while the notional cap is 1.0 SOL. Add to the runbook, not to the clause: the arm sets `cap_sol = min(1.0, 200 USD / SOL price minus fees)` at arm time and funding never exceeds that cap plus fees.")
e("")
e("**E5 (scope list; N6 section 4 and 5).** Add to the `Scope` list the copies the draft missed: `prompts/bot-04-sniper.xml` (lines 6 and 27), `prompts/bot-00-chief.xml` line 65 and `agents/chief.md` line 72 (`never allow SNIPER without the exact human approval phrase`), `AGENTS.md` line 91, `ARCHITECTURE.md` line 170, `SETUP.md` lines 120, 203, 241, `docs/ROSTER.md` line 116 and the key-custody rows at lines 196, 238, 280, `docs/runbooks/setup.md` line 27, `skills/key-custody/SKILL.md` line 24 (`There is nothing to custody`), and `docs/RISK_POLICY.md` section 3.3 line 128 (`R17: no live auto-exit exists`). Also name the INV-S-01 text change: the documented scope lists `services/` and `scripts/` as exempt; the signer needs an explicit statement.")
e("")
e("Why these matter: E1 closes a blocker (as drafted, exits would be suspended exactly when stop-loss and kill-flatten must run); E2 removes a weakening; E3 to E5 remove contradictions between the amendment and the runbook, and incomplete copies that the oracle and `assemble-prompts --check` would otherwise leave inconsistent.")
open("/tmp/v4/final/amendment-errata.md", "w").write(sanitize("\n".join(E) + "\n"))
print("docs written; PRs", n_prs, "plans", n_plans)

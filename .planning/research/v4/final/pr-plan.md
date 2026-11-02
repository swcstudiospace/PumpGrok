# PumpGrok v4: pull request plan

Inputs: `/tmp/v4/final/plans.json` (74 plans, nine phases), `/tmp/v4/planning/pr-topology.md`, `/tmp/v4/design/N6-critique.md` section 8. Every statement about code was checked against repo HEAD `641927c`; statements about PRs 17 to 20 assume the owner-approved merge (owner decision, settled) and are enforced by the preflight commands in plan 11-01. Seat ownership of every path of every plan was verified with `resolve_owner(path, load_manifest(DEFAULT_MANIFEST))`; the PR graph below was checked acyclic by `/tmp/v4/final/tools/build.py`.

## 1. Summary

- **45 pull requests** for **74 plans** (target was at most 45 PRs and about 60 plans). Per phase, plans: P11 11, P12 5, P13 7, P14 9, P15 8, P16 7, P17 7, P18 11, P19 9. Per phase, PRs: P11 8, P12 3, P13 5, P14 6, P15 4, P16 3, P17 4, P18 6, P19 6.
- Grouping rule: one PR per (phase, seat); a group is split only when a cross-seat dependency forces an order. The splits that occurred: Phase 11 risk (pins first, quality foundation last, because Q09 needs the sniper, rug, scout and chief splits), Phase 14 risk (gateway first, doctor and idle gate after the chief PR), Phase 19 chief (health metrics before the risk PR, docs and audit after it). The amendment PR is the only PR that is not seat-pure.
- 74 plans = 18 closers (one journal CHANGELOG plan and one chief `.planning` plan per phase) + 56 feature plans. The 127 units (111 sequencer units minus 4 deleted or split parents, plus 16 new units and 4 split halves) average 1.7 units per plan after bundling by (seat, phase); the new units and split halves add about a dozen plans (for example 12-01 SET0, 14-05 and 14-06 seat cycles, 17-05 recovery, 18-04 signer tx policy). Phase 11 (11 plans) and Phase 18 (11 plans) are above the 5 to 9 band because they carry 30 and 14 sequencer units; every other phase is inside it.
- Pull-forwards used to save PRs (all sanctioned by `phases.md` pull-forward candidates): B01 (rug decoder) and B02 (chief probe script) ride in the Phase 11 rug and chief PRs; C-03s (sniper entry hook) rides in the Phase 13 sniper PR against a Protocol, which removes a Phase 17 sniper PR; B04c moves from Phase 13 to the Phase 14 chief PR.
- Ship checkpoints (owner approves a batch of receipts): after Phase 12, after 14, after 17, after 19 (section 5). Plans only list which PRs need the human approver; no plan, receipt or script records that approval.

## 2. Pull requests

Columns: PR number (merge order), branch `bot-0N-seat/v4-pPHASE-slug`, seat, plans in the order they are committed, depends on (PR numbers, transitive reduction of the plan graph plus shared-file order), receipt path (one receipt per PR, `task_id` = slug, `branch` = the branch, `.gitignore` glob from PRC-RECEIPTS covers it), approver.

| PR | Branch | Seat | Plans | Depends on | Receipt | Approver | Checkpoint |
|----|--------|------|-------|------------|---------|----------|------------|
| PR-01 | `bot-02-risk/v4-p11-receipts-pins-characterization` | 02-risk | 11-01, 11-02 | none | `.receipts/bot-02-risk/v4-p11-receipts-pins-characterization.json` | human:owner (batch); agent review first | CP12 |
| PR-02 | `bot-04-sniper/v4-p11-paper-adapter-split` | 04-sniper | 11-06 | PR-01 | `.receipts/bot-04-sniper/v4-p11-paper-adapter-split.json` | bot-02-risk (agent) | CP12 |
| PR-03 | `bot-05-rug/v4-p11-rug-excepts-event-decoder` | 05-rug | 11-07 | PR-01 | `.receipts/bot-05-rug/v4-p11-rug-excepts-event-decoder.json` | bot-02-risk (agent) | CP12 |
| PR-04 | `bot-01-scout/v4-p11-jupiter-excepts` | 01-scout | 11-08 | PR-01 | `.receipts/bot-01-scout/v4-p11-jupiter-excepts.json` | bot-02-risk (agent) | CP12 |
| PR-05 | `bot-00-chief/v4-p11-adopt-milestone-seat-task` | 00-chief | 11-09 | PR-01 | `.receipts/bot-00-chief/v4-p11-adopt-milestone-seat-task.json` | human:owner (batch); agent review first | CP12 |
| PR-06 | `bot-02-risk/v4-p11-quality-foundation` | 02-risk | 11-03, 11-04, 11-05 | PR-02, PR-03, PR-04, PR-05 | `.receipts/bot-02-risk/v4-p11-quality-foundation.json` | human:owner (batch); agent review first | CP12 |
| PR-07 | `bot-09-journal/v4-p11-changelog` | 09-journal | 11-10 | PR-06 | `.receipts/bot-09-journal/v4-p11-changelog.json` | bot-02-risk (agent) | CP12 |
| PR-08 | `bot-00-chief/v4-p11-close` | 00-chief | 11-11 | PR-07 | `.receipts/bot-00-chief/v4-p11-close.json` | bot-02-risk (agent) | CP12 |
| PR-09 | `bot-02-risk/v4-p12-settings-events-core` | 02-risk | 12-01, 12-02, 12-03 | PR-06 | `.receipts/bot-02-risk/v4-p12-settings-events-core.json` | human:owner (batch); agent review first | CP12 |
| PR-10 | `bot-09-journal/v4-p12-changelog` | 09-journal | 12-04 | PR-07, PR-09 | `.receipts/bot-09-journal/v4-p12-changelog.json` | bot-02-risk (agent) | CP12 |
| PR-11 | `bot-00-chief/v4-p12-close` | 00-chief | 12-05 | PR-08, PR-10 | `.receipts/bot-00-chief/v4-p12-close.json` | bot-02-risk (agent) | CP12 |
| PR-12 | `bot-02-risk/v4-p13-datafeed-recorder-probe` | 02-risk | 13-01, 13-02 | PR-09 | `.receipts/bot-02-risk/v4-p13-datafeed-recorder-probe.json` | bot-00-chief (agent) | CP14 |
| PR-13 | `bot-04-sniper/v4-p13-fees-paper-factory-hooks` | 04-sniper | 13-03 | PR-02 | `.receipts/bot-04-sniper/v4-p13-fees-paper-factory-hooks.json` | bot-02-risk (agent) | CP14 |
| PR-14 | `bot-05-rug/v4-p13-curve-layout-status-flips` | 05-rug | 13-04, 13-05 | PR-12, PR-13 | `.receipts/bot-05-rug/v4-p13-curve-layout-status-flips.json` | human:owner (batch); agent review first | CP14 |
| PR-15 | `bot-09-journal/v4-p13-changelog` | 09-journal | 13-06 | PR-10, PR-14 | `.receipts/bot-09-journal/v4-p13-changelog.json` | bot-02-risk (agent) | CP14 |
| PR-16 | `bot-00-chief/v4-p13-close` | 00-chief | 13-07 | PR-11, PR-15 | `.receipts/bot-00-chief/v4-p13-close.json` | bot-02-risk (agent) | CP14 |
| PR-17 | `bot-02-risk/v4-p14-grok-gateway` | 02-risk | 14-01 | PR-09 | `.receipts/bot-02-risk/v4-p14-grok-gateway.json` | bot-00-chief (agent) | CP14 |
| PR-18 | `bot-08-signal/v4-p14-gateway-agents` | 08-signal | 14-02 | PR-17 | `.receipts/bot-08-signal/v4-p14-gateway-agents.json` | bot-02-risk (agent) | CP14 |
| PR-19 | `bot-00-chief/v4-p14-event-wake-cycles` | 00-chief | 14-03, 14-04, 14-05, 14-06 | PR-12, PR-18 | `.receipts/bot-00-chief/v4-p14-event-wake-cycles.json` | bot-02-risk (agent) | CP14 |
| PR-20 | `bot-02-risk/v4-p14-doctor-failure-suite-idle-gate` | 02-risk | 14-07 | PR-19 | `.receipts/bot-02-risk/v4-p14-doctor-failure-suite-idle-gate.json` | human:owner (batch); agent review first | CP14 |
| PR-21 | `bot-09-journal/v4-p14-changelog` | 09-journal | 14-08 | PR-15, PR-20 | `.receipts/bot-09-journal/v4-p14-changelog.json` | bot-02-risk (agent) | CP14 |
| PR-22 | `bot-00-chief/v4-p14-close` | 00-chief | 14-09 | PR-16, PR-21 | `.receipts/bot-00-chief/v4-p14-close.json` | bot-02-risk (agent) | CP14 |
| PR-23 | `bot-02-risk/v4-p15-strategy-framework` | 02-risk | 15-01, 15-02, 15-03, 15-04, 15-05 | PR-12, PR-13 | `.receipts/bot-02-risk/v4-p15-strategy-framework.json` | human:owner (batch); agent review first | CP17 |
| PR-24 | `bot-00-chief/v4-p15-paper-root-router` | 00-chief | 15-06 | PR-19, PR-23 | `.receipts/bot-00-chief/v4-p15-paper-root-router.json` | bot-02-risk (agent) | CP17 |
| PR-25 | `bot-09-journal/v4-p15-changelog` | 09-journal | 15-07 | PR-21, PR-24 | `.receipts/bot-09-journal/v4-p15-changelog.json` | bot-02-risk (agent) | CP17 |
| PR-26 | `bot-00-chief/v4-p15-close` | 00-chief | 15-08 | PR-22, PR-25 | `.receipts/bot-00-chief/v4-p15-close.json` | bot-02-risk (agent) | CP17 |
| PR-27 | `bot-02-risk/v4-p16-backtest-v2` | 02-risk | 16-01, 16-02, 16-03, 16-04 | PR-20, PR-24 | `.receipts/bot-02-risk/v4-p16-backtest-v2.json` | bot-00-chief (agent) | CP17 |
| PR-28 | `bot-09-journal/v4-p16-reports-changelog` | 09-journal | 16-05, 16-06 | PR-25, PR-27 | `.receipts/bot-09-journal/v4-p16-reports-changelog.json` | bot-02-risk (agent) | CP17 |
| PR-29 | `bot-00-chief/v4-p16-close` | 00-chief | 16-07 | PR-26, PR-28 | `.receipts/bot-00-chief/v4-p16-close.json` | bot-02-risk (agent) | CP17 |
| PR-30 | `bot-02-risk/v4-p17-risk-promotion` | 02-risk | 17-01, 17-02, 17-03 | PR-27 | `.receipts/bot-02-risk/v4-p17-risk-promotion.json` | human:owner (batch); agent review first | CP17 |
| PR-31 | `bot-00-chief/v4-p17-event-desk-recovery` | 00-chief | 17-04, 17-05 | PR-30 | `.receipts/bot-00-chief/v4-p17-event-desk-recovery.json` | bot-02-risk (agent) | CP17 |
| PR-32 | `bot-09-journal/v4-p17-changelog` | 09-journal | 17-06 | PR-28, PR-31 | `.receipts/bot-09-journal/v4-p17-changelog.json` | bot-02-risk (agent) | CP17 |
| PR-33 | `bot-00-chief/v4-p17-close` | 00-chief | 17-07 | PR-29, PR-32 | `.receipts/bot-00-chief/v4-p17-close.json` | bot-02-risk (agent) | CP17 |
| PR-34 | `bot-00-chief/v4-p18-amendment` | 00-chief | 18-07 | PR-05 | `.receipts/bot-00-chief/v4-p18-amendment.json` | human (owner applies and merges) | CP19 |
| PR-35 | `bot-02-risk/v4-p18-dormant-live-path` | 02-risk | 18-01, 18-02, 18-03, 18-04, 18-05, 18-06 | PR-30, PR-34 | `.receipts/bot-02-risk/v4-p18-dormant-live-path.json` | human:owner (batch); agent review first | CP19 |
| PR-36 | `bot-04-sniper/v4-p18-live-dispatch` | 04-sniper | 18-08 | PR-35 | `.receipts/bot-04-sniper/v4-p18-live-dispatch.json` | human:owner (batch); agent review first | CP19 |
| PR-37 | `bot-00-chief/v4-p18-runbooks-live-wiring` | 00-chief | 18-09 | PR-31, PR-36 | `.receipts/bot-00-chief/v4-p18-runbooks-live-wiring.json` | human:owner (batch); agent review first | CP19 |
| PR-38 | `bot-09-journal/v4-p18-changelog` | 09-journal | 18-10 | PR-32, PR-37 | `.receipts/bot-09-journal/v4-p18-changelog.json` | bot-02-risk (agent) | CP19 |
| PR-39 | `bot-00-chief/v4-p18-close` | 00-chief | 18-11 | PR-33, PR-38 | `.receipts/bot-00-chief/v4-p18-close.json` | bot-02-risk (agent) | CP19 |
| PR-40 | `bot-01-scout/v4-p19-market-data-skill` | 01-scout | 19-01 | PR-12 | `.receipts/bot-01-scout/v4-p19-market-data-skill.json` | bot-02-risk (agent) | CP19 |
| PR-41 | `bot-08-signal/v4-p19-backtest-skill` | 08-signal | 19-02 | PR-27 | `.receipts/bot-08-signal/v4-p19-backtest-skill.json` | bot-02-risk (agent) | CP19 |
| PR-42 | `bot-00-chief/v4-p19-health-metrics` | 00-chief | 19-03 | PR-31 | `.receipts/bot-00-chief/v4-p19-health-metrics.json` | bot-02-risk (agent) | CP19 |
| PR-43 | `bot-02-risk/v4-p19-doctor-soak-alerts-docs` | 02-risk | 19-04, 19-05 | PR-35, PR-42 | `.receipts/bot-02-risk/v4-p19-doctor-soak-alerts-docs.json` | human:owner (batch); agent review first | CP19 |
| PR-44 | `bot-09-journal/v4-p19-changelog` | 09-journal | 19-06 | PR-38, PR-40, PR-41, PR-43 | `.receipts/bot-09-journal/v4-p19-changelog.json` | bot-02-risk (agent) | CP19 |
| PR-45 | `bot-00-chief/v4-p19-docs-audit-close` | 00-chief | 19-07, 19-08, 19-09 | PR-39, PR-44 | `.receipts/bot-00-chief/v4-p19-docs-audit-close.json` | human:owner (batch); agent review first | CP19 |

Merge order inside a phase follows the table top to bottom; across phases follow the Depends column. A scheduler may start any PR whose dependencies are merged; development may run earlier on a stacked draft (depth 2, retarget to main through REST before the parent merges, `git merge origin/main` not rebase after the parent squash, skill `ultrathink-ship-stacked-prs`). At most three phases have open PRs, three open PRs per seat, eight overall.

### Per-phase notes that change what a scheduler does

- **Phase 11.** PR-01 (receipt glob, waiver removal, both hash pins, Q14c) merges first and unblocks everyone. PR-02, PR-03, PR-04, PR-05 run in parallel. PR-06 contains Q09 (ratchet-down) and therefore merges last, after the four of them; it also contains Q13s, which Phase 12 needs, so Phase 12 is developed as a draft stacked on PR-06 (depth 2) and retargeted when it merges.
- **Phase 13.** Order: PR-13 (status-agnostic execution tests, fee model v2 selectable, paper factory, entry hook) and PR-12 (datafeed, sources, probe docs with status-agnostic tests) first, then PR-14 (layout rewrite, then the human flips). Agnostic tests before the rewrite removes the rug to risk to rug cycle. If the human declines the flips, the flip commit is dropped from PR-14 and the phase closes ASSUMED.
- **Phase 14.** PR-17 (gateway) then PR-18 (agents) then PR-19 (wake, metrics, measurement, Hermes cutover, probe-script deletion, seat cycles) then PR-20 (doctor, failure suite, idle gate in CI). The chief PR is large (7 units); the seat-cycle plans (14-05, 14-06) are separate commits so a reviewer can stop after the wake core.
- **Phase 15.** PR-23 then PR-24. Plan 15-01 contains the only deliberate hash move of the milestone (FEE2: trading-smoke hash; smoke-10m unchanged) and its before and after pair is recorded by PR-25.
- **Phase 17.** PR-30 (slice, kill, entry checks, feed health, promotion) then PR-31 (event desk composition root, restart recovery). Checkpoint 17 is the first point where the whole paper desk runs end to end on recorded data.
- **Phase 18.** PR-34 (owner-applied amendment) is independent of code; PR-35 contains plans that do not need it (18-01, 18-02) and plans that do (18-03 to 18-06): the PR as a whole merges after the amendment, but 18-01 may be developed and reviewed first (the contract acknowledgement round trip). PR-36, PR-37 follow. Nothing in Phase 18 arms anything; live stays exit 3.
- **Phase 19.** PR-40, PR-41, PR-42 first; PR-43 after PR-42 (alerts need the metric names) and after the amendment; PR-44; then PR-45 (docs, milestone audit, close). The audit reads every phase's CHANGELOG lines, so it follows the journal PR.

## 3. The amendment pull request (single exception)

PR-34 = plan 18-07 = units C-13 and C-14 plus the missed copies. It spans three seats (risk, chief, sniper), so it cannot pass G-1 as seat-pure. It carries ONE waiver (below) and nothing else in v4 does. N6 item 6: a human applies and merges it.

**Preconditions.** (1) The owner approves, in writing, the exact text of `/tmp/v4/design/C-AMENDMENT-DRAFT.md` as corrected by `/tmp/v4/final/amendment-errata.md` (OD-01). (2) PRC-WAIVER (plan 11-01) and PLN-00 (plan 11-09) are merged. No other plan is required; the PR is independent of all code and may merge any time after both, recommended at the start of Phase 18 once checkpoint 17 passed.

**Procedure.**
1. The owner, or an executor working strictly from the approved text on a branch the owner opens, creates `bot-00-chief/v4-p18-amendment` from main. The `bot-00-chief` prefix satisfies the branch regex; agents never apply, paraphrase or merge the text on their own.
2. Commit 1 (risk-owned files): `rules/pumpgrok-team.mdc`, `prompts/_shared/core-directives.xml`, `docs/RISK_POLICY.md` including section 3.3 line 128 (`R17: no live auto-exit exists`), `SECURITY.md`, `docs/LIVE_READINESS.md`, `docs/SAFETY_INVARIANTS.md`, `AGENTS.md:91`, `ARCHITECTURE.md:170`, `docs/ROSTER.md:116` and the key-custody rows at 196, 238, 280, `skills/key-custody/SKILL.md:24`, plus the new frozen oracle `tests/safety/amendment_2026_10_28_frozen.txt`, its test, the updated 2026-10-25 test, and `tests/safety/test_amendment_copies_complete.py` (greps every quoting file for the superseded phrases).
3. Commit 2 (chief-owned files): `make prompts` regenerates `agents/*.md` and `prompts-assembled/*.xml` (including `agents/chief.md:72`, `agents/sniper.md` item 3); hand edits to `prompts/bot-00-chief.xml:65`, `skills/desk-operating-model/SKILL.md` lines 24 and 39, `.planning/PROJECT.md` out-of-scope rows, `README.md`, `SETUP.md:120,203,241`, `docs/runbooks/setup.md:27`. Commit 3 (sniper-owned): `prompts/bot-04-sniper.xml:6,27`.
4. Open the PR. Once the number N exists, commit 4 changes `.github/workflows/gates.yml` so that exactly one step, `G-1 - Path ownership`, has `if: github.event.pull_request.number != N || github.event.pull_request.head.repo.full_name != github.repository` and sets the pinned waiver set in `ci/tests/test_no_pr_waivers.py` to `(N,)`. G-1 manifest self-check, bot derivation, G-2 through G-7 stay enforced (the 2026-10-26 waiver covered G-1, G-2, G-5 and G-6; this one is strictly narrower).
5. Receipt: bot `bot-00-chief`, the branch, commands `uv run pytest -q tests/safety/test_constitution_amendment_2026_10_28.py tests/safety/test_constitution_amendment.py tests/safety/test_amendment_copies_complete.py`, `python3 scripts/generate-templates.py --check`, `make prompts`, `make check`; the `unverified` list names the single waived step, the PR number N and the approver. The owner supplies `approved_by` and merges.
6. After merge, every `amendment_wait` plan unblocks (18-03 to 18-06, 18-08, 18-09). Plan 19-04 (PRC-19) is the only plan allowed to follow it in gates.yml: it removes the waiver and restores the empty set. A PR that fails G-1 anywhere else is split, never waived.

## 4. Human approver (who needs `human:owner` and why)

A seat never approves its own work. For PRs below, the agent reviewer (chief for risk-authored, risk for every other seat) reads the diff first; the owner then adds `approved_by` and `approved_at` in a single-file commit, in a batch at the checkpoint. Receipts for human-gated plans are committed WITHOUT `approved_by` and the PR stays draft with a failing G-2 by design (as PRs 17 to 20 did).

| PR | Plans | Why a human approver |
|----|-------|----------------------|
| PR-01 `P11-RISK-A` | 11-01, 11-02 | edits .gitignore; edits ci/; edits a GitHub workflow; re-pins a hash oracle |
| PR-05 `P11-CHIEF` | 11-09 | edits PROJECT.md |
| PR-06 `P11-RISK-B` | 11-03, 11-04, 11-05 | edits a GitHub workflow; edits ci/; edits docker-compose.yml |
| PR-09 `P12-RISK` | 12-01, 12-02, 12-03 | defines live caps; defines signer limits |
| PR-14 `P13-RUG` | 13-04, 13-05 | unit B05 is human-gated; unit B05e is human-gated |
| PR-20 `P14-RISK-2` | 14-07 | edits ci/; edits a GitHub workflow |
| PR-23 `P15-RISK` | 15-01, 15-02, 15-03, 15-04, 15-05 | re-pins a hash oracle |
| PR-30 `P17-RISK` | 17-01, 17-02, 17-03 | edits mint lists; edits promotion thresholds |
| PR-34 `P18-AMEND` | 18-07 | unit C-13 is human-gated; unit C-13 waits for the amendment; unit C-14 is human-gated; unit C-14 waits for the amendment; edits the constitution rules; edits the amendment oracle; edits a GitHub workflow; edits ci/; edits PROJECT.md |
| PR-35 `P18-RISK` | 18-01, 18-02, 18-03, 18-04, 18-05, 18-06 | edits a contract surface; edits the signer protocol; edits execution/live; unit C-09a waits for the amendment; edits the signer service; edits docker-compose.yml; unit C-09b waits for the amendment; unit C-10 waits for the amendment; unit C-11 waits for the amendment; unit C-17 waits for the amendment |
| PR-36 `P18-SNIPER` | 18-08 | unit C-12 waits for the amendment |
| PR-37 `P18-CHIEF` | 18-09 | unit C-15 waits for the amendment; unit WIRE-18 waits for the amendment |
| PR-43 `P19-RISK` | 19-04, 19-05 | edits a GitHub workflow; edits ci/ |
| PR-45 `P19-CHIEF-2` | 19-07, 19-08, 19-09 | unit AUDIT-19 is human-gated |

PRs not listed use an agent approver and are merged by an agent after green CI and the Greptile bar (V3-5; the score is never written into a receipt).

## 5. Ship checkpoints

The owner approves receipts in batches. Each checkpoint lists the PRs of its window that need `human:owner`, the owner decisions due (`owner-decisions.md`), and the integration check that must be green first (success criteria of the phases in the window, run on `v4/integration` per `pr-topology.md` section 10).

### Checkpoint 12 (phases 11, 12)

Human receipts in this batch: PR-01 (`P11-RISK-A`), PR-05 (`P11-CHIEF`), PR-06 (`P11-RISK-B`), PR-09 (`P12-RISK`).
Decisions due: OD-02 and OD-03 (defaults), OD-09 (fee constants review starts), OD-21 (confirm these checkpoints). Also the one-time mainnet read-only probe run for OD-04 may start here (script from plan 11-09).

### Checkpoint 14 (phases 13, 14)

Human receipts in this batch: PR-14 (`P13-RUG`), PR-20 (`P14-RISK-2`).
Decisions due: OD-04 (probe review and the two status flips, plan 13-05), OD-05 (RPC provider), OD-13 (Hermes cutover), OD-10 (autonomy level for live-paper). OD-01 (amendment text) should already be circulating.

### Checkpoint 17 (phases 15, 16, 17)

Human receipts in this batch: PR-23 (`P15-RISK`), PR-30 (`P17-RISK`).
Decisions due: OD-01 (amendment text approved in writing: required before Phase 18 merges), OD-03, OD-06, OD-08, OD-09 (Phase 15 trading-smoke re-pin pair), OD-11, OD-14, OD-15, OD-16, OD-17. The first live-fed paper run (needs OD-04, OD-05, OD-10) is the checkpoint demonstration.

### Checkpoint 19 (phases 18, 19)

Human receipts in this batch: PR-34 (`P18-AMEND`), PR-35 (`P18-RISK`), PR-36 (`P18-SNIPER`), PR-37 (`P18-CHIEF`), PR-43 (`P19-RISK`), PR-45 (`P19-CHIEF-2`).
Decisions due: OD-07, OD-12, OD-18, OD-19 (the milestone audit is read by the owner). After this checkpoint nothing remains but the human arm procedure from the runbooks; live is still exit 3.

## 6. Closing PRs per phase

| Phase | Journal CHANGELOG PR | Chief `.planning` close PR |
|-------|----------------------|-----------------------------|
| 11 | PR-07 plans ['11-10'] | PR-08 plans ['11-11'] |
| 12 | PR-10 plans ['12-04'] | PR-11 plans ['12-05'] |
| 13 | PR-15 plans ['13-06'] | PR-16 plans ['13-07'] |
| 14 | PR-21 plans ['14-08'] | PR-22 plans ['14-09'] |
| 15 | PR-25 plans ['15-07'] | PR-26 plans ['15-08'] |
| 16 | PR-28 plans ['16-05', '16-06'] | PR-29 plans ['16-07'] |
| 17 | PR-32 plans ['17-06'] | PR-33 plans ['17-07'] |
| 18 | PR-38 plans ['18-10'] | PR-39 plans ['18-11'] |
| 19 | PR-44 plans ['19-06'] | PR-45 plans ['19-07', '19-08', '19-09'] |

Each journal PR adds one CHANGELOG section with `Phase N: smoke-10m events.hash before/after` AND `Phase N: trading-smoke events.hash before/after` lines (N6 section 3 item 7: equal pairs are recorded, not skipped). Phase 15 is the one phase where the trading-smoke pair differs (fee model v2); Phase 14 additionally records `events-smoke-10m` and `events-soak-3d` golden hashes; the Phase 19 PR also records the nightly soak golden hash. The chief close PR is the integration receipt for the phase (commands and exit codes of the phase success criteria run on `v4/integration`); closers merge in phase order.

## 7. Receipt discipline (standard command set)

Every PR receipt carries the commands of each of its plans (`acceptance_commands` in plans.json; all are written so that exit 0 means success, including the live-refusal check `uv run pumpgrok run --mode live --once; test $? -eq 3`, which is deployment-shaped and therefore carries a `rollback_plan` of 12 or more words). Rules added by N6:
- Run receipts in a fresh git worktree (no `var/ledger.sqlite`): `verify` reads `operator_active_set` from the cwd ledger, which changes the hash (N6 section 3 item 3). The trading-smoke pin test also chdirs into a tmp path.
- `pytest --co`, `--collect-only`, `-rs`-less skip checks, `|| true`, `stderr discard to /dev/null`, `--dry-run`, an inline `PUMPGROK_LIVE_ENABLE` never appear (G-2 bypass family). Plans use `! uv run pytest PATH -rs | grep -q SKIPPED` to prove no skips.
- Plans that touch `src/` also run `make lint` and `make typecheck`; at PR level run `make check` (fast path after Q02) and `python3 ci/gates/run_all.py --bot SEAT --base PARENT --receipt RECEIPT`; the full `pytest -q` including soak (about 50 minutes) is the nightly job, not a per-plan command.
- Claims avoid exhaustive wording (all, every, no regressions) unless a command proves it. Hash lines: smoke-10m `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`; trading-smoke pinned in `tests/fixtures/replay/pins/trading_smoke.json` (observed at HEAD 641927c: `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54`, re-measured at `v4-base` by plan 11-01).
- Foreign-test fallout: before a PR is marked ready run the whole suite; if a test owned by another seat fails, open a one-file companion plan by the owning seat and merge it first (contingent, not counted). Known contingent cases: CURVE_ACCOUNT_SIZE importers (kept stable), the narrow EventSource literals (pinned), gate reason strings (C-06).
- Source of truth for GSD: `plans.json` is the input to `gsd-plan-phase`; the executor writes the PLAN.md and SUMMARY.md of each plan under `.planning/phases/NN-*/` (N6 section 6 criterion a: PLN-00 installs the phase directories, the per-plan files are produced by the workflow).

## 8. Stack and shared-file merge order (computed)

Files edited by more than one plan, in merge order (all same seat except the amendment PR). A later plan merges only after the earlier one.

| File | Plans in order |
|------|----------------|
| `.github/workflows/ci.yml` | 11-03 then 14-07 then 19-04 |
| `.github/workflows/gates.yml` | 11-01 then 18-07 then 19-04 |
| `.planning/PROJECT.md` | 11-09 then 18-07 |
| `.planning/ROADMAP.md` | 11-09 then 12-05 then 13-07 then 14-09 then 15-08 then 16-07 then 17-07 then 18-11 then 19-09 |
| `.planning/STATE.md` | 11-11 then 12-05 then 13-07 then 14-09 then 15-08 then 16-07 then 17-07 then 18-11 then 19-09 |
| `AGENTS.md` | 18-07 then 19-05 |
| `ARCHITECTURE.md` | 18-07 then 19-05 |
| `CHANGELOG.md` | 11-10 then 12-04 then 13-06 then 14-08 then 15-07 then 16-06 then 17-06 then 18-10 then 19-06 |
| `Makefile` | 11-03 then 11-05 then 14-07 |
| `README.md` | 18-07 then 19-07 |
| `SETUP.md` | 18-07 then 19-07 |
| `ci/tests/test_no_pr_waivers.py` | 11-01 then 18-07 then 19-04 |
| `docker-compose.yml` | 11-03 then 18-03 |
| `pyproject.toml` | 11-03 then 11-05 |
| `src/pumpgrok/cli/backtest.py` | 11-04 then 16-04 |
| `src/pumpgrok/cli/dispatch.py` | 12-02 then 16-04 then 17-03 then 18-02 then 18-05 |
| `src/pumpgrok/cli/parsing.py` | 12-02 then 14-07 then 16-04 then 17-03 then 18-02 then 18-05 |
| `src/pumpgrok/cli/verbs_ops.py` | 16-04 then 17-03 then 18-02 then 18-05 |
| `src/pumpgrok/cli/verbs_state.py` | 14-07 then 16-04 |
| `src/pumpgrok/config/sections/paper_fees.py` | 12-01 then 15-01 |
| `src/pumpgrok/config/settings.py` | 11-04 then 12-01 |
| `src/pumpgrok/config/upgrade_bounds.toml` | 15-04 then 15-05 |
| `src/pumpgrok/core/errors.py` | 12-02 then 13-01 |
| `src/pumpgrok/doctor.py` | 11-04 then 14-07 then 18-02 then 19-04 |
| `src/pumpgrok/execution/__init__.py` | 13-03 then 18-08 |
| `src/pumpgrok/risk/breakers.py` | 17-02 then 18-05 |
| `src/pumpgrok/risk/engine/constants.py` | 17-01 then 17-02 |
| `src/pumpgrok/risk/engine/core.py` | 11-04 then 17-01 |
| `src/pumpgrok/risk/engine/steps.py` | 17-01 then 17-02 then 18-01 then 18-05 |
| `src/pumpgrok/strategies/registry.py` | 15-02 then 15-03 then 15-04 then 15-05 |
| `src/pumpgrok/strategies/runtime.py` | 15-02 then 15-03 |
| `src/pumpgrok/strategies/tape.py` | 15-02 then 15-03 |
| `src/pumpgrok/supervisor/live_paper.py` | 15-06 then 17-04 then 18-09 |
| `src/pumpgrok/supervisor/metrics_events.py` | 14-04 then 19-03 |
| `src/pumpgrok/supervisor/scheduler/wake.py` | 14-03 then 17-04 then 18-09 |
| `src/pumpgrok/supervisor/seat_task.py` | 11-09 then 14-03 |
| `src/pumpgrok/tools/onchain/curve_layout.py` | 13-04 then 13-05 |
| `src/pumpgrok/tools/onchain/pump_events.py` | 11-07 then 13-05 |
| `src/pumpgrok/upgrade/gate.py` | 15-01 then 17-03 |
| `tests/fixtures/replay/pins/trading_smoke.json` | 11-01 then 15-01 |
| `tests/fixtures/replay/pins/trading_smoke_rows.json` | 11-01 then 15-01 |
| `tests/harness/faults.py` | 12-02 then 18-05 |

Collapsed by this plan: `config/settings.py` is now touched by Q13s and SET0 only (was eight units); `cli/*.py` stays one serial lane (A1, A12, B18, C-05, C-06, C-10); `tests/conftest.py` only by B07; `gates.yml` and `ci/tests/test_no_pr_waivers.py` by PRC-WAIVER, the amendment PR and PRC-19.

## 9. Risks that remain after the plan

- PR size: PR 02 (quality foundation), PR 19/20 (event wake and cycles), the Phase 15 risk PR (five plans) and the Phase 18 risk PR (six plans, signer included) are large. The grouping rule keeps them as one PR each; an executor MAY cut numbered sub-PRs of the same seat for review size (`v4-p18-dormant-live-path-a`), recorded in the receipt `unverified` list; they do not change the PR count in this plan.
- Review fatigue at checkpoints: batches contain between 2 and 12 human receipts; checkpoint 17 and 19 are the heavy ones.
- The Phase 11 risk PR serializes the start of Phase 12; mitigated by the stacked draft.
- N6 section 7 items with no plan by design: bus capacity on public RPC (OD-05 decides), pump.fun REST availability (B07 degrades), docs and runbooks for each new surface (D19c, D19r, C-15).

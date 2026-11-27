# Phase inventory: PumpGrok Desk v3 (current) and v2 (archived)

**Conclusion.** Ten phases are on disk: five in the current milestone v3 (`.planning/phases/06` to `10`) and five in the archived milestone v2 (`.planning/milestones/v2-phases/01` to `05`). Every phase has a CONTEXT file, a SUMMARY for every PLAN (plus the 06-01b fix-up), and a VERIFICATION file whose frontmatter reads `status: passed`. No phase is STATUS_DRIFT or INCOMPLETE_NEEDS_EXECUTION. Two phases are BLOCKED. Phase 6 (v3) is BLOCKED because its phase PR is unmerged and criterion 17 is owner-waived only for that PR. v2 Phase 3 is BLOCKED because a human action that needs an account is still pending. The other eight phases are COMPLETE_VERIFIED. The five v2 phases exist only under the archive path. The stall in the GSD review is consistent with this inventory: Phase 6 is the only v3 phase the state files leave open, and the discovery rule in the autonomous workflow keeps any phase with `phase_complete !== true` in scope.

## Method

- Read: `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/MILESTONES.md`, all of `.planning/phases/`, and the archive `.planning/milestones/` (contains `v2-ROADMAP.md`, `v2-REQUIREMENTS.md`, `v2-MILESTONE-AUDIT.md` and `v2-phases/01..05`). Also read `phases/10-live-readiness-kept-disabled/10-CONTEXT.md`, the VERIFICATION files, and the `depends_on` fields of PLAN files.
- Did not read: `PROJECT.md`, `REQUIREMENTS.md`, `AMENDMENT-2026-10-25.md`, `TODO-BACKLOG.md`, `audit/`, `research/`, `config.json`. Nothing under `.planning/` was modified.
- Classification rules applied in the order given in the assignment. Rule 1 (BLOCKED) was read as: an **open** user decision or external dependency recorded against the phase. Resolved approvals, accepted deviations, and items the state files disposition as out of scope or deferred with no pending human action do not count. This reading is the main judgement call. See "Interpretation and borderline cases".

## Evidence table

Columns: **ROADMAP status** is the progress-table row (`ROADMAP.md`) or the archived ROADMAP line. **STATE status** is verbatim from `STATE.md` (`milestones/v2-*` entries have no per-phase STATE line; the milestone-level line is quoted). **Artifacts** counts files in the phase directory. **VERIF frontmatter** is the `status:` value in the phase's `*-VERIFICATION.md`.

| Phase | Milestone | Path | ROADMAP status (verbatim) | STATE status (verbatim) | CONTEXT | PLAN / SUMMARY | VERIFICATION.md | VERIF frontmatter status (verbatim) | Archive-only | Class |
|---|---|---|---|---|---|---|---|---|---|---|
| 6 Integrity closure | current (v3) | `.planning/phases/06-integrity-closure/` | `\| 6. Integrity closure \| 9/9 (+ fix-up 06-01b) \| Complete \| 2026-10-26 \|` | `stopped_at: Phase 6 closed 2026-10-26 with owner-approved deviations; ship in progress (PR not yet merged).` | yes (`06-CONTEXT.md`) | 9 / 10 (09 plans 06-01..06-09; 10 summaries incl. `06-01b-SUMMARY.md`) | yes | `passed` | no | **BLOCKED** |
| 7 Documentation upgrade | current (v3) | `.planning/phases/07-documentation-upgrade/` | `\| 7. Documentation upgrade \| 6/6 \| Complete \| 2026-10-25 \|` | `Phases 7 to 10: complete.` | yes | 6 / 6 | yes | `passed` | no | **COMPLETE_VERIFIED** |
| 8 Backtest and paper evaluation | current (v3) | `.planning/phases/08-backtest-and-paper-evaluation/` | `\| 8. Backtest and paper evaluation \| 10/10 \| Complete \| 2026-10-25 \|` | `Phases 7 to 10: complete.` | yes | 10 / 10 | yes (+ `08-CORRECTION.md`) | `passed` | no | **COMPLETE_VERIFIED** |
| 9 Bounded paper self-upgrade | current (v3) | `.planning/phases/09-bounded-paper-self-upgrade/` | `\| 9. Bounded paper self-upgrade \| 7/7 \| Complete \| 2026-10-25 \|` | `Phases 7 to 10: complete.` | yes | 7 / 7 | yes | `passed` | no | **COMPLETE_VERIFIED** |
| 10 Live readiness, kept disabled | current (v3) | `.planning/phases/10-live-readiness-kept-disabled/` | `\| 10. Live readiness, kept disabled \| 3/3 \| Complete \| 2026-10-25 \|` | `Phases 7 to 10: complete.` | yes | 3 / 3 | yes | `passed` | no | **COMPLETE_VERIFIED** |
| v2 Phase 1 Foundation | archived (v2) | `.planning/milestones/v2-phases/01-foundation/` | `- [x] **Phase 1: Foundation** ... (completed 2026-10-21)` (`milestones/v2-ROADMAP.md:11`) | No per-phase line. Milestone-level: `v2 is shipped and archived (.planning/MILESTONES.md).` | yes (`01-CONTEXT.md`) | 14 / 14 | yes (`01-VERIFICATION.md`) | `passed` | **yes** | **COMPLETE_VERIFIED** |
| v2 Phase 2 Restructure | archived (v2) | `.planning/milestones/v2-phases/02-restructure/` | `- [x] **Phase 2: Restructure** ... (completed 2026-10-21)` (`v2-ROADMAP.md:12`) | No per-phase line. Milestone-level as above. | yes | 5 / 5 | yes | `passed` | **yes** | **COMPLETE_VERIFIED** |
| v2 Phase 3 Tools and Skills | archived (v2) | `.planning/milestones/v2-phases/03-tools-and-skills/` | `- [x] **Phase 3: Tools and Skills** ... (completed 2026-10-21)` (`v2-ROADMAP.md:13`) | No per-phase line. Milestone-level as above. | yes | 7 / 7 | yes | `passed` | **yes** | **BLOCKED** |
| v2 Phase 4 Paper Trading and Autonomy | archived (v2) | `.planning/milestones/v2-phases/04-paper-trading-and-autonomy/` | `- [x] **Phase 4: Paper Trading and Autonomy** ... (completed 2026-10-22)` (`v2-ROADMAP.md:14`) | No per-phase line. Milestone-level as above. | yes | 10 / 10 | yes | `passed` | **yes** | **COMPLETE_VERIFIED** |
| v2 Phase 5 Hardening | archived (v2) | `.planning/milestones/v2-phases/05-hardening/` | `- [x] **Phase 5: Hardening** ... (completed 2026-10-23)` (`v2-ROADMAP.md:15`) | No per-phase line. Milestone-level as above. | yes | 8 / 8 | yes | `passed` | **yes** | **COMPLETE_VERIFIED** |

Verification score lines, for reference: 06 `16/17 met; criterion 17 owner-waived for the phase PR (PROJECT V3-5)`; 07 `9/9`; 08 `13/13`; 09 `10/10`; 10 `8/8`; v2-01 `13/13 must-haves verified`; v2-02 `5/5 must-haves verified`; v2-03 `6/6 must-haves verified`; v2-04 `28/28 must-haves verified`; v2-05 `5/5 success criteria verified`.

Milestone totals: v3 STATE frontmatter `total_plans: 35`, `completed_plans: 35` (9+6+10+7+3 = 35). v2 `MILESTONES.md:5` `5 phases, 44 plans` (14+5+7+10+8 = 44).

### Per-phase classification evidence

- **Phase 6 (BLOCKED).** Open items recorded against it:
  - `STATE.md:82-86`, "Pauses and blockers (owner decisions)": approved_by resolved; G-1/G-2 Route A chosen as a PR-bound waiver; Tracker rows; "Ship ... The phase PR is the remaining step."
  - `STATE.md:30-31` and `:149`: "The phase PR and the merge through ultrathink-ship are the remaining steps."
  - `06-VERIFICATION.md:86` and `:156-157`: criterion 17 is `WAIVED (owner-approved, CI only)`. `:85` criterion 16b `NOT RUN (network)`.
  - `STATE.md:103`: G-1 shows 170 foreign-owned paths; "The 170 foreign-owned paths stay foreign-owned until a follow-up change" (`:86`).
  - `STATE.md:106`: the CI waiver for PR 16 "does not make the gates pass" and "must be removed in the same change as the milestone waiver."
  - `10-CONTEXT.md:4`: "Phase 6 is blocked on owner decisions that do not affect Phase 10."
  - Both files still say the phase is complete, which makes it a disagreement and not a clean state. ROADMAP `:65` says "Phase closed 2026-10-26 with owner-approved deviations" and STATE `:6` says "ship in progress (PR not yet merged)".
- **Phase 7 (COMPLETE_VERIFIED).** Artifacts complete (CONTEXT, 6 PLAN, 6 SUMMARY). VERIFICATION `passed`, 9/9. ROADMAP `:16` `[x]` and progress row Complete. STATE `:31` "Phases 7 to 10: complete." No open decision. The DOC-03 plugin-version decision recorded at `STATE.md:108` (2026-11-12) is resolved ("deliberate, not reverted"). OVERRIDE-A/B/C (`STATE.md:94-96`) are recorded deviations, not pending decisions.
- **Phase 8 (COMPLETE_VERIFIED).** Artifacts complete (10 PLAN, 10 SUMMARY). VERIFICATION `passed`, 13/13. ROADMAP `:17` `[x]`. The D-12 divergence defaults approved 2026-10-25 (`08-CONTEXT.md:43`) are resolved. Evaluator correction recorded at `STATE.md:100-101` and resolved by 08-08..08-10.
- **Phase 9 (COMPLETE_VERIFIED).** Artifacts complete (7 PLAN, 7 SUMMARY). VERIFICATION `passed`, 10/10. ROADMAP `:18` `[x]`. Constitution amendment approved 2026-10-25 and applied (ROADMAP `:161`). Conditional dependency: the BLIND advisory applies only while no paid RPC provider is recorded (ROADMAP criterion 7 at `:148`, `09-CONTEXT.md` G-06). This is a deliverable condition, not an open block. See borderline cases.
- **Phase 10 (COMPLETE_VERIFIED).** Artifacts complete (3 PLAN, 3 SUMMARY). VERIFICATION `passed`, 8/8. ROADMAP `:19` `[x]`. `10-CONTEXT.md:4` says Phases 7-9 "are complete and verified." The deferred live-readiness record (`docs/LIVE_READINESS.md`, LIV-02) is the deliverable. Its custody, venue and legal items are future-decision requirements, not current blockers of this phase. `10-VERIFICATION.md` `## Not verified` says the human spot-check "is not required to close this phase."
- **v2 Phase 1 (COMPLETE_VERIFIED).** 14 PLAN / 14 SUMMARY / CONTEXT / VERIFICATION `passed` 13/13. `v2-ROADMAP.md:11` `[x]`, `MILESTONES.md:3` "Shipped: 2026-10-23". No open item in `STATE.md`.
- **v2 Phase 2 (COMPLETE_VERIFIED).** 5/5/CONTEXT/VERIFICATION `passed` 5/5. Same ROADMAP and milestone evidence.
- **v2 Phase 3 (BLOCKED).** `STATE.md:115`: "Phase 3 human actions: G-4 consumer acknowledgements; live bonding-curve confirmation (needs an account)." `STATE.md:59-61` and `:61`: "bonding-curve layout stays ASSUMED", "Backlog." The live bonding-curve confirmation is an open external dependency with no pending disposition. G-4 alone is dispositioned as backlog, so it does not block by itself.
- **v2 Phase 4 (COMPLETE_VERIFIED).** 10/10/CONTEXT/VERIFICATION `passed` 28/28. `STATE.md:127-139` deferred items. Their dispositions are `deferred-beyond-v3`, `none`, or `Out of Scope (human-owned roster)`. None is an open decision. The `bot-06-exit` roster item (`STATE.md:132`) is dispositioned "Out of Scope," so it does not block.
- **v2 Phase 5 (COMPLETE_VERIFIED).** 8/8/CONTEXT/VERIFICATION `passed` 5/5. `STATE.md:134`: Telegram live verification "not verified without a live bot", dispositioned `Out of Scope (Telegram live verification)`. Treated as out of scope, not as a pending human action. This is the closest call among the COMPLETE_VERIFIED v2 rows.

## Dependency edges

- **ROADMAP ordering.** `ROADMAP.md:198`: "Phases execute in numeric order: 6 -> 7 -> 8 -> 9 -> 10."
- **v3 explicit "Depends on"** (`ROADMAP.md`):
  - Phase 6: `Nothing (first v3 phase; branch bot-00-chief/phase-6-integrity from origin/main f3887bb)` (`:26`)
  - Phase 7 depends on Phase 6 (`:70`)
  - Phase 8 depends on Phase 6, "integer money and the new result schema" (`:101`)
  - Phase 9 depends on Phase 8 (`:138`)
  - Phase 10 depends on Phase 9 (`:171`)
- `STATE.md:76` agrees: "Phase 8 also depends only on phase 6, but runs after phase 7 in ROADMAP numeric order. Both edit CHANGELOG.md, so they are serialized."
- **Out-of-order completion.** Phase 7 was completed 2026-10-25 and Phase 6 was closed 2026-10-26 (`ROADMAP.md:198-206`). Phase 7 therefore completed before its dependency was closed. Recorded dates only.
- **Replay-hash edges.** Phases 8, 9, 10 each require the `smoke-10m` events.hash to be recorded "before" and "after" against Phase 6's value (`ROADMAP.md:116`, `:150`, `:182`; `STATE.md:101` "unchanged (b69c2959...)").
- **v3 PLAN-level `depends_on`** (from PLAN frontmatter):
  - 06: 03→01; 04→02; 07→03; 08→01,02,04; 09→01..08; others `[]`.
  - 07: 02→01; 05→01,02,03,04; 06→05.
  - 08: 04→01; 05→01,02,03; 06→04,05; 07→10 (forward reference to a later-numbered plan); 08→06; 09→08; 10→09.
  - 09: 02→01; 03→02; 04→03; 07→01..06.
  - 10: 03→01,02.
- **v2 PLAN-level `depends_on`:** `01-foundation` 04→02,03; 05→01; 06→01; 07→04,06; 08→02,03,04,05; 09→06,07,08; 12→13. `02-restructure` 02→01; 03→02; 04→03; 05→03. `03-tools-and-skills` 02→01; 03→02; 04→03; 05→04; 06→04; 07→05,06.
- **Cross-phase code and artifact references:** Phase 6 INT-07 re-applies WR-07 and the ledger-mark fee fix (`ROADMAP.md:58`). Phase 7 documents the Phase 6 code (`ROADMAP.md:69`). Phase 9 reuses Phase 8's divergence check and trial limits (`09-VERIFICATION.md:44`, `09-CONTEXT.md:10`). Phase 10's import-graph proof spans the backtest, paper and upgrade modules (`ROADMAP.md:178`).

## Archive-only flags

- **All five v2 phases** exist only under `.planning/milestones/v2-phases/` (`01-foundation` through `05-hardening`). No copy exists under `.planning/phases/`. Their milestone roadmap is `.planning/milestones/v2-ROADMAP.md`, linked from `ROADMAP.md:11`.
- No v3 phase (06-10) has artifacts under an archive path.

## Interpretation and borderline cases

1. **Rule 1 (BLOCKED).** A literal "any decision recorded" reading would move these phases to BLOCKED: Phase 7 (DOC-03 decision, `STATE.md:108`), Phase 8 (D-12 approval `08-CONTEXT.md:43`; D-13 human-set autonomy level `08-CONTEXT.md:48-49`), Phase 9 (amendment approval, paid RPC provider condition), and Phase 10 (live-path sign-off, `STATE.md:108`). I did not apply that reading, because each of these is resolved or is a deliverable condition, and the 10-CONTEXT text says Phase 10 is not blocked.
2. **Phase 9 borderline.** `09-VERIFICATION.md:88` says the other nine seats keep the shared clause 3 "until the human writes a hi[gh-spend ...]". That is a pending human action on a runtime condition. It is not a phase closure dependency, so Phase 9 is COMPLETE_VERIFIED. A stricter reading would make it BLOCKED.
3. **v2 Phase 3 vs Phase 5.** Both have external items. Phase 3 has a pending human action ("needs an account", `STATE.md:61`, `:115`). Phase 5 has an item dispositioned "Out of Scope" (`STATE.md:134`). I applied the pending-versus-dispositioned distinction.
4. **Phase 6 verification body.** `06-VERIFICATION.md` frontmatter says `status: passed`. The body still contains a `Correction (2026-10-25)` that says "Status remains `gaps_found`" and a `Superseded (2026-10-26)` note. Rule 3 uses the frontmatter, so the body does not change the class. Phase 6 is BLOCKED on rule 1 regardless.
5. **STATE frontmatter disagrees with its body on Phase 6.** `STATE.md:14` says `blocked_phases: 0`, while `STATE.md:82-86` records open owner-decision pauses on Phase 6 and `STATE.md:103` says "Phase 6 stays gaps_found." The body is what I used.

## Discrepancies observed (not changed)

- `STATE.md:6` says Phase 6 is "ship in progress (PR not yet merged)", but `ROADMAP.md:15` and `:202` mark it `[x]` / Complete. Rule 4 would require the state files to agree, so they do not agree for Phase 6 (this reinforces BLOCKED).
- `STATE.md:29-31` and `:76` say Phase 8 "depends only on phase 6"; `ROADMAP.md:101` says `Depends on: Phase 6`. These agree.
- Plan 08-07 `depends_on: [08-10]` names a later-numbered plan. Recorded only.
- `STATE.md:108` (2026-11-12) records that marketplace files were restored in a follow-up commit after a DOC-03 mismatch. Phase 7 was last verified at `da6c071` (`07-VERIFICATION.md` frontmatter `head: da6c071`), so the Phase 7 verification predates that change. Not verified (see below).

## Not verified

- Did not run any test, gate, lint, or gsd-tools command. Verification status is the frontmatter value only; no artifact content was re-verified against code.
- Did not confirm the human autonomy level for PAP-03 (`08-CONTEXT.md:48-49`); no state line records it.
- Did not confirm the phase PR state (`STATE.md:85`) with `gh`; BLOCKED rests on the state files.
- Did not check whether `.receipts/bot-00-chief/phase-6.json` or the G-1 waiver changes since 2026-10-26 altered Phase 6 status. The file exists on disk (listed, not read).
- Did not read `PROJECT.md`, `REQUIREMENTS.md`, `AMENDMENT-2026-10-25.md`, `TODO-BACKLOG.md`, `audit/`, or `research/`, which were outside the assignment.
- Did not confirm the v2 STATE status per phase, because none exists in `STATE.md`.

## Commands run (read-only, except the noted temp file)

All ran in `/root/src/repos/pumpgrok` or `.planning`. Each exited 0 unless noted.

- `ls -la .planning/`, `ls -la .planning/phases/`, `find .planning -maxdepth 3 -type d | sort`, `ls -la .receipts`: exit 0.
- `find phases -type f`, `find milestones -type f`, `ls -la audit`, `find research -maxdepth 2`: exit 0.
- `find ... -name '*VERIFICATION*' -exec sh -c '...' > /tmp/verif_head.txt`: exit 0. **This wrote a temp file to `/tmp/verif_head.txt`, outside the report path.** I removed it with `rm -f /tmp/verif_head.txt`, which exited 0. No other files were written.
- `awk` frontmatter extraction over all `*VERIFICATION*.md`, plus per-directory `ls | grep -c` artifact counts: exit 0.
- `grep` over `.planning/milestones/v2-ROADMAP.md`, `phases/*/*-CONTEXT.md`, `phases/*/*-VERIFICATION.md`, `phases/*/*-PLAN.md`, and `milestones/v2-phases/*/*-PLAN.md` for `depends_on`, status and blocker keywords: exit 0.
- `sed` / `awk` extraction of `09-CONTEXT.md:70-82`, `08-CONTEXT.md:40-52`, `10-CONTEXT.md:1-8`, `06-VERIFICATION.md:1-40`, and the `## Not verified` sections: exit 0.
- `ls -la .receipts/bot-00-chief/`: exit 0.
- Report written with the `write` tool to `.receipts/bot-00-chief/phase-inventory.md`.

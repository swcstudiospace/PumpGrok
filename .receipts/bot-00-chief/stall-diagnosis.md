# Stall diagnosis: GSD autonomous milestone review, PumpGrok Desk v3

## Conclusion

On disk, the phase-level state is internally consistent. ROADMAP.md, STATE.md and the five phase directories agree on phase identifiers (6–10), on counters (5/5 phases, 35/35 plans, 34/34 requirements), and all five `*-VERIFICATION.md` frontmatters read `status: passed`. The phase-discovery filter in `autonomous.md` therefore selects no phase from the observed fields. The one deterministic break on the milestone-review path is the audit lookup. `autonomous.md:666-667` reads `.planning/v${milestone_version}-MILESTONE-AUDIT.md` and greps `^status:` from it. The only audit file on disk is `.planning/MILESTONE-AUDIT.md`, which has no `status:` line. Whenever the lifecycle step runs, audit detection falls into `handle_blocker` with "Audit did not produce results — audit file missing or malformed" (`autonomous.md:670-672`). **Verdict: (b), artifact-path mismatch.** Whether a given run reaches the lifecycle at all depends on `phase_complete`, which is computed by the GSD tool and is not on disk. That part is not reproduced here (see the last section).

## 1. Phase identifiers, ROADMAP.md vs STATE.md

| Source | Field / line | Observed value | Result |
|---|---|---|---|
| ROADMAP.md | l.15–19 phase list | Phases 6, 7, 8, 9, 10; all `[x]` | Set = {6,7,8,9,10} |
| ROADMAP.md | l.1 title; l.7 coverage | "PumpGrok Desk v3"; "all 34 v3 requirements" | — |
| STATE.md | frontmatter l.3 `milestone` | `v3` | matches ROADMAP |
| STATE.md | frontmatter l.10 `current_phase` | `6` | in set |
| STATE.md | l.29 Current Position | "Phase: 6 of 10 (Integrity closure)"; "Phases 7, 8, 9 and 10 are complete" | in set |
| STATE.md | l.75–77 Dependency levels | Level 0 phase 6; Level 1 phase 7; Level 2 phase 9; Level 3 phase 10 | in set; phase 8 named at l.76 |
| STATE.md | l.55–71 TODO mapping | Phases 6–10 referenced | in set |

**Diff of identifier sets:** no mismatch. Phase numbers and names agree (e.g. "Integrity closure", "Live readiness, kept disabled").

Field-level discrepancies found in the same files (none changes the phase set):

| # | File | Field / line | Observed | Conflicting source |
|---|---|---|---|---|
| D1 | STATE.md | l.35–39 "Discovery (2026-10-25)" | Says phase 7 has "no SUMMARY" and "Phases 8-10 have no artifacts" | Disk: 07 has 6 SUMMARY files; 08, 09, 10 have CONTEXT, PLAN, SUMMARY and VERIFICATION (see §3). Stale, dated narrative. |
| D2 | STATE.md | l.104 "re-verified at da6c071" for phases 6–10 | Phase 6 frontmatter `head: 404e0f6` (06-VERIFICATION.md l.6) | Phases 7–10 frontmatter `head: da6c071` (l.6 each). Phase 6 is the exception. |
| D3 | STATE.md | frontmatter l.7 `last_updated: "2026-10-26T12:00:22Z"` | Body l.106–109 contains owner decisions dated 2026-11-12 | Frontmatter metadata not updated after the later decisions. |
| D4 | ROADMAP.md | l.45 Phase 6 criterion 16 | Requires `gh pr list ... --jq 'all(.isDraft and .mergedAt == null)'` to print `true` | STATE.md l.105 "ready PR merged on green CI"; l.118 "Criterion 16 (draft PR) conflicts with the owner's ready-PR decision. Requirement text unchanged." ROADMAP still `[x]`. |
| D5 | ROADMAP.md | l.46 Phase 6 criterion 17 | Requires `run_all.py` exit 0 for each completion claim | STATE.md l.97 "criterion 17 is a FAIL, not a PASS"; l.83 PR-bound waiver; 06-VERIFICATION.md l.5 "16/17 met; criterion 17 owner-waived". ROADMAP still `[x]`. |

## 2. STATE.md current-position fields vs ROADMAP.md progress table

| Counter / field | STATE.md (frontmatter) | ROADMAP.md (Progress table l.200–206, Phase details) | Match |
|---|---|---|---|
| total phases | `total_phases: 5` (l.12) | 5 rows | yes |
| completed phases | `completed_phases: 5` (l.13) | 5 rows, all "Complete" | yes |
| blocked phases | `blocked_phases: 0` (l.14) | no blocked row | yes |
| total plans | `total_plans: 35` (l.15) | 9 + 6 + 10 + 7 + 3 = 35 | yes |
| completed plans | `completed_plans: 35` (l.16) | 9/9, 6/6, 10/10, 7/7, 3/3 | yes |
| percent | `percent: 100` (l.17) | — | — |
| status | `status: in_progress` (l.5) | — | — |
| requirements | — | 12 + 4 + 10 + 6 + 2 = 34 (l.7 says 34) | yes |

Note: `status: in_progress` and `percent: 100` coexist. STATE.md l.31 and l.148 say milestone close has not started and the Phase 6 PR is pending. The counters count plans and phases, not the milestone close.

## 3. Artifact files, phases 6–10

Plan and summary counts are from file listings under each phase directory. Status values are verbatim from frontmatter line 4 unless noted.

| Phase dir | CONTEXT | PLAN files | SUMMARY files | VERIFICATION file | frontmatter `status` (verbatim) | Notes |
|---|---|---|---|---|---|---|
| 06-integrity-closure | `06-CONTEXT.md` yes | 9 (`06-01` to `06-09`) | 10 (`06-01` to `06-09` plus `06-01b-SUMMARY.md`) | `06-VERIFICATION.md` | `status: passed` | `06-01b-SUMMARY.md` has no `06-01b-PLAN.md`. Body l.14 `**Status:** \`passed\``; body l.17 "Status remains \`gaps_found\`" is marked superseded at l.19 and l.23. |
| 07-documentation-upgrade | `07-CONTEXT.md` yes | 6 | 6 | `07-VERIFICATION.md` | `status: passed` | — |
| 08-backtest-and-paper-evaluation | `08-CONTEXT.md` yes | 10 | 10 | `08-VERIFICATION.md` | `status: passed` | Extra non-plan files: `08-CORRECTION.md`, `CHECKER-FIXES-ROUND1.md`. |
| 09-bounded-paper-self-upgrade | `09-CONTEXT.md` yes | 7 | 7 | `09-VERIFICATION.md` | `status: passed` | — |
| 10-live-readiness-kept-disabled | `10-CONTEXT.md` yes | 3 | 3 | `10-VERIFICATION.md` | `status: passed` | A second `status: passed` at body l.11, after frontmatter close at l.7. Body `head: 9562a55` (l.13) differs from frontmatter `head: da6c071` (l.6). |

All five VERIFICATION files are present at the `NN-VERIFICATION.md` name the workflow's discovery expects. No phase has a `human_needed` or `gaps_found` frontmatter value.

## 4. Phases the autonomous run would select (discovery rules, `autonomous.md`)

Rule (`autonomous.md:175`): keep `phase_complete !== true`, including `verification_status !== "passed"`.

- `phase_complete` is not stored in any file read here. It is computed by the GSD tool. A proxy from disk is the ROADMAP checkbox, which is `[x]` for phases 6–10 (ROADMAP l.15–19).
- `verification_status` maps to the frontmatter `status`, which is `passed` for all five phases (§3).
- Result from observed fields: **no phase selected.** `discover_phases` would print "All phases complete! Nothing left to do." and exit cleanly (`autonomous.md:201-209`).
- Control-flow inconsistency: `autonomous.md:201-209` exits cleanly with no lifecycle, while `autonomous.md:624` says "If all phases complete, proceed to lifecycle step" after the iterate loop. The lifecycle (and therefore the audit) runs only through the iterate path, which needs at least one phase to be processed in the run. A run that starts with all phases complete never reaches the audit.
- Candidate that would select phase 6 if the tool counts summaries against plans: 10 SUMMARY vs 9 PLAN (`06-01b`). This is a hypothesis. The counting rule is not visible on disk.

## 5. Pause conditions and pending prompts

| Condition | Where in `autonomous.md` | State from disk | Pause expected? |
|---|---|---|---|
| Grey-area / discuss | Smart discuss skipped when `has_context` true (l.263–269); `handle_blocker` only if CONTEXT missing after discuss (l.323) | `*-CONTEXT.md` exists for all five phases (§3) | No |
| Plan-phase failure | `has_plans` check (l.377) | PLAN counts are non-zero for all five | No |
| Verification `human_needed` (validation prompt) | l.456–462 | No frontmatter value is `human_needed` (§3) | No |
| Verification `gaps_found` / other status | l.476–530, l.454 | No frontmatter value is `gaps_found` or other (§3) | No |
| STATE blockers check | l.611: "Check for blockers in the Blockers/Concerns section" | STATE.md has no heading named "Blockers/Concerns". Its heading is "## Pauses and blockers (owner decisions)" (STATE.md l.80), with 4 items (l.82–86). Items 1–2 are marked "resolved". Item 3 (Linear rows skipped) and item 4 (Phase 6 PR "remaining step") are not marked resolved. | Unknown. The parser's section match is not on disk. If it matches, a `handle_blocker` prompt is surfaced, not a silent stall. |
| Deferred verification skip | l.169–173 keys on `## Deferred Verification` | No `## Deferred Verification` heading in STATE.md (grep of all `^#` headings). STATE.md l.107 says "blocked phases accepted as deferred", but no table exists to parse. | No skip recorded |
| Audit missing/malformed | l.666–672 | See §6 | Yes, when lifecycle is reached |
| Audit `gaps_found` / `tech_debt` prompts | l.683–711 | Audit file has no `gaps_found` or `tech_debt` token (§6) | Not reached |
| Pending owner decision without prompt | STATE.md l.106–109 (2026-11-12 entries) | Entries are recorded as answered ("HITL answer"). l.109 says "Applied defaults … only for questions the owner did not answer." l.118 records an unresolved conflict (criterion 16, see D4) with "Requirement text unchanged." | No open prompt recorded. One unresolved conflict (D4) is noted but not presented as a question. |

## 6. Root-cause verdict

**Verdict: (b), artifact-path mismatch.**

Evidence chain:

1. `autonomous.md:666`: `AUDIT_FILE=".planning/v${milestone_version}-MILESTONE-AUDIT.md"`.
2. `autonomous.md:667`: `AUDIT_STATUS=$(grep "^status:" "${AUDIT_FILE}" ...)`.
3. `STATE.md` frontmatter l.3: `milestone: v3`. The expected path is therefore `.planning/v3-MILESTONE-AUDIT.md` if `milestone_version` is `3`, or `.planning/vv3-MILESTONE-AUDIT.md` if it is `v3`. The value from `init.autonomous` was not read, so the exact expected path is unverified. Neither candidate exists.
4. Files named `*AUDIT*` under `.planning/` (glob): `.planning/MILESTONE-AUDIT.md` and `.planning/milestones/v2-MILESTONE-AUDIT.md`. The v2 archive uses the `v2-` prefix. The current audit does not.
5. `.planning/MILESTONE-AUDIT.md`: a grep for `^status:`, `^---$`, `gaps_found` and `tech_debt` matched only line 1 (`# Milestone audit: PumpGrok Desk v3`). The file has no YAML frontmatter and no `status:` line. Line 3 says "Audit date: 2026-11-12." So `AUDIT_STATUS` evaluates to empty, which routes to `autonomous.md:670-672`.

Two defects sit on this path. The path does not match the convention the workflow computes (`v<version>-` prefix). The file has no machine-readable `status:` field. Either one alone produces the same empty `AUDIT_STATUS` and the same blocker message.

**Scope of the verdict:** this explains the stall at the milestone-review (audit) step, once the run reaches it. It does not explain why the run reaches the lifecycle. Phase selection (§4) is consistent with "nothing to do" on disk, so the trigger for the reported stall on prior phases is not established by these files (see the last section).

## Not verified

- **`phase_complete`** and **`verification_status`** as computed by the GSD tool. Only the ROADMAP checkbox and the frontmatter `status` were observed. I did not run `gsd_run query init.manager`, `init.autonomous`, `init.phase-op`, or `verification.status`.
- **`milestone_version`** as returned by `init.autonomous`. Only STATE.md frontmatter `milestone: v3` was observed.
- **Whether the blocker check at `autonomous.md:611`** matches the STATE.md section "Pauses and blockers (owner decisions)". The check's heading match is not on disk.
- **Audit body content** beyond the frontmatter-style grep in §6 (`.planning/MILESTONE-AUDIT.md`). I did not read its body.
- **Archive directory** for step 5b (`autonomous.md:731`). Not checked.
- **Whether `06-01b`** is counted as a plan by the tool. The count mismatch (10 SUMMARY, 9 PLAN) is observed, but its effect on `phase_complete` is not.
- **Runtime behaviour** of any run. No autonomous run was executed, and no gate, test, lint or typecheck was run.

## Log needed to reproduce the stall on prior phases

Capture from one autonomous invocation (read-only queries only):

1. The JSON from `gsd_run query init.autonomous` and `gsd_run query init.manager`, including `milestone_version`, `phase_count`, `completed_phases`, and the `phases[]` array with `phase_complete` and `verification_status` for each phase.
2. Output of `gsd_run query verification.status .planning/phases/06-integrity-closure --pick status` and the same for phases 07–10.
3. The printed "Phase Plan" table from `autonomous.md` discover_phases (l.213–222).
4. The stderr or AskUserQuestion text for any `handle_blocker` invocation, including the description string.
5. `ls -la .planning/` output, to confirm the audit path the run computed.

## Commands run

No shell commands were run. All evidence came from file read, glob and grep tool calls. No gsd-tools command was run, so no exit codes apply. Reads were within the assignment, with two exceptions. I read `autonomous.md` line ranges 439–463 and 599–763, which the assignment did not list, because they hold the verification routing and lifecycle steps. I also ran grep across the body of the VERIFICATION files to check status tokens, which reaches past their frontmatter. No file other than this report was written.

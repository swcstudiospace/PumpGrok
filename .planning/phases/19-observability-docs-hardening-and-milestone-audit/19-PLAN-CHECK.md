# Phase 19 Plan Check: Observability, docs, hardening and milestone audit

**Verdict: PASS** — 9 plans checked (19-01 to 19-09 plus 19-PLAN-INDEX.md),
against 19-CONTEXT.md, ROADMAP Phase 19 (8 requirements), and REQUIREMENTS.md.
No blockers. 3 warnings and 3 advisories below.

## Requirement coverage (all 8 ROADMAP ids claimed)

| Requirement | Plans | Status |
|-------------|-------|--------|
| OBS-01 doctor v4 read-only | 19-04 | Covered, test-first, refusal-only exit |
| OBS-02 health and metric families | 19-03 | Covered, test-first, event-gated |
| OBS-03 alert rules name real metrics | 19-05 | Covered, test-first registry pin |
| OBS-04 docs, skills, runbooks, commands run | 19-01, 19-02, 19-05, 19-07 | Covered, verify_doc_commands in each |
| OBS-05 milestone audit, live refused | 19-08 | Covered, human-gated, exit 3 proof |
| OBS-06 nightly event-mode soak, zero idle Grok | 19-04 | Covered, scheduled job plus fast-path acceptance |
| PRC-06 phase close records | 19-06, 19-09 | Covered |
| PRC-08 waiver removed, set empty | 19-04 | Covered, only plan allowed after amendment PR |

PRC-03 (hash pins) is additionally claimed by 19-06 though absent from the
ROADMAP Phase 19 line. This is correct, not scope creep: REQUIREMENTS.md
requires every phase close to record its CHANGELOG before and after pair.

## Dimensions checked

1. **Dependencies and waves.** No cycles. All cross-phase deps point
   backward (11-01, 13-02, 14-04, 14-07, 16-04, 17-02/03/04, 18-02/07/10/11).
   Waves match the CONTEXT plan list: 19-01/02/03/04 in wave 1,
   19-05 and 19-07 in wave 2 (19-05 after 19-03; 19-07 after 19-04),
   19-06 in wave 3, 19-08 in wave 4, 19-09 in wave 5.
   Merge order PR-40 through PR-45 matches plans; 19-06 orders after 18-10
   and 19-09 after 18-11. Shared branches have no file overlap
   (PR-43: 6 files vs 7 files disjoint; PR-45: 7 vs 2 vs 3 disjoint).
2. **Seat purity (G-1).** Verified by executing resolve_owner with
   load_manifest(DEFAULT_MANIFEST): tests/desk maps to bot-00-chief
   (the CONTEXT D-06 exception), supervisor/health to chief, the scout
   skill to bot-01-scout, CHANGELOG.md to bot-09-journal, .planning paths
   to bot-00-chief. Every plan forbids .planning writes except the
   explicit chief exception (19-08, 19-09); summaries go to
   /tmp/v4/summaries. Every plan states the receipt is committed WITHOUT
   approved_by; human approval lands as human:SomeRandmGuyy at CP19.
3. **Acceptance honesty.** No banned construct in any verify block:
   no collect-only, no --co, no --no-verify, no error swallowing, no
   --dry-run, no inline PUMPGROK_LIVE_ENABLE (mentions are prohibitions
   in execution text only). No vacuous checks: 19-03 carries the
   no-SKIPPED gate; 19-05 fails on any unknown metric name; 19-06 reads
   the trading-smoke hash live from the pin file and records equal
   before and after pairs. Behavior plans (19-03, 19-04, 19-05) are
   test-first with named red-green steps.
4. **Determinism and hash safety.** Integer lamports, Clock-only time,
   and read-only doctor/health semantics are stated in plan execution
   blocks. Hash b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
   is cited identically in 19-03, 19-04, 19-05, 19-06; the trading-smoke
   hash is never hardcoded (read from pins/trading_smoke.json).
   Ledger payloads are untouched; fresh worktrees without
   var/ledger.sqlite are required for receipt commands.
5. **Metric family safety.** 19-03 registers P and L families event-mode
   only, pins the nine existing family names in Test 3, keeps cadence
   output byte-identical, and records the new family names in its summary
   for 19-05 alert rules to consume. The nine-family exposition test
   stays valid by construction.
6. **Scope and live safety.** No plan arms anything, adds timers, adds
   signing or key code (grep for signing, private key, mnemonic, keypair
   returns nothing), or claims profitability (grep for profit, expected
   or guaranteed returns returns nothing). Live refusal with exit 3 is an
   acceptance command in 19-03, 19-04, and 19-08. Waiver removal sits
   only in 19-04 with deps on 18-07. 19-08 is autonomous false,
   human-gated under OD-19, and the audit contains no arm steps.
7. **Cited files and symbols.** All pre-existing citations resolve
   (metrics.py NINE_FAMILIES at line 64, doctor.py, ci.yml, gates.yml,
   skills, ARCHITECTURE, CLAUDE, AGENTS, README, SETUP, quality-gates,
   CHANGELOG, check.sh, verify_doc_commands.sh, ownership gate).
   Absent paths (metrics_events.py, new desk and docs tests, soak test,
   runbooks, alerts.yaml, trading pin, no_pr_waivers test, datafeed dir)
   are predecessor-phase artifacts from unexecuted phases 11 to 18, and
   the LivePriceSource name is confirmed in the 13-02 plan chain.
   Expected, not defects.
8. **Context compliance.** All D-01 through D-13 decisions are
   implemented: D-09 single-follower rule for gates.yml, D-10 fast-path
   acceptance with the schedule paying the soak cost, D-12 full
   requirement matrix from plans.json with the unverified list, D-13
   close records. No deferred idea (Grafana, wake_mode flip, v5 scope)
   appears in any plan.

## Warnings (should fix, execution may proceed)

### W-1. Double-run determinism proof has no owning verify
- Plan: 19-06. ROADMAP criterion 11 requires the a-then-b equality run
  proving smoke-10m verify is deterministic across invocations. 19-06
  records the equal pair and runs a single verify grep, but no plan in
  phases 11 through 19 executes the two-sample equality command
  (repository-wide grep for the two-sample shape returns nothing).
- Fix: add the two-sample equality command to 19-06 acceptance or to
  the 19-08 nine-phase rerun list.

### W-2. Criterion 5 content grep has no owning verify
- Plan: 19-07. ROADMAP criterion 5 requires README, SETUP, and CLAUDE
  to mention event mode or wake_mode. 19-07 task 1 writes that prose
  but verifies only with verify_doc_commands.sh, which checks that
  commands run, not that the wording is present.
- Fix: add the grep for event mode or wake_mode across the three files
  to 19-07 acceptance.

### W-3. No repository-wide TODO or FIXME scan before closeout
- Phase scope. CONTEXT D-05 and every doc plan forbid TODO and
  placeholder text, and check.sh enforces the your-org placeholder and
  emoji gates, but nothing scans the tree for TODO or FIXME strings:
  ruff select lacks TD rules and no plan or gate runs such a scan.
- Fix: add a TODO and FIXME scan command to 19-07 or 19-09 acceptance
  (or record in 19-08 that the audit performed it).

## Advisories

- I-1. Full make test, make cov, and make test-all (criterion 1) run in
  CI rather than per-plan, by explicit CONTEXT design given the 50-minute
  soak; 19-08 reruns all nine phases of receipt commands on the final
  tree. No action required.
- I-2. Negated greps (no pull_request.number, no SKIPPED) are genuine
  absence proofs, not error swallowing; each is paired with a positive
  gate (ci/tests, the health suite). No action required.
- I-3. 19-03 task 4 verifies with make lint while its done clause also
  claims typecheck; typecheck is separately an acceptance command, so
  coverage holds. No action required.

## Recommendation

No blockers. Address warnings W-1 through W-3 at planner discretion,
then proceed to execution.

# Phase 16 Plan Check: Backtest v2 and autonomous evaluation

Verdict: PASS. 7 plans, 26 tasks, waves 1-6. Zero blockers, zero warnings, 5 advisories.
Checked against 16-CONTEXT.md (D-01 to D-13, G-01 to G-03), ROADMAP Phase 16
(8 requirements, 13 success criteria), seat manifest (G-1 OK, 10 bots, 192 rules),
and the working tree at this HEAD.

## Coverage

| Requirement | Plans | Real command | Status |
|-------------|-------|--------------|--------|
| REC-03 record/import verbs | 16-04 | tests/cli/test_record.py, test_strategy_backtest.py | Covered |
| BT-08 metrics formulas | 16-01 | test_metrics_v2.py (RED first) | Covered |
| BT-09 round trips, per-strategy | 16-01, 16-05 | test_roundtrip.py, test_strategy_section.py | Covered |
| BT-10 look-ahead, grading | 16-02 | test_lookahead.py, test_grading.py | Covered |
| BT-11 gaps, haircut, cooldown | 16-02 | test_gaps.py | Covered |
| BT-12 strategy replay, bisect perf | 16-02, 16-04 | test_strategy_replay.py, test_dataset_curve_source_perf.py | Covered |
| BT-13 scheduler, store, provider | 16-03 | test_scheduler.py, test_evidence_provider.py | Covered |
| OBS-07 per-strategy section | 16-05 | tests/reporting | Covered |

## Focus areas (all hold)

- Formulas: 16-01 RED task asserts every D-07 formula verbatim, including
  annualized None with annualization_valid false under 7 days, profit-factor
  None with no loser and 0 with no winner, sortino None cases, drawdown over
  the full series including marks, exposure integral ratio. Money integer
  lamports, ratios Decimal, no time calls.
- Look-ahead canary is real: 16-02 plants extreme ticks after time T and asserts
  decisions at or before T are unchanged; fills price at the latest tick known
  at decision plus seeded latency; ts_utc is knowledge time.
- Ordering key: 16-02 replays through the phase-12 DeterministicBus ordered by
  (ts, priority_rank, source_seq), explicitly NOT (ts, line). Same bus class as
  live-paper, so the key is equal by construction. (Bus lands in phase 12,
  which executes before phase 16; no symbol to verify at this HEAD.)
- equity.py preflight: 16-01 task 3 checks for backtest/equity.py (absent at
  this HEAD because draft PRs 17-20 are unmerged) and HALTS with a blocker in
  the receipt unverified list instead of inventing a second valuation function.
- Scheduler: 16-03 subscribes only to A1 catalog edges, no B-private events,
  no timers, no sleeps, single-flight, read_autonomy gate at autonomous-paper.
- Grading: 16-02 grades traded_only, fixture and hand-authored data as research
  or synthetic, never promotion; promotion needs all_launches or watchset,
  gap and overflow shares at most 5 percent each, span 7 days, 200 tokens.
- Seat purity: every files_modified path resolves to its plan seat via
  resolve_owner; tests, cli, reporting, CHANGELOG, .planning splits all match.
  Receipts under .receipts/SEAT with task_id, never approved_by; summaries and
  fragments under /tmp/v4/summaries; executors never write .planning files.
- Honesty: no --co, collect-only, --dry-run, --force, 2>/dev/null compares,
  output swallowing, or live-enabling env in any verify; live refusal exit 3
  in every plan acceptance; no signing or key code anywhere.
- Determinism: 16-06 measures both hash pairs twice and halts on divergence;
  equal pairs recorded, never skipped; no plan touches contracts/.
- Dependencies: DAG is acyclic; waves match depends_on; 16-04 and 16-05 share
  wave 4 with disjoint seats and files; PR merge order PR-27, PR-28, PR-29
  follows plan dependencies; no shared src file across plans; 16-05 defers its
  CHANGELOG lines to 16-06 per G-02.
- Citations: replay/sources.py scan, verbs_state.py:88 record stub
  (return _not_implemented), manifest.py dataset_digest (line 78),
  ledger/autonomy.py read_autonomy (line 30) all verified in tree.

## Advisories (info only, no revision required)

1. [residual-criteria] ROADMAP criteria 2, 8, 10 carry exact shell commands
   (expected-return grep, backtest double-run cmp, grid grep plus
   test_single_search_engine) that no plan verify block runs verbatim.
   Plans: 16-01, 16-04, 16-03. Evidence: grep over plan verifies finds only the
   behavioral equivalents (no-expected-return-language action, v1-output
   preservation, TrialLedger reuse). Example fix: run those three literal
   commands once in 16-07 evidence collection.
2. [seventh-plan-files] 16-07 files_modified lists .planning paths while its
   actions correctly write only /tmp drafts for the orchestrator to apply.
   Plan: 16-07. Evidence: files_modified vs action text. Example fix: note in
   frontmatter that .planning paths are orchestrator-applied, not executor writes.
3. [manifest-strings] D-09 requires fixture manifest values as strings
   (dict[str, str]); 16-02 creates strat-gap/manifest.json but no task asserts
   the string-typing. Plan: 16-02. Example fix: one assertion in test_gaps.py.
4. [task-count] Plans 16-01 to 16-05 carry 4 tasks each (upper bound of the
   convention). Mitigated by narrow file sets (4 to 12 files) and single-seat
   scope; no split required.
5. [roadmap-deliverable] ROADMAP deliverables name a `live serve` verb that
   CONTEXT D-13 deliberately omits (live stays refused, LIV-07). Plans are
   correct to omit it; the ROADMAP line is stale. Example fix: drop
   `live serve` from the Phase 16 deliverables list.

Plans verified. Run /gsd:execute-phase 16 to proceed.

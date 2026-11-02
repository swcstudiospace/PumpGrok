# Phase 11 Plan Check: Engineering foundation and quality

Verdict: FAIL — 1 blocker, 2 warnings. No execution until the blocker is fixed.

## Checks run

- Ownership: resolved every files_modified path of all 11 plans with resolve_owner and load_manifest from ci/gates/check_ownership.py. Every path resolves to its plan seat. Chief-owned .planning writes appear only in chief-seated plans 11-09 and 11-11. Receipt paths match the D-06 glob. No plan writes approved_by.
- Forbidden patterns: scanned all plans for collect-only, --co, --no-verify, output swallowing, --force, --dry-run, inline PUMPGROK_LIVE_ENABLE. Clean. Live refusal exit 3 is verified in every plan that touches src. No signing, key, or send-path code in any plan.
- Dependencies and waves: graph is acyclic, wave numbers equal CONTEXT, plan list and PR mapping equal CONTEXT and 11-PLAN-INDEX. No cross-branch shared files. Same-branch shared files (pyproject.toml and Makefile in 11-03 and 11-05, PR-06 branch) are wave-ordered.
- Requirement coverage: all 15 ROADMAP Phase 11 requirements are claimed. QLT-01, QLT-02, QLT-07, QLT-08, QLT-09, QLT-10, PRC-10 in 11-03. QLT-03 in 11-05. QLT-04 in 11-04, 11-05, 11-06, 11-09. QLT-05 in 11-02, 11-06. QLT-06 in 11-04, 11-05, 11-07, 11-08. PRC-03, PRC-04, PRC-05, PRC-09 in 11-01. Extra claims RSK-08 (11-02), MKT-02 (11-07), MKT-03 plus PRC-06 (11-09, 11-10, 11-11) are CONTEXT-authorized pulled-forwards, consistent with the REQUIREMENTS partial-landing rule.
- CONTEXT decisions D-01 through D-15: each has implementing tasks. D-09 regen-prints-never-writes and library-entry replay are in 11-01 task 5. D-11 section rule is in 11-02 task 3 and 11-04. D-06 and D-07 are in 11-01 tasks 3 and 4 with separate commits.
- ROADMAP criteria 1 through 19 mapped against every plan verification block. Two gaps, filed below as warnings.
- Cited files: verified existence of all hotspot sources, gates, workflows, Makefile, fixtures smoke, smoke-10m, soak-3d, and characterization files referenced by verifications. Sizes match CONTEXT (settings.py 651, seat_task.py 608, backtest.py 650, steps.py 417). Only _is_writer exists at ledger/active_set.py:51 and equity.py is absent, which is exactly the preflight-fails-until-merged behavior 11-01 gates on. scripts/probe_pump_accounts.py, rules.py, and config sections are absent because plans 11-09 and 11-04 create them.
- Determinism: money integer lamports and injected Clock stated in every execution block. Hashes are compare-to-recorded only. 11-10 records before and after pairs for both hashes read from measured values, never invented.

## BLOCKER

1. severity blocker, dimension dependency_correctness.
   required_property: The ratchet plan executes against post-split code and its branch merges after the split branches.
   description: 11-05 depends on 11-06, 11-07, 11-08, 11-09 (frontmatter depends_on, 11-05-PLAN.md lines 6-12) and its purpose is to ratchet complexity down after every hotspot split, merging last per G-03 (11-05-PLAN.md line 53, line 57). But the merge order in 11-PLAN-INDEX.md line 3 and the CONTEXT PR table places PR-06 second (PR-01, PR-06, PR-02, ...), contradicting CONTEXT G-03 (CONTEXT line 29, PR-06 merges last). On that order the 11-05 executor never sees the sniper, rug, scout, or chief splits, so the baseline is recorded pre-split and later merges can exceed it unchecked.
   fix: Change the merge order in CONTEXT and 11-PLAN-INDEX.md to PR-01, PR-02, PR-03, PR-04, PR-05, PR-06, PR-07, PR-08, and add one first step to 11-05 execution to update from main after PR-02 through PR-05 have merged before measuring the baseline.

## WARNINGS

1. severity warning, dimension requirement_coverage.
   required_property: Every ROADMAP success criterion is executed by at least one plan verification block.
   description: ROADMAP criterion 1 requires make test and the paper replay to exit 0. No plan verification block runs either command; 11-03 proves only make -n output shape, and scripts/check.sh lints instruction files rather than running the suite.
   fix: Append make test and uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke to the 11-11 verification block, where the fast suite is complete.

2. severity warning, dimension acceptance_honesty.
   required_property: Every claimed proof in a task action has a matching command in that plan verification block.
   description: 11-05 task 3 claims to prove the mutation-smoke target is not part of make check, but the 11-05 verification block has no exclusion proof and no docs-content proof; ROADMAP criterion 11 requires both.
   fix: Add grep -q risk docs/mutation-testing.md and the negated make -n check probe for mutation to the 11-05 verification block.

## Advisories (info, no revision required)

- Scope shape: 11-01 carries 6 tasks and 11-03 carries 5, with five more plans at 4 tasks. All tasks are CONTEXT-mandated and small, and shared files sit on one branch in wave order, so no split is recommended.
- Cross-branch reads (11-04 running PR-01 characterization tests, 11-09 running the 11-02 seat_task test, 11-10 reading the 11-01 pins JSON) assume the executor starts from main after the depended-on PRs merge. Stating one update-from-main line in 11-04, 11-05, 11-09, 11-10, and 11-11 would remove the guesswork.
- The negated SKIPPED probes pass vacuously if pytest itself crashes, but each sits beside a non-negated run of the same suite that would fail first, so coverage holds.
- ROADMAP criterion 6 names a tomllib assertion over the ruff select set; 11-05 runs ruff check and the ratchet test but not that exact command. Adding it to 11-05 verification would close the wording gap.

## Recommendation

Fix the blocker by reordering PR-06 last with an update-from-main step in 11-05, add the two warning commands, then re-run this check.

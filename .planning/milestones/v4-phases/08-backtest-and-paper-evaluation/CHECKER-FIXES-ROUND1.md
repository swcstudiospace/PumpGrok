# Plan-checker round 1 issues for the Phase 8 correction set

Source: independent gsd-plan-checker report, round 1. The planner must apply each fix to the named plan file, then reply with the list of changed lines. The fixes must keep the binding contract in /tmp/plan8fix-brief.md (sections A to H).

1. 08-09-PLAN.md, Task 1. The action says to keep _params_hash as an identity helper, but its body calls sha256 (src/pumpgrok/backtest/harness.py lines 87-93), and the acceptance bans the string sha256 in that file. Fix: replace the local definition with the import from pumpgrok.backtest.manifest of param_set_hash (defined at manifest.py line 168). Delete the hashlib import and _DIGEST_SCALE. Keep _load_stamps.

2. 08-08-PLAN.md, Task 1. The action requires a slice manifest with recomputed per-file sha256, but the acceptance bans sha256 or hashlib in evaluate.py. The contract allows identity hashing, so the plan is stricter than the contract and contradicts itself. Fix: reuse dataset_digest from manifest.py (defined at line 78) through an import, so evaluate.py has no hashlib text. Or narrow the acceptance grep to score-path names. Choose one and state it.

3. 08-08-PLAN.md, Tasks 1 and 2. Task 1 validates the filter override by constructing FilterSettings, which accepts min_total_score (a known field, default 0.65 in settings.py). Task 2 requires that this key be rejected. A literal Task 1 would fail Task 2's test. Rejection is the correct design: decide_token (src/pumpgrok/engine/pipeline.py lines 100-105) consults only passes_filter, so the knob is inert. Fix: add an explicit blocklist to Task 1's action. Keys that are scoring knobs, including min_total_score inside filter, raise a typed validation error. Cite pipeline.py lines 100-105 as the reason.

4. 08-10-PLAN.md, Task 2. Its acceptance uses --fixture smoke. Roadmap criterion 7 mandates smoke-10m, and 08-06's smoke-10m acceptance ran in wave 3, before this plan rewrites cli.py and report.py in wave 6. A weakened command is blocking. Fix: add the roadmap criterion 7 command verbatim to Task 2's acceptance. That is the smoke-10m double run, cmp, and the holdout, trial, slippage and fees greps. Keep the smoke check as well.

5. 08-08-PLAN.md, Task 2. It asserts that desk-default overrides score above zero on the smoke full window. Nothing confirms this. Entries are not fills, and a positive net needs a profitable exit inside the window. Fix: drop the sign assumption. Pin the integer type, determinism across two runs, and equality with the ledger-derived SELL total minus BUY total minus fees. Let the executor record the observed score in SUMMARY.

After applying these fixes, re-read each changed task and confirm that its action and acceptance do not contradict each other. Reply with the changed file and line ranges. Do not run gates.

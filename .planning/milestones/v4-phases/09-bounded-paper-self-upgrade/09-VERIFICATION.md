---
phase: 09-bounded-paper-self-upgrade
verified: 2026-10-26T07:33:17Z
status: passed
score: 10/10
head: da6c071
---

# Phase 9 Verification Report: Bounded paper self-upgrade

Status: passed
Score: 10/10 roadmap criteria verified, 13/13 substance checks pass
Head: 41df27c docs(09): fill Phase 9 replay hashes (unchanged) and add UPG changelog entries
Gate logs read at /tmp/g9_lint.log, /tmp/g9_type.log, /tmp/g9_test.log, /tmp/g9_check.log, /tmp/g9_vdc.log, /tmp/g9_smoke.log, /tmp/g9_live.log. No gate rerun.

## Criteria table

| # | Criterion | Command or test | Exists | Verdict | Evidence |
|---|-----------|-----------------|--------|---------|----------|
| 1 | lint, typecheck, test, check.sh green, paper smoke one cycle | make lint, make typecheck, make test, ./scripts/check.sh, pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke | yes | PASS | /tmp/g9_lint.log exit 0 All checks passed; /tmp/g9_type.log exit 0 no issues in 177 files; /tmp/g9_test.log exit 0 full suite; /tmp/g9_check.log exit 0 ok 35 skills 10 agents 299 markdown files; /tmp/g9_vdc.log PASS paper --once exit 0, PASS doctor exit 0 |
| 2 | param-set hash, active-set ledger, bounds TOML parses | tests/upgrade/test_param_set_hash.py, tests/upgrade/test_active_set_ledger.py, python tomllib load of src/pumpgrok/config/upgrade_bounds.toml | yes | PASS | Test files present in /root/src/repos/pumpgrok/tests/upgrade/; full suite exit 0; TOML parses (verified by read, 1.2K file with filter and exits range tables) |
| 3 | gate blocks five cases | tests/upgrade/test_promotion_gate.py, 10 tests | yes | PASS | File present; test names cover pass, out-of-bounds, 21-trial, below-autonomy, failed holdout, negative holdout, divergence breach, order, winner binding, empty run id; full suite exit 0 |
| 4 | promotion evidence record | tests/upgrade/test_promotion_evidence.py, 7 tests | yes | PASS | File present; src/pumpgrok/upgrade/evidence.py writes var/upgrade/promotions/HASH.json plus desk JournalNote; full suite exit 0 |
| 5 | exact rollback round trip | tests/upgrade/test_rollback_exact.py | yes | PASS | True promote-then-restore round trip, see check C; full suite exit 0 |
| 6 | escalation, no promotion | tests/upgrade/test_escalation.py | yes | PASS | Out-of-bounds and over-trial escalation plus eligible-verdict refusal, see check E; full suite exit 0 |
| 7 | SAFE-4 and SAFE-8 BLIND advisory, rest KILL, revert on provider | tests/safety/test_blind_advisory.py, 6 tests | yes | PASS | Provider signal unit plus 5 end-to-end verdict cases via MockTransport; full suite exit 0; code path in check F |
| 8 | generate-templates --check and amendment oracle test | scripts/generate-templates.py --check, tests/safety/test_constitution_amendment.py, 12 tests | yes | PASS | Test file present with 12 named tests covering every amended carrier; make check target runs generate-templates.py --check per /root/src/repos/pumpgrok/Makefile lines 52-56; /tmp/g9_check.log exit 0; full suite exit 0 |
| 9 | replay before and after hashes recorded | CHANGELOG.md Phase 9 lines plus orchestrator verify-twice | yes | PASS | CHANGELOG lines 18-19 both carry b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d, equal as allowed; /tmp/g9_smoke.log shows same hash on the smoke fixture runs |
| 10 | live refused with upgrade modules present | pumpgrok run --mode live --once, tests/safety/test_no_backtest_to_live_path.py live-refusal test | yes | PASS | /tmp/g9_live.log exit 3, 9 of 9 preconditions unmet, no transaction attempted; live-refusal exit-3 test intact in guard file |

## Substance checks

### A. Hollow sweep: PASS

Hits for sha256, hashlib, random, secrets, uuid in /root/src/repos/pumpgrok/src/pumpgrok/upgrade, /root/src/repos/pumpgrok/src/pumpgrok/backtest, /root/src/repos/pumpgrok/src/pumpgrok/tools/safety, /root/src/repos/pumpgrok/src/pumpgrok/cli.py:

- /root/src/repos/pumpgrok/src/pumpgrok/upgrade/params.py line 87: return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest() inside content_hash, documented lines 78-86 and module docstring as identity only, never a score metric or verdict. Pinned by test_hash_is_identity_only which asserts ParamSet has no score, verdict, or metric attribute.
- /root/src/repos/pumpgrok/src/pumpgrok/backtest/manifest.py lines 90-91, 165, 172, 178, 217: run-id, dataset-digest, FilterSettings-hash, param-set-hash, manifest-id. All name exact sets or runs; Phase 8 correction already replaced the hash-scored harness with net-lamports ranking.
- /root/src/repos/pumpgrok/src/pumpgrok/cli.py lines 1112-1131: config_hash identity in the live-confirmation record, wallet_allowlist_sha256 of a constant, hmac signature. None decides a promotion, score, metric, or sort.
- No random, secrets, or uuid value in any of the four trees decides a verdict. The only secrets hit is the name refuse_cli_secrets. No os.urandom in new code.

### B. Gate reuse: PASS

/root/src/repos/pumpgrok/src/pumpgrok/upgrade/gate.py imports the Phase 8 divergence check (from pumpgrok.backtest.divergence import breach_line, check, line 23), the trial limits (from pumpgrok.backtest.trials import MAX_ALLOWED_TRIALS, MAX_ELIGIBLE_TRIALS, line 26), autonomy (from pumpgrok.ledger.autonomy import read_autonomy, line 27), and the holdout (search.holdout_net_lamports and search.holdout_id on the HarnessResult, lines 148-157). No literal 20, 50, or D7 threshold in code; the only numerals are the imported names in messages. First-failure order in evaluate_candidate: bounds via validate_against_bounds, then trials, then read_autonomy against REQUIRED_AUTONOMY_LEVEL autonomous-paper, then holdout_net_lamports <= 0, then check(backtest, paper) divergence. Winner binding enforced: params.content_hash must equal search.best_params_hash else ValueError.

### C. Rollback realness: PASS

/root/src/repos/pumpgrok/tests/upgrade/test_rollback_exact.py test_promote_then_rollback_round_trip is a real round trip: records SET_A, promotes SET_B through the gate, records SET_B, then restore_active_set with SET_A content hash, asserting:

assert restored == SET_A.content_hash
assert read_active_set(store) == SET_A.content_hash
assert [row["payload"]["new_hash"] for row in changes] == [SET_A.content_hash, SET_B.content_hash, SET_A.content_hash]

Content hash and ledger order both asserted. test_malformed_prior_hash_writes_nothing pins fail-closed on bad input.

### D. Bounds: PASS

/root/src/repos/pumpgrok/src/pumpgrok/upgrade/bounds.py _check_section raises OutOfBoundsError for unknown keys, wrong types, and out-of-range values, with no clamp path anywhere in the file:

raise OutOfBoundsError(f"out of bounds: section.key=value outside [minimum, maximum]")

Pinned by tests/upgrade/test_promotion_gate.py test_out_of_bounds_blocks using OUT_OF_BOUNDS ParamSet filter min_unique_buyers 5000, asserting verdict.reason == REASON_OUT_OF_BOUNDS, a reason reachable only through the except OutOfBoundsError path in the gate. Nuance: no standalone unit test asserts pytest.raises(OutOfBoundsError) on validate_against_bounds directly; the gate test exercises the raise path.

### E. Escalation: PASS

/root/src/repos/pumpgrok/src/pumpgrok/upgrade/escalate.py escalate_candidate writes one Escalation row kind upgrade_blocked plus one desk JournalNote, writes no active-set row, and refuses eligible verdicts:

if verdict.promotion_eligible or verdict.reason == REASON_PASS:
    raise ValueError("verdict is eligible: nothing to escalate")

Pinned by tests/upgrade/test_escalation.py test_eligible_verdict_escalates_nothing asserting pytest.raises(ValueError, match="nothing to escalate") with no Escalation, no note, and the set unchanged.

### F. BLIND advisory UPG-05: PASS

- Only SAFE-4 top10_concentration and SAFE-8 deployer_history are advisory: /root/src/repos/pumpgrok/src/pumpgrok/tools/safety/checks/__init__.py lines 57-60 HOLDER_ADVISORY_PAIR frozenset of exactly those two ids, comment dated amendment 2026-10-25.
- Only while no provider is recorded: /root/src/repos/pumpgrok/src/pumpgrok/tools/safety/score_report.py line 441 advisory_active = not paid_rpc_provider_recorded(), where paid_rpc_provider_recorded in /root/src/repos/pumpgrok/src/pumpgrok/tools/safety/provider.py reads env PUMPGROK_PAID_RPC_PROVIDER by that exact name, empty or unset meaning none recorded.
- Every other required blind still forces KILL: blind_required at score_report.py lines 443-449 excludes only the pair while advisory_active; verdict KILLs on any remaining blind_required entry.
- Verdict rows keep status blind with reasons and list the pair in advisory_blind_checks. Matches amendment section wording: advisory while no paid RPC provider recorded, reason written into the verdict, not by itself a KILL, exception ends when a provider is recorded.

### G. Amendment completeness UPG-06: PASS with one out-of-scope stale paraphrase noted

Verified present, byte-checked against /root/src/repos/pumpgrok/.planning/AMENDMENT-2026-10-25.md:

- /root/src/repos/pumpgrok/rules/pumpgrok-team.mdc: description ten-seat line 2, line 8 ten-role sentence with SIGNAL and JOURNAL, SIGNAL and JOURNAL bullets lines 18-19, clause 2 append Simulated paper fills are not sends, clause 8 full replacement No live strategies and no return claims ending No output claims an expected return.
- /root/src/repos/pumpgrok/skills/desk-operating-model/SKILL.md: line 24 live-spend plus autonomy wording, line 31 SAFE-4 and SAFE-8 exception, line 32 ten-role sentence.
- /root/src/repos/pumpgrok/prompts/_shared/core-directives.xml: clause 10 advisory exception in the shared section line 22 and in the risk section line 34.
- All ten /root/src/repos/pumpgrok/agents/*.md carry the clause 10 exception; grep for holder-concentration (SAFE-4) matches all 10 seat files; all regenerated, none hand-edited.
- /root/src/repos/pumpgrok/agents/risk.md clause 3 line 37 carries the amended variant with recorded in the ledger; the other nine seats keep the shared clause 3 every spend until the human writes a higher autonomy level in the journal, confirmed unchanged in all nine files.
- /root/src/repos/pumpgrok/docs/RISK_POLICY.md: row 8 quotes amended clause 8 verbatim, section 2.4 heading and advisory paragraph present lines 94-98.
- /root/src/repos/pumpgrok/.planning/PROJECT.md: BLIND constraint line 135 and strategy row line 78 carry the amended wording.
- No nine-seat or nine-role leftovers anywhere in the carriers.

Stale paraphrase outside amendment scope, not a FAIL: /root/src/repos/pumpgrok/docs/RISK_POLICY.md line 25 still paraphrases clause 10 as output BLIND - cannot proceed and stop with BLIND treated as KILL, without naming the advisory exception. It defers to section 2.4, which now carries the exception, and it was not in the amendment section 4 list, so the carriers match the amendment exactly. Flagged for a future docs pass, not a gap.

### H. Frozen oracle: PASS

/root/src/repos/pumpgrok/tests/safety/amendment_2026_10_25_frozen.txt pins every amended clause; key phrases verified present in both the amendment and the frozen file: Simulated paper fills are not sends, No live strategies and no return claims, holder-concentration (SAFE-4), BLIND is KILL except advisory holder checks heading, BLIND is treated as KILL except for SAFE-4 and SAFE-8, New alpha and new signal families. Constitutional bytes confirmed in the frozen file: U+2013 en-dash present, U+201C and U+201D quotes present. /root/src/repos/pumpgrok/tests/safety/test_constitution_amendment.py loads the frozen file and checks it with 12 tests including frozen coverage, every seat clause 10, clause 8 identity across rules and risk policy, project rows, risk clause 3, and other seats unchanged.

### I. Guard integrity: PASS

Diff of /root/src/repos/pumpgrok/tests/safety/test_no_backtest_to_live_path.py against c0c0dcf shows exactly four hunks: UPGRADE_DIR constant added, upgrade files joined into the scanned file list, docstring updated from absent to present upgrade path, and the assert not (SRC / upgrade).exists() line replaced with assert UPGRADE_DIR.is_dir(). The AST live-import scan over backtest, paper, and now upgrade is unweakened, the signing-symbol guard in /root/src/repos/pumpgrok/tests/safety/test_no_signing_outside_live_stub.py is untouched and covers all of SRC, and test_run_mode_live_once_exits_3 asserting main run --mode live exit 3 is unchanged.

### J. Manual-ticket guard: PASS

/root/src/repos/pumpgrok/tests/safety/test_manual_ticket_no_upgrade.py asserts after a manual-ticket paper cycle: read_autonomy == manual-ticket, no autonomy ConfigChanged rows, read_active_set is None, no active-set ConfigChanged rows, and not (tmp_path / var / upgrade).exists(). Manual-ticket promotion is impossible: no autonomy row, no active-set record, no upgrade directory.

### K. CHANGELOG and hashes: PASS

/root/src/repos/pumpgrok/CHANGELOG.md lines 18-19: Phase 9 before and after both b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d, matching the smoke-10m hash on both orchestrator runs, equal as the roadmap allows. No placeholders remain; no angle-bracket tokens. Added bullets match the code: UPG-01 bounds plus typed rejection, UPG-02 five-check gate order, UPG-03 ConfigChanged plus promotions directory plus one-operation restore, UPG-04 Escalation channel with no active-set row, UPG-05 advisory with PUMPGROK_PAID_RPC_PROVIDER restoring KILL, UPG-06 amendment with frozen oracle and risk-only clause 3. No bullet claims anything the code does not do.

### L. Criterion mapping: all PASS

See criteria table: 10 of 10 PASS, each with the command, existence, and verdict.

### M. Open items judged

M1. tests/tools/safety/test_score_report.py change: PASS, intent preserved. test_blind_never_raises_and_forces_kill now pins the provider env to test-provider, which selects the recorded-provider branch where top10_concentration blind forces KILL; the new test_blind_holder_pair_is_advisory_without_provider deletes the env and asserts blind stays blind, appears in blind_checks, and the verdict is CLEAR. Both branches of the amended contract are pinned; the old unconditional-KILL expectation is kept exactly where the amendment says KILL still applies.

M2. Risk-only clause 3 via security-constitution-risk section audience risk in prompts/_shared/core-directives.xml, referenced by prompts/bot-02-risk.xml: PASS, matches the amendment. The amendment asks for agents/risk.md constitution variant wording and generator-produced agent files; the end state is byte-exact amended clause 3 in agents/risk.md line 37 only, the other nine seats byte-identical to the shared section, and the mechanism is the repository own generator pattern rather than hand-editing. The 12-test oracle pins both the risk wording and the nine-seat invariance.

## Not verified

Nothing outstanding. Per-file test counts were not re-derived from the dot-only /tmp/g9_test.log; whole-suite exit 0 at HEAD 41df27c is the evidence, and reruns were forbidden by the brief.

## Re-verification at HEAD da6c071

Re-checked every Phase 9 success criterion at HEAD da6c071 by reading code, tests, docs and the gate logs from the last full gate chain run at HEAD 7a0b6eb (/tmp/h_lint.log, /tmp/h_type.log, /tmp/h_test.log, /tmp/h_check.log, /tmp/h_vdc.log, /tmp/h_smoke.log, /tmp/h_live.log). No gate rerun. Commits 7a0b6eb..da6c071 touch docs and planning records only; git log over src/pumpgrok/upgrade, tests/upgrade, tests/safety/test_blind_advisory.py, tests/safety/test_constitution_amendment.py, src/pumpgrok/config/upgrade_bounds.toml, src/pumpgrok/tools/safety, rules/pumpgrok-team.mdc, agents/risk.md, docs/RISK_POLICY.md, .planning/PROJECT.md and CHANGELOG.md is empty in that range, so the gate evidence still covers the Phase 9 code. Smoke-10m events.hash b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d on both runs, equal as the roadmap allows.

| # | Criterion | PASS or FAIL | Evidence |
|---|-----------|--------------|----------|
| 1 | lint, typecheck, test, check.sh green, paper smoke one cycle | PASS | /tmp/h_lint.log ruff check plus format check exit 0; /tmp/h_type.log mypy 204 source files exit 0; /tmp/h_test.log full pytest suite exit 0; /tmp/h_check.log 35 skills 10 agents 309 markdown files exit 0; /tmp/h_vdc.log PASS paper once exit 0 and PASS doctor exit 0 |
| 2 | param-set hash plus active-set ledger tests green, bounds TOML parses | PASS | tests/upgrade/test_param_set_hash.py and tests/upgrade/test_active_set_ledger.py present; src/pumpgrok/config/upgrade_bounds.toml present with filter and exits range tables; full suite exit 0 in /tmp/h_test.log |
| 3 | promotion gate blocks five cases | PASS | tests/upgrade/test_promotion_gate.py present with 10 tests: pass, out-of-bounds, above-20-trials, below-autonomy, failed holdout, negative holdout, divergence breach, first-failure order, winner binding, empty run id; full suite exit 0 |
| 4 | promotion evidence record | PASS | tests/upgrade/test_promotion_evidence.py present with 7 tests; src/pumpgrok/upgrade/evidence.py writes var/upgrade/promotions/HASH.json plus desk JournalNote; full suite exit 0 |
| 5 | exact rollback round trip | PASS | tests/upgrade/test_rollback_exact.py test_promote_then_rollback_round_trip asserts restored hash equals prior hash and ledger order SET_A SET_B SET_A; full suite exit 0 |
| 6 | escalation, no promotion | PASS | tests/upgrade/test_escalation.py present with 3 tests: out-of-bounds escalates, over-trial-count escalates, eligible verdict escalates nothing and raises; src/pumpgrok/upgrade/escalate.py writes Escalation row plus JournalNote and no active-set row; full suite exit 0 |
| 7 | SAFE-4 and SAFE-8 BLIND advisory, rest KILL, revert on provider | PASS | tests/safety/test_blind_advisory.py present with 6 tests: provider signal, holder advisory without provider, deployer advisory without provider, required blind still KILL, holder revert to KILL with provider, deployer revert to KILL with provider; src/pumpgrok/tools/safety/provider.py reads PUMPGROK_PAID_RPC_PROVIDER with empty or unset meaning none recorded; full suite exit 0 |
| 8 | generate-templates check plus amendment oracle test | PASS | Makefile check target runs scripts/generate-templates.py --check; tests/safety/test_constitution_amendment.py present with 12 tests covering rules clauses 2 and 8, ten-role correction, agents/risk.md clause 10, docs/RISK_POLICY.md row 8 and section 2.4, .planning/PROJECT.md BLIND constraint, frozen oracle plus risk-only clause 3; /tmp/h_check.log exit 0; full suite exit 0 |
| 9 | replay before and after hashes recorded | PASS | CHANGELOG.md Phase 9 before line and after line both carry b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d, equal as allowed; /tmp/h_smoke.log shows the paper replay cycle completing with filled trades |
| 10 | live refused with upgrade modules present | PASS | /tmp/h_live.log refuses mode live with 9 of 9 preconditions unmet and no transaction attempted, exit 3 per gate record; tests/upgrade/test_no_live_imports.py proves no import path from upgrade to a live adapter; full suite exit 0 |

Verdicts changed from the body: none. The body verdict passed at 10 of 10 criteria is confirmed at HEAD da6c071, score 10/10.

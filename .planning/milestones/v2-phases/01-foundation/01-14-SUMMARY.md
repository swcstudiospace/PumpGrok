---
phase: 01-foundation
plan: 14
subsystem: infra
tags: [r61-review, secrets-gate, allowlist, gap-closure]
dependency_graph:
  requires: ["01-06-SUMMARY.md key-files plus 01-06 commit trail"]
  provides: ["R61 keep/revert decision record for 01-06 out-of-scope edits"]
  affects: []
tech_stack:
  added: []
  patterns: ["R61 review: keep is the default; revert only with a stated defect"]
key_files:
  created:
    - .planning/phases/01-foundation/01-14-SUMMARY.md
  modified: []
decisions:
  - "KEEP all five 01-06 out-of-scope files: pragma edits are correct, line-scoped, behavior-free"
  - "KEEP ci/security/* scanner configs by design (01-06 deviation 1): security-pr.yml references them"
  - "Seat names bot-05-rug/bot-06-exit/bot-07-shill are ROSTER-conformant, not a defect"
metrics:
  duration: not measured
  completed: 2026-10-21
status: complete
---

# Phase 1 Plan 14 Summary

**R61 keep-or-revert review of the five plan-01-06 out-of-scope files: all five kept, zero reverts, gates green**

## Task Commits

1. **Task 1: R61 keep-or-revert review** — no code commit (review-only; every decision is KEEP, so the five owned files are untouched by this plan). Verification evidence below.

## Per-File R61 Decisions

Out-of-scope set reconstructed from 01-06-SUMMARY.md key-files/deviations and the commit trail (`a3ce98f`, `fc92ece`, `1419b03`, `31acf45`, `42cb7cf`): commit `1419b03` added one `# pragma: allowlist secret` trailing comment per hit in exactly these five files; no other 01-06 commit touched them.

| File | Decision | Reason |
|------|----------|--------|
| AGENTS.md:270 | KEEP | Trailing `<!-- pragma: allowlist secret: JSON-RPC method names, not credentials -->` on the PumpPortal observation line. The flagged tokens are public method names (`subscribeNewToken`, `subscribeTokenTrade`), not credentials; pragma is the gate's own prescribed false-positive mechanism (`check_secrets.py:309`: "If it is a false positive, add '# pragma: allowlist secret' with a reason"). Comment-only, no behavior change. |
| .planning/research/STACK.md:210 | KEEP | Same observation line, same pragma, same reason as AGENTS.md. Comment-only, no behavior change. |
| docs/DISCOVERY.md:414 | KEEP | Trailing pragma on the config-placeholder table row (`YOUR-BASE58-PRIVATE-KEY`, `${GROKBOT_WALLET_PRIVATE_KEY:-}` placeholder labels quoted from vendor example files). Labels, not credentials; gate-prescribed mechanism; comment-only. |
| tests/config/test_forbidden_keys.py:26,27,33 | KEEP | Three line-scoped pragmas: two forbidden env-name fixtures (`PUMPGROK_SOLANA__SECRET_KEY`, `PUMPGROK_KEYPAIR_PATH` — names under test, flagged only because G-3 treats `keypair` as a secret name) and one planted no-echo value (`PLANTED-SECRET-9f3k7z-no-echo`). Suppressing them is correct: the test's purpose is to assert refusal, so the values must be present. Python end-of-line comments, no behavior change. |
| tests/replay/test_fixtures.py:88,92,93 | KEEP | Three line-scoped pragmas on the planted `SECRET-VALUE-DO-NOT-ECHO` value and the two assertions that it is redacted. The value must literally appear to prove non-echo; pragma is the only correct disposition. Comments only, no behavior change. |

**Suppression-scope evidence (no over-broad suppression):** `scan_line` (`ci/gates/check_secrets.py:165-167`) returns `[]` only when `ALLOWLIST_MARKER` is in that same line — strictly per-line, never file-wide. Every pragma above sits on the exact flagged line. No stated defect exists for any revert; per R61, keeps are the default.

**Recorded but not edited (outside this plan's files_modified, no change made):**

- `ci/security/{gitleaks.toml,semgrep.yml,bandit.ini,bandit_json_to_sarif.py}` — KEEP by design (01-06 deviation 1): `security-pr.yml` references these paths, so creating them was required for the workflow to function. Follow-up `42cb7cf` renamed the `solana-base58-secret-key` rule id to `solana-base58-key` without changing the regex. No defect, no edit.
- Seat names `bot-05-rug` / `bot-06-exit` / `bot-07-shill` — ROSTER-conformant (`docs/ROSTER.md:41-43`, `ownership.yaml:31-39`), matching the rest of the repo. The plan-01-06 file list's `bot-05-exit` / `bot-06-shill` / `bot-07-social` names were the error, not the implementation. No defect, no edit.

## Verification

- `uv run pytest tests/config/test_forbidden_keys.py tests/config/test_secret_refusal.py tests/config/test_settings.py tests/replay/test_clock.py tests/replay/test_fixtures.py -v` → **50 passed, exit 0**. (Note: the `-q` directory-arg form prints the known environment-quirk line "Pytest: No tests collected"; explicit file paths with `-v` report the authoritative count. Bare `python3 -m pytest` fails with `ModuleNotFoundError` — `uv run` is the canonical invocation per Makefile.)
- `python3 ci/gates/check_ownership.py --validate-manifest` → exit 0 (`G-1 manifest OK — 10 bots, 171 rules; 340 tracked path(s), each with one declared owner`).
- `python3 ci/gates/check_secrets.py --base origin/main` → exit 0 (`G-3 PASS — 237 file(s) scanned, no secrets detected`), proving the kept pragmas cover exactly the false positives with nothing real hidden.
- `git status --porcelain` shows no edits in the five owned files (only pre-existing user changes to `.planning/phases/01-foundation/01-CONTEXT.md`, `01-REVIEW.iter2.md`, `.planning/state.json`, which this plan did not stage or touch).

## Deviations from Plan

None — plan executed exactly as written. No reverts were needed; the review is the deliverable.

## Issues Encountered

None. No stubs, no auth gates, no blockers.

## Next Phase Readiness

R61 satisfied: every 01-06 out-of-scope edit is accounted for with a recorded decision, and no correct edit was lost. No follow-up plans depend on this beyond the decision record itself.

## Self-Check: PASSED

- SUMMARY file exists at `.planning/phases/01-foundation/01-14-SUMMARY.md`: FOUND (this file).
- No code commits required (all KEEP, zero file edits) — nothing to hash-verify.
- Verify commands above all exit 0; outputs quoted verbatim.

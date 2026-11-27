# Acceptance criteria - PumpGrok outstanding milestones (T1482-req)

Machine-checkable criteria for v4 Phases 11-14, Phase 17, sweeps B00-B09 and L1-P1.
Each line holds exactly one criterion. Each criterion names its story, its
check and its automated flag. A criterion passes only when its check returns
the stated number or code.

AC-001 story: US-001 Given 12 work units in phase 11 When the phase closure check runs Then 12 of 12 units report completion evidence with exit 0 check: receipt-audit; automated: true
AC-002 story: US-002 Given phase 11 closed and phase 12 open When the entry check runs Then 0 phase 12 units start before 12 of 12 phase 11 units show exit 0 check: phase-order; automated: true
AC-003 story: US-003 Given 8 quality claims in phase 13 When the auditor reruns the transcripts Then 8 of 8 commands return exit 0 with matching output check: transcript-replay; automated: true
AC-004 story: US-004 Given phase 14 closed When the docs check runs Then 1 changelog entry exists naming 0 open defects check: changelog-scan; automated: true
AC-005 story: US-005 Given 4 phase 17 deliveries open When the ledger check runs Then each of 4 deliveries names 1 owner and 0 deliveries remain unassigned check: delivery-ledger; automated: true
AC-006 story: US-006 Given the full package source tree When the strict type checker runs Then 0 errors and 0 suppression comments appear in src check: mypy-strict; automated: true
AC-007 story: US-007 Given 5 gate runs on the sweep commit When the linter and formatter checks run Then 0 violations and 0 format diffs appear in all 5 runs check: ruff-check; automated: true
AC-008 story: US-008 Given every monetary field across core, ledger and execution When the money-type scan runs Then 0 float annotations appear on money fields and 100 percent of amounts are integer base units check: money-ast-scan; automated: true
AC-009 story: US-009 Given all timestamp call sites in src When the clock scan runs Then 0 wall-clock reads appear outside replay/clock.py check: clock-ast-scan; automated: true
AC-010 story: US-010 Given 37 registered tools When the contract validation probe sends 1 request with an unknown field Then 37 of 37 tools reject with a named error and exit code 1 check: contract-probe; automated: true
AC-011 story: US-011 Given 6 uncertain data states injected When an order is attempted Then 6 of 6 attempts receive a named refusal and 0 orders fill check: fail-closed-probe; automated: true
AC-012 story: US-012 Given the smoke-10m dataset and seed 7 When two replays run Then both event hashes equal sha256 b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d check: replay-hash; automated: true
AC-013 story: US-013 Given the full test collection with 0 skipped safety cases When pytest runs Then exit 0 with 0 failures in the root suite check: pytest-suite; automated: true
AC-014 story: US-014 Given the frozen lockfile export When the dependency audit runs Then 0 known vulnerabilities appear with strict mode enabled check: pip-audit-strict; automated: true
AC-015 story: US-015 Given 24 operator commands across the docs When each command is executed verbatim Then 24 of 24 return the documented exit code check: doc-command-run; automated: true
AC-016 story: US-016 Given 4 L1-P1 defects When the regression tests run Then 4 of 4 defects reproduce before the fix and pass after it with exit 0 check: regression-suite; automated: true
AC-017 story: US-017 Given the merge commit on main When the 4 canonical targets run Then lint, typecheck, test and audit each return exit 0 check: make-check; automated: true
AC-018 story: US-018 Given the smoke fixture with 10 seats When the replay runs offline Then exit 0 with 1 full cycle and an identical hash on rerun check: replay-smoke; automated: true
AC-019 story: US-019 Given the live-mode invocation with 9 preconditions When the run command executes Then exit code 3 appears and 9 unmet lines are printed check: live-refusal; automated: true
AC-020 story: US-020 Given 15 gateway test files When the gateway project runner executes Then exit 0 with 0 failures across all 15 files check: gateway-pytest; automated: true
AC-021 story: US-021 Given 66 open pull requests When CI evaluates each one Then each merge candidate shows 100 percent of required jobs green before merge check: ci-status; automated: true
AC-022 story: US-022 Given the shipped configuration When the adapter registry loads Then 0 live adapters register and 0 key-material symbols resolve outside the live stub check: adapter-scan; automated: true
AC-023 story: US-023 Given 16 milestone groups When the tracker export runs Then 16 parent issues exist with 1 numbered sub-issue per work unit and 0 units lack a sub-issue check: tracker-audit; automated: true
AC-024 story: US-024 Given a pull request with red CI When a merge is attempted Then the merge is refused with a named reason and main stays at the prior commit check: merge-guard; automated: true
AC-025 story: US-025 Given 1 completed unit When the receipt gate runs Then 1 receipt exists naming every command with its exit code and 0 claims lack a command check: receipt-gate; automated: true
AC-026 story: US-026 Given 5 new documents When the instruction-file lint runs Then exit 0 with 0 non-ASCII bytes in all 5 documents check: check-sh; automated: true
AC-027 story: US-017 Given the same merge commit When the full make check target runs Then exit 0 including prompt-assembly, template and schema drift checks check: make-check-full; automated: true
AC-028 story: US-018 Given 1 calibrating fixture dataset When the verify verb runs twice Then both hashes match and 0 bytes differ in the JSONL output check: verify-twice; automated: true
AC-029 story: US-021 Given 1 pull request with 3 required jobs When 1 job fails Then the merge gate reports fail with the failing job named check: ci-fail-signal; automated: true
AC-030 story: US-022 Given 1 audit run over committed files When the secret scanner executes Then 0 secret shapes appear and 0 signed transactions register check: secret-scan; automated: true

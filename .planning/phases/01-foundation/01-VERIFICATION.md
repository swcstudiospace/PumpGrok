---
phase: 01-foundation
verified: 2026-10-21T06:15:00Z
status: gaps_found
score: 8/12 must-haves verified
covered_files:
  - ".planning/phases/01-foundation/01-01-PLAN.md"
  - ".planning/phases/01-foundation/01-01-SUMMARY.md"
  - ".planning/phases/01-foundation/01-02-PLAN.md"
  - ".planning/phases/01-foundation/01-02-SUMMARY.md"
  - ".planning/phases/01-foundation/01-03-PLAN.md"
  - ".planning/phases/01-foundation/01-03-SUMMARY.md"
  - ".planning/phases/01-foundation/01-04-PLAN.md"
  - ".planning/phases/01-foundation/01-04-SUMMARY.md"
  - ".planning/phases/01-foundation/01-05-PLAN.md"
  - ".planning/phases/01-foundation/01-05-SUMMARY.md"
  - ".planning/phases/01-foundation/01-06-PLAN.md"
  - ".planning/phases/01-foundation/01-06-SUMMARY.md"
  - ".planning/phases/01-foundation/01-07-PLAN.md"
  - ".planning/phases/01-foundation/01-07-SUMMARY.md"
  - ".planning/phases/01-foundation/01-08-PLAN.md"
  - ".planning/phases/01-foundation/01-08-SUMMARY.md"
  - ".planning/phases/01-foundation/01-09-PLAN.md"
  - ".planning/phases/01-foundation/01-09-SUMMARY.md"
covered_digest: "v3:sha256:bb9a7992182442c4f8ab5d122164a24084b7a719dba8a071c5ab8b9c40dd1ac8"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 8/12
  gaps_closed:
    - "Container build/run, check.sh rewrite, vendor pin, pyc removal (01-09 executed; SC4 now fully observed green)"
    - "G-7 desk integrity now exits 0 (observed, not claimed)"
    - "F841 in tests/core/test_registry.py fixed (commit 67a6640; no F841 remains)"
  gaps_remaining:
    - "ruff check 171 errors + ruff format 15 files (unchanged count since prior pass)"
    - "mypy --strict 4 errors (unchanged)"
    - "3 event schemas drifted (unchanged set)"
    - "WR-08 ledger half still open (ApprovalRecorded lacks token_units)"
  regressions: []
gaps:
  - truth: "`make lint` is green on a clean checkout (SC1)"
    status: failed
    reason: "ruff check reports 171 errors; ruff format --check flags 15 files"
    artifacts:
      - path: "tools/ (legacy)"
        issue: "122 of 171 ruff errors live in legacy tools/ (Phase 2 removes this tree)"
      - path: "src/ (4), tests/ (21), ci/ (24)"
        issue: "49 non-legacy ruff errors incl. tests/core/test_registry.py B017/SIM117"
      - path: "15 files flagged by ruff format --check"
        issue: "includes tests/test_tools_cli.py, ci/gates/check_receipt.py, 6 tools/*.py, docs + planning .md code blocks"
    missing:
      - "Clear the 49 non-legacy ruff errors, decide tools/ lint scope (exclude in ruff config or fix; Phase 2 removes tools/), and run ruff format on the 15 drifted files"
  - truth: "mypy --strict src/ is green (SC1)"
    status: failed
    reason: "mypy reports 4 errors in 3 files (config already sets strict = true, so `mypy src/` is equally red)"
    artifacts:
      - path: "src/pumpgrok/ledger/events.py:341,349"
        issue: "Missing type arguments for generic type dict [type-arg] x2"
      - path: "src/pumpgrok/core/registry.py:27, src/pumpgrok/core/__init__.py:30"
        issue: "Module pumpgrok.core.ids does not explicitly export attribute Clock [attr-defined] x2"
    missing:
      - "Parameterize the 2 dict generics; explicitly export Clock from core.ids (or import from its defining module)"
  - truth: "Event schemas are byte-stable with the generator (FOUND-008)"
    status: failed
    reason: "scripts/generate-event-schemas.py --check exits 1: 3 drifted schemas, all missing the PriceDecimal pattern on string fields"
    artifacts:
      - path: "contracts/events/fill_recorded.schema.json"
        issue: "drift: 3 hunks add decimal pattern"
      - path: "contracts/events/position_opened.schema.json"
        issue: "drift: 2 hunks add decimal pattern"
      - path: "contracts/events/position_closed.schema.json"
        issue: "drift: 2 hunks add decimal pattern"
    missing:
      - "Regenerate contracts/events/*.schema.json in the locked env (uv run python scripts/generate-event-schemas.py)"
  - truth: "Sell approvals bind token units end-to-end (WR-08)"
    status: partial
    reason: "Domain half closed (commit 3df5aae): ApprovalRecord.token_units required for human_sell/exit_rule, matches() checks kind/side/quantity. Ledger half open: ApprovalRecorded in src/pumpgrok/ledger/events.py has size_lamports but no token_units; contracts/events/approval_recorded.schema.json likewise lacks it."
    artifacts:
      - path: "src/pumpgrok/ledger/events.py (class ApprovalRecorded)"
        issue: "no token_units field; a persisted sell approval would silently drop the quantity binding"
      - path: "contracts/events/approval_recorded.schema.json"
        issue: "has size_lamports, no token_units"
    missing:
      - "Add token_units to ApprovalRecorded (+ schema regen, same task as schema drift); no runtime writer of ApprovalRecorded rows exists in Phase 1 so nothing breaks today"
---

# Phase 01: Foundation Verification Report (post wave 4, all 9 plans)

**Phase Goal:** A clean checkout installs from the lockfile, passes the canonical gates, loads layered settings, and runs one skip-only replay cycle that writes a hash-chained ledger with no network access.
**Verified:** 2026-10-21T06:15:00Z
**Status:** gaps_found
**Re-verification:** Yes — after gap closure round (all plans 01-01..01-09 executed). Prior report (commit 8e6c84d, ASCII rewrite a42cfe7) superseded and overwritten.

Method: every behavioral claim below is observed command output captured to files (/tmp/*.txt) in this pass — pytest output piped through head/tail is summarized unreliably by the runner, so all test results were re-captured via file redirect. No product/test/PLAN/SUMMARY files edited; no formatters run.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Clean checkout installs from the lockfile | [PASS] VERIFIED | `uv sync --frozen` exit 0 ("Checked 53 packages"); uv.lock + .python-version + Makefile + pyproject.toml all tracked |
| 2 | Full canonical suite green incl. static guards and F841 fix | [PASS] VERIFIED | `python -m pytest -q` exit 0; 301 collected (19 files incl. ci/tests 159, static guards 21, live gate 5, skip cycle 8); all dots, no F/E |
| 3 | `make lint` green (ruff check + format) | [FAIL] FAILED | ruff check: 171 errors (src 4 / tests 21 / ci 24 / tools 122 legacy); ruff format --check: 15 files would reformat |
| 4 | mypy --strict src/ green | [FAIL] FAILED | 4 errors in 3 files: events.py:341,349 dict type-arg; registry.py:27 + core/__init__.py:30 Clock export |
| 5 | Skip-only replay cycle writes JournalNote=1 (SC2) | [PASS] VERIFIED | `pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exit 0 (events_read 4, ledger_seq 1); sqlite count query prints `1` |
| 6 | G-1, G-7, secrets gate, ci gate tests green (SC3) | [PASS] VERIFIED | check_ownership --validate-manifest exit 0 (10 bots, 171 rules, 332 paths); check_desk_integrity --repo . exit 0 (G-7 PASS, 10 rosters); check_secrets --base origin/main exit 0 (227 files); ci/tests green inside the 301 |
| 7 | Compose config/build/run + check.sh green (SC4) | [PASS] VERIFIED | `docker compose config --quiet` exit 0; `docker compose build pumpgrok` exit 0; `docker compose run --rm pumpgrok` exit 0 (same deterministic correlation_id 01KDVDNA009GZ05Q914M5Q55G1 as host run); ./scripts/check.sh exit 0 |
| 8 | Banned-call statics, no Jito/wallet key, no root config/ (SC5) | [PASS] VERIFIED | time/asyncio.sleep/timeout only in replay/clock.py (the allowed module, guard test passes); no `import uuid` in src; no JitoConfig/wallet_private_key in src; `test ! -d config` passes |
| 9 | Event schemas byte-stable (FOUND-008) | [FAIL] FAILED | generate-event-schemas.py --check exit 1: 3 drifted (fill_recorded, position_opened, position_closed — PriceDecimal pattern) |
| 10 | WR-08 sell approvals bind token_units end-to-end | [FAIL] PARTIAL | Domain closed (commit 3df5aae + re-confirmed: token_units required for human_sell/exit_rule, matches() checks quantity); ledger ApprovalRecorded + schema lack token_units |
| 11 | Live refusal fails fast; doctor honest | [PASS] VERIFIED | `pumpgrok run --mode live --once` exit 3 with 9 unmet preconditions listed, no transaction; `pumpgrok doctor` exit 0 (6 present, 5 Phase-2+ packages warned not-yet-implemented) |
| 12 | 01-09 container/docs/hygiene artifacts landed | [PASS] VERIFIED | 18 event schemas + 11 rosters (_core + 10 seats); AGENTS/SECURITY/CHANGELOG + 3 desk docs + VENDOR_PIN present; all 3 overlays live.enabled=false; 3 workflows + 10 .receipts seats + pre-commit hook present; no tracked *.pyc/tissue.json |

**Score:** 8/12 truths verified (0 present-but-unverified).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| pyproject.toml / uv.lock / .python-version / Makefile | installable package, canonical targets | [PASS] | uv sync --frozen exit 0; lint/typecheck/test/audit targets present |
| src/pumpgrok/{config,core,ledger,replay,logging,execution,cli,doctor} | Phase-1 substrates | [PASS] | doctor lists 6 present; no stub modules in tree |
| src/pumpgrok/core/{interfaces,registry,ids,approvals}.py | R31 contracts | [PASS] | 6 registry tests pass; LiveGateError on LIVE_WRITE |
| contracts/events/*.schema.json (18) | R32 event schemas | [FAIL] | 3 drifted (see gap) |
| contracts/tool-rosters (11) + prompts/assemble | R35/R19 | [PASS] | G-7 PASS; check.sh assembles |
| Dockerfile / compose / .dockerignore | R50 one-shot image | [PASS] | non-root build + run observed exit 0 |
| ownership.yaml + ci/gates/* + workflows + receipts | G-1..G-7, SEC-001 | [PASS] | G-1/G-7/secrets observed exit 0 |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| run verb | replay fixtures -> ledger sqlite | skip-only cycle, ledger_seq 1, JournalNote row | [PASS] WIRED |
| settings loader | LiveGate -> run/doctor | paper default; live mode refused exit 3 | [PASS] WIRED |
| doctor | compose HEALTHCHECK | Dockerfile exec-form doctor; container run healthy path | [PASS] WIRED |
| ApprovalRecord | ApprovalRecorded ledger event | quantity binding | [FAIL] DISCONNECTED (token_units missing on ledger side) |
| ledger/events.py | contracts/events/*.schema.json | generator --check | [FAIL] 3 drifted |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| var/replay/smoke/ledger.sqlite | JournalNote row | skip-only cycle write | Yes (count=1 observed) | [PASS] FLOWING |
| cycle_end log line | events_read/ledger_seq/correlation_id | replay run | Yes (4/1/deterministic ID in host AND container runs) | [PASS] FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| suite green | python -m pytest -q (file capture) | exit 0, 301 tests, all pass | [PASS] |
| replay cycle | pumpgrok run --mode paper --once --replay .../smoke | exit 0, ledger_seq 1 | [PASS] |
| journal write | sqlite count JournalNote/replay | `1` | [PASS] |
| live refusal | pumpgrok run --mode live --once | exit 3, 9 preconditions | [PASS] |
| doctor | pumpgrok doctor | exit 0 | [PASS] |
| container cycle | docker compose run --rm pumpgrok | exit 0, same correlation ID | [PASS] |
| gates | check_ownership / check_desk_integrity / check_secrets / check.sh / compose config / compose build | all exit 0 | [PASS] |

### Probe Execution

No phase-declared probe scripts (`scripts/*/tests/probe-*.sh` absent; grep finds no probe references in PLAN/SUMMARY files). Behavioral spot-checks above serve as the executable proof. No MISSING_PROBE — probes were never part of this phase's contract.

### Requirements Coverage (all 19 Phase-1 IDs accounted for)

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|----------|
| FOUND-001 | 01-01 | SATISFIED | uv sync --frozen exit 0; lockfile + toolchain tracked |
| FOUND-002 | 01-01 | BLOCKED (lint/typecheck) | test/audit halves green (301 pass; audit per 01-09 proof); lint + typecheck red |
| FOUND-003 | 01-09 | SATISFIED | config/build/run all exit 0 observed; one-shot, doctor healthcheck |
| FOUND-004 | 01-02 | SATISFIED | settings tests pass (11); paper default; refusal paths tested |
| FOUND-005 | 01-03 | SATISFIED | core contract tests pass (ids/models/registry 19) |
| FOUND-006 | 01-06 | SATISFIED | G-1 exit 0, 332 paths owned |
| FOUND-007 | 01-06 | SATISFIED | ci/tests 159 pass inside the 301 |
| FOUND-008 | 01-07 | BLOCKED (schema drift) | 18 schemas exist; 3 drifted |
| FOUND-009 | 01-07 | SATISFIED | rosters + prompt pipeline; G-7 + check.sh green |
| FOUND-010 | 01-06 | SATISFIED | 3 workflows, 10 receipt seats, pre-commit hook present |
| FOUND-011 | 01-09 | SATISFIED | AGENTS/SECURITY/CHANGELOG + 3 desk docs present |
| FOUND-012 | 01-05 | SATISFIED | clock/rng/fixture + static-guard tests pass; network block enforced |
| FOUND-013 | 01-04 + 01-08 | SATISFIED | ledger hash chain tests pass; skip cycle + JournalNote=1 observed |
| STRUCT-001 | 01-09 | SATISFIED | no tracked pyc/tissue; VENDOR_PIN records 409e74c; check.sh rewritten |
| STRUCT-008 | 01-02 | SATISFIED | no JitoConfig/wallet_private_key in src; no root config/ |
| OBS-001 | 01-08 | SATISFIED | one-line JSON logs with correlation_id observed in both runs |
| OBS-002 | 01-08 | SATISFIED | redaction + contextvars tests pass (4 logging + 2 correlation) |
| SEC-001 | 01-06 | SATISFIED | secrets gate exit 0 (227 files); security-pr workflow present |
| SEC-002 | 01-02 | SATISFIED | all overlays live.enabled=false; live run refused exit 3 |

No orphaned IDs: every Phase-1 REQUIREMENTS.md ID is claimed by exactly one plan's frontmatter (01-04 SUMMARY lacks a requirements-completed line but its PLAN claims FOUND-013, completed jointly with 01-08 — counted once).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| scripts/hermes-bootstrap.sh | 106 | "TBD" in "Default paper size: TBD" | Info | Pre-existing legacy script; refers to print paper size, not work debt |
| (none in src/tests/ci) | - | TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER | - | Clean |

Ruff's 171 findings are lint debt (tracked as gap T3), not stub patterns: no `return null/[]/{}` placeholders, no console.log-only handlers, no hardcoded-empty renders in src/.

### G-4 note (observation, not a gap)

`check_contracts.py --base origin/main` without `--change` exits 1 on this branch because the branch adds contract surfaces — that is the gate's designed behavior, and SC3 does not require branch-level G-4 green. Per-task invocations pass `--change` when touching contracts.

### Gaps Summary

Phase 1 is 8/12 with all runtime behavior observed working (install, suite, gates, replay cycle, ledger write, logging, live refusal, container). What blocks "done" is conformance-only, unchanged in kind since the prior pass: (1) lint red — 171 ruff errors (122 in legacy `tools/`, a Phase-2-removes scoping decision, plus 49 in src/tests/ci) and 15 files needing format; (2) mypy --strict 4 errors in 3 files; (3) 3 drifted event schemas (PriceDecimal pattern); (4) WR-08 ledger half — one missing `token_units` field, same regen task as (3). Items 3+4 are one task; items 1+2 are mechanical fixes plus the tools/ scope decision. 01-09 (the entire prior tail) is now closed and verified.

---
_Verified: 2026-10-21T06:15:00Z_
_Verifier: Claude (gsd-verifier)_

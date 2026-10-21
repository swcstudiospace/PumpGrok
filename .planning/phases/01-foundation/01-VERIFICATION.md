---
phase: 01-foundation
verified: 2026-10-21T06:00:00Z
status: gaps_found
score: 8/12 truths verified
covered_files:
  - ".planning/REQUIREMENTS.md"
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
covered_digest: "v3:sha256:444e2d482b8011fb7dabf8f6b2ab2b43c3c0e4c3c4ba485aabd8342827c2394f"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 1/19
  gaps_closed:
    - "Clean checkout installs from lockfile (01-01 executed, pyproject.toml/uv.lock/Makefile exist)"
    - "Network-blocked harness, replay clock/rng/fixtures, static guards (01-05 executed)"
    - "Ownership, ported G-1..G-7 gates, workflows, secrets gate (01-06 executed)"
    - "Contracts tree and prompt assembly pipeline (01-07 executed)"
    - "Skip-only replay cycle, doctor, logging, live gate (01-08 executed)"
  gaps_remaining:
    - "Container build/run, check.sh rewrite, vendor pin, pyc removal (01-09 not executed)"
  regressions: []
gaps:
  - truth: "`make lint typecheck` is green on a clean checkout (SC1)"
    status: failed
    reason: "ruff check reports 171 issues; ruff format --check would reformat 15 files; mypy --strict reports 4 errors"
    artifacts:
      - path: "pyproject.toml"
        issue: "ruff config does not exclude legacy tools/ (122 of 171 issues live there)"
      - path: "src/pumpgrok/ledger/events.py"
        issue: "mypy type-arg errors on 2 dict generics (lines 341, 349)"
      - path: "src/pumpgrok/core/registry.py"
        issue: "mypy attr-defined: Clock not explicitly exported from pumpgrok.core.ids"
    missing:
      - "Clear the 4 src/ ruff issues + 4 mypy errors, and decide tools/ lint scope (exclude in ruff config or fix; Phase 2 removes tools/)"
      - "Run ruff format on the 15 drifted files (no --fix per this pass; left for implementer)"
  - truth: "Event schemas are byte-stable with the generator (FOUND-008, 01-07 must-have)"
    status: failed
    reason: "scripts/generate-event-schemas.py --check exits 1: fill_recorded, position_opened, position_closed drift (PriceDecimal pattern missing from committed schemas)"
    artifacts:
      - path: "contracts/events/fill_recorded.schema.json"
        issue: "drift: 3 hunks add decimal pattern"
      - path: "contracts/events/position_opened.schema.json"
        issue: "drift: 2 hunks add decimal pattern"
      - path: "contracts/events/position_closed.schema.json"
        issue: "drift: pattern hunks (see /tmp/sch.txt)"
    missing:
      - "Regenerate contracts/events/*.schema.json with the canonical locked env (uv run python scripts/generate-event-schemas.py)"
  - truth: "Sell approvals bind token units end-to-end (WR-08)"
    status: partial
    reason: "Domain half closed (commit 3df5aae): ApprovalRecord.token_units required for human_sell/exit_rule, matches() checks kind+side+quantity. Ledger half OPEN: ApprovalRecorded event and its committed schema have no token_units field, so the documented persistence path would drop the sell binding"
    artifacts:
      - path: "src/pumpgrok/ledger/events.py"
        issue: "ApprovalRecorded has size_lamports but no token_units"
      - path: "contracts/events/approval_recorded.schema.json"
        issue: "no token_units property"
    missing:
      - "Add token_units to ApprovalRecorded event, regenerate schemas (closes schema-drift gap at the same time), or record an explicit deferral to Phase 4 with the loss documented"
  - truth: "Container builds and runs the one-shot replay; repo hygiene and desk docs land (01-09, FOUND-003/FOUND-011/STRUCT-001)"
    status: failed
    reason: "Plan 01-09 has not run: no SUMMARY, no Dockerfile/docker-compose.yml/.dockerignore, scripts/check.sh not rewritten, 6 tracked *.pyc remain, docs/VENDOR_PIN.md absent"
    artifacts:
      - path: "Dockerfile"
        issue: "MISSING"
      - path: "docker-compose.yml"
        issue: "MISSING"
      - path: "tests/__pycache__/test_tools_cli.cpython-312.pyc + 5 tools/__pycache__/*.pyc"
        issue: "tracked junk STRUCT-001 requires removed"
      - path: "docs/VENDOR_PIN.md"
        issue: "MISSING"
    missing:
      - "Execute plan 01-09 (container, docs, hygiene, phase-gate proof)"
---

# Phase 01: Foundation Verification Report

**Phase Goal:** A clean checkout installs from the lockfile, passes the canonical gates, loads layered settings, and runs one skip-only replay cycle that writes a hash-chained ledger with no network access.
**Verified:** 2026-10-21T06:00:00Z
**Status:** gaps_found
**Re-verification:** Yes — previous VERIFICATION.md (stale: claimed 01-01 halted, pyproject.toml missing) is superseded. All 8 executed plans re-verified fresh against the tree at 397dd34; 01-09 has no SUMMARY and is recorded as not run.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Locked install: `uv sync --frozen` green | ✓ VERIFIED | `uv sync --frozen --group dev` → "Checked 53 packages"; `uv lock --check` exit 0; pyproject/uv.lock/Makefile/`.python-version` exist |
| 2 | `make lint` green (ruff check + format --check) | ✗ FAILED | `ruff check .` → 171 issues (src 4, tests 21, ci 24, tools 122 legacy); `ruff format --check` → 15 files would reformat |
| 3 | `make typecheck` green (mypy --strict src/) | ✗ FAILED | 4 errors: events.py:341,349 `type-arg` on bare `dict`; registry.py:27 + core/__init__.py:30 `Clock` not explicitly exported from ids |
| 4 | `make test` green (`uv run pytest -q`) | ✓ VERIFIED | 301 passed, exit 0 (incl. 159 ci/tests). Note: bare `uv run pytest -q` prints dots; count confirmed via verbose run |
| 5 | `make audit` green (pip-audit over uv export) | ✓ VERIFIED | `pip-audit -r /tmp/pumpgrok-req.txt --strict` → "No known vulnerabilities found", exit 0 |
| 6 | Layered settings load, refuse forbidden/unknown/key-bearing inputs, default paper, no root config/ | ✓ VERIFIED | settings tests pass in suite; `test ! -d config` ✓; `grep -rn -e JitoConfig -e wallet_private_key src/pumpgrok` empty ✓ |
| 7 | Core contracts hold (registry I1–I5, LIVE_WRITE refusal, ULIDs, uuid ban) | ✓ VERIFIED | tests/core pass (incl. `test_uuid_is_banned_from_src_pumpgrok`); F841 fix confirmed (commit 67a6640 removed the dead `bot` binding; no F841 in current ruff output for that file) |
| 8 | Ownership + ported gates green (SC2) | ✓ VERIFIED | check_ownership --validate-manifest exit 0 (10 bots, 170 rules, 329 paths); check_desk_integrity --repo . exit 0 (G-7 PASS, 10 rosters); check_secrets --base origin/main exit 0 (222 files); ci/tests 159 passed |
| 9 | Contracts tree + prompt pipeline byte-stable | ✗ FAILED | Rosters/prompts --check pass; BUT generate-event-schemas.py --check exits 1 (3 drifted schemas). Committed inputs identical to generation commit (EVENTS_IDENTICAL/GEN_IDENTICAL) yet output differs → schemas were generated outside the locked env |
| 10 | Skip-only replay writes exactly one source=replay JournalNote; live refused exit 3 | ✓ VERIFIED | Observed: replay exit 0, `cycle_end` log with correlation_id; sqlite count = 1 ✓; `run --mode live --once` → LIVE_EXIT:3 with 8/9 unmet preconditions ✓ |
| 11 | JSON logs redacted + correlation chain (OBS-001/002) | ✓ VERIFIED | tests/test_logging.py + test_correlation.py pass; replay stdout shows `correlation_id`, `seat`, `mode`, redacted shape |
| 12 | 01-09 container/docs/hygiene complete (SC4) | ✗ FAILED | No Dockerfile/compose/.dockerignore; 6 tracked *.pyc; no docs/VENDOR_PIN.md; check.sh exits 0 but is the legacy script (still references vendor PUMPGROK.md per MIGRATION_MAP:166) |

**Score:** 8/12 truths verified (0 present-but-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| pyproject.toml / uv.lock / Makefile / .python-version | locked install | ✓ VERIFIED | present; sync + lock --check green |
| src/pumpgrok/config/{settings,overlays} | R30 loader, 3 overlays live.enabled=false | ✓ VERIFIED | tests pass; doctor `mode=paper` |
| src/pumpgrok/core/* | interfaces/registry/ids/approvals | ✓ VERIFIED | WR-08 domain half closed (see gaps) |
| src/pumpgrok/ledger/{store,events}.py | hash chain + 18 R32 models | ✓ VERIFIED | substantive + wired (replay writes sqlite; tamper/exit-4/5 tests pass) |
| src/pumpgrok/{replay,harness,logging,execution/cli/doctor} | offline tests, clock/rng, redacted logs, live gate | ✓ VERIFIED | replay exit 0 observed; doctor exit 0 (6 present, 5 not-yet-implemented warns — expected pre-Phase-2..4) |
| ownership.yaml + ci/gates/*.py + workflows + receipts + pre-commit | G-1..G-7, 3 workflows, 10 receipt dirs | ✓ VERIFIED | all exist; .receipts/bot-* x10, ci/gates.yml/security-pr.yml/ci.yml, .pre-commit-config.yaml |
| contracts/{events x18,tool-rosters x11} + prompts pipeline | G-7 green, --check stable | ⚠️ PARTIAL | tree exists, G-7 green, prompts --check green; 3 schemas drifted |
| Dockerfile / compose / VENDOR_PIN / docs | 01-09 | ✗ MISSING | plan not executed |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| Makefile test | pytest suite | `uv run pytest -q` | WIRED | 301 passed observed |
| settings effective mode | live gate / run verb | mode=paper default | WIRED | replay ran paper; live refused exit 3 observed |
| replay cycle | ledger sqlite | JournalNote source=replay | WIRED | count query returned 1 |
| events.py models | contracts/events/*.schema.json | generator --check | NOT_WIRED | --check exits 1, 3 files drifted |
| core ApprovalRecord | ledger ApprovalRecorded | documented persistence | PARTIAL | domain binds token_units; event cannot carry it |
| doctor | compose HEALTHCHECK | Dockerfile | NOT_WIRED | no Dockerfile (01-09) |
| ownership rules | G-1 self-test | git ls-files | WIRED | 329 paths, one owner each |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| replay run | events_read=4, ledger_seq=1 | tests/fixtures/replay/smoke manifest | ✓ FLOWING | observed cycle_end JSON |
| ledger sqlite | JournalNote row | skip-cycle writer | ✓ FLOWING | count = 1 queried |
| live refusal | 8 unmet preconditions | live_gate nine R21 ids | ✓ FLOWING | printed block observed, exit 3 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| replay cycle | `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` | exit 0, cycle_end | ✓ PASS |
| ledger row | sqlite count JournalNote/source=replay | `1` | ✓ PASS |
| live refusal | `uv run pumpgrok run --mode live --once` | exit 3, 8/9 unmet | ✓ PASS |
| doctor | `uv run pumpgrok doctor` | exit 0, 6 present / 5 warned absent | ✓ PASS |
| suite | `uv run pytest -q` | 301 passed | ✓ PASS |
| ci suite | `python3 -m pytest ci/tests/` | 159 passed | ✓ PASS |
| ownership | `check_ownership.py --validate-manifest` | exit 0 | ✓ PASS |
| desk integrity | `check_desk_integrity.py --repo .` | G-7 PASS exit 0 | ✓ PASS |
| secrets | `check_secrets.py --base origin/main` | exit 0, 222 files | ✓ PASS |
| audit | `pip-audit --strict` | no vulns, exit 0 | ✓ PASS |
| mypy | `uv run mypy src/` | 4 errors, exit 1 | ✗ FAIL |
| ruff check | `uv run ruff check .` | 171 issues (src 4 / tests 21 / ci 24 / tools 122) | ✗ FAIL |
| ruff format | `ruff format --check .` | 15 files reformat, exit 1 | ✗ FAIL |
| schemas | `generate-event-schemas.py --check` | exit 1, 3 drifted | ✗ FAIL |
| prompts/templates | `assemble-prompts.sh --check`, `generate-templates.py --check` | both exit 0 | ✓ PASS |
| check.sh | `./scripts/check.sh` | exit 0 | ✓ PASS (legacy script; rewrite pending) |

### Probe Execution

No phase-declared `probe-*.sh` files exist; conventional `scripts/*/tests/probe-*.sh` absent. Step skipped — behavioral spot-checks above substitute.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| FOUND-001 | 01-01 | uv_build package, lockfile, sync --frozen | ✓ SATISFIED | sync + lock --check green |
| FOUND-002 | 01-01 | make lint typecheck test audit exit 0 | ✗ BLOCKED | lint + typecheck red; test + audit green |
| FOUND-003 | 01-09 | compose builds + runs, doctor healthcheck | ✗ BLOCKED | no Dockerfile/compose (01-09 pending) |
| FOUND-004 | 01-02 | layered settings, guards, no root config/ | ✓ SATISFIED | tests pass; no config/ dir |
| FOUND-005 | 01-03 | core contracts, LIVE_WRITE refusal, ULIDs | ✓ SATISFIED | tests/core pass |
| FOUND-006 | 01-06 | ownership.yaml + G-1 exit 0 | ✓ SATISFIED | observed exit 0 |
| FOUND-007 | 01-06 | ported gates + ci/tests pass | ✓ SATISFIED | 159 passed |
| FOUND-008 | 01-07 | contracts tree, 18 schemas, G-7 green | ⚠️ PARTIAL | tree + G-7 green; 3 schemas drifted; ApprovalRecorded lacks token_units |
| FOUND-009 | 01-07 | prompts assemble, no placeholders | ✓ SATISFIED | both --check exit 0 |
| FOUND-010 | 01-06 | receipts, workflows, scanners, pre-commit | ✓ SATISFIED | all artifacts exist; gate tests pass |
| FOUND-011 | 01-09 | check.sh, docs, vendor pin | ⚠️ PARTIAL | check.sh exits 0 but legacy; docs/pin pending |
| FOUND-012 | 01-05 | offline harness, clock/rng/fixtures, static guards | ✓ SATISFIED | static-guard + network-block tests pass |
| FOUND-013 | 01-04 + 01-08 | hash-chained ledger + skip-only cycle | ✓ SATISFIED | replay exit 0 + JournalNote=1 observed |
| STRUCT-001 | 01-09 | no tracked *.pyc/tissue.json, VENDOR_PIN 409e74c | ✗ BLOCKED | 6 tracked .pyc; no VENDOR_PIN.md |
| STRUCT-008 | 01-02 | no JitoConfig/wallet_private_key | ✓ SATISFIED | grep empty |
| OBS-001 | 01-08 | JSON logs, redaction | ✓ SATISFIED | logging tests pass; JSON observed |
| OBS-002 | 01-08 | ULID correlation chain | ✓ SATISFIED | correlation tests pass; id observed |
| SEC-001 | 01-06 | no committed secrets, gate on diff | ✓ SATISFIED | G-3 exit 0 |
| SEC-002 | 01-02 | forbidden keys refused, values never printed | ✓ SATISFIED | forbidden-key + redaction tests pass |

All 19 phase requirement IDs accounted for (13 satisfied, 2 partial, 4 blocked). No orphaned IDs: every ID maps to exactly one executed-or-pending plan.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none blocking) | — | `TBD/FIXME/XXX` in phase-touched src | — | `grep` finds no debt markers in src/pumpgrok |
| tools/*.py (legacy) | many | 122 ruff issues (I001, UP-*, T201, PLR0912, …) | ℹ️ Info | legacy dir Phase 2 removes; counts against `ruff check .` until scoped |
| tests/**, ci/** | many | B017/SIM117/PLC0415/E501 style | ⚠️ Warning | test-only style; no behavior impact |

### Open Items From This Run

**(a) F841 in tests/core/test_registry.py — CONFIRMED FIXED.** Commit 67a6640 removed the unused `bot` binding in `test_find_ungranted_tool_refuses_and_audits`. Current `ruff check` on the file reports only PLC0415/SIM117/B017 style notes, no F841.

**(b) WR-08 (sell approvals bind token_units) — PARTLY CLOSED (domain yes, ledger no).** Commit 3df5aae closed the domain half: `ApprovalRecord.token_units` required for `human_sell`/`exit_rule`, `matches()` now refuses wrong kind/side/quantity/unconsumed. The ledger half is OPEN: `ApprovalRecorded` in `src/pumpgrok/ledger/events.py` (and `contracts/events/approval_recorded.schema.json`) has `size_lamports` but no `token_units`, while `core/approvals.py` documents approvals as "persisted in the ledger as ApprovalRecorded events". No runtime writer of ApprovalRecorded rows exists yet in Phase 1, so nothing breaks today — but the first sell-approval persistence would silently drop the quantity binding. Fix with the schema regeneration (same task).

**(c) Ruff counts — `uv run ruff check .`: 171 total.** By rule (top): UP006 36, T201 23, E501 19, UP035 13, UP045 13, RUF002 8, B017 8, UP017 7, SIM117 7, PLW1510 6, PLR0912 6, I001 4, E741 3, PLC0415 3, others ≤2. By dir: src 4, tests 21, ci 24, tools 122 (legacy), vendor 0, scripts 0. Plus `ruff format --check`: 15 files would reformat. No `--fix` was run (per contract).

**G-7 note (from 01-06 SUMMARY):** the "G-7 does not exit 0, re-run after 01-07" item is CLOSED — `check_desk_integrity.py --repo .` now exits 0 (G-7 PASS). Observed, not claimed.

**G-4 note (observation, not a gap):** `check_contracts.py --base origin/main` without `--change` exits 1 because the branch adds contract surfaces. That is the gate's designed behavior and SC2 does not require branch-level G-4 green; per-task CI invocations pass `--change` when touching contracts. No action required for Phase 1 unless the team wants a phase-level change document for the greenfield contracts tree.

### Gaps Summary

Phase 1 is 8/12 truths green with all runtime behavior observed working (install, settings, gates, replay cycle, ledger, logging, live refusal). What blocks "done" is conformance + the unexecuted tail: (1) lint/typecheck red — small, mostly mechanical, but includes a scoping decision on legacy `tools/`; (2) 3 drifted event schemas — regenerate in the locked env; (3) WR-08 ledger half — one field + regen; (4) plan 01-09 entirely pending — container, docs, hygiene. Items 2+3 are one task; item 1 is one task; item 4 is the 01-09 plan as written. Recommend: close 1–3 with targeted fix plans, then execute 01-09 as the phase-gate proof.

---
_Verified: 2026-10-21T06:00:00Z_
_Verifier: Claude (gsd-verifier)_

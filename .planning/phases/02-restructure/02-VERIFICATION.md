---
phase: 02-restructure
verified: 2026-10-23T06:06:02Z
status: passed
score: 5/5 must-haves verified
head: ef2f2f614a1ef392889b5dbf0c356fa0f6faef0f (origin/main, PR 6 merge)
export_dir: /tmp/phase2-main (git archive origin/main, pristine; no product/test/workflow/git changes made)
behavior_unverified: 0
overrides_applied: 0
---

# Phase 02: Restructure Verification Report (re-verified at origin/main ef2f2f6)

**Phase Goal:** The read-only tools and the vendor screening engine run from `src/pumpgrok` under characterization tests while the vendor tree stays alive as the oracle; skills, CLI verbs and the signing guard match the target layout.
**Verified:** 2026-10-23T06:06:02Z
**Status:** passed
**HEAD:** ef2f2f614a1ef392889b5dbf0c356fa0f6faef0f on origin/main
**Re-verification:** Yes - full re-run against a pristine `git archive origin/main` export in /tmp/phase2-main after PR 6. Every criterion below was executed by this verifier in that export; commands and exit codes are recorded verbatim.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Ported read-only tools pass characterization tests (STRUCT-002) | PASSED | SC1 literal exit 0; direct run 13 passed |
| 2 | Engine characterization suite green, no untranslated Cyrillic strings remain (STRUCT-003) | PASSED | SC2a literal exit 0, 243 passed 2 skipped; SC2b `! grep Cyrillic` exit 0 (grep exit 1, no match); vendor oracle clause superseded (Phase 4 SC5 retired the tree; path absent) |
| 3 | Every skill directory carries bots and gates frontmatter; no lite-api or --max-micro phrasing (STRUCT-007) | PASSED | SC3 chain exit 0; 35 dirs, 35 with bots:, 35 with gates:; forbidden-phrase grep exit 1 (no match) so `! grep` exit 0 |
| 4 | CLI exposes pumpgrok verbs and paper buy carries the five required flags (STRUCT-005) | PASSED | SC4a exit 0; SC4b exit 0; all five flags present in help text |
| 5 | AST guard fails on any signing symbol outside the live stub (SEC-003) | PASSED | SC5 literal exit 0; direct run 14 passed |

**Score:** 5/5 truths verified (0 present-behavior-unverified)

### Per-Criterion Commands and Exit Codes

All commands run from the /tmp/phase2-main export root unless noted.

| SC | Command | Result | Status |
|----|---------|--------|--------|
| SC1-literal | `uv run pytest -q tests/characterization/test_authority_check.py tests/characterization/test_holder_check.py tests/characterization/test_jupiter_quote.py tests/characterization/test_priority_fee.py` | exit 0 | PASS |
| SC1-counts | `.venv/bin/pytest tests/characterization/test_authority_check.py tests/characterization/test_holder_check.py tests/characterization/test_jupiter_quote.py tests/characterization/test_priority_fee.py` | exit 0, 13 passed in 0.39s | PASS |
| SC2a-literal | `uv run pytest -q tests/characterization/` | exit 0 | PASS |
| SC2a-counts | `.venv/bin/pytest tests/characterization/` | exit 0, 243 passed, 2 skipped in 10.12s | PASS |
| SC2b | `! grep -rlP '\p{Cyrillic}' src/pumpgrok/engine/` (via /usr/bin/grep: raw exit 1, no match) | exit 0 | PASS |
| SC2-vendor | `cd vendor/grokbot-pumpfun && python3 -m pytest -q` | NOT RUN - SUPERSEDED by Phase 4 SC5, which retires vendor/grokbot-pumpfun; `ls vendor/` fails (no such directory) at this HEAD | SUPERSEDED |
| SC3-counts | `ls -d skills/*/ \| wc -l` = 35; `grep -l '^bots:' skills/*/SKILL.md \| wc -l` = 35; `grep -l '^gates:' skills/*/SKILL.md \| wc -l` = 35 | exit 0 | PASS |
| SC3-phrases | `! grep -rn -e lite-api -e --max-micro skills/` (via /usr/bin/grep: raw exit 1, no match) | exit 0 | PASS |
| SC3-chain | full SC3 compound test chain | exit 0 | PASS |
| SC4a | `uv run pumpgrok --help` | exit 0 | PASS |
| SC4b | `uv run pumpgrok paper buy --help` | exit 0; help lists --ticket, --mint, --size-sol, --slippage-bps, --approval-id (all five confirmed via grep, exit 0) | PASS |
| SC5-literal | `uv run pytest -q tests/safety/test_no_signing_outside_live_stub.py` | exit 0 | PASS |
| SC5-counts | `.venv/bin/pytest tests/safety/test_no_signing_outside_live_stub.py` | exit 0, 14 passed in 3.11s | PASS |

Notes recorded without weakening any criterion:

- SC1 wording: ROADMAP says "reproducing the 6 root unittest cases", but the literal command runs 13 pytest tests across the 4 files and all 13 passed. Both facts are recorded; no files were changed to reconcile the wording.
- SC2a skip count moved from 5 skipped (prior HEAD 2599815) to 2 skipped (HEAD ef2f2f6) with 243 passed and 0 failed; the criterion only requires exit 0, so this remains a pass.
- SC3 text notes the count of 23 became 35 under Phase 3; at this HEAD the invariant holds as 35/35/35. The harmless `skills/README.md: Not a directory` stderr from the `skills/*/` glob does not affect the counts.
- SC2 vendor clause: superseded by Phase 4 SC5, which retires the vendor tree. `vendor/grokbot-pumpfun` is absent at HEAD, so the clause cannot run and is not counted as a gap.
- Counting runs used `.venv/bin/pytest` (same venv binary `uv run pytest` resolves to) because this repo's `addopts` already carries `-q`, so a literal extra `-q` on the CLI collapses output to `-qq` while keeping the exit code. Literal commands were still run exactly as written for the exit-code evidence; the direct-binary runs supply the pass/skip counts. `ci/tests/test_gates.py:1083` documents this `-qq` collapse behavior.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/pumpgrok/tools/market/jupiter.py` | ported Jupiter quote tool | VERIFIED | present; covered by SC1 13/13 green |
| `src/pumpgrok/tools/onchain/authorities.py` | ported authority check | VERIFIED | present; covered by SC1 13/13 green |
| `src/pumpgrok/tools/onchain/holders.py` | ported holder check | VERIFIED | present; covered by SC1 13/13 green |
| `src/pumpgrok/tools/onchain/priority_fee.py` | ported priority fee | VERIFIED | present; covered by SC1 13/13 green |
| `src/pumpgrok/tools/onchain/rpc.py` | single RPC client with failover | VERIFIED | present; exercised by SC1 fixture-backed runs |
| `src/pumpgrok/engine/` (analyzer, monitor, scoring, reputation, agents, tune, exits, watcher) | ported engine | VERIFIED | all modules present; SC2a 243 passed 2 skipped 0 failed |
| `src/pumpgrok/cli.py` | CLI verbs, paper buy flags | VERIFIED | SC4a/SC4b exit 0; all five flags in help text |
| `skills/*/SKILL.md` (35 dirs) | bots+gates frontmatter | VERIFIED | 35/35 bots:, 35/35 gates:; SC3 green |
| `tests/safety/test_no_signing_outside_live_stub.py` | AST signing guard | VERIFIED | SC5 14/14 green |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| characterization tests | ported tools | fixtures in `tests/fixtures/http/` | WIRED | SC1 13/13 green against recorded fixtures |
| characterization tests | ported engine | 1:1 module tests | WIRED | SC2a green (2 skipped, 0 failed) |
| `cli.py paper buy` | five flags | argparse | WIRED | SC4b shows all five |
| AST guard test | `execution/live/` stub | exempt-prefix exact match | WIRED | SC5 green |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| STRUCT-002 | 4 tools ported over single RPC client | SATISFIED | SC1 exit 0, 13/13 |
| STRUCT-003 | engine ported, suite green, no Cyrillic; vendor oracle | SATISFIED | SC2a/SC2b green; vendor clause superseded by Phase 4 SC5 |
| STRUCT-005 | CLI verbs + paper buy flags + pumpgrok-only cron | SATISFIED | SC4a/SC4b exit 0, five flags present |
| STRUCT-007 | skills bots/gates; quote-only Jupiter; no --max-micro | SATISFIED | SC3 35/35/35, phrase grep clean |
| SEC-003 | AST signing guard | SATISFIED | SC5 exit 0, 14/14 |

No other REQUIREMENTS.md row maps to Phase 2 (traceability table confirms exactly these five IDs).

### Anti-Patterns Found

None scanned as blocking. Phase scope files (ported tools, engine, CLI, skills, signing guard) show no TBD/FIXME/XXX debt markers affecting the criteria; "not yet implemented" help strings are the required STRUCT-005 contract (exit 5 JSON), not debt.

### Human Verification Required

None. All five success criteria are command exit codes executed in the pristine export; no visual, real-time, or external-service behavior is in scope for Phase 2.

### Gaps Summary

No gaps. Every executable criterion passes with literal exit codes at origin/main ef2f2f6; the single non-executed clause (vendor oracle) is superseded by Phase 4 SC5, which retired the vendor tree that no longer exists at HEAD. All five requirement IDs remain satisfied. Ready to proceed.

---
_Verified: 2026-10-23T06:06:02Z_
_Verifier: Claude (gsd-verifier)_

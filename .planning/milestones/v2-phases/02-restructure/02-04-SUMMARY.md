---
phase: 02-restructure
plan: "04"
subsystem: cli-cron-hermes
tags: [struct-005, cli, cron, hermes, forbidden-owners]
requires: [02-03]
provides: [cli-verb-tree, cron-prompts, hermes-env-fix]
affects: [phase-4-execution, phase-4-supervisor]
tech-stack:
  added: []
  patterns: ["absent-verb JSON plus exit 5", "required --seat with forbidden_owners refusal"]
key-files:
  created:
    - tests/test_forbidden_owners.py
  modified:
    - src/pumpgrok/cli.py
    - hermes/cron/prompts/scout-discover.md
    - hermes/cron/prompts/scout-pipeline.md
    - hermes/cron/prompts/risk-audit.md
    - hermes/cron/prompts/chief-pickup.md
    - hermes/cron/prompts/rug-watch.md
    - hermes/cron/prompts/chief-journal.md
    - scripts/hermes-install-cron.sh
    - scripts/hermes-bootstrap.sh
    - scripts/hermes-verify-isolation.sh
decisions:
  - Task 2 checkpoint taken as option (a): required --seat on paper/state verbs, sniper/exit refused with exit 1; decided under the non-interactive rule with no blocking-human gate
  - Absent verbs exit 5 with fixed JSON, not CONTEXT exit 2; cli.py reserves 2 for ledger inconsistency
  - Cron prompts pass --seat <owner> on state status pre-flights; prompts never export PUMPGROK_* names
metrics:
  duration: 1 working session
  completed: 2026-10-21
  tasks: 3
  commits: 2
status: complete
actuals:
  tokens: 13000
  tasks: 3
  commits: 2
  plan_head_before: 871496b
---

# Phase 02 Plan 04: CLI Verbs, Cron Prompts, and Hermes Env Fix Summary

Full STRUCT-005 verb surface: every DISCOVERY verb plus R12 and R40 additions parses flags and returns the absent-verb contract (fixed JSON on stdout, one stderr line, exit 5) until its subsystem lands. `paper buy|sell` parse all five flags; `paper` and `state` require `--seat` and refuse `sniper`/`exit`. Six cron prompts wrap `pumpgrok` only and treat exit 5 as not-yet-implemented without inventing results. Hermes scripts no longer export `PUMPGROK_*` names.

## Tasks Completed

| # | Task | Commit | Verify |
|---|------|--------|--------|
| 1 | Tracer: paper buy and sell verbs with five flags | 3f78b05 | paper buy --help lists all five flags; desk seat exits 5 with the JSON object |
| 2 | Decide forbidden_owners enforcement mechanism | decided (a), no commit | 12 tests collected; choice recorded below |
| 3 | Remaining verbs, cron prompts, and Hermes env fix | 7771f18 | pumpgrok --help exits 0 with all verbs; prompts/scripts clean |

## Verification Evidence

- SC4a: `uv run pumpgrok --help` -> exit 0, lists run doctor audit verify report scout risk chief rug journal ticket state killswitch paper live replay (17 verb mentions).
- SC4b: `uv run pumpgrok paper buy --help` -> exit 0, lists --ticket --mint --size-sol --slippage-bps --approval-id plus --seat.
- Absent-verb sweep (15 invocations: scout discover, risk audit, chief pickup, rug watch, journal rollup, ticket next, state status, killswitch status, live confirm, replay trim, audit, verify, report, run --record, state autonomy) -> every one exits 5 printing exactly `{"ok": false, "status": "not-yet-implemented", "verb": "<name>"}`.
- Tracer: allowed seat `paper buy --seat desk` -> exit 5 with `paper buy` JSON on stdout; `--seat sniper|exit` on paper/state -> exit 1 with `refused` on stderr.
- Regression: `uv run python -m pytest tests/` -> exit 0, 314 passed (includes new 12-test forbidden-owners file and unchanged test_skip_cycle).
- Static: `ruff check` clean, `ruff format --check` clean, `mypy src/pumpgrok/cli.py` strict clean.
- Prompts: grep for `desk_state|pipeline_evidence|ticket_helper|PUMPGROK_ROOT|PUMPGROK_DESK|PUMPGROK_ROLE` in `hermes/cron/prompts/` -> no matches (exit 1).
- Scripts: anchored grep for `^export PUMPGROK_` / `^PUMPGROK_*=` assignments in the three hermes scripts -> no matches (exit 1); `bash -n` passes on all three; installer `--dry-run` exits 0 with the new REPO/DESK header.
- Note: bare `uv run pytest <file>` in this shell reports "No tests collected" while `uv run python -m pytest <file>` runs normally; all counts above use the module form. Pre-existing shell behavior, unaffected by this plan.

## Deviations from Plan

### Auto-fixed Issues

None. No bugs, missing validation, or blockers beyond the plan were found in the touched files.

### Structural notes (not deviations from intent)

**1. Full verb tree landed in the Task 1 commit.**
- Found during: task 1 implementation.
- The paper verbs share the parser, seat gate, and dispatch contract with every other absent verb, so the whole tree was built in one pass rather than split across two commits. Task 1 commit (3f78b05) carries cli.py plus the forbidden-owners tests; Task 3 commit (7771f18) carries the six prompts plus the three scripts.
- Recorded here so the file history reads correctly against the plan's per-task file lists.

**2. Flagged CONTEXT-vs-code conflict handled as specified: absent verbs exit 5, not 2.**
- CONTEXT discretion says exit 2; `cli.py` reserves 2 for ledger inconsistency and `tests/test_skip_cycle.py` asserts 5 (Pitfall 17, Open Q1). Exit 5 with the fixed JSON shape is implemented everywhere.

### Decision record (Task 2 checkpoint, option a)

- Checkpoint: `Decide forbidden_owners enforcement mechanism`. Options: (a) required `--seat` option on the paper and state verbs, refused with a non-zero exit when the value is `sniper` or `exit`; (b) read the caller from the Hermes cron env at dispatch.
- Chosen: (a). Rationale: no seat identity exists on the CLI today and `logging/json.py bind_seat` only covers the replay cycle; a cron-env identity (b) would be spoofable and invisible in `--help`. Refusal uses exit 1 (`EXIT_CONFIG`) with `refused: seat '<v>' is a forbidden owner` on stderr, so it is distinct from the exit-5 absent-verb signal.
- Taken under the non-interactive rule with no blocking-human gate, per orchestrator direction. Task 2 is complete; implementation is covered by the Task 1/3 commits and `tests/test_forbidden_owners.py`.

## Key Decisions

- `--seat` lives on the leaf parsers (`paper buy|sell`, `state status|halt|autonomy`), so `paper buy --help` shows it next to the five trade flags; prompts pass `--seat <owner>` on state-status pre-flights.
- Size conversion happens exactly once in `size_sol_to_lamports`; the handler logs the lamports value and returns the fixed JSON (no operator input echoed into stdout, T-02-12).
- Mint validation is base58 alphabet plus 32-44 character length; approval-id validation mirrors the `ApprovalRecord` ULID pattern; slippage is int 0-10000.
- Prompt headers now carry literal `REPO=`/`DESK=` lines and the installer tells the agent to substitute them into `uv run --project "$REPO" pumpgrok ...`; nothing named `PUMPGROK_*` is exported or assigned by any hermes script.
- `hermes-verify-isolation.sh` engagement guard rejects any `desk.md` engagement outside `research|paper` without naming the retired level; it also now covers `scout-pipeline.md` and gates prompt purity plus the no-export rule.

## Known Stubs

None. Every new verb parses real flags and validates input; absent backends return the loud not-implemented contract rather than stubs. No placeholders, mocks in src, or unwired paths were introduced.

## Threat Flags

None beyond the plan threat model (T-02-10/11/12, T-02-SC): forbidden seats are refused before any verb logic with exit 1; trade flags are validated in argparse before dispatch; absent-verb errors carry a fixed shape with no paths, env, or config; no new packages were added.

## Self-Check: PASSED

- All created/modified files exist on disk; prompts contain no root-tool or PUMPGROK references; scripts contain no PUMPGROK export/assignment statements.
- Commits 3f78b05 and 7771f18 present in `git log`.

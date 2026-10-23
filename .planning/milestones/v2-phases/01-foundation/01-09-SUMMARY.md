---
phase: 01-foundation
plan: 09
subsystem: infra
tags: [docker, compose, healthcheck, replay, check-sh, vendor-pin, docs, gates, ownership]

# Dependency graph
requires:
  - phase: 01-06
    provides: "gates G-1..G-7 under ci/gates and the run_all.py entry point"
  - phase: 01-07
    provides: "contracts tree, generated event schemas, prompt assembly and agent generation"
  - phase: 01-08
    provides: "pumpgrok CLI with run --once --replay and doctor, the skip-only replay cycle"
provides:
  - "Dockerfile: multi-stage python:3.12-slim build with uv 0.13.4, non-root runtime user, PUMPGROK_PROFILE=paper, smoke fixture baked in, doctor HEALTHCHECK, SIGTERM stop, replay as default CMD"
  - "docker-compose.yml: one-shot pumpgrok service, no restart policy (R50), optional .env via env_file required:false, loopback port, json-file logging, 512M limit"
  - ".dockerignore: excludes vendor/, var/, .env*, .planning/, .git, tests/ except the smoke fixture"
  - "scripts/check.sh rewritten without vendor paths; VENDOR_PIN check; your-org allowlist check; emoji scan covers .planning/**; ASCII-only script"
  - "docs/VENDOR_PIN.md recording vendor pin 409e74c905faa0e9de42e918efe2c604f206856e"
  - "AGENTS.md desk-rules index above line 1 (GSD marker blocks unchanged), SECURITY.md, CHANGELOG.md, docs/quality-gates.md, docs/desk-operating-model.md, docs/cross-bot-protocol.md"
  - "Repo hygiene: six tracked *.pyc untracked, issues/tissue.json removed"
affects: [phase-02-restructure]

# Actuals
actuals:
  tasks: 3
  commits: 6

# Tech tracking
tech-stack:
  added: ["uv 0.13.4 (container installer)"]
  patterns: ["multi-stage uv build with --frozen --no-dev --no-editable", "one-shot compose service with no restart policy (R50)", "allowlist-by-exclusion .dockerignore with a single re-included fixture"]

key-files:
  created:
    - "Dockerfile"
    - "docker-compose.yml"
    - ".dockerignore"
    - "docs/VENDOR_PIN.md"
    - "SECURITY.md"
    - "CHANGELOG.md"
    - "docs/quality-gates.md"
    - "docs/desk-operating-model.md"
    - "docs/cross-bot-protocol.md"
  modified:
    - "scripts/check.sh"
    - "AGENTS.md"
    - "ownership.yaml"
    - ".planning/phases/01-foundation/01-VALIDATION.md"
    - ".planning/phases/01-foundation/01-VERIFICATION.md"
  deleted:
    - "issues/tissue.json"
    - "tests/__pycache__/test_tools_cli.cpython-312.pyc (untracked)"
    - "tools/__pycache__/authority_check.cpython-312.pyc (untracked)"
    - "tools/__pycache__/holder_check.cpython-312.pyc (untracked)"
    - "tools/__pycache__/jupiter_quote.cpython-312.pyc (untracked)"
    - "tools/__pycache__/paper_sim.cpython-312.pyc (untracked)"
    - "tools/__pycache__/priority_fee.cpython-312.pyc (untracked)"

key-decisions:
  - "Container default CMD is the R50 skip-only replay: run --mode paper --once --replay tests/fixtures/replay/smoke. The pumpgrok service has no restart policy."
  - "HEALTHCHECK lives in the Dockerfile (exec form, pumpgrok doctor). Compose does not repeat it."
  - "Planning reports are kept ASCII (research Pitfall 10): status glyphs in 01-VALIDATION.md and 01-VERIFICATION.md were replaced with PASS/FAIL/WARN so check.sh can scan .planning/**."
  - "The your-org placeholder check allows the placeholder only in the five files that still carry it (plugin.json, the two marketplace manifests, SETUP.md, ARCHITECTURE.md). An allowlisted file that drops the placeholder must leave the list, so the list only shrinks until STRUCT-007."
  - "No var/ bind mount in compose. The image runs as uid 999 and a root-owned host var/ would be unwritable; the one-shot writes its ledger inside the container and --rm discards it."
  - "prompts-assembled/ is not copied into the image: the Phase 1 CLI reads no prompts at run time."
  - "The desk docs are authored for the ten-seat desk (not copied from programming-desk). They name the ten seats, research|paper levels, and G-1..G-7, and link to the gate scripts."

patterns-established:
  - "Placeholder allowlist in check.sh that fails when an allowlisted file no longer contains the placeholder"
  - "Compose one-shot services carry a comment explaining the absent restart policy"

requirements-completed: ["FOUND-003", "FOUND-011", "STRUCT-001"]

# Coverage metadata
coverage:
  - id: D1
    description: "Multi-stage non-root image with doctor HEALTHCHECK, SIGTERM stop and the smoke fixture; builds and runs the R50 replay to exit 0"
    requirement: "FOUND-003"
    verification:
      - kind: automated_ui
        ref: "docker compose build pumpgrok && docker compose run --rm pumpgrok (exit 0)"
        status: pass
    human_judgment: false
  - id: D2
    description: "docker-compose.yml one-shot service: no restart policy, env_file optional, loopback port, json-file logging"
    requirement: "FOUND-003"
    verification:
      - kind: other
        ref: "docker compose config --quiet"
        status: pass
    human_judgment: false
  - id: D3
    description: "scripts/check.sh rewritten without vendor paths; exits 0 with .planning/** scanned"
    requirement: "FOUND-011"
    verification:
      - kind: other
        ref: "./scripts/check.sh"
        status: pass
    human_judgment: false
  - id: D4
    description: "AGENTS, SECURITY (R40 custody line), CHANGELOG and three desk docs in pumpgrok shape"
    requirement: "FOUND-011"
    verification:
      - kind: other
        ref: "grep checks for ten seat ids, research|paper, G-1..G-7, R40 wording; ASCII scan"
        status: pass
    human_judgment: true
    rationale: "Prose quality of the desk docs is a reviewer judgment; only their structural content is machine-checked"
  - id: D5
    description: "Six tracked *.pyc untracked, issues/tissue.json removed, docs/VENDOR_PIN.md records 409e74c"
    requirement: "STRUCT-001"
    verification:
      - kind: other
        ref: "git ls-files | grep -E '\\.pyc$|tissue' (empty); grep 409e74c docs/VENDOR_PIN.md"
        status: pass
    human_judgment: false
  - id: D6
    description: "Canonical suite on the final tree: make lint and make typecheck"
    requirement: "FOUND-003"
    verification:
      - kind: other
        ref: "make lint (exit 2, ruff check 171 errors); make typecheck (exit 2, mypy 4 errors)"
        status: fail
    human_judgment: false

# Metrics
duration: n/a
completed: 2026-10-21
status: complete-with-blockers
---

# Phase 1, Plan 09: Container, hygiene, desk docs and phase-gate proof Summary

**Image, compose one-shot and desk docs landed and the replay exits 0 in the container; the phase gate is blocked by lint and typecheck debt that predates this plan.**

## Performance

- **Duration:** n/a
- **Completed:** 2026-10-21
- **Tasks:** 3 of 3 executed
- **Commits:** 6 (plus this SUMMARY commit)

## Accomplishments

- `docker compose config --quiet` exits 0; `docker compose build pumpgrok` exits 0.
- `docker compose run --rm pumpgrok` exits 0. The skip-only replay reads 4 fixture events and writes `ledger_seq` 1. The correlation ID is identical across two runs, which confirms the seeded replay is deterministic.
- Image runs as uid 999 (`pumpgrok`), has no `/app/config`, contains no `.env`, and its HEALTHCHECK `pumpgrok doctor` exits 0.
- `./scripts/check.sh` exits 0 with the `.planning/**` emoji scan and the placeholder allowlist active.
- Six tracked `*.pyc` are untracked, `issues/tissue.json` is removed, and `docs/VENDOR_PIN.md` records `409e74c905faa0e9de42e918efe2c604f206856e`.
- `make test`, `uv run pytest -q` and `make audit` exit 0. `make audit` reports no known vulnerabilities.
- `ci/gates/check_ownership.py --validate-manifest` passes: 10 bots, 171 rules, 331 tracked paths, each with one owner.

## Task Commits

1. **Task 1 (tracer): image, compose, dockerignore** - `342fb06` (feat)
2. **Task 2a: untrack pyc, remove tissue.json** - `a87f11b` (chore)
3. **Task 2b: check.sh rewrite, VENDOR_PIN, ASCII planning reports** - `c661067` (chore)
4. **Task 2c: AGENTS, SECURITY, CHANGELOG, desk docs** - `02decc8` (docs)
5. **Task 2d: own .dockerignore under RISK** - `ce7a7e5` (fix)
6. **Task 2e: name seats, levels and gates; verbatim R40 line; compose comment** - `4d7037e` (docs)

Task 3 (phase-gate proof) made no commit: it is verification only.

## Files Created/Modified

- `Dockerfile`, `docker-compose.yml`, `.dockerignore` - container surface (created)
- `scripts/check.sh` - rewritten (modified); no vendor paths; no non-ASCII bytes
- `docs/VENDOR_PIN.md` - vendor pin note moved from `vendor/grokbot-pumpfun/PUMPGROK.md` (created)
- `AGENTS.md` - desk-rules index inserted above line 1; 72 lines added, 0 removed (modified)
- `SECURITY.md`, `CHANGELOG.md`, `docs/quality-gates.md`, `docs/desk-operating-model.md`, `docs/cross-bot-protocol.md` (created)
- `ownership.yaml` - `.dockerignore` rule added under `bot-02-risk` (modified)
- `.planning/phases/01-foundation/01-VALIDATION.md`, `01-VERIFICATION.md` - status glyphs replaced with ASCII words (modified)
- `issues/tissue.json` and six `*.pyc` - removed from the index (deleted)

## Decisions Made

- Default CMD is the R50 skip-only replay; `pumpgrok` has no restart policy.
- HEALTHCHECK is in the Dockerfile only. The plan's key-link mentions compose; the tracer action placed it in the Dockerfile, and one definition avoids drift.
- No `var/` bind mount in compose (see key-decisions in the frontmatter).
- `prompts-assembled/` is not copied into the image (FOUNDATION_STACK 3.3 draft copies it; the Phase 1 CLI reads no prompts).
- uv pinned to 0.13.4 per the plan; FOUNDATION_STACK 3.3 shows 0.13.3 and is superseded here.

## Deviations from Plan

**[Rule 3 - Blocking] Planning reports rewritten to ASCII** - Found during: Task 2
Issue: the plan requires `check.sh` to scan `.planning/**`; `01-VALIDATION.md` and `01-VERIFICATION.md` contained U+2713/2717/274C/26A0 and a U+FE0F selector, so `check.sh` exited 1.
Fix: replaced those glyphs with `PASS`, `FAIL` and `WARN`. No other text changed.
Files modified: `.planning/phases/01-foundation/01-VALIDATION.md`, `.planning/phases/01-foundation/01-VERIFICATION.md`
Verification: `./scripts/check.sh` exit 0
Commit: `c661067`
Note: `01-VERIFICATION.md` is the verifier's report. Only glyphs changed, but the orchestrator should know its bytes differ.

**[Rule 1 - Bug] `.dockerignore` had no owner** - Found during: canonical `make test`
Issue: my new `.dockerignore` was unowned, so the G-1 every-path-owned self-test failed (`UNOWNED .dockerignore`).
Fix: added a rule assigning it to `bot-02-risk`, next to `Dockerfile` and `docker-compose.yml`.
Files modified: `ownership.yaml`
Verification: `check_ownership.py --validate-manifest` OK; `make test` exit 0
Commit: `ce7a7e5`

**[Rule 2 - Missing critical] Placeholder check did not exist** - Found during: Task 2
Issue: the plan says to keep "the your-org allowlist"; the current `check.sh` had no such check. STRUCT-001 requires the placeholder check to be present.
Fix: implemented it. It fails on `your-org` outside five allowlisted files and fails when an allowlisted file no longer contains the placeholder.
Verification: negative probe (temporary file with `your-org`) exits 1; probe removed; final run exit 0.
Commit: `c661067`

**[Rule 2 - Dead code] Two no-op checks removed from `check.sh`** - MIGRATION_MAP row 35 flags the writer-set and agent-name checks as dead `pass` branches. Removed while rewriting the file.
Commit: `c661067`

**Note on the vendor-path replacement.** The plan says to replace the vendor-path block with the VENDOR_PIN note. I implemented that as an existence and pin-string check on `docs/VENDOR_PIN.md`, which is stricter than a comment.

**[Process incident, corrected before commit]** A block edit (`PUT 1*`) on `docs/quality-gates.md` replaced the whole file with one line. I restored the file with a full rewrite and re-verified it before committing. No commit contains the truncated version.

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug), 1 missing-critical addition, 1 dead-code removal.
**Impact:** all are needed for the plan's own acceptance criteria. No scope added beyond the plan's named files.

## Issues Encountered

- **`make lint` fails (exit 2).** `ruff check .` reports 171 errors (67 auto-fixable), and `ruff format --check .` would reformat 15 files. These are lint debt in `src/`, `tests/` and `ci/`, already recorded by the verifier as out of scope. Not fixed, per the orchestrator's instruction. None of the files I changed is Python.
- **`make typecheck` fails (exit 2).** mypy `--strict` reports 4 errors in 3 files: `src/pumpgrok/ledger/events.py:341` and `:349` (missing `dict` type arguments), `src/pumpgrok/core/registry.py:27` and `src/pumpgrok/core/__init__.py:30` (`Clock` not explicitly exported from `pumpgrok.core.ids`). Pre-existing and out of scope.
- **Plan verify chain halts at lint.** `make lint typecheck test audit` stops at the first failing target, so I ran each target separately. `test` and `audit` pass.

## Verification (run on the final tree, after commit `4d7037e`)

| Command | Exit | Note |
|---|---|---|
| `docker compose config --quiet` | 0 | |
| `docker compose build pumpgrok` | 0 | base images from local cache |
| `docker compose run --rm pumpgrok` | 0 | one replay cycle, 4 events, ledger_seq 1 |
| `docker inspect` HEALTHCHECK / user | n/a | `pumpgrok doctor`; user `pumpgrok`; StopSignal SIGTERM |
| `pumpgrok doctor` in image | 0 | 6 present, 5 not-yet-implemented warnings |
| `./scripts/check.sh` | 0 | 23 skills, 10 agents, 106 markdown files |
| `test ! -d config` | 0 | |
| `uv sync --frozen` | 0 | 53 packages |
| `make lint` | 2 | 171 ruff errors (out of scope) |
| `make typecheck` | 2 | 4 mypy errors (out of scope) |
| `make test` / `uv run pytest -q` | 0 | |
| `make audit` | 0 | no known vulnerabilities |
| `check_ownership.py --validate-manifest` | 0 | 331 paths, each with one owner |
| `git ls-files \| grep -E '\.pyc$\|tissue'` | empty | |
| AGENTS.md diff vs. prior commit | 72 insertions, 0 deletions | 14 GSD marker lines intact |

## Self-Check: FAILED

Reason: the plan's Task 3 acceptance criterion `uv sync --frozen && make lint typecheck test audit` exits 0 is not met. `make lint` (171 ruff errors) and `make typecheck` (4 mypy errors) fail on code outside this plan. Every other criterion in Tasks 1-3 passes, and the SUMMARY's file list matches `git show --stat` for the six commits.

## User Setup Required

None. No external service is configured. The optional `.env` for compose is operator-supplied at run time and is not required.

## Next Phase Readiness

- The image, compose one-shot and desk docs are in place for Phase 2.
- Blocking for SC1 (`make lint`, `make typecheck` on a clean checkout): the ruff and mypy debt listed above. It needs a separate fix plan. Its scope is `src/`, `tests/` and `ci/` Python only.
- Desk-doc prose is authored for the ten-seat desk; reviewers should check it against the seat files as the engine lands.

---
*Phase: 01-foundation*
*Completed: 2026-10-21*

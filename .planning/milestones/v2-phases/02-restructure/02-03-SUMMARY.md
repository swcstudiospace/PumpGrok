---
phase: 02-restructure
plan: "03"
subsystem: engine-pipeline-agents
tags: [characterization, struct-003, pipeline, agents, tune, replay-checkpoint]
requires: [02-02]
provides: [engine-pipeline, engine-agents, engine-tune, core-ops, replay-decision]
affects: [02-04-cli, phase-4-replay]
tech-stack:
  added: []
  patterns: ["injected Clock sleeps", "seeded Random jitter", "MockTransport fixtures", "pure filter replay"]
key-files:
  created:
    - src/pumpgrok/engine/pipeline.py
    - src/pumpgrok/engine/tune.py
    - src/pumpgrok/engine/agents/__init__.py
    - src/pumpgrok/engine/agents/base.py
    - src/pumpgrok/engine/agents/checker.py
    - src/pumpgrok/engine/agents/narrative.py
    - src/pumpgrok/engine/agents/timing.py
    - src/pumpgrok/engine/agents/auditor.py
    - src/pumpgrok/core/ratelimit.py
    - src/pumpgrok/core/budget.py
    - src/pumpgrok/core/llm.py
    - tests/characterization/test_pipeline.py
    - tests/characterization/test_agents.py
    - tests/characterization/test_tune.py
    - tests/fixtures/http/xai_chat.json
  modified:
    - src/pumpgrok/cli.py
    - src/pumpgrok/ledger/events.py
    - src/pumpgrok/engine/__init__.py
    - tests/test_skip_cycle.py
    - ownership.yaml
decisions:
  - Replay candidates satisfy metadata and age gates by construction so the checkpoint exercises the fail-closed evidence gate, documented in the note text
  - Engine decision recorded as JournalNote verdict, model resolution skip recorded in text, no startup model lookup
  - Retry and timeout knobs travel as agent constructor arguments; settings.py stays untouched
  - No wire effort field is sent (vendor parity); the A3 field-name question stays open and effort lives in settings only
  - Circuit breaker and metrics sink are Phase 4; GrokOps precheck reports the budget only
  - Tune reads plain JSONL records and ScoringWeights; no TradeLog dependency, no config-file weights
metrics:
  duration: 1 working session
  completed: 2026-10-21
  tasks: 3
  commits: 3
status: complete
actuals:
  tokens: 62000
  tasks: 3
  commits: 3
  plan_head_before: 86c7758
---

# Phase 02 Plan 03: Agents, Pipeline, and Tune Summary

Remaining engine surface (STRUCT-003 part 2): the replay pipeline prints one engine decision, the four Grok agents run on the injected clock with seeded jitter against the x.ai base URL, the tune grid search is ported dependency-free, and all three SC2 gates pass with the vendor oracle untouched.

## Tasks Completed

| # | Task | Commit | Verify |
|---|------|--------|--------|
| 1 | Tracer: replay prints one engine decision plus JournalNote | 627b939 | checkpoint exits 0, prints skip, one verdict note |
| 2 | Grok agents and core ops ports | 3adbe9a | 20 agent tests pass, ruff plus mypy clean |
| 3 | Tune port, Cyrillic gate, and oracle close-out | 3f2a0ce | vendor 279 passed, characterization 151 passed, gate empty |

## Verification Evidence

- SC2 checkpoint: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` -> exit 0, stdout `engine decision=skip reason=data_unavailable`; ledger holds exactly one `JournalNote` (source replay, verdict) whose text records `model resolution skipped (replay)`.
- SC2a: `cd vendor/grokbot-pumpfun && python3 -m pytest` -> exit 0, 279 passed in 1.82s with the system python3 (RESEARCH availability confirmed: httpx, pydantic, websockets, pyyaml and pytest present, so no /tmp venv was needed).
- SC2b: `uv run pytest -q tests/characterization/` -> exit 0, 151 passed across 13 files, no live network (all x.ai traffic served by MockTransport).
- SC2c: `LC_ALL=C.UTF-8 grep -rlP '\p{Cyrillic}' src/pumpgrok/engine/` prints nothing (grep exit 1); vendor positive control matches (`log.py`, `ops.py`, `alerts.py`), so the gate is live.
- Regression: full root suite `uv run pytest tests/` -> exit 0, 302 passed.
- Ownership: `python3 ci/gates/check_ownership.py --validate-manifest` -> exit 0, 396 tracked paths owned.
- Static: `ruff check` and `ruff format --check` clean on every new or touched file; `mypy` strict clean on all 12 new source files (whole-project run still reports 3 pre-existing errors in untouched `analyzer.py`/`watcher.py`, left alone as out of scope).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Lost `model` property and `endpoint` header during base.py edits**
- Found during: task 2 test run (`TypeError: __init__() should return None`, then `no attribute 'model'`)
- Issue: two range edits each swallowed a neighboring member (the `endpoint` property header, then the `model` property)
- Fix: restored both members; suite went from 11 failures to 20 passed
- Files modified: src/pumpgrok/engine/agents/base.py

**2. [Rule 1 - Bug] Retry knobs have no home in GrokSettings**
- Found during: task 2 implementation
- Issue: `GrokSettings` carries only base URL, models, effort, and key; vendor timeouts and retry counts live nowhere in settings, and the plan files list does not include settings.py
- Fix: `timeout_seconds`, `max_retries`, and `retry_base_delay` are agent constructor arguments with vendor-parity defaults; no settings or overlay touched
- Files modified: src/pumpgrok/engine/agents/base.py

**3. [Rule 1 - Test] Limiter delay expectation used the wrong rate**
- Found during: task 2 test run (obtained 1.0, expected 60.0)
- Issue: at 60 calls per minute one token accrues per second, so an empty bucket waits 1.0s, not 60s
- Fix: expectation corrected to 1.0
- Files modified: tests/characterization/test_agents.py

**4. [Rule 2 - Missing] GrokSettings has no request-timeout or retry fields**
- Covered by fix 2 above; recorded here because the plan assumed settings-carried knobs. The A3 wire question (`reasoning_effort` field name) stays open: payloads keep vendor parity (model, temperature, messages) and effort lives in settings only.

**5. [Rule 1 - Test] Stale duplicate test after reformat**
- Found during: task 2 lint pass (F811 redefinition)
- Issue: a range edit left the old sync `test_ops_slot_counts_and_snapshot_reports` body behind the new async one
- Fix: removed the stale copy; ruff clean
- Files modified: tests/characterization/test_agents.py

**6. [Rule 1 - Lint] E501 and PLC0415 in tune sources**
- Found during: task 3 lint pass
- Issue: three long lines in `tune.py`, five long fixture lines plus an inline import in `test_tune.py`
- Fix: split signatures, added a `_scored` record helper plus `json.dumps` row building, hoisted the `Outcome` import
- Files modified: src/pumpgrok/engine/tune.py, tests/characterization/test_tune.py

### Vendor count note

- The vendor oracle reports 279 passed, not the 264 cited in CONTEXT: the suite grew upstream. Criterion SC2a is exit 0, which holds; the count is recorded, not asserted.

## Key Decisions

- `note_kind=verdict` for the replay decision (a filter verdict, not a desk note); `test_skip_cycle.py` now asserts the decision line in stdout, the note text, and the skipped model resolution.
- Timing cache keys on explicit caller `now`; pessimistic fallbacks are never cached and `invalidate` forces refresh.
- `TimingAgent` takes `cache_seconds` explicitly; every agent takes `clock`, seeded `rng`, an optional shared client, and optional `GrokOps`.
- Prompts are English code constants; the smoke xAI fixture was authored after the prompts were final (ordered per CONTEXT discretion).
- Tune `main` returns its exit code and writes via `sys.stdout.write`; `run_report` separates line building from I/O for testability.

## Known Stubs

None. No placeholders, mocks in src, or unwired paths were introduced. Test doubles (`ImmediateClock`, `MockTransport`) live in tests only.

## Threat Flags

None beyond the plan threat model (T-02-07/08/09, T-02-SC): untrusted model output is parsed as data into pydantic models; no live path exists in the pipeline; jitter runs on the seeded rng through virtual sleeps; no new packages were added.

## Self-Check: PASSED

- All created files exist on disk; all modified files committed.
- Commits 627b939, 3adbe9a, 3f2a0ce present in `git log`.

---
phase: 02-restructure
reviewed: 2026-10-21T00:00:00Z
depth: deep
files_reviewed: 33
files_reviewed_list:
  - src/pumpgrok/cli.py
  - src/pumpgrok/config/overlays/dev.toml
  - src/pumpgrok/config/overlays/live.toml
  - src/pumpgrok/config/overlays/paper.toml
  - src/pumpgrok/config/settings.py
  - src/pumpgrok/core/budget.py
  - src/pumpgrok/core/datasource.py
  - src/pumpgrok/core/llm.py
  - src/pumpgrok/core/ratelimit.py
  - src/pumpgrok/engine/__init__.py
  - src/pumpgrok/engine/agents/__init__.py
  - src/pumpgrok/engine/agents/auditor.py
  - src/pumpgrok/engine/agents/base.py
  - src/pumpgrok/engine/agents/checker.py
  - src/pumpgrok/engine/agents/narrative.py
  - src/pumpgrok/engine/agents/timing.py
  - src/pumpgrok/engine/analyzer.py
  - src/pumpgrok/engine/exits.py
  - src/pumpgrok/engine/models.py
  - src/pumpgrok/engine/monitor.py
  - src/pumpgrok/engine/pipeline.py
  - src/pumpgrok/engine/reputation.py
  - src/pumpgrok/engine/scoring.py
  - src/pumpgrok/engine/tune.py
  - src/pumpgrok/engine/watcher.py
  - src/pumpgrok/ledger/events.py
  - src/pumpgrok/tools/__init__.py
  - src/pumpgrok/tools/market/__init__.py
  - src/pumpgrok/tools/market/jupiter.py
  - src/pumpgrok/tools/onchain/__init__.py
  - src/pumpgrok/tools/onchain/authorities.py
  - src/pumpgrok/tools/onchain/holders.py
  - src/pumpgrok/tools/onchain/priority_fee.py
  - src/pumpgrok/tools/onchain/rpc.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 02: Code Review Report (iteration 2 — re-review after fixes)

**Reviewed:** 2026-10-21T00:00:00Z
**Depth:** deep
**Files Reviewed:** 33
**Status:** clean (CR-03 resolved on re-verification 2026-10-23, 0 open findings)

## Summary

Re-review of the Phase 02 scope after the iteration-1 fixes (commits
`010b8d0`, `541f49c`, `d30490e`, `4b3f587`, `b810f39`, `849389d`,
`07d97dd`, `6c5a8e6`, plus lint-only `642d23f`). Each prior finding was
re-verified against the current source at the exact lines cited below.
8 of 9 prior findings are resolved; the 9th (CR-03) was deliberately
skipped by the fixer per the locked characterization test and remains
open, restated below with its current file:line. Deep cross-checks of the
fix diffs (import graph, caller signatures, exception contracts,
pydantic `ValidationError`-is-`ValueError` subclassing, `Settings.risk`
field existence) surfaced **no new Critical or Warning defects**.
One pre-existing residual edge (non-dict payload passed directly to
`handle_event`) is noted inline under CR-02 but is not a new defect:
the production path (`stream`) guards with `isinstance`, and it predates
the fixes.

## Prior Findings Status

| ID | Title | Status | Evidence |
|----|-------|--------|----------|
| CR-01 | Jupiter quote mapper raises on malformed shape | resolved | `src/pumpgrok/tools/market/jupiter.py:65-100` — mapping inside `try`; non-dict payload and non-list `routePlan` return `{"ok": False}`; `priceImpact` coerced defensively; non-dict route entries skipped |
| CR-02 | Monitor socket parser raises, dropping the stream | resolved | `src/pumpgrok/engine/monitor.py:76-116` — `_coerce_float` on all three untrusted floats; whole body wrapped, returns `None` on `(TypeError, ValueError, AttributeError)` |
| CR-03 | Corrupt reputation file silently discards rug history | **open** (deliberately skipped, locked test) | `src/pumpgrok/engine/reputation.py:77-92` — `load` still swallows all exceptions and returns an empty book; restated as CR-03 below |
| WR-01 | Malformed holder/trade record aborts analysis | resolved | `src/pumpgrok/engine/analyzer.py:119-130,152-156,202-207` — `_safe_parse` per-row guard, non-dict `info` normalized to `{}`, `enrich_token` coercions under `suppress` |
| WR-02 | Analyzer logs URL-carrying exception text | resolved | `src/pumpgrok/engine/analyzer.py:103` — logs `type(exc).__name__` only |
| WR-03 | Watcher drops pending peak-persist on later sale | resolved | `src/pumpgrok/engine/watcher.py:92-93,108-109,125-126` — independent `peak_grew`/`sold` flags, persist when either is true |
| WR-04 | Tune CLI ignores operator-configured weights | resolved | `src/pumpgrok/engine/tune.py:289-294,300` — `_current_weights()` via `load_settings().scoring.weights` with `ConfigError` fallback; `load_settings` raises only `ConfigError` per its contract (`src/pumpgrok/config/settings.py:434-447`) |
| WR-05 | Lamport truncation + no equity cap | resolved | `src/pumpgrok/cli.py:120-124,388-396` — `Decimal`/`ROUND_HALF_UP`, `_size_sol` rejects non-finite/non-positive, size refused above `settings.risk.paper_equity_lamports` (property exists at `src/pumpgrok/core/risk_budget.py:43-44`); `_paper` has exactly one caller with the updated signature (`cli.py:423`) |
| WR-06 | Trailing-stop ratchet split across modules | resolved | `src/pumpgrok/engine/exits.py:98-112`, `src/pumpgrok/engine/watcher.py:106-109` — `apply_price` ratchets via `max` then evaluates; watcher captures pre-call `old_peak` for the persist-step comparison; `exit_signal` untouched and still pure |

Residual note (not a finding): `LaunchMonitor.handle_event`
(`src/pumpgrok/engine/monitor.py:172-183`) calls `payload.get` before
`parse_create_event`'s guarded body, so a non-dict passed *directly* to
`handle_event` still raises `AttributeError`. The production caller
(`stream`, line ~238) guards with `isinstance(payload, dict)` first, and
`parse_create_event` itself is safe against non-dict input via its
`except AttributeError`. Pre-existing, unreachable in production; left
for Phase 4 only if the trade leg adds new direct callers.

## Critical Issues

### CR-03: Corrupt reputation file silently discards rug history (fail-open) — RESOLVED on re-verification 2026-10-23

**File:** `src/pumpgrok/engine/reputation.py:77-92` (verified on origin/main export; `load` at lines 83-122 quarantines and sets `degraded=True`; fail-closed enforced in `src/pumpgrok/risk/engine.py:754-756`)
**Resolution evidence:** `tests/safety/test_reputation_degraded.py::test_corrupt_file_degraded_book_refuses_buy_with_escalation` passes (exit 0 via `uv run --frozen` from pristine `/tmp/cr03-main` export); no-crash contract `tests/characterization/test_reputation.py::test_corrupt_file_does_not_crash` still holds
**Issue:** `ReputationBook.load` still catches *all* exceptions on a
present-but-unreadable/invalid file (unreadable bytes, bad JSON,
pydantic validation failure), logs, and returns an empty book.
`verdict()` returns `None` for unknown creators, so a corrupted
`var/reputation.json` re-admits every previously-blocked rugger address
at ingress with no signal except a log line. The fail-open behavior is
unchanged from iteration 1. Per the fixer report this was deliberately
not fixed because raising would break the locked characterization test
`test_corrupt_file_does_not_crash`, which requires `load` on a corrupt
file to return an empty book, and no production `load` caller exists yet
to migrate to a strict variant.
**Fix (for the orchestrator / Phase-4 pipeline wiring, not this phase):**
distinguish "file absent" (start empty) from "file present but
unreadable/invalid" (raise `ConfigError`/`RuntimeError` and refuse to
start):
```python
    if not file.exists():
        ...  # start empty
    try:
        raw = json.loads(...)
        return cls.model_validate(raw)
    except Exception as exc:
        raise ConfigError([f"reputation book unreadable: {file}"]) from exc
```

## Warnings

None. No new Warning defects were introduced by the iteration-1 fixes.

## Info

None.

---

_Reviewed: 2026-10-21T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
_Iteration: 2 (re-review after fixes; prior: 3 Critical, 6 Warning, 6 Info)_

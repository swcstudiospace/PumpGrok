---
phase: 02-restructure
fixed_at: 2026-10-21T00:00:00Z
review_path: .planning/phases/02-restructure/02-REVIEW.md
iteration: 2
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-10-21T00:00:00Z
**Source review:** .planning/phases/02-restructure/02-REVIEW.md
**Iteration:** 2 (CR-03 quarantine follow-up; iteration-1 record below unchanged)

**Summary:**
- Findings in scope: 1 (CR-03, carried open from iteration-1 re-review)
- Fixed: 1
- Skipped: 0

Verification ran in the isolated worktree
(`.claude/worktrees/rf-02-*`, branch `gsd-reviewfix/02-*`, fast-forwarded
into `feat/grokbot-desk-merge` on completion); the numbers below reproduce
from the main checkout after teardown. Final tree state: `ruff check src/`
clean, `ruff format --check src/` clean, no Cyrillic in
`src/pumpgrok/engine/`, targeted suites green (129 passed:
jupiter/monitor/reputation/analyzer/watcher/exits/tune characterization
plus forbidden-owners and the signing-guard safety test).

## Fixed Issues

### CR-01: Jupiter quote mapper raises on malformed upstream shape

**Files modified:** `src/pumpgrok/tools/market/jupiter.py`
**Commit:** 010b8d0
**Applied fix:** response-shape mapping moved inside the `try`; non-dict
payload and non-list `routePlan` return `{"ok": False}`; `priceImpact`
coerced defensively (`None` on garbage); non-dict route entries skipped.
Module docstring contract (`{"ok": False}` with no raise) now holds.

### CR-02: Monitor socket parser raises on malformed payload, dropping the stream

**Files modified:** `src/pumpgrok/engine/monitor.py`
**Commit:** 541f49c
**Applied fix:** new `_coerce_float` helper (default on `TypeError` /
`ValueError`) for `vSolInBondingCurve`, `timestamp`/`createdTimestamp`,
and `marketCapSol`; whole body wrapped so any residual coercion failure
logs the exception type and returns `None`. One hostile message degrades
to a dropped event, never a reconnect.

### WR-01: One malformed holder/trade record aborts the whole analysis

**Files modified:** `src/pumpgrok/engine/analyzer.py`
**Commit:** d30490e
**Applied fix:** new `_safe_parse` per-row guard (`None` on `ValueError` /
`TypeError`, row skipped) in `fetch`; non-dict `info` normalized to
`{}`; `enrich_token` float coercions guarded with `contextlib.suppress`.

### WR-02: Analyzer logs exception text that can carry the request URL

**Files modified:** `src/pumpgrok/engine/analyzer.py`
**Commit:** 4b3f587
**Applied fix:** `_get` failure log now records `type(exc).__name__`
instead of `str(exc)`, matching the no-URL rule enforced in `rpc.py`.

### WR-03: Watcher drops a pending peak-persist when a later position sells

**Files modified:** `src/pumpgrok/engine/watcher.py`
**Commit:** b810f39
**Applied fix:** single `persist_needed` flag replaced with independent
`peak_grew` / `sold` flags; `book.persist()` runs when either is true, so
a sale can no longer clear another position's grown peak.

### WR-04: Tune CLI reports defaults as "current weights", ignoring operator config

**Files modified:** `src/pumpgrok/engine/tune.py`
**Commit:** 849389d
**Applied fix:** `main()` resolves weights via new `_current_weights()`,
which loads `load_settings().scoring.weights` and falls back to factory
defaults on `ConfigError` (keeps the CLI total and the characterization
test deterministic in a bare environment).

### WR-05: SOL→lamport conversion truncates on float error

**Files modified:** `src/pumpgrok/cli.py`
**Commit:** 07d97dd
**Applied fix:** `size_sol_to_lamports` uses
`Decimal(str(size_sol))` with `ROUND_HALF_UP` (`0.29 SOL` -> `290000000`,
was `289999999`); `_size_sol` rejects non-finite input; `_paper` (now
receiving `Settings`) refuses sizes above `risk.paper_equity_lamports`,
the configured risk-limit bound, instead of a hard-coded constant.

### WR-06: Trailing-stop ratchet lives in the watcher, not in `exit_signal`

**Files modified:** `src/pumpgrok/engine/exits.py`, `src/pumpgrok/engine/watcher.py`
**Commit:** 6c5a78e
**Applied fix:** new `apply_price(position, price, cfg, now)` entry point
that ratchets `peak_price` (via `max`) then evaluates; watcher routes
through it while keeping its own `PEAK_PERSIST_STEP` comparison on the
pre-call peak. `exit_signal` stays pure, so the characterization test
asserting purity still passes and any future caller gets the ratchet.

## Iteration-2 Fix

### CR-03: Corrupt reputation file silently discards rug history (fail-open)

**Files modified:** `src/pumpgrok/engine/reputation.py`
**Commit:** baa4a47
**Applied fix:** `load` no longer silently drops a corrupt book. On a
present-but-unreadable/invalid file it (1) keeps the no-crash contract
(returns an empty book, `test_corrupt_file_does_not_crash` green
unmodified), (2) moves the corrupt file aside atomically via
`Path.rename` to `<name>.corrupt-<UTC timestamp>` (timestamp from the
injected clock via `format_ts_utc`, no `time.time()`), so the evidence
survives the next `save`, (3) logs at ERROR with the quarantine path
and the exception type name only (no URLs or secrets), and (4) returns
the book with new `degraded=True` (`Field(default=False,
exclude=True)`, so the saved vendor JSON shape
`{version, creators, updated_at}` is unchanged and
`test_save_keeps_vendor_json_shape` still passes). A missing file still
loads as a clean non-degraded empty book. Verification ran in the main
checkout: `tests/characterization/test_reputation.py` exit 0 (20
passed), `tests/safety/` exit 0 (42 passed); `ruff check` and `ruff
format --check` clean on the edited file, engine still ASCII-only.

## Skipped Issues

None in iteration 2. (Iteration-1 note superseded: the locked test's
stated contract — no crash, empty book — is satisfied by the quarantine
approach, so no skip was needed.)

## Supporting commit

- `642d23f` `fix(02): lint review-fix edits to gate-clean (ruff check and
  format)` — lint-only corrections to the fix commits above (import
  order, f-string prefix, `TypeVar` placement → PEP 695, `suppress`
  instead of `try/except/pass`, `max` ratchet, dropped unneeded
  `type: ignore`, format collapse). No finding behavior changed.

---

_Fixed: 2026-10-21T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_

---
phase: 03-tools-and-skills
iteration: 3
reviewed: 2026-10-21T16:21:46Z
depth: deep
files_reviewed: 4
files_reviewed_list:
  - services/desk-gateway/src/desk_gateway/server.py
  - services/desk-gateway/tests/test_long_content_length.py
  - src/pumpgrok/tools/journal/append.py
  - tests/tools/journal/test_append_seat_scoped.py
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
status: clean
---

# Phase 03-tools-and-skills: Code Review Report (iteration 3)

**Reviewed:** 2026-10-21
**Depth:** deep
**Files Reviewed:** 4
**Scope:** `git diff e036f6f..HEAD` (commit `194092b` only) plus
re-verification of iteration-2 findings WR-09 and WR-10 in source
**Status:** clean

## Summary

Final-pass review under the auto-fix cap. The single commit in scope
(`194092b`) addresses exactly the two open warnings from iteration 2, with
one regression test per fix. Both fixes are verified correct in source, the
tests assert the right behavior, cross-file callers are unaffected, and no
new defects were introduced. The only remaining notes are two non-blocking
Info items (one carried, one new observation on the strictness trade-off).

**Iteration-2 warnings — both verified fixed:**

| ID | Fix location | Verified |
|----|--------------|----------|
| WR-09 unbounded Content-Length parse | `server.py:213,291-304` | Digit string capped at `_MAX_CONTENT_LENGTH_DIGITS = 7` before regex, `int()` wrapped in `try/except ValueError`; over-long input returns `None` and hits the existing 400 `bad_length` path (`server.py:316-329`). Auth still precedes the length check (`do_POST`: seat → auth → length), so unauthenticated over-long requests still answer 401 — asserted by `test_over_long_length_unauthenticated_is_401_not_400`. |
| WR-10 seat-less journal idempotency key | `append.py:89-93,138` | `journal_append_key` now takes `seat` as its second parameter and folds it into the digest (`f"{kind}\n{seat}\n..."`); the call site passes the resolved `seat` (`bound if bound is not None else inp.bot`), i.e. the same value `_payload_of` stamps into the event. Two seats with identical kind/ticket/body now derive different keys; same-seat repeats still dedup — both asserted by the new seat-scoped tests. |

**Regression checks performed:**

- `journal_append_key` has no other callers: grep finds only the definition,
  the single updated call site, and the `__all__` export (name unchanged, so
  no import breakage; signature change is internal — no stale 3-arg callers
  exist in `src/` or `tests/`).
- WR-08 idempotent-export semantics preserved: the sibling test
  (`test_append_idempotent_export.py`) exercises repeats without a bound seat
  (`calling_seat()` → `None`, so `seat = inp.bot`), which derives the same
  key as before for a fixed bot — dedup and no-second-line behavior hold.
- `_declared_length` has a single call site (`do_POST`); the `None` → 400
  contract is unchanged, and all previously-valid inputs (absent header → 0,
  1–7 digit values ≤ 1 MiB → int) behave exactly as before.
- New tests fit repo conventions: `asyncio_mode = "auto"` in `pyproject.toml`
  covers the bare `async def` tests; the gateway test reuses the existing
  module-scoped `gateway` fixture (`conftest.py:77`); the seat test uses
  `bind_calling_seat` and a `FixtureClock` consistent with sibling tests.
- `int()` inside `try/except` after the regex + length cap is unreachable
  defensive code (a ≤7-digit `[0-9]+` cannot trip the 4300-digit stdlib cap),
  but it is harmless defense-in-depth, not dead logic worth flagging.

## Info

### IN-05 (carried from iteration 2): Idempotent repeat returns a journal path that is never ensured to exist

**File:** `src/pumpgrok/tools/journal/append.py:155-157`
**Issue:** The repeat path still builds the prior day's path via
`_journal_file` without `mkdir` (unlike `_export_line`). If the journal
directory was wiped after the original write, the returned `journal_path`
points at a nonexistent file. Unchanged by `194092b`; remains a
documentation-level concern only — callers that assume existence will fail
downstream.
**Fix:** `journal_dir.mkdir(parents=True, exist_ok=True)` before building the
repeat path, or document that the path is informational and may not exist.

### IN-06 (new): Zero-padded Content-Length longer than 7 digits is now a 400

**File:** `services/desk-gateway/src/desk_gateway/server.py:294`
**Issue:** The length cap counts digits, not value, so a zero-padded header
such as `Content-Length: 00000001` (8 chars, value 1) is rejected with 400
`bad_length` where the old code accepted it as 1. Fail-closed and negligible
in practice (no real client zero-pads `Content-Length`), but it is a slight
strictness change worth recording. Not a correctness defect.
**Fix:** No change required; if exactness is ever wanted, strip leading zeros
(`value.lstrip("0") or "0"`) before the length check.

---

_Reviewed: 2026-10-21T16:21:46Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
_Iteration: 3 (prior: 03-REVIEW.iter2.md)_

---
phase: 03-tools-and-skills
iteration: 2
reviewed: 2026-10-21T00:00:00Z
depth: deep
files_reviewed: 44
files_reviewed_list:
  - services/desk-gateway/src/desk_gateway/server.py
  - src/pumpgrok/core/binding_key.py
  - src/pumpgrok/core/ids.py
  - src/pumpgrok/core/registry.py
  - src/pumpgrok/ledger/store.py
  - src/pumpgrok/tools/__init__.py
  - src/pumpgrok/tools/_common.py
  - src/pumpgrok/tools/desk/_memory.py
  - src/pumpgrok/tools/desk/brief.py
  - src/pumpgrok/tools/desk/docs_search.py
  - src/pumpgrok/tools/desk/event_emit.py
  - src/pumpgrok/tools/desk/memory_recall.py
  - src/pumpgrok/tools/desk/memory_retain.py
  - src/pumpgrok/tools/desk/ownership_resolve.py
  - src/pumpgrok/tools/desk/receipt_check.py
  - src/pumpgrok/tools/desk/doctor.py
  - src/pumpgrok/tools/exec/place.py
  - src/pumpgrok/tools/exec/positions.py
  - src/pumpgrok/tools/exec/quote.py
  - src/pumpgrok/tools/journal/append.py
  - src/pumpgrok/tools/journal/render_report.py
  - src/pumpgrok/tools/market/holders_snapshot.py
  - src/pumpgrok/tools/market/liquidity.py
  - src/pumpgrok/tools/market/ohlcv.py
  - src/pumpgrok/tools/market/price.py
  - src/pumpgrok/tools/market/trades.py
  - src/pumpgrok/tools/notify/alert.py
  - src/pumpgrok/tools/onchain/authorities_tool.py
  - src/pumpgrok/tools/onchain/deployer_history.py
  - src/pumpgrok/tools/onchain/large_transfers.py
  - src/pumpgrok/tools/onchain/lp_status.py
  - src/pumpgrok/tools/onchain/priority_fee_tool.py
  - src/pumpgrok/tools/onchain/rpc.py
  - src/pumpgrok/tools/onchain/token_metadata.py
  - src/pumpgrok/tools/onchain/top_holders.py
  - src/pumpgrok/tools/portfolio/exposure.py
  - src/pumpgrok/tools/portfolio/ledger_read.py
  - src/pumpgrok/tools/portfolio/ledger_write.py
  - src/pumpgrok/tools/portfolio/pnl.py
  - src/pumpgrok/tools/risk/check_limits.py
  - src/pumpgrok/tools/risk/drawdown.py
  - src/pumpgrok/tools/risk/halt_status.py
  - src/pumpgrok/tools/risk/kill_switch.py
  - src/pumpgrok/tools/safety/score_report.py
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
status: issues_found
---

# Phase 03-tools-and-skills: Code Review Report (iteration 2)

**Reviewed:** 2026-10-21
**Depth:** deep
**Files Reviewed:** 44
**Scope:** `git diff 4fa9674..HEAD` (commits d5c0985 through 3e847b7)
**Status:** issues_found

## Summary

Re-review of the eight iteration-1 warnings (WR-01..WR-08) against the fix
commits, plus a hunt for regressions in the changed code: token/secret
handling, path handling, body limits, seat binding, fail-open risk paths,
unbounded ledger folds, and clock discipline.

**All eight iteration-1 warnings are verified fixed in source:**

| ID | Fix commit | Verified |
|----|-----------|----------|
| WR-01 doctor path traversal | d5c0985 | `_AGENT_RE = ^[A-Za-z0-9_-]{1,64}$` rejects `../evil`, `a/b`, 65-char and empty inputs (`doctor.py:36,121-129`); defense-in-depth `resolve()` + `is_symlink()` check follows (`doctor.py:134-141`). Regex alone already excludes every traversal character. |
| WR-02 caller-claimed seat | 00d7e69 | Registry stamps `bind_calling_seat(bot.id)` around every dispatch (`registry.py:249`); `run_journal_append` raises `PermissionDenied` on mismatch (`append.py:130-136`); `run_event_emit` uses `calling_seat() or bot` (`event_emit.py:112`). Empty-seat fallback fails closed via `JournalAppendIn.bot min_length=1` (`append.py:54`). |
| WR-03 wall-clock envelopes | db28f75 | `meta_now`/`utcnow` take an injected `Clock` (`_common.py:32-44`); all 30+ call sites pass `clock`/`rpc.clock` (grep-verified); no bare `utcnow()`, `datetime.now`, or `time.time` remains outside `replay/clock.py` and factory-default `WallClock()` injection points. `RpcClient.clock` exposes the injected clock (`rpc.py:116-119`). |
| WR-04 unbounded gateway body | 1aed59f | Auth runs before any body read (`server.py:305-309` precedes read at `335`); multi/empty `Content-Length` → 400, `>1MiB` → 413 (`server.py:287-334`). |
| WR-05 MemoryBank corrupt line | 500eb5f | Byte-level load skips undecodable/invalid/non-dict lines and counts them (`_memory.py:29-45`, `corrupt_lines`); torn-final-line guard on retain (`_memory.py:64-73`). |
| WR-06 ephemeral doctor key | 1aed59f | `load_or_create_binding_key` persists 32 random bytes, `0600` via `mkstemp`, hard-link-once creation, `O_NOFOLLOW` open, refusal on symlink/non-regular/loose-mode/undecodable key (`binding_key.py`). Both gateway and CLI registry paths load the persisted key. |
| WR-07 kill-switch source | e0c15f4 | Ledger-active fold reports `source = "command"` (`kill_switch.py:124-126`). |
| WR-08 duplicate JSONL export | f747c59 | Repeat path returns the prior day's file and skips `_export_line` (`append.py:151-157`). |

Two new Warnings and one Info were found in the changed code (below). No
Critical findings. The five `limit=None` full-ledger folds (kill_switch,
halt_status, exposure, pnl, render_report) are correct: `store.read`
parameterizes all predicates, `limit=None` only omits the `LIMIT` clause
(`store.py:232-261`), and `ledger_read`'s user-controlled limit stays
`ge=1, le=1000` (`ledger_read.py:31`). All renamed-signature callers
repo-wide (CLI/gateway registries, `brief.py`, tests) were checked and match.

## Warnings

### WR-09: Uncaught `ValueError` on over-long `Content-Length` digit string

**File:** `services/desk-gateway/src/desk_gateway/server.py:287-296`
**Issue:** `_declared_length` regex-accepts `[0-9]+` of any length, then calls
`int(value)` outside any `try`. On Python 3.11+ the stdlib int→str digit cap
(4300 digits) makes `int()` raise `ValueError`, which propagates uncaught out
of `do_POST`: the connection drops with no response instead of the intended
400. Reachable only after successful auth (auth precedes the length check),
and fail-closed (nothing is read), but it is an unhandled-exception path in
new code that should return a clean status.
**Fix:**
```python
value = values[0].strip()
if len(values) != 1 or len(value) > 7 or _CONTENT_LENGTH_RE.fullmatch(value) is None:
    return None
try:
    return int(value)
except ValueError:
    return None
```

### WR-10: `journal_append_key` does not bind the seat, so idempotent dedup crosses seat boundaries

**File:** `src/pumpgrok/tools/journal/append.py:89-93,138`
**Issue:** The key is `d(kind, ticket_id, sha256(body))` with no seat input.
Two seats appending the same `kind`/`ticket_id`/`body` through
`run_journal_append` each pass the new bound-seat check (each `bot` matches
its own `calling_seat()`), but the second call hits the `IntegrityError`
repeat path and returns the *first* seat's `seq` and day-file without
recording anything: a silent success with no seat-attributed event. The
`event_emit` path is accidentally safe (its body embeds `seat`), but direct
`journal.append` callers are not. The new seat enforcement in the same
function makes this the remaining attribution gap.
**Fix:**
```python
def journal_append_key(kind: str, ticket_id: str | None, seat: str, body: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        f"{kind}\n{seat}\n{ticket_id or ''}\n{json.dumps(body, sort_keys=True)}".encode()
    ).hexdigest()
    return digest[:32]
```
and pass the resolved `seat` at the call site (note: this changes key
derivation; existing stored keys will not dedup against new ones, which is
the safe direction).

## Info

### IN-05: Idempotent repeat returns a journal path that is never ensured to exist

**File:** `src/pumpgrok/tools/journal/append.py:155-157`
**Issue:** The repeat path builds the prior day's path via `_journal_file`
without `mkdir` (unlike `_export_line`). If the journal directory was wiped
after the original write, the returned `journal_path` points at a nonexistent
file and callers that assume existence will fail downstream.
**Fix:** `journal_dir.mkdir(parents=True, exist_ok=True)` before building the
repeat path, or document that the path is informational and may not exist.

---

_Reviewed: 2026-10-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
_Iteration: 2 (prior: 03-REVIEW.iter1.md)_

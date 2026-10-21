---
phase: 03-tools-and-skills
reviewed: 2026-10-21T00:00:00Z
depth: standard
files_reviewed: 31
files_reviewed_list:
  - services/desk-gateway/src/desk_gateway/server.py
  - services/desk-gateway/src/desk_gateway/config.py
  - services/desk-gateway/tests/conftest.py
  - src/pumpgrok/core/registry.py
  - src/pumpgrok/core/idempotency.py
  - src/pumpgrok/core/manifests.py
  - src/pumpgrok/contracts/projection.py
  - src/pumpgrok/ledger/store.py
  - src/pumpgrok/tools/__init__.py
  - src/pumpgrok/tools/_common.py
  - src/pumpgrok/tools/desk/receipt_check.py
  - src/pumpgrok/tools/desk/docs_search.py
  - src/pumpgrok/tools/desk/ownership_resolve.py
  - src/pumpgrok/tools/desk/event_emit.py
  - src/pumpgrok/tools/desk/doctor.py
  - src/pumpgrok/tools/desk/_tokens.py
  - src/pumpgrok/tools/desk/_memory.py
  - src/pumpgrok/tools/desk/brief.py
  - src/pumpgrok/tools/desk/memory_retain.py
  - src/pumpgrok/tools/desk/memory_recall.py
  - src/pumpgrok/tools/social/client.py
  - src/pumpgrok/tools/notify/notifier.py
  - src/pumpgrok/tools/notify/allowlist.py
  - src/pumpgrok/tools/notify/alert.py
  - src/pumpgrok/tools/onchain/rpc.py
  - src/pumpgrok/tools/exec/place.py
  - src/pumpgrok/tools/exec/cancel.py
  - src/pumpgrok/tools/risk/kill_switch.py
  - src/pumpgrok/tools/risk/halt_status.py
  - src/pumpgrok/tools/risk/check_limits.py
  - src/pumpgrok/tools/risk/drawdown.py
findings:
  critical: 0
  warning: 8
  info: 4
  total: 12
status: issues_found
---

# Phase 03-tools-and-skills: Code Review Report

**Reviewed:** 2026-10-21
**Depth:** standard
**Files Reviewed:** 31
**Status:** issues_found

## Summary

Standard-depth review of the phase 3 product and service code: registry and
idempotency core, desk-gateway auth and dispatch, all write-side tools
(exec/journal/portfolio/risk/notify/desk), the shared READ helpers, the RPC
client, the CLI approval path, seat rosters, and skill security posture.

The load-bearing invariants hold: money stays int/Decimal at every reviewed
boundary, exec.place/exec.cancel require approval_id and fail closed through
the refusing limits checker, LIVE_WRITE is registered-but-never-resolvable,
least-privilege rosters grant no seat ledger_write, the gateway compares
bearer tokens with hmac.compare_digest across all seats, and skill files carry
no LIVE_WRITE or key material. No Critical findings.

Eight Warnings remain, all verified against source: an unsanitized filename in
desk.doctor register (path traversal inside the data dir), caller-claimed seat
attribution on journal writes plus a hardcoded chief binding on event_emit,
envelope timestamps that bypass the injected Clock (R27), an unbounded gateway
request body read before authentication, a MemoryBank startup crash on one
corrupt line, an ephemeral doctor HMAC key that breaks re-verification after
restart, a kill-switch status that reports source none while ledger-active,
and a duplicate JSONL export line on idempotent journal repeats.

## Warnings

### WR-01: desk.doctor register writes to an unsanitized caller-controlled path

**File:** `src/pumpgrok/tools/desk/doctor.py:40,113`

**Issue:** `DoctorIn.agent_uuid` is a free-form optional string with no
pattern, and `_register_rows` interpolates it directly into a filesystem
path: `record = bindings_dir / f"{inp.agent_uuid}.json"`, followed by
`record.write_text(...)` when no record exists and `record.read_text(...)`
when one does. A value such as `../alerts` escapes the bindings directory
and writes attacker-shaped JSON elsewhere under the data dir; a pre-planted
symlink at the target is followed by both the read and the write. The tool
is PAPER_WRITE and desk.doctor is in the core eight, so every seat can reach
it. Impact is bounded (`.json` suffix, JSON-shaped content, data dir only),
so this is a Warning, not Critical.

**Fix:**
```python
_AGENT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# in _register_rows, before building the path:
if not _AGENT_RE.fullmatch(inp.agent_uuid or ""):
    return False, [{"check": "register", "status": "fail",
                     "detail": "agent_uuid must be [A-Za-z0-9_-], max 64"}]
```

### WR-02: Seat attribution on ledger writes is caller-claimed or hardcoded

**File:** `src/pumpgrok/tools/journal/append.py:50`, `src/pumpgrok/tools/desk/event_emit.py:110-135`, `src/pumpgrok/tools/__init__.py:192`, `services/desk-gateway/src/desk_gateway/server.py:162`

**Issue:** Two facets of one integrity gap. (a) `JournalAppendIn.bot` is a
free-form string (`min_length=1, max_length=64`) with no check against the
calling seat, and `run_journal_append` stores it verbatim as the ledger
`seat`. The gateway passes tool arguments straight through, so any seat
holding journal.append (all ten rosters) can file entries attributed to any
other seat. (b) `build_event_emit_tool` is bound with the literal seat
`"bot-00-chief"` in both composition roots, so every seat's
desk.event_emit journal_note is attributed to chief regardless of caller.
The ledger audit trail is therefore unreliable for who-wrote-what.

**Fix:** Bind the seat server-side instead of trusting input: pass the
resolved manifest seat id into the journal/event factories (gateway
`_tools_call` already knows `seat_id`; CLI `_with_tools` knows the
manifest), set `seat` from that binding, and either drop `JournalAppendIn.bot`
or validate `inp.bot == bound_seat` and refuse on mismatch.

### WR-03: Envelope timestamps bypass the injected Clock (R27)

**File:** `src/pumpgrok/tools/_common.py:32-34`

**Issue:** `utcnow()` is documented as "Wall-clock now for envelope stamps
via the replay clock" but is implemented as
`datetime.fromtimestamp(WallClock().now(), UTC)`, constructing a fresh wall
clock on every call. `meta_now` uses it, so every tool envelope's
`fetched_at`/`freshness_s` is stamped with real time even when the registry
runs under a FixtureClock. This breaks replay determinism for every tool at
once and contradicts the Clock-only rule the module docstring itself cites
("only `replay/clock.py` may touch it" refers to `datetime.now`, but the
same rule covers fresh `WallClock()` instances in tool code).

**Fix:** Thread the bound clock through: change `meta_now` to accept the
calling tool's clock (e.g. `meta_now(source, correlation_id, clock)`), or
store the active clock in a contextvar set by the registry wrapper, and
delete the `WallClock()` construction from `_common.py`.

### WR-04: Gateway reads the full request body before authenticating, with no size cap

**File:** `services/desk-gateway/src/desk_gateway/server.py:285-287`

**Issue:** `do_POST` does `length = int(self.headers.get("Content-Length") or
0)` then `raw = self.rfile.read(length)` before `_authenticate` runs, and no
maximum is enforced anywhere on the handler. An unauthenticated client can
make the server buffer an arbitrarily large body (memory exhaustion), and a
malformed non-integer Content-Length raises an unhandled ValueError (the
`int(...)` conversion is outside any try), killing that connection with a
traceback instead of a 400. Auth must come first and the body must be
bounded for a seat-exposed HTTP service.

**Fix:**
```python
_MAX_BODY_BYTES = 1 << 20  # 1 MiB; tool arguments are small JSON
try:
    length = int(self.headers.get("Content-Length") or 0)
except ValueError:
    self._send_json(400, {"error": {"code": "bad_length", ...}})
    return
if length < 0 or length > _MAX_BODY_BYTES:
    self._send_json(413, {"error": {"code": "body_too_large", ...}})
    return
# authenticate the seat BEFORE reading the body
```

### WR-05: One corrupt MemoryBank line crashes every CLI/gateway startup

**File:** `src/pumpgrok/tools/desk/_memory.py:30`

**Issue:** `MemoryBank.__init__` does `record = json.loads(line)` with no
guard. A single corrupt line in `memory.jsonl` raises out of the
constructor, and both composition roots construct the bank unconditionally
at startup, so one poisoned line breaks all verbs (fail-open crash, not
fail-closed). The codebase already established the opposite discipline for
untrusted rows (phase 2 WR-01: skip poisoned holder/trade rows).

**Fix:**
```python
try:
    record = json.loads(line)
except json.JSONDecodeError:
    continue
```
plus a one-line log naming the file (never the line content).

### WR-06: Doctor binding key is ephemeral, so register never survives restart

**File:** `src/pumpgrok/tools/__init__.py:193`, `services/desk-gateway/src/desk_gateway/server.py:167`

**Issue:** Both composition roots pass `os.urandom(32)` as the doctor
`binding_key` on every build. Bindings persist under `data_dir/bindings`,
but the key that minted them is discarded with the process, so after any
restart every re-registration reports "binding mismatch" and no two
processes (CLI vs gateway) ever agree. Registration is permanently
single-process-lifetime, which defeats the purpose of a persisted binding.

**Fix:** Derive the key from persisted material: generate once with
`os.urandom(32)`, store it mode-0600 under the data dir on first boot, and
reload it thereafter (or take it from an explicit `DESK_BINDING_KEY_FILE`
setting like the gateway tokens).

### WR-07: Kill-switch status reports source none while ledger-engaged

**File:** `src/pumpgrok/tools/risk/kill_switch.py:120-126`

**Issue:** `_status` maps env to `"env"` and file to `"file"`, but the final
`else` assigns `"none"` even when `ledger_active` is true. A killswitch
engaged purely through the ledger (the normal tool path) returns
`active=True` with `source="none"`, and the `KillSwitchOut.source` Literal
even offers `"command"` yet no branch ever assigns it. Operators reading the
status cannot tell a ledger engagement from no engagement source at all.

**Fix:**
```python
if env_set:
    source = "env"
elif file_set:
    source = "file"
elif ledger_active:
    source = "command"
else:
    source = "none"
```

### WR-08: Idempotent journal repeat still appends a duplicate JSONL export line

**File:** `src/pumpgrok/tools/journal/append.py:130-146`

**Issue:** On `sqlite3.IntegrityError` the ledger row correctly dedups via
`store.by_key`, but `_export_line` runs unconditionally afterwards, so a
retried append writes a second line for the same seq into the day's journal
file. The spec marks the tool `idempotent=True`; the ledger honors it but
the export layer does not, and downstream report folds or replays reading
the JSONL will double-count the entry.

**Fix:** Only export on a fresh insert; on the duplicate path, return the
existing row's seq and journal path without appending (or check
`by_key` first and skip the export when the key already exists).

## Info

### IN-01: Notifier dedup cache is process memory only

**File:** `src/pumpgrok/tools/notify/notifier.py:64-70`

**Issue:** `_seen_keys` suppresses minute-key repeats only within one
process. After a restart the set is empty, so the same alert re-sends
(stdout, file, and network sinks). Noise/duplication only; no money or
safety impact.

**Fix:** Persist recent keys alongside the alert file, or accept and
document process-lifetime dedup in the Notifier docstring.

### IN-02: docs_search reads whole files with no size cap

**File:** `src/pumpgrok/tools/desk/docs_search.py:60-80`

**Issue:** `_iter_text_files` collects every file under docs/skills/contracts
and `run_docs_search` reads each fully into memory. A large checked-in file
balloons per-call memory; any seat can invoke it repeatedly (READ tool in
the core eight). No binary sniffing beyond a per-line NUL check, which still
requires the full read first.

**Fix:** Skip files over a fixed size (e.g. 1 MiB via `stat().st_size`)
before reading.

### IN-03: CLI constructs the production ledger file even for refused verbs

**File:** `src/pumpgrok/cli.py:222-227`

**Issue:** `_with_tools` calls `build_operator_registry` with
`data_dir=Path("var")/desk` before resolving finds, and the build constructs
`LedgerStore`, creating `var/desk/ledger.sqlite` on disk even when the verb
is then refused (bad seat, missing grant, unknown approval). Read-only or
refused invocations should not create state files as a side effect.

**Fix:** Defer `LedgerStore` creation (lazy factory) until a tool actually
needs it, or resolve finds against manifests before building backends.

### IN-04: Known lint side notes (accepted, no action beyond acknowledgment)

**File:** `services/desk-gateway/tests/*:type: ignore[attr-defined]`, `tests/registry_harness.py:type: ignore[arg-type]`

**Issue:** Per the assignment brief these remain as Info only: `# type:
ignore[attr-defined]` on `gateway_state` in the desk-gateway tests, and one
`# type: ignore[arg-type]` at the RPC MockTransport line in
`tests/registry_harness.py`. Both are typed-ignore hygiene, not behavior.

**Fix:** None required; remove if the harness is ever retyped to expose
`gateway_state` on the server class.

---

_Reviewed: 2026-10-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

---
phase: 01-foundation
reviewed: 2026-10-21T03:11:18Z
depth: deep
files_reviewed: 32
files_reviewed_list:
  - .env.example
  - docs/design/paper-engine.md
  - src/pumpgrok/config/overlays/dev.toml
  - src/pumpgrok/config/overlays/live.toml
  - src/pumpgrok/config/overlays/paper.toml
  - src/pumpgrok/config/settings.py
  - src/pumpgrok/core/__init__.py
  - src/pumpgrok/core/adapter.py
  - src/pumpgrok/core/approvals.py
  - src/pumpgrok/core/atomic_write.py
  - src/pumpgrok/core/bot.py
  - src/pumpgrok/core/correlation.py
  - src/pumpgrok/core/datasource.py
  - src/pumpgrok/core/errors.py
  - src/pumpgrok/core/idempotency.py
  - src/pumpgrok/core/ids.py
  - src/pumpgrok/core/interfaces.py
  - src/pumpgrok/core/registry.py
  - src/pumpgrok/core/side_effect.py
  - src/pumpgrok/core/skill.py
  - src/pumpgrok/core/tool.py
  - src/pumpgrok/ledger/__init__.py
  - src/pumpgrok/ledger/events.py
  - src/pumpgrok/ledger/store.py
  - tests/config/test_forbidden_keys.py
  - tests/config/test_secret_refusal.py
  - tests/config/test_settings.py
  - tests/core/test_ids.py
  - tests/core/test_models.py
  - tests/core/test_registry.py
  - tests/ledger/test_events.py
  - tests/ledger/test_store.py
findings:
  critical: 1
  warning: 9
  info: 14
  total: 24
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-10-21T03:11:18Z
**Depth:** deep
**Files Reviewed:** 32
**Status:** issues_found

## Summary

Scope is the file set named by the SUMMARY.md artifacts of plans 01-02, 01-03 and 01-04 (`task-commits` evaluation scope, base `1f7cb6ef`). Review covered the config loader and startup guards, the hash-chained ledger store and event models, the core contracts (ids, idempotency, approvals, registry, tool, bot, adapter), and the tests for each slice. Cross-module call chains were traced for: `ToolRegistry.find` -> `_wrap` -> `tool()` -> `Tool.__call__`; `LedgerStore.append` -> `_row_hash` -> `canonical_json`; `ApprovalRecord.matches` -> `OrderRequest`; `load_settings` -> `collect_startup_problems` -> `Settings` -> overlays. Several defects were confirmed by targeted runtime probes outside the test suite (not run here): the `.env.example` key check, `mask()` output, the `atomic_write_json` temp-file leak, ledger acceptance of unknown event types, snapshot overwrite, the span counter across roots, and the `PUMPGROK_PROFILE=live` effective mode.

The most important issue is CR-01: the documented `.env.example` template cannot be loaded by the loader as written. The remaining warnings concern a duplicated risk-budget schema, unenforced retry/rate-limit contracts, a weakened secret mask, and ledger write paths that bypass the R32 closed models. `docs/design/paper-engine.md` was reviewed by targeted search and selected sections, not line by line; the source and test files were read in full.

## Critical Issues

### CR-01: `.env.example` documents 18 keys the loader refuses at startup

**File:** `.env.example:5-40`
**Issue:** The header states "Every key is read by pydantic-settings with prefix PUMPGROK_." The loader does not do that. `load_settings()` runs `find_unknown_env()` against the names declared on `Settings` (`allowed_env_names()`), and raises `ConfigError` for any `PUMPGROK_*` name it does not know. Of the 23 assignments in the template, 18 are unknown to the current models: `PUMPGROK_VAR_DIR`, `PUMPGROK_LOG_LEVEL`, `PUMPGROK_LOG_JSON`, `PUMPGROK_HEALTH_PORT`, `PUMPGROK_DATA__REST_URL`, `PUMPGROK_DATA__WS_URL`, `PUMPGROK_SOLANA__RPC_URLS`, `PUMPGROK_SOLANA__RPC_API_KEY`, `PUMPGROK_ALERTS__TELEGRAM_BOT_TOKEN`, `PUMPGROK_ALERTS__TELEGRAM_CHAT_ID`, `PUMPGROK_ALERTS__WEBHOOK_URL`, `PUMPGROK_KILLSWITCH`, `PUMPGROK_LIVE_ENABLE`, `PUMPGROK_LIVE__MIN_PAPER_DAYS`, `PUMPGROK_LIVE__WALLET_ALLOWLIST`, `PUMPGROK_LIVE__NOTIONAL_CAP_SOL`, `PUMPGROK_LIVE__CONFIRMATION_RECORD`, `PUMPGROK_LIVE__ADAPTER`. `LiveSettings` declares only `enabled`. Following the documented setup path (export or compose `env_file` from this template) makes every start fail. The failure is loud, but the template is wrong, and the claim in its header is false.
**Fix:** Either trim the template to the keys `Settings` declares (`PUMPGROK_PROFILE`, `PUMPGROK_CONFIG`, `PUMPGROK_MODE`, `PUMPGROK_RISK__*`, `PUMPGROK_REPLAY__SEED`, `PUMPGROK_LIVE__ENABLED`), or declare the remaining settings in their owning models in the same change. Do not ship the template in its current form. Add a test that loads `.env.example` through `find_unknown_env` so drift fails in CI:

```python
def test_env_example_keys_are_declared(clean_env):
    keys = [line.split("=", 1)[0].strip() for line in ENV_EXAMPLE.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#") and "=" in line]
    assert find_unknown_env({k: "x" for k in keys}, allowed_env_names()) == []
```

## Warnings

### WR-01: Two `RiskBudget` schemas with diverging fields

**File:** `src/pumpgrok/config/settings.py:93-106`, `src/pumpgrok/core/bot.py:25-50`
**Issue:** `bot.py` describes its `RiskBudget` as "The ONLY risk-budget schema (R20)", and the design doc's `risk/limits.py` entry says the `[risk]` block is the only schema. The code has two classes with the same name. `bot.RiskBudget` adds `paper_equity_sol` and a `daily_loss_halt_fraction` validator. `settings.RiskBudget` has neither. Both are `extra="forbid"`. The `[risk]` overlay values are validated only against the settings copy, while seat `risk_budget` manifests are validated against the bot copy, so one limit can pass one check and fail the other.
**Fix:** Move one definition into a shared module (e.g. `core/risk_budget.py`) and import it from both `config/settings.py` and `core/bot.py`. Keep `paper_equity_sol` in the shared class, or make it explicit that it is not an overlay key.

### WR-02: `mask()` reveals almost all of a short secret

**File:** `src/pumpgrok/config/settings.py:84-90`
**Issue:** For any secret longer than 8 characters the function returns the first four and last four characters plus the length. Verified: `mask("123456789")` returns `1234...6789 (9 chars)`, which shows 8 of 9 characters. Secrets of 9 to 11 characters are almost fully disclosed in logs, which is the case this helper exists to prevent. The helper is also unused in `src/` (only `tests/config/test_secret_refusal.py` calls it), so the defect has no runtime path yet but is a trap for the next caller.
**Fix:** Return a fixed-width placeholder with no characters from the secret:

```python
def mask(secret: str) -> str:
    if not secret:
        return "<empty>"
    return f"*** ({len(secret)} chars)"
```

### WR-03: `atomic_write_json` leaks its temp file on non-OSError failures

**File:** `src/pumpgrok/core/atomic_write.py:17-30`
**Issue:** The cleanup `except OSError:` only runs for OS errors. `json.dump` raises `TypeError` for non-JSON leaves (for example a `Decimal` in `state`), and that path leaves `state.json.tmp<pid>` behind. Verified: `atomic_write_json(p, {"amt": Decimal("1.5")})` raises `TypeError` and leaves `state.json.tmp<pid>` in the directory. The test `test_atomic_write_fails_loudly_and_leaves_no_tmp` covers only the `OSError` path.
**Fix:**

```python
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(dict(payload), fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
```

Add a test that passes a non-JSON leaf and asserts no `*.tmp*` file remains.

### WR-04: `write_snapshot` silently overwrites and is not append-only

**File:** `src/pumpgrok/ledger/store.py:223-228` (schema at lines 50-54)
**Issue:** The docstring says snapshots are "append-only like events", but the `snapshots` table has no `BEFORE UPDATE` or `BEFORE DELETE` triggers, and `write_snapshot` uses `INSERT OR REPLACE`. Verified: two calls with `seq=1` leave one row with the second state, with no error. A snapshot can therefore be rewritten after the fact without touching the hash chain, and the verifier does not cover snapshots at all.
**Fix:** Add the same append-only triggers used for `events` to `snapshots`, and use plain `INSERT` so a duplicate `seq` raises. Make the docstring match the behaviour, and cover snapshots in `verify()` or document that they are excluded.

### WR-05: `LedgerStore.append` accepts any event type and payload

**File:** `src/pumpgrok/ledger/store.py:111-126`, `src/pumpgrok/ledger/events.py:309-328`
**Issue:** `append` validates only `source` and non-empty strings. The `type` string and `payload` are not checked against `EVENT_MODELS`, so the R32 closed vocabulary and `extra="forbid"` rules are not enforced on the write path. Verified: `append(type="NotARealEvent", payload={"anything": "goes"})` returns `seq 1` and the chain verifies. The audit log's schema guarantee is therefore conventional, not enforced. No caller in this phase exploits it, which is why this is a warning and not critical.
**Fix:** Validate before hashing:

```python
model = EVENT_MODELS[EventType(type)]          # raises ValueError for unknown types
payload_json = canonical_json(model.model_validate(dict(payload)).model_dump(mode="json"))
```

### WR-06: Registry claims retry, rate limiting and critical alerts that are not implemented

**File:** `src/pumpgrok/core/registry.py:189-218`, `src/pumpgrok/core/registry.py:42-47`, `src/pumpgrok/core/tool.py:16-25,57-72,102-107`
**Issue:** `_wrap` applies only the timeout. `ToolSpec.retry` (`RetryPolicy`) and `ToolSpec.rate_limit_key` are never read outside `tool.py`; the code comment "retries use tenacity(...)" describes behaviour that does not exist. The `tool()` docstring and `_wrap` docstring both say retry and rate limit are applied. `GrantAudit`'s docstring says every LIVE_WRITE attempt "is also emitted as a critical alert", and `_refuse` only appends to the audit sink. Declared policy that is silently ignored is worse than no policy: a tool declared `attempts=3` runs once.
**Fix:** Either implement the retry (tenacity with `clock.sleep`), rate limiting, and alert emission now, or remove the unused fields and correct the docstrings and the comment. If deferred to a later plan, say so in the docstrings and do not declare `retry` on specs until it is wired.

### WR-07: Span counter is not per-root, contrary to the documented contract

**File:** `src/pumpgrok/core/ids.py:70-108`
**Issue:** `CorrelationId` documents child spans as `<ulid>.<n>` with `n` the "1-based span counter of the root's dynamic extent". `next_span` uses one process-wide `ContextVar`, and `bind_correlation` does not reset it. Verified: after binding root A and then root B, the first span under B is `B.2`, not `B.1`. Uniqueness still holds, but the numbering is not per root, and replay determinism now depends on the order in which roots were bound in the process.
**Fix:** Reset the counter when a correlation is bound, saving the token from `__enter__`:

```python
class bind_correlation:
    def __enter__(self) -> CorrelationId:
        self._token = _correlation.set(self._cid)
        self._span_token = _span_counter.set(0)
        return self._cid

    def __exit__(self, *exc: object) -> None:
        _span_counter.reset(self._span_token)
        _correlation.reset(self._token)
```

### WR-08: Sell approvals do not bind the sell quantity, and `matches` ignores `kind`

**File:** `src/pumpgrok/core/approvals.py:78-87`
**Issue:** `matches` skips `size_lamports` when the request side is `sell`. A `human_sell` approval carries a SOL-denominated `size_lamports` and no token quantity, so an approved sell on a ticket and mint can fill any token amount. `matches` also does not check `kind`, so any unconsumed approval whose ticket, mint and slippage fields equal the request's would match, whatever its kind. Current constructors make most cross-kind collisions unlikely because `mint` and `ticket_id` are `None` for several kinds, but nothing enforces it.
**Fix:** Bind the sell quantity explicitly (add `token_units` to `ApprovalRecord` and compare it for sells), and restrict matching to the kinds that may authorise an order:

```python
_ORDER_KINDS = {"human_buy": "buy", "human_sell": "sell", "exit_rule": "sell"}
def matches(self, request: OrderRequest) -> bool:
    if _ORDER_KINDS.get(self.kind) != request.side.value or self.consumed:
        return False
    ...
```

If an unbound sell is intentional, record that decision in the design doc.

### WR-09: `PUMPGROK_PROFILE=live` loads with effective mode `live` and nothing refuses it

**File:** `src/pumpgrok/config/settings.py:129-181`, `src/pumpgrok/config/overlays/live.toml:8-9`
**Issue:** With `PUMPGROK_PROFILE=live`, `load_settings()` returns `effective_mode == "live"` (verified; `live.enabled` is `False`). Nothing in this layer refuses it. The design (section 7.2) puts the refusal in the live gate, which is not in this tree yet, so the outcome depends on a later module that is not present. Any consumer that branches on `effective_mode` before the gate lands would run live intent.
**Fix:** Until the live gate exists, make `load_settings()` raise `ConfigError` when `effective_mode == "live"`, with a message that names the missing gate. Remove that guard when the gate is wired.

## Info

### IN-01: Unreachable float branch in `_normalize`

**File:** `src/pumpgrok/core/idempotency.py:18-20`
**Issue:** The first branch tests `isinstance(value, float)` inside the `(str, bool, int)` branch, which can never be true. The `pragma: no cover` marks it, but the code is dead.
**Fix:** Delete the two dead lines.

### IN-02: Duplicated correlation helpers and inconsistent validation

**File:** `src/pumpgrok/core/correlation.py:12-27`, `src/pumpgrok/core/ids.py:83-88`
**Issue:** `root_of` duplicates `CorrelationId.root`. `child_span` rejects `n < 1`, but `CorrelationId.child(n)` accepts any `n`.
**Fix:** Have `correlation.py` delegate to the `CorrelationId` methods, and validate `n` in `child()`.

### IN-03: `derive_idempotency_key` docstring overstates the exclusion

**File:** `src/pumpgrok/core/idempotency.py:49-65`
**Issue:** The docstring says fields named `correlation_id` are excluded. Only top-level keys are filtered; a nested `correlation_id` is still hashed.
**Fix:** Say "top-level `correlation_id`", or filter recursively if nested ids are possible.

### IN-04: No directory fsync after `os.replace`

**File:** `src/pumpgrok/core/atomic_write.py:23-27`
**Issue:** The rename is not made durable. On POSIX a crash after `os.replace` can lose the new name, even though the file contents were fsynced.
**Fix:** After `os.replace`, open the parent directory and `os.fsync` it.

### IN-05: Duplicate pragmas and duplicate source enumeration

**File:** `src/pumpgrok/ledger/store.py:31-34,105-109`, `src/pumpgrok/ledger/events.py:31`
**Issue:** WAL and synchronous pragmas are set once in `__init__` and again in `_SCHEMA`. `SOURCES` (store) and `EventSource` (events) enumerate the same three values separately.
**Fix:** Drop the pragmas from one of the two places, and derive `SOURCES` from `EventSource`.

### IN-06: Naming rule and money conventions are inconsistent in event models

**File:** `src/pumpgrok/ledger/events.py:41-43,133,146-149,165,227,235,303`
**Issue:** The module says `MoneyInt` is for lamports and units and `PriceDecimal` for prices and fractions. In practice `MoneyInt` holds `slippage_bps`, `max_slippage_bps`, `hold_seconds`, `cooldown_s` and `after_s`, and `PriceDecimal` holds `latency_s` and `score`, which are neither prices nor fractions.
**Fix:** Add `Seconds`, `Bps` and `Score` aliases, or document the exceptions in the module docstring.

### IN-07: Hash chain is unkeyed; tail truncation is not detected

**File:** `src/pumpgrok/ledger/store.py:73-96,180-216`
**Issue:** Anyone who can write the database can recompute the chain, and the append-only triggers can be dropped. `verify()` checks only the chain from genesis, so removing the last row(s) is not detected. This detects accidental corruption, not an adversary with write access.
**Fix:** No change required in this phase. Record the limit in the design doc, and plan an external head anchor (e.g. the last hash kept in a separate file) if tamper evidence is a requirement.

### IN-08: Misplaced protocol comment and stale docstring in adapter

**File:** `src/pumpgrok/core/adapter.py:158,163-164`
**Issue:** The comment about `cancel`'s return value sits above `positions`. `LiveAdapterStub` is documented as the "Base of `LiveAdapter`", but no `LiveAdapter` exists and `__init__` always raises.
**Fix:** Move the comment above `cancel`, and correct the docstring to say the stub is the placeholder for the future adapter.

### IN-09: Star re-export shim

**File:** `src/pumpgrok/core/interfaces.py:1-6`
**Issue:** A module whose only content is `from pumpgrok.core import *` exists for a migration note. The project rule is clean cutover with no shims. Its only documented reference is in `docs/design/paper-engine.md`.
**Fix:** If nothing imports `pumpgrok.core.interfaces`, delete the file and update the design doc reference.

### IN-10: Test hygiene

**File:** `tests/core/test_models.py:36-39`, `tests/core/test_registry.py:95-96,201`, `tests/ledger/test_store.py:50-53,59-60`, `tests/config/test_forbidden_keys.py:76-81`, `tests/config/test_settings.py:87-92`
**Issue:** Several tests use `pytest.raises(Exception)`, which passes for any failure. `_call` in `test_registry.py` is unused. `test_key_bearing_url_refuses_without_echo` uses `PUMPGROK_ALERTS__WEBHOOK_URL`, which is not a declared setting; the test passes because the unknown-key error also names it, so it does not exercise the key-bearing check on a real field. `test_live_overlay_keeps_live_disabled` checks substrings of the TOML text rather than parsed values.
**Fix:** Narrow the exception types (`ValidationError`, `sqlite3.IntegrityError`, `PermissionDenied`), delete `_call`, use a declared field for the URL test, and assert on the parsed TOML (`tomllib.loads(...)["live"]["enabled"] is False`).

### IN-11: Template and overlay comments

**File:** `.env.example:5-10,13-40`, `src/pumpgrok/config/overlays/dev.toml:3-4`
**Issue:** Values are followed by trailing `#` comments. Dotenv and compose parsers handle inline comments inconsistently, so a value can end up with comment text attached. The `dev.toml` comment says the logging module enforces `PUMPGROK_LOG_JSON`; no logging module exists in this tree.
**Fix:** Use full-line comments in `.env.example`, and reword the `dev.toml` note to refer to the planned module.

### IN-12: Skill manifest validation is weaker than the bot manifest

**File:** `src/pumpgrok/core/skill.py:37-52`
**Issue:** `bots` entries are checked only with `startswith("bot-0")`, while `BotManifest.id` uses `^bot-0[0-9]-[a-z-]+$`. `SkillPermissions.network` defaults to `True`, which is a permissive default for a least-privilege contract.
**Fix:** Reuse the bot id pattern for `bots`, and default `network` to `False`.

### IN-13: Forbidden-name scan covers the whole host environment

**File:** `src/pumpgrok/config/settings.py:225-233`
**Issue:** `refuse_forbidden_env` scans every environment variable name, not only `PUMPGROK_*`. Unrelated host variables containing `SECRET_KEY` or `SEED` (for example a CI secret) will hard-fail startup. This fails closed, which is the intent, but the operator-facing message does not say why an unrelated variable matters.
**Fix:** No code change required. Document the behaviour in the operator notes and in the refusal message.

### IN-14: Design document drift from the code

**File:** `docs/design/paper-engine.md` (health.json atomic-write reference, `risk/limits.py` entry, section 7.1 `[live]` keys)
**Issue:** The `health.json` atomic-write helper is attributed to `ledger/store.py`; the helper is `core/atomic_write.py`. Section 7.1 lists `[live]` keys (`min_paper_days`, `performance_thresholds`, `wallet_allowlist`, `notional_cap_sol`, `adapter`) that `LiveSettings` does not declare. The `risk/limits.py` entry places `RiskBudget` in a module that does not exist (see WR-01).
**Fix:** Update the references when the owning modules land, and record which keys are deferred.

---

_Reviewed: 2026-10-21T03:11:18Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_

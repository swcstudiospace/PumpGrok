---
phase: 13-curve-truth-live-market-data-and-recorder
reviewed: 2026-11-10T15:03:19Z
depth: deep
files_reviewed: 7
files_reviewed_list:
  - src/pumpgrok/datafeed/events.py
  - src/pumpgrok/datafeed/bridge.py
  - src/pumpgrok/datafeed/readonly.py
  - src/pumpgrok/replay/live_recorder.py
  - tests/datafeed/test_bridge.py
  - tests/datafeed/test_readonly.py
  - tests/replay/test_live_recorder.py
findings:
  critical: 4
  warning: 0
  info: 0
  total: 4
status: issues_found
---

# Phase 13-01: Code Review Report

## Summary

Reviewed Tasks 1 and 2 against the existing replay loader, RPC client, event bus, and the plan. Four behavioral and safety blockers remain. Tests were not run, as instructed.

## Narrative Findings (AI reviewer)

### CR-01: Query credentials outside a narrow name list reach the transport — BLOCKER

**File:** `src/pumpgrok/datafeed/readonly.py:10-32`

**Issue:** The query-name denylist does not cover common credential-bearing parameters such as `?signature=example-secret` or `?sig=example-secret`; neither matches `KEY_BEARING_VALUE_RE`. These URLs pass validation and are passed unchanged to the injected transport at line 52, contrary to the explicit requirement to refuse query secrets before I/O.

**Fix:** Enforce a fail-closed allowlist of known nonsecret query parameters, or reject query parameters entirely unless explicitly permitted. Add transport-capture cases for signed URLs and other credential parameter names.

### CR-02: RPC frames omit the required JSON-RPC envelope — BLOCKER

**File:** `src/pumpgrok/datafeed/readonly.py:56-59`

**Issue:** `rpc()` supplies the transport only `method` and `params`; the captured frame has neither `jsonrpc: "2.0"` nor a request `id`. A transport sending that frame as specified cannot issue a valid Solana JSON-RPC request or correlate a `logsSubscribe` response. The existing client constructs the complete envelope in `src/pumpgrok/tools/onchain/rpc.py:133-136`. The fake transport returns success without checking wire compatibility.

**Fix:** Construct complete JSON-RPC request envelopes with correlatable IDs before sending, or explicitly define and implement an injected transport that constructs the envelope. Assert the actual outbound frame against the existing RPC contract.

### CR-03: Published first tick and sealed manifest lack directory durability — BLOCKER

**File:** `src/pumpgrok/replay/live_recorder.py:35-43,69-79`

**Issue:** Fsyncing a newly created `events.jsonl` file does not guarantee its directory entry survives a crash. The bridge may publish its first tick after that fsync even though the file name, or a newly created dataset directory, can disappear after power loss. Likewise the hard-linked manifest is reported sealed without syncing the containing directory. This breaks the required durable-record-before-publish guarantee and can lose a sealed dataset.

**Fix:** Fsync newly created directory entries and their parent directories before allowing publication; after linking the manifest, fsync the dataset directory before reporting a successful seal. Propagate sync failures and test fault paths.

### CR-04: Seal succeeds for a dataset the real loader refuses — BLOCKER

**File:** `src/pumpgrok/replay/live_recorder.py:35-39,57-77`

**Issue:** An existing directory containing another `*.jsonl` file is accepted, and sealing lists only `events.jsonl`. `load_dataset` calls `_verify`, which rejects every unlisted JSONL file (`src/pumpgrok/replay/fixtures.py:125-127`). Consequently the observation has already been published and `seal()` returns successfully, but the promised sealed replay dataset is unusable.

**Fix:** Refuse nonempty or conflicting dataset directories before accepting the first observation, or explicitly validate/list every permitted data file and verify the complete dataset before declaring it sealed. Add a pre-existing stray-JSONL regression case.

# Routing request: LAYOUT_STATUS (INT-10) to bot-05-rug

From: bot-00-chief (via CHIEF, per docs/cross-bot-protocol.md)
To: bot-05-rug
File owned by bot-05-rug: `src/pumpgrok/tools/onchain/curve_layout.py`, line 33,
`LAYOUT_STATUS: Final[str] = "ASSUMED"`.

## Why
The probe that decides the layout now exists and is tested
(`scripts/probe_curve_layout.py`, commit 1c3d4f8). It flips to VERIFIED only when exactly one
candidate order (`idl_order` or `repo_order`) passes the scale and `real <= virtual` invariants on
a real program-owned 49-byte account.

No real account has been decoded yet. A bounded discovery run on the public RPC (20 signatures,
429-aware backoff) found none (commit 9b09a75; `tests/fixtures/rpc/bonding_curve/probe.json` is
`ASSUMED`).

## Requested action
Do not change `LAYOUT_STATUS` on synthetic bytes. Flip it only after a real account returns a
`VERIFIED` record with `layout_id` and `account` filled in. Provide the account pubkey through
`--account` or `--discover` on a non-rate-limited endpoint, or from the operator.

## Not requested
No edit to this file from bot-00-chief. This branch does not touch the constant.

---
phase: 13-curve-truth
plan: 05
status: complete (task 1), human checkpoint deferred
commit: 6a14fc1
---

# Phase 13 Plan 05: Probe record (human-gated)

## What shipped (task 1, auto)

- `scripts/probe_pump_accounts.py` gained `format_record_markdown`/`write_record_doc` and `--record-doc`; never writes VERIFIED; discriminator checked before decode.
- `docs/CURVE_LAYOUT_PROBE.md` states `Status: ASSUMED` with the exact probe error and the `decoded_pending_review` contract.
- `tests/tools/onchain/test_probe_record.py` pins the writer; `tests/desk/test_probe_pump_accounts.py` fixture repacked token-first.

## Verification (task 1)

- `uv run pytest -q tests/desk/test_probe_pump_accounts.py tests/tools/onchain/test_probe_record.py tests/docs` — exit 0.
- `grep -q 'decoded_pending_review' docs/CURVE_LAYOUT_PROBE.md` and `grep -q 'Status: ASSUMED' docs/CURVE_LAYOUT_PROBE.md` — ok.

## Checkpoint (task 2) — DEFERRED HUMAN-VERIFY

- `checkpoint:human-verify` (gate `blocking-human`) NOT resolved: no `reviewed_by` set, neither literal flipped, both stay ASSUMED. This is the plan-permitted close outcome ("if the human does not review, the record stays ASSUMED"). Awaiting human review; no VERIFIED was fabricated.
